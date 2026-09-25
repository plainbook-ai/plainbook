"""Static audit of --log coverage across the API surface.

main.py cannot be imported under pytest (it calls parse_args() at module scope
and builds a Plainbook), so these read it with ast instead. That is enough: what
is being checked is which decorators sit on which route.

The point is to make adding a route a decision rather than an oversight. A new
POST route silently missing @action_log.logged is invisible twice over: it is
absent from a user study's record, and -- because the guard in
action_log.logged is the *only* thing that refuses mutations in --logview mode
-- it stays writable in a session that is supposed to be read-only.
"""

import ast
import pathlib

import pytest

from plainbook.action_log import OP_LOG_CONFIG

MAIN_PY = pathlib.Path(__file__).resolve().parent.parent / "plainbook" / "main.py"

# POST routes that deliberately carry no log entry, with the reason. Adding a
# route here is a claim that it is not a user action on the notebook.
EXEMPT_POST_ROUTES = {
    "/login": "authentication, not a notebook action",
    "/shutdown": "connection lifecycle; must stay callable in --logview",
    "/file_list": "browses the filesystem, changes nothing",
    "/get_unit_test_state": "a read; POST only to carry a body",
    "/debug_request": "debug helper, enabled only with --debug",
    "/log_client_event": "the client-event channel itself; logging it would double-count",
}


def _decorator_name(dec):
    node = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(node, ast.Attribute):
        base = node.value.id if isinstance(node.value, ast.Name) else ""
        return f"{base}.{node.attr}" if base else node.attr
    return node.id if isinstance(node, ast.Name) else None


def _first_string_arg(dec):
    if isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant):
        return dec.args[0].value
    return None


def _routes():
    """(function_name, [(method, path)], logged_op or None) for every route."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        methods, op = [], None
        for dec in node.decorator_list:
            name = _decorator_name(dec)
            if name in ("get", "post", "route"):
                methods.append((name.upper(), _first_string_arg(dec)))
            elif name == "action_log.logged":
                op = _first_string_arg(dec)
        if methods:
            found.append((node.name, methods, op))
    return found


ROUTES = _routes()


def test_routes_were_found():
    """Guards against the ast walk silently matching nothing."""
    assert len(ROUTES) > 50


@pytest.mark.parametrize("fn,methods,op",
                         [r for r in ROUTES if any(m == "POST" for m, _ in r[1])])
def test_every_post_route_is_logged_or_exempt(fn, methods, op):
    paths = [p for m, p in methods if m == "POST"]
    if op is not None:
        return
    for path in paths:
        assert path in EXEMPT_POST_ROUTES, (
            f"POST {path} ({fn}) has no @action_log.logged decorator. Either add one "
            f"(and an OP_LOG_CONFIG entry), or list it in EXEMPT_POST_ROUTES with the "
            f"reason it is not a user action. Without it the call is missing from "
            f"--log records and is not refused in --logview mode."
        )


def test_every_logged_op_is_configured():
    """An op absent from OP_LOG_CONFIG still logs, but falls back to defaults:
    no redaction and no truncation, so a large result lands in the notebook
    verbatim."""
    used = {op for _, _, op in ROUTES if op}
    missing = sorted(used - set(OP_LOG_CONFIG))
    assert not missing, f"logged ops with no OP_LOG_CONFIG entry: {missing}"


def test_no_stale_config_entries():
    used = {op for _, _, op in ROUTES if op}
    stale = sorted(set(OP_LOG_CONFIG) - used)
    assert not stale, f"OP_LOG_CONFIG entries no route uses: {stale}"


def test_op_names_are_unique():
    ops = [op for _, _, op in ROUTES if op]
    dupes = sorted({o for o in ops if ops.count(o) > 1})
    assert not dupes, f"the same op name is used by more than one route: {dupes}"


def test_exempt_list_has_no_dead_entries():
    post_paths = {p for _, methods, _ in ROUTES for m, p in methods if m == "POST"}
    dead = sorted(set(EXEMPT_POST_ROUTES) - post_paths)
    assert not dead, f"EXEMPT_POST_ROUTES names routes that no longer exist: {dead}"
