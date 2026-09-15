"""Local open-weights models: runtime install, model download, server lifecycle.

Plainbook can run one open-weights model on the user's machine so that it is
usable without any cloud API key.  This module owns everything about that:

* the catalog of models we offer (LOCAL_MODEL_CATALOG);
* the backend that runs them (OllamaBackend): finding or installing the Ollama
  runtime in userspace, pulling and deleting models, starting and stopping the
  `ollama serve` subprocess, and sending chat requests to it;
* the module-level manager used by main.py: the single background "setup job"
  (runtime download, then model download) with progress, and start()/stop().

The backend is deliberately small so that another one (e.g. MLX on Apple
Silicon) could be added later behind the same methods without touching the UI
or the provider module (local_gpt_oss.py).

Only ONE local model is ever configured, globally: the machines this targets do
not have memory for more.
"""
import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import requests

# Same location as main.CONFIG_DIR; repeated here because importing main has
# side effects (argument parsing, kernel start).
CONFIG_DIR = Path.home() / ".config" / "plainbook"
MANAGED_DIR = CONFIG_DIR / "ollama"

# The Ollama release Plainbook downloads when none is found on the machine.
OLLAMA_VERSION = os.environ.get("PLAINBOOK_OLLAMA_VERSION", "v0.34.0")
OLLAMA_RELEASE_URL = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# How long a model stays loaded after a request, and the context window we
# ask for (Ollama's default is too small for Plainbook's prompts).
KEEP_ALIVE = os.environ.get("PLAINBOOK_LOCAL_KEEP_ALIVE", "30m")
NUM_CTX = int(os.environ.get("PLAINBOOK_LOCAL_NUM_CTX", "32768"))
CHAT_TIMEOUT = 600      # seconds; a local model on CPU can be slow
SERVER_START_TIMEOUT = 30

# The models offered in Settings, in display order.  `backend_name` is the
# name the backend knows the model by (an Ollama tag).
LOCAL_MODEL_CATALOG = [
    {
        "id": "gpt-oss-20b",
        "label": "GPT-OSS 20B",
        "backend_name": "gpt-oss:20b",
        "download_gb": 14,
        "min_memory_gb": 16,
        "supports_think_levels": True,
        "description": ("OpenAI's open-weights reasoning model. Runs on machines with "
                        "16 GB of memory or more; a good fit for a 24 GB laptop."),
    },
]


class LocalModelError(Exception):
    """A failure the user can act on; the message is shown as is."""


def catalog_entry(model_id):
    for entry in LOCAL_MODEL_CATALOG:
        if entry["id"] == model_id:
            return entry
    return None


def catalog_entry_by_backend_name(name):
    for entry in LOCAL_MODEL_CATALOG:
        if entry["backend_name"] == name:
            return entry
    return None


def machine_memory_gb():
    """Total physical memory in GB, or None when it cannot be determined."""
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return int(out.strip()) / 1e9
        if system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024 / 1e9
        if system == "Windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1e9
    except Exception:
        pass
    return None


# ── Ollama backend ──────────────────────────────────────────────────────────

# (system, machine) -> release asset.  Machines are normalised by _arch().
_RUNTIME_ASSETS = {
    ("Darwin", "arm64"): "ollama-darwin.tgz",
    ("Darwin", "amd64"): "ollama-darwin.tgz",       # universal binary
    ("Linux", "amd64"): "ollama-linux-amd64.tar.zst",
    ("Linux", "arm64"): "ollama-linux-arm64.tar.zst",
    ("Windows", "amd64"): "ollama-windows-amd64.zip",
    ("Windows", "arm64"): "ollama-windows-arm64.zip",
}


def _arch(machine=None):
    m = (machine or platform.machine()).lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


