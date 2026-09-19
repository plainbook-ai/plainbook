"""Tests for the local model backend (Ollama), with fake HTTP and no network."""
import json
import os
import subprocess
import threading

import pytest
import requests

from plainbook import local_models
from plainbook.local_models import (LocalModelError, LOCAL_MODEL_CATALOG, OllamaBackend,
                                    catalog_entry, catalog_entry_by_backend_name, _arch)


class FakeResponse:
    def __init__(self, status_code=200, body=None, lines=None, text=""):
        self.status_code = status_code
        self._body = body
        self._lines = lines or []
        self.text = text or (json.dumps(body) if body is not None else "")
        self.headers = {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_lines(self):
        for line in self._lines:
            yield json.dumps(line).encode() if isinstance(line, dict) else line

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("PLAINBOOK_OLLAMA", raising=False)
    return OllamaBackend(managed_dir=tmp_path / "ollama")


class TestCatalog:
    def test_entries_have_the_fields_the_panel_needs(self):
        assert LOCAL_MODEL_CATALOG
        for e in LOCAL_MODEL_CATALOG:
            for k in ("id", "label", "backend_name", "download_gb", "min_memory_gb",
                      "supports_think_levels", "description"):
                assert k in e, k

    def test_lookup(self):
        e = LOCAL_MODEL_CATALOG[0]
        assert catalog_entry(e["id"]) is e
        assert catalog_entry_by_backend_name(e["backend_name"]) is e
        assert catalog_entry("nope") is None
        assert catalog_entry(None) is None


class TestRuntimeAsset:
    @pytest.mark.parametrize("system,machine,asset", [
        ("Darwin", "arm64", "ollama-darwin.tgz"),
        ("Darwin", "x86_64", "ollama-darwin.tgz"),
        ("Linux", "x86_64", "ollama-linux-amd64.tar.zst"),
        ("Linux", "aarch64", "ollama-linux-arm64.tar.zst"),
        ("Windows", "AMD64", "ollama-windows-amd64.zip"),
        ("Windows", "ARM64", "ollama-windows-arm64.zip"),
    ])
    def test_per_platform(self, backend, system, machine, asset):
        assert backend.runtime_asset(system, machine) == asset

    def test_unsupported_raises(self, backend):
        with pytest.raises(LocalModelError):
            backend.runtime_asset("Linux", "riscv64")

    def test_arch_normalisation(self):
        assert _arch("x86_64") == _arch("AMD64") == "amd64"
        assert _arch("aarch64") == _arch("arm64") == "arm64"


class TestFindExecutable:
    def test_none_when_nothing_installed(self, backend, monkeypatch):
        monkeypatch.setattr(local_models.shutil, "which", lambda name: None)
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        assert backend.find_executable() is None
        assert backend.runtime_info() == {"installed": False, "managed": False,
                                          "path": None, "version": None}

    def test_prefers_path_over_managed(self, backend, monkeypatch):
        exe = backend.managed_executable()
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        monkeypatch.setattr(local_models.shutil, "which", lambda name: "/usr/bin/ollama")
        assert backend.find_executable() == ("/usr/bin/ollama", False)

    def test_managed_copy_is_last_resort(self, backend, monkeypatch):
        exe = backend.managed_executable()
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        (backend.managed_dir / "version.json").write_text(json.dumps({"version": "v1.2.3"}))
        monkeypatch.setattr(local_models.shutil, "which", lambda name: None)
        real_isfile = os.path.isfile
        monkeypatch.setattr(os.path, "isfile", lambda p: str(p) == str(exe) and real_isfile(p))
        assert backend.find_executable() == (str(exe), True)
        assert backend.runtime_info()["version"] == "v1.2.3"

    def test_env_override_wins(self, backend, monkeypatch, tmp_path):
        exe = tmp_path / "my-ollama"
        exe.write_text("")
        monkeypatch.setenv("PLAINBOOK_OLLAMA", str(exe))
        monkeypatch.setattr(local_models.shutil, "which", lambda name: "/usr/bin/ollama")
        assert backend.find_executable() == (str(exe), False)


class TestBaseUrl:
    def test_default(self, backend):
        assert backend.base_url == "http://127.0.0.1:11434"

    @pytest.mark.parametrize("host,url", [
        ("0.0.0.0:11500", "http://0.0.0.0:11500"),
        ("http://box:11434/", "http://box:11434"),
        ("box", "http://box:11434"),
    ])
    def test_ollama_host(self, backend, monkeypatch, host, url):
        monkeypatch.setenv("OLLAMA_HOST", host)
        assert backend.base_url == url


class TestInstalledModels:
    def test_reads_manifests_when_no_server(self, backend, monkeypatch, tmp_path):
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "models"))
        lib = tmp_path / "models" / "manifests" / "registry.ollama.ai" / "library"
        (lib / "gpt-oss").mkdir(parents=True)
        (lib / "gpt-oss" / "20b").write_text("{}")
        (lib / "llama3").mkdir()
        (lib / "llama3" / "latest").write_text("{}")
        assert sorted(backend.installed_models()) == ["gpt-oss:20b", "llama3:latest"]

    def test_empty_without_manifests(self, backend, monkeypatch, tmp_path):
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "nothing"))
        assert backend.installed_models() == []

    def test_asks_server_when_up(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: True)
        monkeypatch.setattr(local_models.requests, "get", lambda url, **kw: FakeResponse(
            body={"models": [{"name": "gpt-oss:20b"}]}))
        assert backend.installed_models() == ["gpt-oss:20b"]


