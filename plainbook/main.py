# General imports
import argparse
import asyncio
import atexit
import datetime
from functools import wraps
import json
from . import __version__
from .ai_common import (reset_session_tokens, DEFAULT_EXPLANATION_DETAIL_LEVEL,
                        DEFAULT_EXPLANATION_USE_BULLETS, DEFAULT_EXPLANATION_USE_LATEX,
                        DEFAULT_FIX_ERROR_AMENDS_DESCRIPTION, DEFAULT_ASK_QUESTIONS,
                        DEFAULT_SKIP_REGENERATION)
from .plainbook import CellExecutionError
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import threading
import time
import yaml
import sys
import webbrowser
# Bottle imports
from bottle import route, template, get, post, static_file, view, HTTPError
from bottle import run, default_app, request, response, redirect, TEMPLATE_PATH

# print(f"DEBUGGER PYTHON: {sys.executable}")

# Plainbook imports
from .plainbook import (ExecutionError, ClarificationNeeded, check_notebook_file,
                        normalize_notebook_name, unique_notebook_path)
from .claude import CLAUDE_MODEL, list_claude_models, select_claude_providers
from .gemini import list_gemini_models, select_gemini_providers
from .openai import list_openai_models, select_openai_providers
from . import local_models
from .local_models import LocalModelError

APP_FOLDER = os.path.dirname(__file__)
TEMPLATE_PATH.insert(0, os.path.join(APP_FOLDER, 'views'))

app_path = Path(APP_FOLDER)
PARENT_FOLDER = app_path.parent
TEST_INPUTS = os.path.join(PARENT_FOLDER, "tests/files")
ROOT_DIR = os.path.abspath(os.sep)

# Configuration file, the 'Good Citizen' way
APP_NAME = "plainbook"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
INVALID_TOKEN_MESSAGE = '<p class="has-text-danger has-text-centered mb-4">Invalid token. Please try again.</p>'

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run the plainbook notebook server')
parser.add_argument('notebook',
                    help='Path to the notebook file to open')
parser.add_argument('--debug', action='store_true', default=False,
                    help='Enable debug mode')
parser.add_argument('--dump-ai-requests', nargs='?', const=True, default=False,
                    help='Dump AI requests. Optionally specify a folder path to save as JSON files; otherwise prints to stdout.')
parser.add_argument('--port', type=int, default=8080,
                    help='Port to run the server on')
parser.add_argument('--host', type=str,
                    default='0.0.0.0' if os.environ.get('CODESPACES') else '127.0.0.1',
                    help='Host to bind the server to (default: 0.0.0.0 in Codespaces, 127.0.0.1 otherwise)')
parser.add_argument('--log', action='store_true', default=False,
                    help='Log all user actions to notebook.metadata["log"] for user studies. See Log.md.')
parser.add_argument('--logview', action='store_true', default=False,
                    help='Open the notebook in read-only log-view mode. Enables the /log_view replay UI and rejects all mutations. Does not write new log entries.')
parser.add_argument('--print-all', '--print_all', dest='print_all',
                    action='store_true', default=False,
                    help='Include the navbar and files/instructions panel in the browser print/PDF output.')
parser.add_argument('--app-window', action='store_true', default=False,
                    help='Open the UI in a dedicated app window instead of a normal browser tab.')
# Deprecated: a normal browser tab is now the default, so this flag does nothing.
# Kept (hidden) so existing commands and aliases keep working.
parser.add_argument('--use-browser', action='store_true', default=False,
                    help=argparse.SUPPRESS)
args = parser.parse_args()

try:
    with open(SETTINGS_FILE, 'r') as f:
        settings = yaml.safe_load(f)
except FileNotFoundError:
    settings = {}

# _saved_settings tracks what was loaded from (and should be written to) the file.
# Environment-variable keys are applied only to the in-memory settings dict so
# they are never persisted to disk.
_saved_settings = dict(settings)


def _write_settings():
    """Persist the settings file.

    Only _saved_settings is written. `settings` additionally holds values that
    must never reach disk -- API keys taken from environment variables, and the
    '__bedrock__' sentinel -- so dumping it instead would leak them into
    ~/.config/plainbook/settings.yaml. Raises on I/O failure."""
    with open(SETTINGS_FILE, 'w') as f:
        yaml.dump(dict(_saved_settings), f)


def _save_settings(**values):
    """Set one or more global settings, in memory and on disk.

    The single way to change a persisted setting: writes each value to both
    stores (so it takes effect now and survives a restart) and then saves.
    Raises on I/O failure, so callers that report errors to the client should
    wrap this. Never use it for values that must stay out of the file -- assign
    those to `settings` directly."""
    for store in (settings, _saved_settings):
        store.update(values)
    _write_settings()

# The API-key settings, with the environment variable that can supply each
# (e.g. Codespaces secrets).  Every provider key is listed here.
API_KEY_SETTINGS = [
    ('claude_api_key', 'CLAUDE_API_KEY'),
    ('gemini_api_key', 'GEMINI_API_KEY'),
    ('openai_api_key', 'OPENAI_API_KEY'),
]

def _apply_env_api_keys():
    """Fills in API keys missing from settings from the environment (in memory
    only, so env-provided keys are never written to the settings file)."""
    for setting_key, env_var in API_KEY_SETTINGS:
        if not settings.get(setting_key) and os.environ.get(env_var):
            settings[setting_key] = os.environ[env_var]

def _api_key_flags():
    """{'has_claude_key': bool, ...} for the client."""
    return {'has_' + k.replace('_api_key', '_key'): bool(settings.get(k))
            for k, _ in API_KEY_SETTINGS}

_apply_env_api_keys()

# Bedrock support: when enabled, Claude is available without an API key
CLAUDE_VIA_BEDROCK = os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1"
if CLAUDE_VIA_BEDROCK:
    # Use a sentinel so key-presence checks pass for Claude providers
    settings['claude_api_key'] = '__bedrock__'

# The list of AI providers offered in the navbar, in the shape the client
# expects: {id, name, major, key_setting, model}.  It is built from the
# providers' model APIs by _build_provider_registry(), at startup and whenever
# an API key is saved, and mutated in place so references stay valid.
AI_PROVIDER_REGISTRY = []

# Per major: (settings key for the API key, settings key for the cached
# provider list, fetcher returning the provider entries).
_PROVIDER_SOURCES = {
    "claude": ("claude_api_key", "claude_providers",
               lambda key: select_claude_providers(list_claude_models(key))),
    "gemini": ("gemini_api_key", "gemini_providers",
               lambda key: select_gemini_providers(list_gemini_models(key))),
    "openai": ("openai_api_key", "openai_providers",
               lambda key: select_openai_providers(list_openai_models(key))),
}


