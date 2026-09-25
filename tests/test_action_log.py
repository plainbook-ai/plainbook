"""Unit tests for plainbook/action_log.py (the --log user-study logger)."""

import threading

import pytest

from plainbook.plainbook import Plainbook
from plainbook import action_log


@pytest.fixture
def notebook(tmp_notebook_path):
    nb = Plainbook(tmp_notebook_path)
    yield nb
    nb._shutdown()


@pytest.fixture
def logger_bound(notebook):
    """Binds the action_log module to a fresh Plainbook for each test and
    resets LOG_ENABLED afterwards so state doesn't leak across tests."""
    action_log.bind(notebook, True)
    action_log._warned_size = False
    yield notebook
    action_log.bind(None, False)
    action_log._warned_size = False


# === Filter helpers ===


class TestFilterParams:

    def test_redacts_api_keys(self):
        params = {"gemini_api_key": "real-secret", "claude_api_key": "also-secret",
                  "openai_api_key": "third-secret", "provider": "gemini:2.5-flash"}
        out = action_log._filter_params("set_key", params)
        assert out["gemini_api_key"].startswith("<redacted len=")
        assert "real-secret" not in out["gemini_api_key"]
        assert out["claude_api_key"].startswith("<redacted len=")
        assert out["openai_api_key"].startswith("<redacted len=")
        assert "third-secret" not in out["openai_api_key"]
        assert out["provider"] == "gemini:2.5-flash"

    def test_passthrough_when_no_config(self):
        params = {"cell_index": 3, "source": "print('hi')"}
        assert action_log._filter_params("edit_code", params) == params

    def test_truncates_large_param_fields(self):
        big = "x" * 5000
        out = action_log._filter_params("set_ai_instructions", {"ai_instructions": big})
        assert len(out["ai_instructions"]) < 5000
        assert "truncated" in out["ai_instructions"]


class TestFilterResult:

    def test_strips_state(self):
        r = {"status": "success", "state": {"num_cells": 5, "other": "big"}}
        assert action_log._filter_result("edit_code", r) == {"status": "success"}

    def test_strips_unit_test_state(self):
        r = {"status": "ok", "state": {}, "unit_test_state": {"cell_index": 1}}
        assert action_log._filter_result("save_unit_tests", r) == {"status": "ok"}

    def test_drops_execute_outputs(self):
        r = {"status": "ok", "state": {}, "outputs": [{"output_type": "stream"}],
             "details": "ok"}
        out = action_log._filter_result("execute_cell", r)
        assert "outputs" not in out
        assert "details" not in out
        assert out == {"status": "ok"}

    def test_truncates_generated_code(self):
        big_code = "x = 0\n" * 5000
        r = {"status": "success", "code": big_code, "state": {}}
        out = action_log._filter_result("generate_code", r)
        assert len(out["code"]) < len(big_code)
        assert "truncated" in out["code"]

    def test_passes_non_dict_through(self):
        assert action_log._filter_result("x", None) is None
        assert action_log._filter_result("x", "hello") == "hello"


# === Cell snapshot ===