class OllamaBackend:
    """Runs local models through Ollama's HTTP API.

    `ensure_server()` starts `ollama serve` when nothing answers on the base
    URL; `stop()` unloads our model and terminates the server only if this
    process started it.  Several Plainbook windows (separate processes) may
    therefore share one server: whichever one needs it first starts it."""

    name = "ollama"

    def __init__(self, managed_dir=MANAGED_DIR):
        self.managed_dir = Path(managed_dir)
        self._serve_process = None
        self._lock = threading.Lock()

    # -- locating the runtime ------------------------------------------------

    @property
    def base_url(self):
        host = os.environ.get("OLLAMA_HOST", "").strip()
        if not host:
            return DEFAULT_BASE_URL
        if "://" not in host:
            host = "http://" + host
        # OLLAMA_HOST may be just a host; Ollama's own default port applies.
        if host.count(":") < 2:
            host += ":11434"
        return host.rstrip("/")

    def managed_executable(self):
        system = platform.system()
        if system == "Windows":
            return self.managed_dir / "ollama.exe"
        if system == "Linux":
            return self.managed_dir / "bin" / "ollama"
        return self.managed_dir / "ollama"

    def find_executable(self):
        """Returns (path, managed) for the `ollama` executable to use, or None.
        Prefers an Ollama the user installed themselves over our own copy."""
        override = os.environ.get("PLAINBOOK_OLLAMA")
        if override and os.path.isfile(override):
            return override, False
        found = shutil.which("ollama")
        if found:
            return found, False
        candidates = [
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
            "/Applications/Ollama.app/Contents/Resources/ollama",
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe"))
        for c in candidates:
            if os.path.isfile(c):
                return c, False
        managed = self.managed_executable()
        if managed.is_file():
            return str(managed), True
        return None

    def managed_version(self):
        try:
            with open(self.managed_dir / "version.json") as f:
                return json.load(f).get("version")
        except Exception:
            return None

    def runtime_info(self):
        found = self.find_executable()
        if not found:
            return {"installed": False, "managed": False, "path": None, "version": None}
        path, managed = found
        return {"installed": True, "managed": managed, "path": path,
                "version": self.managed_version() if managed else None}

    # -- installing the runtime ----------------------------------------------

    def runtime_asset(self, system=None, machine=None):
        """The release archive for this platform; raises when unsupported."""
        key = (system or platform.system(), _arch(machine))
        asset = _RUNTIME_ASSETS.get(key)
        if not asset:
            raise LocalModelError(
                f"Local models are not available on {key[0]} {key[1]}.")
        return asset

    def _download(self, url, dest, progress, cancel_event=None):
        """Streams `url` into `dest`, calling progress(completed, total)."""
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0) or None
            completed = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if cancel_event is not None and cancel_event.is_set():
                        raise _Cancelled()
                    f.write(chunk)
                    completed += len(chunk)
                    progress(completed, total)

    def _expected_sha256(self, asset):
        """The published checksum of `asset`, or None if unavailable."""
        try:
            r = requests.get(f"{OLLAMA_RELEASE_URL}/sha256sum.txt", timeout=30)
            r.raise_for_status()
            for line in r.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == asset:
                    return parts[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    def _extract(self, archive, asset):
        dest = self.managed_dir
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
        elif asset.endswith(".tgz") or asset.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as t:
                _safe_extract(t, dest)
        elif asset.endswith(".tar.zst"):
            try:
                import zstandard
            except ImportError:
                raise LocalModelError(
                    "The 'zstandard' package is needed to unpack the Ollama runtime on Linux: "
                    "pip install zstandard")
            with open(archive, "rb") as f:
                with zstandard.ZstdDecompressor().stream_reader(f) as reader:
                    with tarfile.open(fileobj=reader, mode="r|") as t:
                        _safe_extract(t, dest)
        else:
            raise LocalModelError(f"Unknown archive type: {asset}")
        exe = self.managed_executable()
        if not exe.is_file():
            raise LocalModelError(f"The Ollama archive did not contain {exe.name}.")
        if platform.system() != "Windows":
            for p in dest.rglob("*"):
                if p.is_file() and (p.name.startswith("ollama") or p.name.startswith("llama")):
                    p.chmod(p.stat().st_mode | 0o755)

    def install_runtime(self, progress, cancel_event=None):
        """Downloads and unpacks the Ollama runtime into the managed directory.
        progress(completed_bytes, total_bytes_or_None) is called as it goes."""
        asset = self.runtime_asset()
        self.managed_dir.mkdir(parents=True, exist_ok=True)
        downloads = self.managed_dir / "downloads"
        downloads.mkdir(exist_ok=True)
        archive = downloads / (asset + ".part")
        try:
            self._download(f"{OLLAMA_RELEASE_URL}/{asset}", archive, progress, cancel_event)
            expected = self._expected_sha256(asset)
            if expected and self._sha256(archive) != expected:
                raise LocalModelError("The downloaded Ollama runtime failed its checksum; please retry.")
            # A fresh unpack: remove a previous managed copy first.
            for child in self.managed_dir.iterdir():
                if child != downloads:
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
            self._extract(archive, asset)
            with open(self.managed_dir / "version.json", "w") as f:
                json.dump({"version": OLLAMA_VERSION, "asset": asset}, f)
        finally:
            if archive.exists():
                archive.unlink()

    # -- the server ----------------------------------------------------------

    def is_server_up(self):
        try:
            r = requests.get(f"{self.base_url}/api/version", timeout=1)
            return r.ok
        except requests.RequestException:
            return False

    def ensure_server(self):
        """Makes sure a server answers at base_url, starting one if needed."""
        with self._lock:
            if self.is_server_up():
                return
            found = self.find_executable()
            if not found:
                raise LocalModelError(
                    "The local model runtime is not installed. Open Settings to set up a local model.")
            exe, _ = found
            self.managed_dir.mkdir(parents=True, exist_ok=True)
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            with open(self.managed_dir / "serve.log", "ab") as log:
                proc = subprocess.Popen([exe, "serve"], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, **kwargs)
            deadline = time.monotonic() + SERVER_START_TIMEOUT
            while time.monotonic() < deadline:
                if self.is_server_up():
                    if proc.poll() is None:
                        self._serve_process = proc
                    # else: another process bound the port first; use theirs.
                    return
                if proc.poll() is not None and self.is_server_up():
                    return
                time.sleep(0.3)
            proc.terminate()
            raise LocalModelError(
                f"The local model server did not start (see {self.managed_dir / 'serve.log'}).")

    def loaded_models(self):
        """Names of the models currently in memory ([] when no server)."""
        try:
            r = requests.get(f"{self.base_url}/api/ps", timeout=3)
            r.raise_for_status()
            return [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        except requests.RequestException:
            return []

    def unload_model(self, name):
        try:
            requests.post(f"{self.base_url}/api/generate",
                          json={"model": name, "keep_alive": 0}, timeout=30)
        except requests.RequestException:
            pass

    def stop(self, model_name=None):
        """Frees the memory: unloads our model(s) and terminates the server if
        this process started it.  Never raises."""
        with self._lock:
            if self.is_server_up():
                names = [model_name] if model_name else [
                    n for n in self.loaded_models() if catalog_entry_by_backend_name(n)]
                for n in names:
                    self.unload_model(n)
            proc, self._serve_process = self._serve_process, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # -- models --------------------------------------------------------------

    def models_dir(self):
        return Path(os.environ.get("OLLAMA_MODELS") or (Path.home() / ".ollama" / "models"))

    def installed_models(self):
        """Names of the installed models.  Asks the server when one is running;
        otherwise reads Ollama's manifest directory, so that Settings can show
        the state without starting a server."""
        if self.is_server_up():
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        library = self.models_dir() / "manifests" / "registry.ollama.ai" / "library"
        names = []
        if library.is_dir():
            for model_dir in library.iterdir():
                if model_dir.is_dir():
                    for tag in model_dir.iterdir():
                        if tag.is_file():
                            names.append(f"{model_dir.name}:{tag.name}")
        return names

    def pull_model(self, name, progress, cancel_event=None):
        """Downloads `name`, calling progress(status, completed, total)."""
        self.ensure_server()
        with requests.post(f"{self.base_url}/api/pull",
                           json={"model": name, "stream": True},
                           stream=True, timeout=(30, 300)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if cancel_event is not None and cancel_event.is_set():
                    raise _Cancelled()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise LocalModelError(f"Download failed: {msg['error']}")
                progress(msg.get("status", ""), msg.get("completed"), msg.get("total"))

    def delete_model(self, name):
        self.ensure_server()
        r = requests.delete(f"{self.base_url}/api/delete", json={"model": name}, timeout=60)
        if r.status_code != 404:
            r.raise_for_status()

    def warm_up(self, name):
        """Loads `name` into memory so the first request is fast."""
        self.ensure_server()
        requests.post(f"{self.base_url}/api/generate",
                      json={"model": name, "keep_alive": KEEP_ALIVE}, timeout=CHAT_TIMEOUT)

    def chat(self, model, system, prompt, max_tokens, think=None, timeout=CHAT_TIMEOUT):
        """One request/response exchange.  Returns
        (content, thinking, prompt_tokens, output_tokens).  `think`, when
        given, is the reasoning effort; if the server rejects it (a model
        without that knob), the request is retried without."""
        self.ensure_server()
        request = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": max_tokens, "num_ctx": NUM_CTX},
        }
        if think is not None:
            request["think"] = think
        r = requests.post(f"{self.base_url}/api/chat", json=request, timeout=timeout)
        if r.status_code == 400 and "think" in request:
            del request["think"]
            r = requests.post(f"{self.base_url}/api/chat", json=request, timeout=timeout)
        if r.status_code == 404:
            raise LocalModelError(
                f"The local model {model} is not installed. Open Settings to set it up.")
        if not r.ok:
            raise LocalModelError(f"The local model server answered {r.status_code}: {r.text[:300]}")
        body = r.json()
        message = body.get("message") or {}
        return (message.get("content", ""), message.get("thinking"),
                body.get("prompt_eval_count"), body.get("eval_count"))

    def request_payload(self, model, system, prompt, max_tokens, think=None):
        """What chat() sends, for --dump-ai-requests."""
        payload = {"model": model, "system": system, "prompt": prompt,
                   "num_predict": max_tokens, "num_ctx": NUM_CTX}
        if think is not None:
            payload["think"] = think
        return payload


class _Cancelled(Exception):
    pass


def _safe_extract(tar, dest):
    """tarfile.extractall with the path-traversal guard newer Pythons add."""
    dest = Path(dest).resolve()
    for member in tar:
        target = (dest / member.name).resolve()
        if dest != target and dest not in target.parents:
            raise LocalModelError(f"Unsafe path in archive: {member.name}")
        tar.extract(member, dest)


# ── Manager ─────────────────────────────────────────────────────────────────

_backend = None


def get_backend():
    global _backend
    if _backend is None:
        _backend = OllamaBackend()
    return _backend


# The single setup job: at most one download at a time.
_job = None
_job_lock = threading.Lock()


class _SetupJob:
    def __init__(self, model_id, reinstall, on_done):
        self.model_id = model_id
        self.reinstall = reinstall
        self.on_done = on_done
        self.cancel_event = threading.Event()
        self.state = {"model": model_id, "phase": None, "status": "running",
                      "message": "", "completed": None, "total": None, "error": None}
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _set(self, **fields):
        self.state.update(fields)

    def _run(self):
        backend = get_backend()
        entry = catalog_entry(self.model_id)
        try:
            if backend.find_executable() is None:
                self._set(phase="runtime", message="Downloading the Ollama runtime…",
                          completed=0, total=None)
                backend.install_runtime(
                    lambda c, t: self._set(completed=c, total=t), self.cancel_event)
            if self.reinstall:
                self._set(phase="model", message=f"Removing {entry['label']}…",
                          completed=None, total=None)
                backend.delete_model(entry["backend_name"])
            self._set(phase="model", message=f"Downloading {entry['label']}…",
                      completed=0, total=None)

            def on_pull(status, completed, total):
                self._set(message=f"{entry['label']}: {status}" if status else self.state["message"],
                          completed=completed, total=total)
            backend.pull_model(entry["backend_name"], on_pull, self.cancel_event)
            self._set(status="done", message=f"{entry['label']} is ready.")
        except _Cancelled:
            self._set(status="cancelled", message="Cancelled.")
        except LocalModelError as e:
            self._set(status="error", error=str(e), message="")
        except Exception as e:
            self._set(status="error", error=f"{type(e).__name__}: {e}", message="")
        if self.state["status"] == "done" and self.on_done:
            try:
                self.on_done(self.model_id)
            except Exception as e:
                self._set(status="error", error=f"Saving the setting failed: {e}")


def start_setup(model_id, reinstall=False, on_done=None):
    """Starts the background download; raises LocalModelError if one is running."""
    global _job
    if catalog_entry(model_id) is None:
        raise LocalModelError(f"Unknown local model: {model_id}")
    with _job_lock:
        if _job is not None and _job.state["status"] == "running":
            raise LocalModelError("A local model download is already in progress.")
        _job = _SetupJob(model_id, reinstall, on_done)
        state = dict(_job.state)
        _job.thread.start()
        return state


def cancel_setup():
    with _job_lock:
        if _job is not None and _job.state["status"] == "running":
            _job.cancel_event.set()


def job_state():
    with _job_lock:
        return dict(_job.state) if _job is not None else None


def start(model_name):
    """Brings the server up and loads `model_name`, in the background."""
    def run():
        try:
            get_backend().warm_up(model_name)
        except Exception as e:
            print(f"Warning: could not start the local model {model_name}: {e}")
    threading.Thread(target=run, daemon=True).start()


def stop(background=False):
    """Frees the local model's memory (see OllamaBackend.stop)."""
    if background:
        threading.Thread(target=get_backend().stop, daemon=True).start()
    else:
        get_backend().stop()


def status(selected_id):
    """The state of local models for the Settings panel."""
    backend = get_backend()
    try:
        backend.runtime_asset()
        supported = True
    except LocalModelError:
        supported = False
    server_running = backend.is_server_up()
    try:
        installed = set(backend.installed_models())
    except Exception:
        installed = set()
    loaded = set(backend.loaded_models()) if server_running else set()
    models = []
    for entry in LOCAL_MODEL_CATALOG:
        name = entry["backend_name"]
        models.append(dict(entry, installed=name in installed, loaded=name in loaded,
                           selected=entry["id"] == selected_id))
    return {
        "platform_supported": supported,
        "memory_gb": machine_memory_gb(),
        "runtime": backend.runtime_info(),
        "server_running": server_running,
        "models": models,
        "selected": selected_id,
        "job": job_state(),
    }