def _fetch_providers(major):
    """Returns the provider entries for `major` from its model API, caching
    them in settings so they can be used when the API is unreachable.
    Returns [] when no key is set, or when the fetch fails and nothing is cached."""
    key_setting, cache_setting, fetch = _PROVIDER_SOURCES[major]
    api_key = settings.get(key_setting)
    if not api_key:
        return []
    try:
        providers = fetch(api_key)
        _save_settings(**{cache_setting: providers})
        if args.debug:
            print(f"Updated {major} models: { {p['id']: p['model'] for p in providers} }")
        return providers
    except Exception as e:
        print(f"Warning: could not fetch {major} models: {e}")
        providers = settings.get(cache_setting) or []
        if providers:
            if args.debug:
                print(f"Using cached {major} models: { {p['id']: p['model'] for p in providers} }")
        else:
            print(f"Warning: no cached {major} models; {major} is unavailable until the models can be fetched")
        return providers


def _provider_available(p):
    """Whether the registry entry `p` can be used now: it needs no key
    (key_setting is None, e.g. a local model) or its key is set."""
    return p['key_setting'] is None or bool(settings.get(p['key_setting']))


LOCAL_PROVIDER_ID = "local"


def _current_local_model():
    """The backend name of the local model chosen in Settings, or None.

    Re-read from the settings file rather than from memory: every notebook
    window is its own process, and they must all use the same local model
    (two different ones cannot run at once), so a change made in one window's
    Settings has to reach the others."""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            model_id = (yaml.safe_load(f) or {}).get('local_model')
    except FileNotFoundError:
        model_id = settings.get('local_model')
    entry = local_models.catalog_entry(model_id)
    return entry["backend_name"] if entry else None


def _local_provider_entries():
    """The single "Local" registry entry, present once a local model has been
    chosen in Settings.  Which model it is gets resolved when used (see
    _current_local_model), so the entry carries no model; and it needs no
    API key, hence key_setting None."""
    if _current_local_model() is None:
        return []
    return [{
        "id": LOCAL_PROVIDER_ID,
        "name": "Local",
        "major": "local",
        "key_setting": None,
        "model": None,
    }]


def _build_provider_registry():
    """Rebuilds AI_PROVIDER_REGISTRY in place from the model APIs."""
    providers = list(_local_provider_entries())     # first in the dropdown
    if CLAUDE_VIA_BEDROCK:
        # Bedrock doesn't support models.list; offer the env-configured model
        # (ANTHROPIC_MODEL, falling back to the default in claude.py).
        _bedrock_model = os.environ.get("ANTHROPIC_MODEL", CLAUDE_MODEL)
        providers.append({
            "id": "claude:bedrock",
            "name": f"Claude Bedrock ({_bedrock_model})",
            "major": "claude",
            "key_setting": "claude_api_key",
            "model": _bedrock_model,
        })
    else:
        providers.extend(_fetch_providers("claude"))
    providers.extend(_fetch_providers("gemini"))
    providers.extend(_fetch_providers("openai"))
    AI_PROVIDER_REGISTRY[:] = providers


def _refresh_local_providers():
    """Replaces just the local entries of the registry (a change of local
    model must not re-query the cloud model APIs), then re-validates the
    active provider, starting or stopping the local model as needed."""
    AI_PROVIDER_REGISTRY[:] = (_local_provider_entries()
                               + [p for p in AI_PROVIDER_REGISTRY if p['major'] != 'local'])
    _apply_active_provider(_ensure_active_ai_provider())

_build_provider_registry()


def _ensure_active_ai_provider():
    """Validate active_ai_provider setting; auto-select first available if invalid."""
    current = settings.get('active_ai_provider')
    for p in AI_PROVIDER_REGISTRY:
        if p['id'] == current and _provider_available(p):
            return current
    # Current is invalid or missing — prefer the first provider of the same
    # major (ids change when the model list is rebuilt), else the first
    # provider with a key.
    current_major = current.split(':')[0] if current else None
    for p in AI_PROVIDER_REGISTRY:
        if p['major'] == current_major and _provider_available(p):
            settings['active_ai_provider'] = p['id']
            return p['id']
    for p in AI_PROVIDER_REGISTRY:
        if _provider_available(p):
            settings['active_ai_provider'] = p['id']
            return p['id']
    settings['active_ai_provider'] = None
    return None

_ensure_active_ai_provider()


# The local model is kept running only while it is the active provider: it
# is started (loaded into memory) when chosen, and stopped as soon as a cloud
# provider is chosen instead, or when this process exits.
_local_model_in_use = None      # the backend model name while active


def _apply_active_provider(provider_id):
    """Starts or stops the local model to match the active provider.
    Call after every change of active_ai_provider."""
    global _local_model_in_use
    model = _current_local_model() if provider_id == LOCAL_PROVIDER_ID else None
    if model is None:
        local_models.stop(background=True)      # a no-op when nothing runs
    elif model != _local_model_in_use:
        local_models.start(model)
    _local_model_in_use = model

# At startup only a local active provider needs acting on (bring the model
# up); with a cloud provider active there is nothing of ours to stop.
if settings.get('active_ai_provider') == LOCAL_PROVIDER_ID:
    _apply_active_provider(LOCAL_PROVIDER_ID)

def _get_or_create_debug_token():
    """Return a stable debug token from settings, creating one if absent or stale (>24h)."""
    token_info = settings.get('debug_token')
    if token_info:
        created = token_info.get('created')
        token = token_info.get('token')
        if token and created:
            age = datetime.datetime.now() - created
            if age.total_seconds() < 86400:
                return token
    # Create a new debug token.
    token = secrets.token_hex(32)
    _save_settings(debug_token={
        'token': token,
        'created': datetime.datetime.now(),
    })
    return token

AUTH_TOKEN = _get_or_create_debug_token() if args.debug else secrets.token_hex(32)

# Set by open_ui() when the UI is launched as a chromeless window (no browser
# toolbar, hence no reload button). Read by /get_notebook.
LAUNCHED_CHROMELESS = False

notebook_path = os.path.abspath(args.notebook)

from .plainbook import Plainbook
from . import action_log
notebook = Plainbook(notebook_path, debug=args.debug, dump_ai_requests=args.dump_ai_requests)
assert notebook.kc is not None
assert notebook.km.is_alive()
# The local model server (if this process started one) must not outlive us.
atexit.register(local_models.stop)
action_log.LOGVIEW_ENABLED = args.logview
action_log.bind(notebook, args.log and not args.logview)
                    
# Static file routes
def serve_asset(filepath, folder):
    """Serve a file that the browser must revalidate before reusing.

    Bottle already sends Last-Modified and an ETag and answers conditional
    requests with a 304, but without a Cache-Control header the browser falls
    back to heuristic freshness (roughly 10% of the file's age) and reuses its
    cached copy for days without ever asking. That is how a plainbook upgrade
    ends up still running the old Javascript.

    'no-cache' means "revalidate before use", not "do not store": the browser
    keeps the file and we answer with an empty 304 unless it really changed.
    """
    resp = static_file(filepath, root=os.path.join(APP_FOLDER, folder))
    resp.set_header('Cache-Control', 'no-cache')
    return resp

@route('/js/<filepath:path>')
def server_static_js(filepath):
    return serve_asset(filepath, 'js')

@route('/css/<filepath:path>')
def server_static_css(filepath):
    return serve_asset(filepath, 'css')

@route('/fonts/<filepath:path>')
def server_static_fonts(filepath):
    return serve_asset(filepath, 'fonts')

@route('/images/<filepath:path>')
def server_static_images(filepath):
    return serve_asset(filepath, 'images')

