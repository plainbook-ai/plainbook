"""Action log for user studies.

When Plainbook is run with ``--log``, every mutating API call and every
``active_cell_change`` client event is appended as a structured entry to
``notebook.metadata['log']``. See ``Log.md`` at the repo root for the schema
and analysis recipes.
"""

import datetime
import hashlib
import json
import sys
import time
import traceback
from functools import wraps

from bottle import request, HTTPError


LOG_ENABLED = False
LOGVIEW_ENABLED = False
_plainbook = None

_LOG_SIZE_WARN_THRESHOLD = 10_000
_warned_size = False


def bind(plainbook, enabled):
    """Wire the module to the Plainbook instance created by main.py.
    On first enable, capture log_initial_state so the /log_view replay can
    start from the notebook's state at that moment."""
    global _plainbook, LOG_ENABLED
    _plainbook = plainbook
    LOG_ENABLED = bool(enabled)
    if LOG_ENABLED and plainbook is not None:
        if 'log_initial_state' not in plainbook.nb.metadata:
            with plainbook._lock:
                plainbook.nb.metadata['log_initial_state'] = _make_initial_snapshot(plainbook.nb)
                plainbook._write()


def _make_initial_snapshot(nb):
    """Compact snapshot of current cells + notebook metadata, used as the
    starting point for replay. Outputs and execution_count are omitted
    (not replayable)."""
    cells = []
    for c in nb.cells:
        md = dict(c.get('metadata') or {})
        md.pop('_last_logged_hash', None)
        cells.append({
            'id': c.get('id'),
            'cell_type': c.get('cell_type'),
            'source': c.get('source', ''),
            'metadata': md,
        })
    meta = {k: v for k, v in nb.metadata.items()
            if k not in ('log', 'log_initial_state')}
    return {
        'ts_captured': _now_iso(),
        'cells': cells,
        'metadata': meta,
    }


OP_LOG_CONFIG = {
    "set_key": {"redact_params": ["gemini_api_key", "claude_api_key", "openai_api_key"], "snapshot": False},
    "set_active_ai": {"snapshot": False},
    "edit_explanation": {"snapshot": True},
    "propose_amend": {"snapshot": False, "truncate_param_fields": {"text": 4096},
                      "truncate_result_fields": {"proposed": 8192}},
    "commit_amend": {"snapshot": True, "truncate_param_fields": {"explanation": 8192}},
    "unfold": {"snapshot": True, "truncate_result_fields": {"explanation": 8192, "source": 8192}},
    "edit_code": {"snapshot": True},
    "edit_markdown": {"snapshot": True},
    "clear_code": {"snapshot": True},
    "insert_cell": {"snapshot": True},
    "delete_cell": {"snapshot": False},
    "move_cell": {"snapshot": False},
    "execute_cell": {"snapshot": True, "drop_result_fields": ["outputs", "details"]},
    "execute_test_cell": {"snapshot": True, "drop_result_fields": ["outputs"]},
    "run_unit_test_cell": {"snapshot": True, "drop_result_fields": ["outputs"]},
    "reset_kernel": {"snapshot": False},
    "interrupt_kernel": {"snapshot": False},
    "clear_outputs": {"snapshot": False},
    "cancel_ai_request": {"snapshot": False},
    "generate_code": {"snapshot": True, "truncate_result_fields": {"code": 8192}},
    "generate_test_code": {"snapshot": True, "truncate_result_fields": {"code": 8192}},
    "generate_unit_test_cell_code": {"snapshot": True, "truncate_result_fields": {"code": 8192}},
    "validate_code": {"snapshot": True},
    "explain_code": {"snapshot": True, "truncate_result_fields": {"explanation": 8192}},
    "set_explain_options": {"snapshot": False},
    "validate_unit_test_code": {"snapshot": True},
    "set_validation_visibility": {"snapshot": True},
    "set_unit_test_validation_visibility": {"snapshot": True},
    "save_unit_tests": {"snapshot": True},
    "save_unit_test_explanation": {"snapshot": True},
    "save_unit_test_code": {"snapshot": True},
    "clear_unit_test_code": {"snapshot": True},
    "clear_unit_test_outputs": {"snapshot": True},
    "lock_notebook": {"snapshot": False},
    "set_share_output": {"snapshot": False},
    "set_ask_questions": {"snapshot": False},
    "new_notebook": {"snapshot": False},
    "copy_notebook": {"snapshot": False},
    "open_notebook": {"snapshot": False},
    "set_skip_regeneration": {"snapshot": False},
    "set_fix_error_amends_description": {"snapshot": False},
    "set_files": {"snapshot": False, "truncate_param_fields": {"files": 4096, "missing_files": 4096}},
    "set_ai_instructions": {"snapshot": False, "truncate_param_fields": {"ai_instructions": 4096}},
    "reset_tokens": {"snapshot": False},
}


def _now_iso():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _redact(value):
    s = str(value) if value is not None else ""
    return f"<redacted len={len(s)}>"


def _truncate(value, max_bytes):
    try:
        s = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) <= max_bytes:
        return value
    return s[:max_bytes] + f"...<truncated len={len(s)}>"


def _filter_params(op_name, params):
    if not params:
        return params
    cfg = OP_LOG_CONFIG.get(op_name, {})
    out = dict(params)
    for k in cfg.get("redact_params", ()):
        if k in out and out[k]:
            out[k] = _redact(out[k])
    for k, max_bytes in cfg.get("truncate_param_fields", {}).items():
        if k in out:
            out[k] = _truncate(out[k], max_bytes)
    return out