class TestCellSnapshot:

    def test_first_call_is_changed(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.set_cell_source(idx, "print(1)")
        nb.set_cell_explanation(idx, "print one")
        snap = action_log._cell_snapshot(nb, idx)
        assert snap["changed"] is True
        assert snap["source"] == "print(1)"
        assert snap["description"] == "print one"
        assert snap["cell_type"] == "code"
        assert snap["cell_id"] == nb.nb.cells[idx].id

    def test_repeat_call_same_content_is_unchanged(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.set_cell_source(idx, "print(1)")
        action_log._cell_snapshot(nb, idx)
        snap2 = action_log._cell_snapshot(nb, idx)
        assert snap2["changed"] is False
        assert "source" not in snap2
        assert "description" not in snap2

    def test_edit_retriggers_changed(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.set_cell_source(idx, "print(1)")
        action_log._cell_snapshot(nb, idx)
        nb.set_cell_source(idx, "print(2)")
        snap = action_log._cell_snapshot(nb, idx)
        assert snap["changed"] is True
        assert snap["source"] == "print(2)"

    def test_explanation_change_retriggers_changed(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.set_cell_source(idx, "x = 1")
        nb.set_cell_explanation(idx, "first")
        action_log._cell_snapshot(nb, idx)
        nb.set_cell_explanation(idx, "second")
        snap = action_log._cell_snapshot(nb, idx)
        assert snap["changed"] is True
        assert snap["description"] == "second"

    def test_error_output_surfaces(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.nb.cells[idx]["outputs"] = [{
            "output_type": "error",
            "ename": "NameError",
            "evalue": "name 'x' is not defined",
            "traceback": ["Traceback line 1", "Traceback line 2"],
        }]
        snap = action_log._cell_snapshot(nb, idx)
        assert snap["error"]["ename"] == "NameError"
        assert snap["error"]["evalue"] == "name 'x' is not defined"
        assert snap["error"]["traceback"] == ["Traceback line 1", "Traceback line 2"]

    def test_stderr_output_surfaces(self, logger_bound):
        nb = logger_bound
        _, idx = nb.insert_cell(0, "code")
        nb.nb.cells[idx]["outputs"] = [
            {"output_type": "stream", "name": "stdout", "text": "hi"},
            {"output_type": "stream", "name": "stderr", "text": "warning!"},
        ]
        snap = action_log._cell_snapshot(nb, idx)
        assert snap["stderr"] == "warning!"

    def test_out_of_range_returns_none(self, logger_bound):
        assert action_log._cell_snapshot(logger_bound, 999) is None

    def test_none_index_returns_none(self, logger_bound):
        assert action_log._cell_snapshot(logger_bound, None) is None


# === append_log_entry thread safety ===


class TestThreadSafety:

    def test_concurrent_appends_all_land(self, notebook):
        action_log.bind(notebook, True)
        try:
            N = 50
            threads = []
            for i in range(N):
                def task(i=i):
                    notebook.append_log_entry({"ts_server": "t", "source": "server",
                                               "op": f"op_{i}"})
                threads.append(threading.Thread(target=task))
            for t in threads: t.start()
            for t in threads: t.join()
            log = notebook.nb.metadata.get("log", [])
            assert len(log) == N
            ops = sorted(e["op"] for e in log)
            assert ops == sorted(f"op_{i}" for i in range(N))
        finally:
            action_log.bind(None, False)


# === Client events ===


class TestInitialStateSnapshot:

    def test_captured_on_first_bind(self, notebook):
        nb = notebook
        nb.insert_cell(0, "code")
        nb.set_cell_source(0, "x = 1")
        nb.set_cell_explanation(0, "the answer")
        assert "log_initial_state" not in nb.nb.metadata
        action_log.bind(nb, True)
        try:
            snap = nb.nb.metadata.get("log_initial_state")
            assert snap is not None
            assert snap["cells"][0]["source"] == "x = 1"
            assert snap["cells"][0]["metadata"]["explanation"] == "the answer"
            assert snap["cells"][0]["cell_type"] == "code"
            assert "_last_logged_hash" not in snap["cells"][0]["metadata"]
        finally:
            action_log.bind(None, False)

    def test_preserved_across_rebinds(self, notebook):
        nb = notebook
        nb.insert_cell(0, "code")
        nb.set_cell_source(0, "first")
        action_log.bind(nb, True)
        first_snap = nb.nb.metadata["log_initial_state"]
        action_log.bind(None, False)
        nb.set_cell_source(0, "second")
        action_log.bind(nb, True)
        try:
            assert nb.nb.metadata["log_initial_state"] is first_snap
            assert nb.nb.metadata["log_initial_state"]["cells"][0]["source"] == "first"
        finally:
            action_log.bind(None, False)

    def test_not_captured_when_disabled(self, notebook):
        nb = notebook
        nb.insert_cell(0, "code")
        action_log.bind(nb, False)
        try:
            assert "log_initial_state" not in nb.nb.metadata
        finally:
            action_log.bind(None, False)


class TestLogviewMode:

    def test_logged_decorator_rejects_when_logview(self, notebook):
        """When LOGVIEW_ENABLED is True, decorated handlers raise HTTPError(403)
        before the underlying handler runs."""
        from bottle import HTTPError
        action_log.LOGVIEW_ENABLED = True
        action_log.bind(notebook, False)  # LOG_ENABLED off, LOGVIEW on
        try:
            called = {'n': 0}

            @action_log.logged('edit_code')
            def handler():
                called['n'] += 1
                return {'status': 'success'}

            with pytest.raises(HTTPError) as excinfo:
                handler()
            assert excinfo.value.status_code == 403
            assert called['n'] == 0
        finally:
            action_log.LOGVIEW_ENABLED = False
            action_log.bind(None, False)

    def test_logged_decorator_passes_when_logview_off(self, notebook):
        action_log.LOGVIEW_ENABLED = False
        action_log.bind(notebook, True)
        try:
            @action_log.logged('edit_code')
            def handler():
                return {'status': 'success'}
            # Should not raise.
            result = handler()
            assert result == {'status': 'success'}
        finally:
            action_log.bind(None, False)


class TestClientEvents:

    def test_active_cell_change_is_logged(self, logger_bound):
        nb = logger_bound
        action_log.append_client_event({
            "op": "active_cell_change",
            "ts_client": "2026-04-15T12:00:00.000Z",
            "from_id": "a", "from_index": 0,
            "to_id": "b", "to_index": 1,
            "duration_on_prev_ms": 1234,
        })
        log = nb.nb.metadata["log"]
        assert len(log) == 1
        entry = log[0]
        assert entry["source"] == "client"
        assert entry["op"] == "active_cell_change"
        assert entry["from_id"] == "a"
        assert entry["to_id"] == "b"
        assert entry["duration_on_prev_ms"] == 1234
        assert entry["ts_client"] == "2026-04-15T12:00:00.000Z"
        assert "ts_server" in entry

    def test_disabled_short_circuits(self, notebook):
        action_log.bind(notebook, False)
        try:
            action_log.append_client_event({"op": "active_cell_change"})
            assert "log" not in notebook.nb.metadata
        finally:
            action_log.bind(None, False)


class TestUnitTestSnapshots:
    """A unit-test run is about its sub-cell, not about the cell the test hangs
    off. _cell_snapshot used to read the parent cell's outputs for every op, so a
    failing unit test was logged as having run with no trace of what it found."""

    @staticmethod
    def _cell_with_unit_test(setup_outputs=None, test_outputs=None):
        """A minimal nbformat-ish cell carrying one unit test."""
        import nbformat
        cell = nbformat.v4.new_code_cell(source="x = 1")
        cell.metadata["unit_tests"] = {
            "t1": {"cells": {
                "setup": {"source": "d = 1", "metadata": {}, "outputs": setup_outputs or []},
                "test": {"source": "assert d == 2", "metadata": {}, "outputs": test_outputs or []},
            }}
        }
        return cell

    @staticmethod
    def _error_output(ename, evalue):
        return {"output_type": "error", "ename": ename, "evalue": evalue,
                "traceback": [f"{ename}: {evalue}"]}

    def test_failing_unit_test_error_is_captured(self, notebook):
        cell = self._cell_with_unit_test(
            test_outputs=[self._error_output("AssertionError", "expected 2")])
        notebook.nb.cells.append(cell)
        idx = len(notebook.nb.cells) - 1
        snap = action_log._cell_snapshot(
            notebook, idx, "run_unit_test_cell", {"test_name": "t1", "role": "test"})
        assert snap["error"]["ename"] == "AssertionError"
        assert snap["error"]["evalue"] == "expected 2"
        assert snap["unit_test"] == {"name": "t1", "role": "test"}

    def test_parent_cell_error_is_not_attributed_to_the_sub_cell(self, notebook):
        """The cell itself failed earlier; a passing test must not inherit that."""
        cell = self._cell_with_unit_test()
        cell.outputs = [self._error_output("NameError", "name 'q' is not defined")]
        notebook.nb.cells.append(cell)
        idx = len(notebook.nb.cells) - 1
        snap = action_log._cell_snapshot(
            notebook, idx, "run_unit_test_cell", {"test_name": "t1", "role": "test"})
        assert "error" not in snap, snap

    def test_non_unit_test_ops_still_read_the_cell(self, notebook):
        cell = self._cell_with_unit_test()
        cell.outputs = [self._error_output("NameError", "name 'q' is not defined")]
        notebook.nb.cells.append(cell)
        idx = len(notebook.nb.cells) - 1
        snap = action_log._cell_snapshot(notebook, idx, "execute_cell", {"cell_index": idx})
        assert snap["error"]["ename"] == "NameError"
        assert "unit_test" not in snap

    def test_missing_sub_cell_is_recorded_but_yields_no_error(self, notebook):
        cell = self._cell_with_unit_test()
        notebook.nb.cells.append(cell)
        idx = len(notebook.nb.cells) - 1
        snap = action_log._cell_snapshot(
            notebook, idx, "run_unit_test_cell", {"test_name": "nope", "role": "test"})
        assert snap["unit_test"] == {"name": "nope", "role": "test"}
        assert "error" not in snap

    def test_sub_cell_stderr_is_captured(self, notebook):
        cell = self._cell_with_unit_test(
            test_outputs=[{"output_type": "stream", "name": "stderr", "text": "DeprecationWarning: x"}])
        notebook.nb.cells.append(cell)
        idx = len(notebook.nb.cells) - 1
        snap = action_log._cell_snapshot(
            notebook, idx, "run_unit_test_cell", {"test_name": "t1", "role": "test"})
        assert "DeprecationWarning" in snap["stderr"]