# ── Client liveness ────────────────────────────────────────────────────────
# The server exits when its window goes away: a pagehide beacon schedules the
# exit (see /shutdown), and a watchdog reaps the process if the beacon is lost
# or the browser dies. Both are cancelled/refreshed by any authenticated
# request, which is what makes a page *reload* safe -- a reload fires pagehide
# too, and its first request lands well inside the grace period.
SHUTDOWN_GRACE_SECONDS = 5      # after a beacon; long enough for a reload
CLIENT_IDLE_TIMEOUT_SECONDS = 300   # no requests at all -> assume gone
_last_client_activity = time.monotonic()
_shutdown_at = None
# The idle timeout only starts counting once a client has actually connected, so
# that a server whose URL is being loaded by hand (--debug prints it rather than
# opening a window) is never reaped before anyone arrives.
_client_seen = False


def _note_client_activity():
    """A live client just talked to us: refresh the watchdog and cancel any
    pending shutdown."""
    global _last_client_activity, _shutdown_at, _client_seen
    _last_client_activity = time.monotonic()
    _shutdown_at = None
    _client_seen = True


def _watchdog():
    """Exit once the client is gone.

    Two triggers: a shutdown scheduled by the pagehide beacon whose grace period
    has elapsed, and a long silence (the beacon was lost, or the browser was
    killed). Runs as a daemon thread."""
    while True:
        time.sleep(1)
        now = time.monotonic()
        due = _shutdown_at is not None and now >= _shutdown_at
        idle = _client_seen and (now - _last_client_activity) > CLIENT_IDLE_TIMEOUT_SECONDS
        if due or idle:
            print("\nThe Plainbook window is gone; shutting down.")
            try:
                notebook._shutdown()      # terminate the snapshot kernel
            except Exception as e:
                print(f"Error shutting down the kernel: {e}")
            local_models.stop()           # and the local model server, if ours
            # os._exit, not sys.exit: this is not the main thread (run() owns
            # it), so sys.exit would unwind only this one. atexit therefore will
            # not fire, which is exactly why the kernel is terminated above. The
            # notebook itself is written synchronously on every change.
            os._exit(0)


# Authentication decorator
def require_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.query.get('token')
        if token != AUTH_TOKEN:
            raise HTTPError(403, 'Invalid or missing token')
        _note_client_activity()
        return func(*args, **kwargs)
    return wrapper