def _filter_result(op_name, result):
    if not isinstance(result, dict):
        return result
    cfg = OP_LOG_CONFIG.get(op_name, {})
    out = {k: v for k, v in result.items() if k not in ("state", "unit_test_state")}
    for k in cfg.get("drop_result_fields", ()):
        out.pop(k, None)
    for k, max_bytes in cfg.get("truncate_result_fields", {}).items():
        if k in out and out[k] is not None:
            out[k] = _truncate(out[k], max_bytes)
    return out


def _hash_cell_content(source, description):
    h = hashlib.sha1()
    h.update((source or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((description or "").encode("utf-8"))
    return h.hexdigest()


def _extract_error_outputs(outputs):
    error = None
    stderr_parts = []
    for o in outputs or []:
        otype = o.get("output_type")
        if otype == "error":
            error = {
                "ename": o.get("ename", ""),
                "evalue": o.get("evalue", ""),
                "traceback": list(o.get("traceback", [])),
            }
        elif otype == "stream" and o.get("name") == "stderr":
            text = o.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            stderr_parts.append(text)
    stderr = "".join(stderr_parts) if stderr_parts else None
    return error, stderr


def _cell_snapshot(plainbook, cell_index):
    if cell_index is None:
        return None
    try:
        cell = plainbook.nb.cells[cell_index]
    except (IndexError, TypeError, AttributeError):
        return None
    source = cell.get("source", "")
    description = cell.metadata.get("explanation", "") if hasattr(cell, "metadata") else ""
    new_hash = _hash_cell_content(source, description)
    prev_hash = cell.metadata.get("_last_logged_hash") if hasattr(cell, "metadata") else None
    changed = new_hash != prev_hash
    snap = {
        "cell_id": cell.get("id"),
        "cell_type": cell.get("cell_type"),
        "changed": changed,
    }
    if changed:
        snap["source"] = source
        snap["description"] = description
        cell.metadata["_last_logged_hash"] = new_hash
    outputs = cell.get("outputs", []) if cell.get("cell_type") in ("code", "test") else []
    error, stderr = _extract_error_outputs(outputs)
    if error is not None:
        snap["error"] = error
    if stderr is not None:
        snap["stderr"] = stderr
    return snap


def _resolve_cell_index(op_name, params, result):
    if not isinstance(params, dict):
        return None
    idx = params.get("cell_index")
    if idx is not None:
        return idx
    if op_name == "insert_cell" and isinstance(result, dict):
        return result.get("index")
    return None


def _resolve_cell_id(plainbook, cell_index):
    if cell_index is None:
        return None
    try:
        return plainbook.nb.cells[cell_index].get("id")
    except (IndexError, TypeError, AttributeError):
        return None


def _build_entry(op_name, params, result, duration_ms, error_repr):
    cell_index = _resolve_cell_index(op_name, params, result)
    cfg = OP_LOG_CONFIG.get(op_name, {"snapshot": cell_index is not None})
    entry = {
        "ts_server": _now_iso(),
        "source": "server",
        "op": op_name,
        "params": _filter_params(op_name, params),
        "result": _filter_result(op_name, result) if result is not None else None,
        "cell_id": _resolve_cell_id(_plainbook, cell_index),
        "cell_index": cell_index,
        "duration_ms": duration_ms,
        "error": error_repr,
    }
    if cfg.get("snapshot", False):
        snap = _cell_snapshot(_plainbook, cell_index)
        if snap is not None:
            entry["cell_snapshot"] = snap
            if entry["cell_id"] is None:
                entry["cell_id"] = snap.get("cell_id")
    return entry


def _append(entry):
    global _warned_size
    if _plainbook is None:
        return
    _plainbook.append_log_entry(entry)
    try:
        n = len(_plainbook.nb.metadata.get("log", []))
    except Exception:
        return
    if n > _LOG_SIZE_WARN_THRESHOLD and not _warned_size:
        print(f"Warning: action log has {n} entries (>{_LOG_SIZE_WARN_THRESHOLD}); "
              f"notebook file will continue to grow.", file=sys.stderr)
        _warned_size = True


def logged(op_name):
    """Decorator for Bottle POST routes. Captures request.json, invokes the
    handler, then appends a filtered log entry. Exceptions are logged and
    re-raised."""
    def outer(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if LOGVIEW_ENABLED:
                raise HTTPError(403, 'Notebook is in read-only --logview mode; mutations are not allowed.')
            if not LOG_ENABLED:
                return fn(*a, **kw)
            try:
                params = request.json if request.content_type and "json" in request.content_type else None
            except Exception:
                params = None
            start = time.perf_counter()
            error_repr = None
            result = None
            try:
                result = fn(*a, **kw)
                return result
            except Exception as exc:
                error_repr = repr(exc)
                raise
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                try:
                    entry = _build_entry(op_name, params, result, duration_ms, error_repr)
                    _append(entry)
                except Exception as log_exc:
                    print(f"Warning: action_log append failed for op={op_name}: {log_exc}",
                          file=sys.stderr)
                    if _plainbook is not None and getattr(_plainbook, "debug", False):
                        traceback.print_exc()
        return wrapper
    return outer


def append_client_event(evt):
    """Record a client-originated event (active_cell_change). evt is the raw
    JSON body posted to /log_client_event."""
    if not LOG_ENABLED or _plainbook is None:
        return
    if not isinstance(evt, dict):
        return
    op = evt.get("op") or "client_event"
    entry = {
        "ts_server": _now_iso(),
        "ts_client": evt.get("ts_client"),
        "source": "client",
        "op": op,
        "from_id": evt.get("from_id"),
        "from_index": evt.get("from_index"),
        "to_id": evt.get("to_id"),
        "to_index": evt.get("to_index"),
        "duration_on_prev_ms": evt.get("duration_on_prev_ms"),
    }
    _append(entry)