class TestPull:
    def test_reports_progress_and_finishes(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        lines = [{"status": "pulling manifest"},
                 {"status": "pulling abc", "digest": "abc", "total": 100, "completed": 10},
                 b"",
                 {"status": "pulling abc", "digest": "abc", "total": 100, "completed": 100},
                 {"status": "success"}]
        posted = {}

        def fake_post(url, **kw):
            posted.update(kw)
            posted["url"] = url
            return FakeResponse(lines=lines)
        monkeypatch.setattr(local_models.requests, "post", fake_post)
        seen = []
        backend.pull_model("gpt-oss:20b", lambda s, c, t: seen.append((s, c, t)))
        assert posted["url"].endswith("/api/pull")
        assert posted["json"] == {"model": "gpt-oss:20b", "stream": True}
        assert seen == [("pulling manifest", None, None), ("pulling abc", 10, 100),
                        ("pulling abc", 100, 100), ("success", None, None)]

    def test_error_line_raises(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        monkeypatch.setattr(local_models.requests, "post", lambda url, **kw: FakeResponse(
            lines=[{"error": "pull model manifest: file does not exist"}]))
        with pytest.raises(LocalModelError, match="does not exist"):
            backend.pull_model("nope:1b", lambda *a: None)

    def test_cancel_stops_reading(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        cancel = threading.Event()
        cancel.set()
        monkeypatch.setattr(local_models.requests, "post", lambda url, **kw: FakeResponse(
            lines=[{"status": "x"}] * 5))
        seen = []
        with pytest.raises(local_models._Cancelled):
            backend.pull_model("m", lambda *a: seen.append(a), cancel)
        assert seen == []


class TestChat:
    def _fake_post(self, monkeypatch, reject_think=False):
        calls = []

        def fake_post(url, **kw):
            calls.append(dict(kw["json"]))
            if reject_think and "think" in kw["json"]:
                return FakeResponse(400, text='{"error":"does not support thinking"}')
            return FakeResponse(body={"message": {"content": "print(1)", "thinking": "hmm"},
                                      "prompt_eval_count": 12, "eval_count": 5})
        monkeypatch.setattr(local_models.requests, "post", fake_post)
        return calls

    def test_request_shape_and_result(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        calls = self._fake_post(monkeypatch)
        result = backend.chat("gpt-oss:20b", "SYS", "PROMPT", 123, think="low")
        assert result == ("print(1)", "hmm", 12, 5)
        (req,) = calls
        assert req["model"] == "gpt-oss:20b"
        assert req["messages"] == [{"role": "system", "content": "SYS"},
                                   {"role": "user", "content": "PROMPT"}]
        assert req["stream"] is False
        assert req["think"] == "low"
        assert req["options"]["num_predict"] == 123
        assert req["options"]["num_ctx"] == local_models.NUM_CTX
        assert req["keep_alive"] == local_models.KEEP_ALIVE

    def test_think_omitted_when_none(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        calls = self._fake_post(monkeypatch)
        backend.chat("m", "S", "P", 10)
        assert "think" not in calls[0]

    def test_retries_without_think_when_rejected(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        calls = self._fake_post(monkeypatch, reject_think=True)
        content, *_ = backend.chat("m", "S", "P", 10, think="medium")
        assert content == "print(1)"
        assert len(calls) == 2 and "think" in calls[0] and "think" not in calls[1]

    def test_missing_model_is_a_local_model_error(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "ensure_server", lambda: None)
        monkeypatch.setattr(local_models.requests, "post",
                            lambda url, **kw: FakeResponse(404, text="model not found"))
        with pytest.raises(LocalModelError, match="not installed"):
            backend.chat("m", "S", "P", 10)

    def test_server_needed_but_runtime_missing(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        monkeypatch.setattr(backend, "find_executable", lambda: None)
        with pytest.raises(LocalModelError, match="not installed"):
            backend.chat("m", "S", "P", 10)


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self._returncode = None

    def poll(self):
        return self._returncode

    def terminate(self):
        self.terminated = True
        self._returncode = 0

    def kill(self):
        self.killed = True
        self._returncode = -9

    def wait(self, timeout=None):
        return self._returncode


class TestStop:
    def test_unloads_catalog_models_and_terminates_own_server(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: True)
        monkeypatch.setattr(backend, "loaded_models", lambda: ["gpt-oss:20b", "llama3:latest"])
        unloaded = []
        monkeypatch.setattr(backend, "unload_model", lambda n: unloaded.append(n))
        proc = FakeProcess()
        backend._serve_process = proc
        backend.stop()
        assert unloaded == ["gpt-oss:20b"]      # not the user's other model
        assert proc.terminated
        assert backend._serve_process is None

    def test_leaves_a_server_it_did_not_start(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: True)
        monkeypatch.setattr(backend, "loaded_models", lambda: [])
        backend.stop()          # no process to terminate, no error

    def test_noop_without_server(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        monkeypatch.setattr(backend, "loaded_models", lambda: pytest.fail("must not be called"))
        backend.stop()


class TestEnsureServer:
    def test_noop_when_up(self, backend, monkeypatch):
        monkeypatch.setattr(backend, "is_server_up", lambda: True)
        monkeypatch.setattr(local_models.subprocess, "Popen",
                            lambda *a, **kw: pytest.fail("must not spawn"))
        backend.ensure_server()

    def test_spawns_and_waits(self, backend, monkeypatch, tmp_path):
        exe = tmp_path / "bin" / "ollama"
        exe.parent.mkdir()
        exe.write_text("")
        monkeypatch.setattr(backend, "find_executable", lambda: (str(exe), False))
        ups = iter([False, False, True, True])
        monkeypatch.setattr(backend, "is_server_up", lambda: next(ups))
        spawned = {}
        proc = FakeProcess()

        def fake_popen(argv, **kw):
            spawned["argv"] = argv
            return proc
        monkeypatch.setattr(local_models.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(local_models.time, "sleep", lambda s: None)
        backend.ensure_server()
        assert spawned["argv"] == [str(exe), "serve"]
        assert backend._serve_process is proc

    def test_gives_up_after_timeout(self, backend, monkeypatch, tmp_path):
        exe = tmp_path / "bin" / "ollama"
        exe.parent.mkdir()
        exe.write_text("")
        monkeypatch.setattr(backend, "find_executable", lambda: (str(exe), False))
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        proc = FakeProcess()
        monkeypatch.setattr(local_models.subprocess, "Popen", lambda *a, **kw: proc)
        monkeypatch.setattr(local_models.time, "sleep", lambda s: None)
        monkeypatch.setattr(local_models, "SERVER_START_TIMEOUT", 0)
        with pytest.raises(LocalModelError, match="did not start"):
            backend.ensure_server()
        assert proc.terminated


class TestSetupJob:
    @pytest.fixture(autouse=True)
    def fresh_job(self, monkeypatch):
        monkeypatch.setattr(local_models, "_job", None)

    def test_runs_runtime_then_model_and_calls_on_done(self, backend, monkeypatch):
        monkeypatch.setattr(local_models, "_backend", backend)
        installed = {"runtime": False}
        monkeypatch.setattr(backend, "find_executable",
                            lambda: ("x", True) if installed["runtime"] else None)

        def install_runtime(progress, cancel_event=None):
            progress(50, 100)
            installed["runtime"] = True
        monkeypatch.setattr(backend, "install_runtime", install_runtime)
        pulled = []

        def pull_model(name, progress, cancel_event=None):
            progress("pulling", 5, 10)
            pulled.append(name)
        monkeypatch.setattr(backend, "pull_model", pull_model)
        done = []
        state = local_models.start_setup("gpt-oss-20b", on_done=done.append)
        assert state["status"] == "running"
        local_models._job.thread.join(5)
        final = local_models.job_state()
        assert final["status"] == "done", final
        assert pulled == ["gpt-oss:20b"]
        assert done == ["gpt-oss-20b"]

    def test_error_is_reported(self, backend, monkeypatch):
        monkeypatch.setattr(local_models, "_backend", backend)
        monkeypatch.setattr(backend, "find_executable", lambda: ("x", False))

        def pull_model(name, progress, cancel_event=None):
            raise LocalModelError("boom")
        monkeypatch.setattr(backend, "pull_model", pull_model)
        local_models.start_setup("gpt-oss-20b")
        local_models._job.thread.join(5)
        final = local_models.job_state()
        assert final["status"] == "error" and final["error"] == "boom"

    def test_unknown_model_and_double_start(self, backend, monkeypatch):
        monkeypatch.setattr(local_models, "_backend", backend)
        with pytest.raises(LocalModelError, match="Unknown"):
            local_models.start_setup("nope")
        started = threading.Event()
        release = threading.Event()
        monkeypatch.setattr(backend, "find_executable", lambda: ("x", False))

        def pull_model(name, progress, cancel_event=None):
            started.set()
            release.wait(5)
        monkeypatch.setattr(backend, "pull_model", pull_model)
        local_models.start_setup("gpt-oss-20b")
        started.wait(5)
        with pytest.raises(LocalModelError, match="already in progress"):
            local_models.start_setup("gpt-oss-20b")
        release.set()
        local_models._job.thread.join(5)


class TestStatus:
    def test_shape(self, backend, monkeypatch):
        monkeypatch.setattr(local_models, "_backend", backend)
        monkeypatch.setattr(local_models, "_job", None)
        monkeypatch.setattr(backend, "is_server_up", lambda: False)
        monkeypatch.setattr(backend, "installed_models", lambda: ["gpt-oss:20b"])
        monkeypatch.setattr(backend, "find_executable", lambda: None)
        s = local_models.status("gpt-oss-20b")
        assert s["platform_supported"] in (True, False)
        assert s["runtime"]["installed"] is False
        assert s["server_running"] is False
        assert s["job"] is None
        (m,) = [m for m in s["models"] if m["id"] == "gpt-oss-20b"]
        assert m["installed"] and m["selected"] and not m["loaded"]