# Stateful decorator
def stateful(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        r = func(*args, **kwargs)
        s = notebook.get_state()
        r['state'] = s
        return r
    return wrapper

# Unit-test stateful decorator: piggybacks unit test validity onto responses.
def unit_test_stateful(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        r = func(*args, **kwargs)
        data = request.json or {}
        cell_index = data.get('cell_index')
        if cell_index is not None:
            try:
                r['unit_test_state'] = {
                    'cell_index': cell_index,
                    'state': notebook.get_unit_test_state(cell_index),
                }
            except Exception:
                pass
        return r
    return wrapper

# Main routes
@get('/')
def index():
    token = request.query.get('token')
    if token == AUTH_TOKEN:
        return serve_asset('index.html', 'views')
    if os.environ.get('CODESPACES'):
        redirect('/?token=' + AUTH_TOKEN)
    return template('login', error_message='')

@post('/login')
def login():
    token = request.forms.get('token', '').strip()
    if token == AUTH_TOKEN:
        redirect('/?token=' + AUTH_TOKEN)
    return template('login', error_message=INVALID_TOKEN_MESSAGE)

@get('/get_notebook')
@stateful
@require_token
def get_notebook():
    _in_codespace = bool(os.environ.get('CODESPACES'))
    return dict(
        nb=notebook.get_json(),
        **_api_key_flags(),
        claude_via_bedrock=CLAUDE_VIA_BEDROCK,
        debug=args.debug,
        active_ai_provider=settings.get('active_ai_provider'),
        ai_providers=AI_PROVIDER_REGISTRY,
        local_model=settings.get('local_model'),
        is_codespace=_in_codespace,
        chromeless=LAUNCHED_CHROMELESS,
        log_enabled=args.log and not args.logview,
        logview_enabled=args.logview,
        print_all_enabled=args.print_all,
        explanation_detail=settings.get('explanation_detail', DEFAULT_EXPLANATION_DETAIL_LEVEL),
        explanation_bullets=settings.get('explanation_bullets', DEFAULT_EXPLANATION_USE_BULLETS),
        explanation_latex=settings.get('explanation_latex', DEFAULT_EXPLANATION_USE_LATEX),
        fix_error_amends_description=settings.get(
            'fix_error_amends_description', DEFAULT_FIX_ERROR_AMENDS_DESCRIPTION),
        ask_questions=settings.get('ask_questions', DEFAULT_ASK_QUESTIONS),
        skip_regeneration=settings.get('skip_regeneration', DEFAULT_SKIP_REGENERATION),
    )

@post('/set_key')
@action_log.logged('set_key')
@require_token
def set_key():
    data = request.json
    # Protocol per key: null = explicitly remove, '' = unchanged, non-empty = set new key.
    for setting_key, _ in API_KEY_SETTINGS:
        value = data.get(setting_key, '')
        if setting_key == 'claude_api_key' and CLAUDE_VIA_BEDROCK:
            # Bedrock manages Claude access; ignore any client-side key changes.
            # The sentinel goes to `settings` only, never to the file.
            settings[setting_key] = '__bedrock__'
            continue
        if value is None:
            value = ''
        elif value == '':
            value = _saved_settings.get(setting_key, '')
        # Save only user-provided keys to the file (never env-var keys)
        _saved_settings[setting_key] = value
        settings[setting_key] = value
    # Not _save_settings(): the two stores deliberately disagree under Bedrock,
    # so the assignments above stand and only the write is shared.
    try:
        _write_settings()
    except Exception as e:
        return dict(status='error', message=str(e))
    # After saving, apply env-var fallbacks to in-memory settings only
    if os.environ.get('CODESPACES'):
        _apply_env_api_keys()
    # The available models depend on the keys, so rebuild the provider list.
    _build_provider_registry()
    active = _ensure_active_ai_provider()
    _apply_active_provider(active)
    return dict(
        status='success',
        active_ai_provider=active,
        **_api_key_flags(),
        claude_via_bedrock=CLAUDE_VIA_BEDROCK,
        ai_providers=AI_PROVIDER_REGISTRY,
    )

@post('/set_active_ai')
@action_log.logged('set_active_ai')
@require_token
def set_active_ai():
    data = request.json
    provider_id = data.get('provider')
    valid_ids = [p['id'] for p in AI_PROVIDER_REGISTRY]
    if provider_id not in valid_ids:
        return dict(status='error', message=f'Unknown provider: {provider_id}')
    for p in AI_PROVIDER_REGISTRY:
        if p['id'] == provider_id:
            if not _provider_available(p):
                return dict(status='error', message=f'No API key set for {p["name"]}')
            break
    try:
        _save_settings(active_ai_provider=provider_id)
    except Exception as e:
        return dict(status='error', message=str(e))
    _apply_active_provider(provider_id)
    return dict(status='success', active_ai_provider=provider_id)

@post('/set_explain_options')
@action_log.logged('set_explain_options')
@require_token
def set_explain_options():
    """Persist the global "Explain code" options (complexity level, bullets, LaTeX)."""
    data = request.json
    try:
        detail = int(data.get('detail', DEFAULT_EXPLANATION_DETAIL_LEVEL))
    except (TypeError, ValueError):
        detail = DEFAULT_EXPLANATION_DETAIL_LEVEL
    detail = max(1, min(4, detail))
    bullets = bool(data.get('bullets', DEFAULT_EXPLANATION_USE_BULLETS))
    latex = bool(data.get('latex', DEFAULT_EXPLANATION_USE_LATEX))
    try:
        _save_settings(explanation_detail=detail, explanation_bullets=bullets,
                       explanation_latex=latex)
    except Exception as e:
        return dict(status='error', message=str(e))
    return dict(status='success', explanation_detail=detail,
                explanation_bullets=bullets, explanation_latex=latex)

# ── Local models ───────────────────────────────────────────────────────────
# The Settings panel drives these directly (not through the Save button), since
# a model download takes minutes: /setup starts it, /status is polled.

def _local_model_status():
    return dict(
        status='success',
        **local_models.status(settings.get('local_model')),
        ai_providers=AI_PROVIDER_REGISTRY,
        active_ai_provider=settings.get('active_ai_provider'),
    )


def _select_local_model(model_id):
    """Records `model_id` as the local model and refreshes the registry.
    Called from the routes, and by the setup job when a download completes."""
    _save_settings(local_model=model_id)
    _refresh_local_providers()


@get('/local_model/status')
@require_token
def local_model_status():
    return _local_model_status()


@post('/local_model/setup')
@action_log.logged('local_model_setup')
@require_token
def local_model_setup():
    """Downloads the runtime (if missing) and the model, in the background."""
    data = request.json or {}
    model_id = data.get('model')
    try:
        job = local_models.start_setup(model_id, reinstall=bool(data.get('reinstall')),
                                       on_done=_select_local_model)
    except LocalModelError as e:
        return dict(status='error', message=str(e))
    return dict(status='success', job=job)


@post('/local_model/cancel')
@action_log.logged('local_model_cancel')
@require_token
def local_model_cancel():
    local_models.cancel_setup()
    return _local_model_status()


@post('/local_model/select')
@action_log.logged('local_model_select')
@require_token
def local_model_select():
    """Makes an installed model the local model offered in the navbar."""
    data = request.json or {}
    model_id = data.get('model')
    entry = local_models.catalog_entry(model_id)
    if entry is None:
        return dict(status='error', message=f'Unknown local model: {model_id}')
    try:
        if entry['backend_name'] not in local_models.get_backend().installed_models():
            return dict(status='error', message=f'{entry["label"]} is not installed.')
        _select_local_model(model_id)
    except Exception as e:
        return dict(status='error', message=str(e))
    return _local_model_status()


@post('/local_model/remove')
@action_log.logged('local_model_remove')
@require_token
def local_model_remove():
    """Deletes a downloaded model; if it was the local model, none is left."""
    data = request.json or {}
    model_id = data.get('model')
    entry = local_models.catalog_entry(model_id)
    if entry is None:
        return dict(status='error', message=f'Unknown local model: {model_id}')
    try:
        # Deleting needs the server; stopping (after) frees the memory and
        # terminates the server if this process started it.
        local_models.get_backend().delete_model(entry['backend_name'])
        local_models.stop()
        if settings.get('local_model') == model_id:
            for store in (settings, _saved_settings):
                store.pop('local_model', None)
            _write_settings()
            _refresh_local_providers()
    except Exception as e:
        return dict(status='error', message=str(e))
    return _local_model_status()


def _save_global_flag(key, value):
    """Persist one global boolean setting, and echo it back to the client.

    Returns the route's response dict, so the boolean-setting routes are a
    one-liner each."""
    try:
        _save_settings(**{key: value})
    except Exception as e:
        return dict(status='error', message=str(e))
    return dict(status='success', **{key: value})

@post('/set_fix_error_amends_description')
@action_log.logged('set_fix_error_amends_description')
@require_token
def set_fix_error_amends_description():
    """Persist the global "Fix errors also amends the description" setting."""
    data = request.json or {}
    value = bool(data.get('value', DEFAULT_FIX_ERROR_AMENDS_DESCRIPTION))
    return _save_global_flag('fix_error_amends_description', value)

@post('/edit_explanation')
@action_log.logged('edit_explanation')
@stateful
@require_token
def edit_explanation():
    data = request.json
    cell_index = data.get('cell_index')
    explanation = data.get('explanation')
    notebook.set_cell_explanation(cell_index, explanation)
    # Auto-generate cell name if not yet set
    cell = notebook.nb.cells[cell_index]
    cell_name = cell.metadata.get('name') if cell.cell_type == 'code' else None
    if cell.cell_type == 'code' and not cell_name:
        api_key, ai_provider, model, error = _get_ai_config()
        if not error:
            try:
                cell_name = notebook.generate_cell_name(
                    api_key, cell_index, ai_provider=ai_provider, model=model)
            except Exception as e:
                print(f"Warning: failed to generate cell name: {e}")
    return dict(status='success', cell_name=cell_name)

@post('/propose_amend')
@action_log.logged('propose_amend')
@stateful
@require_token
def propose_amend():
    data = request.json
    cell_index = data.get('cell_index')
    text = data.get('text')
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        proposed = notebook.propose_amend(
            api_key, cell_index, text, ai_provider=ai_provider, model=model)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    return dict(status='success', proposed=proposed)

@post('/commit_amend')
@action_log.logged('commit_amend')
@stateful
@require_token
def commit_amend():
    data = request.json
    cell_index = data.get('cell_index')
    explanation = data.get('explanation')
    notebook.commit_amend(cell_index, explanation)
    return dict(status='success')

@post('/unfold')
@action_log.logged('unfold')
@stateful
@require_token
def unfold():
    data = request.json
    cell_index = data.get('cell_index')
    result = notebook.unfold(cell_index)
    if result is None:
        return dict(status='error', message='Nothing to unfold.')
    return dict(status='success', explanation=result['explanation'],
                source=result['source'])

@post('/edit_code')
@action_log.logged('edit_code')
@stateful
@require_token
def edit_code():
    data = request.json
    cell_index = data.get('cell_index')
    source = data.get('source')
    notebook.set_cell_source(cell_index, source)
    return dict(status='success')

@post('/clear_code')
@action_log.logged('clear_code')
@stateful
@require_token
def clear_code():
    data = request.json
    cell_index = data.get('cell_index')
    notebook.clear_cell_code(cell_index)
    return dict(status='success')

@post('/edit_markdown')
@action_log.logged('edit_markdown')
@stateful
@require_token
def edit_markdown():
    data = request.json
    cell_index = data.get('cell_index')
    source = data.get('source')
    notebook.set_cell_source(cell_index, source)
    return dict(status='success')

@post('/insert_cell')
@action_log.logged('insert_cell')
@stateful
@require_token
def insert_cell():
    data = request.json
    cell_type = data.get('cell_type')
    index = data.get('index')
    new_cell, idx = notebook.insert_cell(index, cell_type)
    return dict(status='success', cell=new_cell, index=idx)

@post('/delete_cell')
@action_log.logged('delete_cell')
@stateful
@require_token
def delete_cell():
    data = request.json
    cell_index = data.get('cell_index')
    notebook.delete_cell(cell_index)
    return dict(status='success')

@post('/move_cell')
@action_log.logged('move_cell')
@stateful
@require_token
def move_cell():
    data = request.json
    cell_index = data.get('cell_index')
    new_index = data.get('new_index')
    notebook.move_cell(cell_index, new_index)
    return dict(status='success')


@get('/state')
@stateful
@require_token
def get_notebook_state():
    return {}

@post('/rename_notebook')
@stateful
@require_token
def rename_notebook():
    """Save the notebook as a copy under a new name; all future edits then
    happen on the new copy. The refreshed state (with the new name) is added
    by the @stateful decorator."""
    data = request.json or {}
    try:
        notebook.rename(data.get('name'))
        return dict(status='success')
    except ValueError as e:
        return dict(status='error', message=str(e))

@post('/execute_cell')
@action_log.logged('execute_cell')
@stateful
@require_token
def execute_cell():
    data = request.json
    cell_index = data.get('cell_index')
    # Sent by a future "Force Run": skips the execution fast path so the cell
    # really runs even when its code and inputs are unchanged.
    force_reexecute = data.get('force_reexecute', False)
    if args.debug:
        print(f"Executing cell {cell_index}")
    try:
        outputs, details = notebook.execute_cell(cell_index, force=force_reexecute)
        return dict(status="ok", details=details, outputs=outputs)
    except CellExecutionError as e:
        # The execution error is already captured in the cell outputs. 
        return dict(status="ok", details="CellExecutionError", 
                    outputs=notebook.nb.cells[cell_index].get('outputs', []))
    except ExecutionError as e:
        return dict(status='error', message=str(e))

@post('/reset_kernel')
@action_log.logged('reset_kernel')
@stateful
@require_token
def reset_kernel():
    notebook.reset_kernel()
    return dict(status='success')

@post('/interrupt_kernel')
@action_log.logged('interrupt_kernel')
@stateful
@require_token
def interrupt_kernel():
    try:
        notebook.interrupt_kernel()
        return dict(status='success')
    except Exception as e:
        return dict(status='error', message=str(e))

@post('/install_package')
@action_log.logged('install_package')
@stateful
@require_token
def install_package():
    data = request.json
    module = data.get('module')
    if args.debug:
        print(f"Installing package for module {module}")
    try:
        success, output = notebook.install_package(module)
        return dict(status='success', success=success, output=output)
    except Exception as e:
        return dict(status='error', message=str(e))
    
    
def _get_ai_config():
    """Resolve AI provider, model, and API key from server-side active provider setting."""
    ai_provider = settings.get('active_ai_provider')
    if not ai_provider:
        return None, None, None, 'No AI provider is active. Please set an API key in Settings.'
    for p in AI_PROVIDER_REGISTRY:
        if p['id'] == ai_provider:
            if not _provider_available(p):
                return None, None, None, f'{p["name"]} API key not set.'
            if p['id'] == LOCAL_PROVIDER_ID:
                # No key; the model is whatever Settings currently says.
                model = _current_local_model()
                if model is None:
                    return None, None, None, 'No local model is set up. Open Settings to set one up.'
                return None, p['major'], model, None
            return settings.get(p['key_setting']), p['major'], p['model'], None
    return None, None, None, f'Unknown AI provider: {ai_provider}'

_BILLING_KEYWORDS = ['credit balance', 'billing', 'quota', 'rate limit', 'resource exhausted', 'exceeded your current']

def _friendly_ai_error(e):
    """If e is an AI failure the user can act on -- a billing/rate-limit
    error, or the local model not being set up -- return its message for the
    client; else None (the route re-raises)."""
    if isinstance(e, LocalModelError):
        return str(e)
    msg = str(e).lower()
    if any(kw in msg for kw in _BILLING_KEYWORDS):
        return ('AI usage limit reached. Please check your AI provider billing '
                'and increase your usage limits.')
    return None

@post('/generate_code')
@action_log.logged('generate_code')
@stateful
@require_token
def generate_code_cell():
    data = request.json
    cell_index = data.get('cell_index')
    validation_feedback = data.get('validation_feedback')
    # "Fix Code" asks for the description to be amended too; honour it only when
    # the global setting is on. When off, generate_code_cell never makes the
    # separate amend_explanation AI call, so the description is left as written.
    amend_description = (data.get('amend_description', False)
                         and settings.get('fix_error_amends_description',
                                          DEFAULT_FIX_ERROR_AMENDS_DESCRIPTION))
    # Sent by explicit user actions (the Regenerate button); absent for the
    # run-driven batch generation, which keeps the generation-skip fast path.
    force_regenerate = data.get('force_regenerate', False)
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        new_code, success, amended = notebook.generate_code_cell(
            api_key, cell_index, ai_provider=ai_provider,
            model=model, validation_feedback=validation_feedback,
            amend_description=amend_description,
            force_regenerate=force_regenerate,
            ask_questions=settings.get('ask_questions', DEFAULT_ASK_QUESTIONS),
            skip_regeneration=settings.get('skip_regeneration', DEFAULT_SKIP_REGENERATION))
    except ClarificationNeeded as e:
        # The AI asked questions; the cell source is untouched.
        return dict(status='needs_clarification', questions=e.questions)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if success:
        result = dict(status='success', code=new_code)
        if amended:
            result['explanation'] = amended
        return result
    else:
        # The request was cancelled, we need to avoid updating the code.
        return dict(status='cancelled', code=None)


@post('/generate_test_code')
@action_log.logged('generate_test_code')
@stateful
@require_token
def generate_test_code():
    data = request.json
    cell_index = data.get('cell_index')
    validation_feedback = data.get('validation_feedback')
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        new_code, success, _amended = notebook.generate_code_cell(
            api_key, cell_index, ai_provider=ai_provider,
            model=model, validation_feedback=validation_feedback)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if success:
        return dict(status='success', code=new_code)
    else:
        return dict(status='cancelled', code=None)


@post('/execute_test_cell')
@action_log.logged('execute_test_cell')
@stateful
@require_token
def execute_test_cell():
    data = request.json
    cell_index = data.get('cell_index')
    try:
        outputs = notebook.execute_test_cell(cell_index)
        return dict(status='ok', outputs=outputs)
    except CellExecutionError:
        # A test that raises -- an assertion that caught something, most often --
        # is a result to show, not a request that failed. execute_test_cell has
        # already appended the error output to the cell, so hand it back the way
        # /execute_cell and /run_unit_test_cell do; without this the outputs were
        # dropped and the cell went on showing whatever it printed last time.
        return dict(status='ok', details='CellExecutionError',
                    outputs=notebook.nb.cells[cell_index].get('outputs', []))
    except NotImplementedError as e:
        return dict(status='error', message=str(e))
    except Exception as e:
        return dict(status='error', message=str(e))


@post('/validate_code')
@action_log.logged('validate_code')
@stateful
@require_token
def validate_code_cell():
    data = request.json
    cell_index = data.get('cell_index')
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        validation_result = notebook.validate_code_cell(api_key, cell_index, ai_provider=ai_provider, model=model)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if validation_result is None:
        return dict(status='cancelled')
    return dict(status='success', validation=validation_result)


@post('/explain_code')
@action_log.logged('explain_code')
@stateful
@require_token
def explain_code_cell():
    data = request.json
    cell_index = data.get('cell_index')
    # Default to the stored settings; allow a per-request override (used by the
    # UI in a later step).
    level = data.get('level', settings.get('explanation_detail', DEFAULT_EXPLANATION_DETAIL_LEVEL))
    use_bullets = data.get('use_bullets', settings.get('explanation_bullets', DEFAULT_EXPLANATION_USE_BULLETS))
    use_latex = data.get('use_latex', settings.get('explanation_latex', DEFAULT_EXPLANATION_USE_LATEX))
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        explanation, index = notebook.explain_code_cell(
            api_key, cell_index, level=level,
            use_bullets=use_bullets, use_latex=use_latex,
            ai_provider=ai_provider, model=model)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if explanation is None:
        return dict(status='cancelled')
    return dict(status='success', explanation=explanation, index=index)


@post('/validate_unit_test_code')
@action_log.logged('validate_unit_test_code')
@stateful
@require_token
def validate_unit_test_code():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        validation_result = notebook.validate_unit_test_cell(
            api_key, cell_index, test_name, role,
            ai_provider=ai_provider, model=model)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if validation_result is None:
        return dict(status='cancelled')
    return dict(status='success', validation=validation_result)


@post('/set_validation_visibility')
@action_log.logged('set_validation_visibility')
@stateful
@require_token
def set_validation_visibility():
    data = request.json
    cell_index = data.get('cell_index')
    is_hidden = data.get('is_hidden', False)
    notebook.set_validation_visibility(cell_index, is_hidden)
    return dict(status='success')


@post('/verify_notebook')
@action_log.logged('verify_notebook')
@stateful
@require_token
def verify_notebook():
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        result = notebook.verify_notebook(api_key, ai_provider=ai_provider, model=model)
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if result is None:
        return dict(status='cancelled')
    return dict(status='success', verification=result)


@post('/set_verification_visibility')
@action_log.logged('set_verification_visibility')
@stateful
@require_token
def set_verification_visibility():
    data = request.json
    is_hidden = data.get('is_hidden', True)
    notebook.set_verification_visibility(is_hidden)
    return dict(status='success')


@post('/set_unit_test_validation_visibility')
@action_log.logged('set_unit_test_validation_visibility')
@stateful
@require_token
def set_unit_test_validation_visibility():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    is_hidden = data.get('is_hidden', True)
    notebook.set_unit_test_validation_visibility(cell_index, test_name, role, is_hidden)
    return dict(status='success')


@post('/cancel_ai_request')
@action_log.logged('cancel_ai_request')
@stateful
@require_token
def cancel_ai_request():
    try:
        notebook.cancel_ai_request()
        return dict(status='success')
    except Exception as e:
        return dict(status='error', message=str(e))
    
    
@post('/clear_outputs')
@action_log.logged('clear_outputs')
@stateful
@require_token
def clear_outputs():
    notebook.clear_outputs()
    return dict(status='success')


@post('/lock_notebook')
@action_log.logged('lock_notebook')
@stateful
@require_token
def lock_notebook():
    data = request.json
    is_locked = data.get('is_locked', False)
    notebook.lock(is_locked)
    return {}


@post('/set_share_output')
@action_log.logged('set_share_output')
@stateful
@require_token
def set_share_output():
    data = request.json
    share = data.get('share', True)
    notebook.set_share_output_with_ai(share)
    return {}


@post('/set_ask_questions')
@action_log.logged('set_ask_questions')
@require_token
def set_ask_questions():
    """Persist the global "Enable asking questions" setting."""
    data = request.json or {}
    value = bool(data.get('value', DEFAULT_ASK_QUESTIONS))
    return _save_global_flag('ask_questions', value)


@post('/set_skip_regeneration')
@action_log.logged('set_skip_regeneration')
@require_token
def set_skip_regeneration():
    """Persist the global "Skip regeneration when data is unchanged" setting."""
    data = request.json or {}
    value = bool(data.get('value', DEFAULT_SKIP_REGENERATION))
    return _save_global_flag('skip_regeneration', value)


@get('/current_dir')
@require_token
def get_current_dir():
    """Returns the folder where the notebook lives (not the working directory
    where plainbook was launched)."""
    return {"path": os.path.dirname(os.path.abspath(notebook.path))}

@get('/ping')
@require_token
def ping():
    """Client heartbeat. The body is irrelevant: require_token has already
    refreshed the liveness clock, which is the whole point of the route."""
    return {}

@post('/shutdown')
@require_token
def shutdown():
    """Asked by the client's pagehide beacon: schedule the exit.

    Deliberately not immediate. A page reload fires pagehide too, so exiting
    here would kill the server on every refresh; instead the watchdog carries it
    out after a grace period, and any request in the meantime cancels it."""
    global _shutdown_at
    _shutdown_at = time.monotonic() + SHUTDOWN_GRACE_SECONDS
    return {}

def _spawn_plainbook(path):
    """Launch an independent plainbook for `path`.

    Exactly what the command line does: a new server on its own scanned port, a
    new Plainbook with its own snapshot kernel, its own auth token, opening its
    own window. Detached so it outlives this process, and silenced because
    nothing reads its output.

    --debug is deliberately NOT inherited: in debug mode main() prints the URL
    instead of opening a window, and this child's stdout goes to DEVNULL, so it
    would start invisibly."""
    cmd = [sys.executable, '-m', 'plainbook.main', path]
    if args.app_window:
        cmd.append('--app-window')
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)

def _resolve_folder(folder):
    """The absolute folder a notebook should be written into.

    Defaults to the current notebook's folder when the client sends nothing, so
    a request without a folder behaves as it always did. Raises ValueError with
    a user-facing message otherwise: the picker only ever offers real
    directories, so this guards against a stale listing or a hand-made
    request."""
    if not folder:
        return os.path.dirname(os.path.abspath(notebook.path))
    path = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(path):
        return _raise_not_a_folder(folder)
    return path


def _raise_not_a_folder(folder):
    raise ValueError(f"{folder} is not a folder.")


@post('/new_notebook')
@action_log.logged('new_notebook')
@require_token
def new_notebook():
    """Create a plainbook in the chosen folder and open it in its own window.
    This process and its notebook are untouched.

    A name that is already taken is *opened* rather than created afresh: the
    name and the folder together name a file, so asking for one that exists is a
    request to open it. The client checks this too, in order to label its
    button; checking again here closes the race and is the only check that
    counts."""
    data = request.json or {}
    try:
        name = normalize_notebook_name(data.get('name'))
        folder = _resolve_folder(data.get('folder'))
    except ValueError as e:
        return dict(status='error', message=str(e))
    path = os.path.join(folder, name + '.plnb')
    opened = os.path.exists(path)
    if opened:
        try:
            check_notebook_file(path)
        except ValueError as e:
            return dict(status='error', message=str(e))
    try:
        _spawn_plainbook(path)
    except Exception as e:
        return dict(status='error', message=f'Could not start the new plainbook: {e}')
    return dict(status='success', name=name, path=path, opened=opened)


@post('/open_notebook')
@action_log.logged('open_notebook')
@require_token
def open_notebook():
    """Open an existing notebook in its own window, leaving this one running.

    The file is checked here rather than left to the child: _spawn_plainbook
    detaches the child and discards its output, so a child that cannot load its
    file dies without anyone noticing."""
    data = request.json or {}
    raw = (data.get('path') or '').strip()
    if not raw:
        return dict(status='error', message='Please choose a notebook to open.')
    path = os.path.abspath(os.path.expanduser(raw))
    try:
        check_notebook_file(path)
    except ValueError as e:
        return dict(status='error', message=str(e))
    try:
        _spawn_plainbook(path)
    except Exception as e:
        return dict(status='error', message=f'Could not open the notebook: {e}')
    return dict(status='success',
                name=os.path.splitext(os.path.basename(path))[0], path=path)

@post('/copy_notebook')
@action_log.logged('copy_notebook')
@require_token
def copy_notebook():
    """Save a copy of this plainbook under a new name, in the chosen folder, and
    open the copy in its own window. This process and its notebook are
    untouched, so work continues here on the original. Unlike a new plainbook, a
    name already in use gets _2, _3, ... appended: a copy must never open, let
    alone overwrite, the file it would have copied onto."""
    data = request.json or {}
    try:
        folder = _resolve_folder(data.get('folder'))
        name, path = notebook.save_copy(data.get('name'), folder=folder)
    except ValueError as e:
        return dict(status='error', message=str(e))
    try:
        _spawn_plainbook(path)
    except Exception as e:
        return dict(status='error', message=f'Could not start the copy: {e}')
    return dict(status='success', name=name, path=path)

@get('/home_dir')
@require_token
def get_home_dir():
    """Returns the absolute path of the current user's home directory."""
    return {"path": str(Path.home())}

@post('/file_list')
@require_token
def file_list():
    # 1. Get the path from the request body
    data = request.json
    requested_path = data.get('path', ROOT_DIR)    
    abs_path = os.path.abspath(requested_path)
    if not os.path.exists(abs_path):
        raise HTTPError(404, 'Path does not exist')
    if not os.path.isdir(abs_path):
        raise HTTPError(400, 'Path is not a directory')
    try:
        results = []
        for entry in os.scandir(abs_path):
            if not entry.name.startswith('.'):  # Skip hidden files
                # We gather name, full path, and determine if it's a file or dir
                results.append({
                    "name": entry.name,
                    "path": entry.path,
                    "type": "directory" if entry.is_dir() else "file"
                })
        # Sort: Directories first, then files alphabetically
        results.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))
        # path/parent let the client navigate without doing platform-specific
        # surgery on the string: at the root, parent == path, which is how the
        # picker knows to disable "Up".
        return {"files": results, "path": abs_path,
                "parent": os.path.dirname(abs_path) or abs_path}

    except PermissionError:
        raise HTTPError(403, 'Permission denied')
    
    
@post('/set_files')
@action_log.logged('set_files')
@require_token
def set_files():
    data = request.json
    files = data.get('files', [])
    missing_files = data.get('missing_files', [])
    notebook.set_input_files(files, missing_files)
    return dict(status='success', state=notebook.get_state())


@get('/get_files')
@require_token
def get_files():
    d = notebook.get_input_files()
    return dict(files=d['input_files'], missing_files=d['missing_input_files'])


@post('/set_ai_instructions')
@action_log.logged('set_ai_instructions')
@require_token
def set_ai_instructions():
    data = request.json
    instructions = data.get('ai_instructions', '')
    notebook.set_ai_instructions(instructions)
    return dict(status='success')


@get('/get_ai_instructions')
@require_token
def get_ai_instructions():
    return dict(ai_instructions=notebook.get_ai_instructions())


## Unit test stub endpoints

@post('/save_unit_tests')
@action_log.logged('save_unit_tests')
@stateful
@unit_test_stateful
@require_token
def save_unit_tests():
    data = request.json
    cell_index = data.get('cell_index')
    unit_tests = data.get('unit_tests', {})
    notebook.save_unit_tests(cell_index, unit_tests)
    return dict(status='success')

@post('/save_unit_test_explanation')
@action_log.logged('save_unit_test_explanation')
@stateful
@unit_test_stateful
@require_token
def save_unit_test_explanation():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    explanation = data.get('explanation')
    notebook.save_unit_test_explanation(cell_index, test_name, role, explanation)
    return dict(status='success')

@post('/save_unit_test_code')
@action_log.logged('save_unit_test_code')
@stateful
@unit_test_stateful
@require_token
def save_unit_test_code():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    source = data.get('source')
    notebook.save_unit_test_code(cell_index, test_name, role, source)
    return dict(status='success')

@post('/clear_unit_test_code')
@action_log.logged('clear_unit_test_code')
@stateful
@unit_test_stateful
@require_token
def clear_unit_test_code():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    notebook.clear_unit_test_code(cell_index, test_name, role)
    return dict(status='success')

@post('/get_unit_test_state')
@require_token
def get_unit_test_state():
    data = request.json
    cell_index = data.get('cell_index')
    try:
        state = notebook.get_unit_test_state(cell_index)
        return dict(status='success', unit_test_state={
            'cell_index': cell_index,
            'state': state,
        })
    except Exception as e:
        return dict(status='error', message=str(e))

@post('/run_unit_test_cell')
@action_log.logged('run_unit_test_cell')
@stateful
@unit_test_stateful
@require_token
def run_unit_test_cell():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    try:
        outputs = notebook.execute_unit_test_cell(cell_index, test_name, role)
        return dict(status='ok', outputs=outputs, role=role)
    except CellExecutionError:
        cell = notebook.nb.cells[cell_index]
        test = cell.metadata.get('unit_tests', {})[test_name]
        if role == 'setup':
            outs = test['cells']['setup'].get('outputs', [])
        elif role == 'target':
            outs = test['cells'].get('target', {}).get('outputs', [])
        else:
            outs = test['cells']['test'].get('outputs', [])
        return dict(status='ok', details='CellExecutionError', outputs=outs, role=role)
    except Exception as e:
        return dict(status='error', message=str(e))

@post('/clear_unit_test_outputs')
@action_log.logged('clear_unit_test_outputs')
@unit_test_stateful
@require_token
def clear_unit_test_outputs():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    try:
        notebook.clear_unit_test_outputs(cell_index, test_name)
        return dict(status='success')
    except Exception as e:
        return dict(status='error', message=str(e))

@post('/generate_unit_test_cell_code')
@action_log.logged('generate_unit_test_cell_code')
@stateful
@unit_test_stateful
@require_token
def generate_unit_test_code():
    data = request.json
    cell_index = data.get('cell_index')
    test_name = data.get('test_name')
    role = data.get('role')
    validation_feedback = data.get('validation_feedback')
    api_key, ai_provider, model, error = _get_ai_config()
    if error:
        return dict(status='error', message=error)
    try:
        new_code, success = notebook.generate_unit_test_cell(
            api_key, cell_index, test_name, role,
            ai_provider=ai_provider, model=model,
            validation_feedback=validation_feedback,
            ask_questions=settings.get('ask_questions', DEFAULT_ASK_QUESTIONS),
            skip_regeneration=settings.get('skip_regeneration', DEFAULT_SKIP_REGENERATION))
    except Exception as e:
        friendly = _friendly_ai_error(e)
        if friendly:
            return dict(status='error', message=friendly)
        raise
    if success:
        return dict(status='success', code=new_code)
    else:
        return dict(status='cancelled', code=None)


@post('/debug_request')
@require_token
@stateful
def debug_request():
    notebook.debug_request()
    return dict(status='success')

@post('/reset_tokens')
@action_log.logged('reset_tokens')
@require_token
def reset_tokens():
    reset_session_tokens()
    return dict(status='success')


@get('/log_view')
@require_token
def log_view():
    if not args.logview:
        raise HTTPError(404, 'Log viewer is only available when the server is started with --logview')
    return serve_asset('log_view.html', 'views')


@post('/log_client_event')
@require_token
def log_client_event():
    if not action_log.LOG_ENABLED:
        return dict(status='success')
    try:
        action_log.append_client_event(request.json or {})
    except Exception as e:
        return dict(status='error', message=str(e))
    return dict(status='success')


################################
# Server startup

def find_free_port():
    port = args.port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((args.host, port))
                return port
            except OSError:
                port += 2
            
def logger_middleware(app):
    def wrapper(environ, start_response):
        # This function catches the status code before it's sent to the browser
        def logging_start_response(status, headers, exc_info=None):
            print(f"{environ['REQUEST_METHOD']} {environ['PATH_INFO']} - {status}")
            return start_response(status, headers, exc_info)
        
        return app(environ, logging_start_response)
    return wrapper
    
    
def _default_chromium_browser():
    """If the system default browser is Chromium-based, return its executable; else None.
    Best-effort and defensive — any failure returns None so we fall back to a scan."""
    try:
        if sys.platform == "darwin":
            import plistlib
            plist = os.path.expanduser(
                "~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist")
            with open(plist, "rb") as f:
                data = plistlib.load(f)
            handlers = {}
            for h in data.get("LSHandlers", []):
                scheme = h.get("LSHandlerURLScheme")
                if scheme in ("http", "https") and h.get("LSHandlerRoleAll"):
                    handlers[scheme] = h["LSHandlerRoleAll"].lower()
            bundle_id = handlers.get("https") or handlers.get("http")
            mac_map = {
                "com.google.chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "com.brave.browser": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "com.microsoft.edgemac": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "org.chromium.chromium": "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "com.vivaldi.vivaldi": "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
                "com.operasoftware.opera": "/Applications/Opera.app/Contents/MacOS/Opera",
            }
            p = mac_map.get(bundle_id)
            return p if p and os.path.exists(p) else None
        elif sys.platform.startswith("win"):
            import winreg, shlex
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as k:
                prog_id = (winreg.QueryValueEx(k, "ProgId")[0] or "").lower()
            if not any(x in prog_id for x in
                       ("chrome", "brave", "edge", "chromium", "vivaldi", "opera")):
                return None
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as k:
                cmd = winreg.QueryValueEx(k, "")[0]
            exe = shlex.split(cmd, posix=False)[0].strip('"')
            return exe if os.path.exists(exe) else None
        else:  # linux/bsd
            out = subprocess.run(["xdg-settings", "get", "default-web-browser"],
                                 capture_output=True, text=True, timeout=3).stdout.strip().lower()
            if not any(x in out for x in
                       ("chrome", "chromium", "brave", "edge", "vivaldi", "opera")):
                return None
            for name in ("brave-browser", "google-chrome", "google-chrome-stable", "chromium",
                         "chromium-browser", "microsoft-edge", "vivaldi", "vivaldi-stable", "opera"):
                if name in out:
                    p = shutil.which(name)
                    if p:
                        return p
            return None
    except Exception:
        return None
    return None


def _first_installed_chromium():
    """Return the first Chromium-based browser found in standard locations, or None."""
    if sys.platform == "darwin":
        for p in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ):
            if os.path.exists(p):
                return p
    elif sys.platform.startswith("win"):
        for b in filter(None, (os.environ.get("PROGRAMFILES"),
                               os.environ.get("PROGRAMFILES(X86)"),
                               os.environ.get("LOCALAPPDATA"))):
            for sub in (r"Google\Chrome\Application\chrome.exe",
                        r"Microsoft\Edge\Application\msedge.exe",
                        r"Chromium\Application\chrome.exe"):
                p = os.path.join(b, sub)
                if os.path.exists(p):
                    return p
    else:  # linux/bsd
        for name in ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "microsoft-edge", "brave-browser"):
            p = shutil.which(name)
            if p:
                return p
    return None


def find_chromium_browser():
    """Return a Chromium-based browser executable: the system default if it is
    Chromium-based, otherwise the first one found installed. None if none exist."""
    return _default_chromium_browser() or _first_installed_chromium()


def open_browser_tab(url):
    """Open the URL in a normal browser tab (the pre-existing behavior)."""
    try:
        webbrowser.open(url)
    except Exception:
        print(f"If the browser does not open, please load this URL: {url}")


def open_ui(url):
    """Open a chromeless app window via a Chromium-based browser if available,
    else fall back to a normal browser tab."""
    global LAUNCHED_CHROMELESS
    exe = find_chromium_browser()
    if exe:
        try:
            # Detach and silence the child: Chromium is chatty on stderr
            # (Wayland/Vulkan/GPU/DBus warnings) and would otherwise spam our terminal.
            subprocess.Popen([exe, f"--app={url}"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
            # An --app window has no toolbar, hence no reload button; the client
            # uses this to show its own Refresh button.
            LAUNCHED_CHROMELESS = True
            return
        except Exception:
            pass
    open_browser_tab(url)


def main():
    print(f"Plainbook {__version__}")
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/?token={AUTH_TOKEN}"
    print(f"Authentication token: {AUTH_TOKEN}")
    if args.debug:
        print(f"Please load this URL: {url}")
    elif args.app_window:
        open_ui(url)            # chromeless app window if a Chromium browser exists, else a tab
    else:
        open_browser_tab(url)   # normal browser tab (the default)
    # Reap this process when its window closes (or its browser dies).
    threading.Thread(target=_watchdog, daemon=True).start()
    app_with_logging = logger_middleware(default_app()) if args.debug else default_app()
    # Do not use reloader=True.
    try:
        run(app=app_with_logging, host=args.host, port=port,
            server='cheroot', numthreads=10, 
            debug=args.debug)
    except KeyboardInterrupt:
            print("\nStopping server...")
    finally:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()
            if not loop.is_closed():
                loop.close()
        except:
            pass

if __name__ == '__main__': 
    main()
    