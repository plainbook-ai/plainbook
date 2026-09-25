"""Tests for --unit-tests-only, the user-study mode.

The study plants a bug in a notebook and asks a participant to find it by
writing unit tests. Two properties have to hold for that to measure anything:

  1. the stored code of the main cells is executed exactly as it stands, and is
     never regenerated -- an AI that quietly rewrites a cell repairs the bug;
  2. nothing lets a participant, or an AI acting for them, edit a main cell or
     have one explained, validated or audited.

main.py cannot be imported under pytest (it parses argv at module scope and
builds a Plainbook), so the route layer is covered by the static audit in
test_action_log_coverage.py and by the deny-list test below, which reads the
decorators with ast. What *is* exercised here for real is property 1, which
lives in Plainbook and is the half that silently fails.
"""

import ast
import pathlib

import pytest

from plainbook.plainbook import Plainbook

MAIN_PY = pathlib.Path(__file__).resolve().parent.parent / "plainbook" / "main.py"

# Every route that must be refused outright in study mode, and why. The reason
# is not decoration: each of these is a way the planted bug could be repaired,
# revealed, or escaped from, and the list is the security argument for the mode.
DENIED_ROUTES = {
    # Editing a main cell directly.
    '/edit_code': 'rewrites a cell',
    '/edit_markdown': 'rewrites a cell (the route does not check the cell type)',
    '/clear_code': 'empties a cell',
    '/edit_explanation': 'rewrites a description, and calls the AI to rename the cell',
    '/propose_amend': 'AI rewrite of a description',
    '/commit_amend': 'installs an amended description',
    '/unfold': 'restores a description and its source',
    '/insert_cell': 'changes the notebook structure',
    '/delete_cell': 'changes the notebook structure',
    '/move_cell': 'changes the notebook structure',
    # Pointing an AI at a main cell.
    '/generate_code': 'regenerates the cell, repairing the bug',
    '/generate_test_code': 'same generator, no cell-type guard',
    '/validate_code': 'AI verdict on the buggy code',
    '/explain_code': 'AI explanation of the buggy code',
    '/verify_notebook': 'audits code against descriptions -- it would report the bug',
    # Steering or invalidating a later generation.
    '/set_files': 'invalidates cells citing removed paths, forcing regeneration',
    '/set_ai_instructions': 'changes the prompt every generation uses',
    '/set_skip_regeneration': 'changes regeneration policy',
    '/set_fix_error_amends_description': 'changes regeneration policy',
    # Escaping into a process without the flag.
    '/new_notebook': 'opens an unrestricted window',
    '/open_notebook': 'opens an unrestricted window',
    '/copy_notebook': 'copies the notebook into an unrestricted window',
    '/rename_notebook': 'moves later writes to another file',
}

# Unit-test routes that must keep working: without these there is no study.
ALLOWED_ROUTES = [
    '/save_unit_tests', '/save_unit_test_explanation', '/save_unit_test_code',
    '/clear_unit_test_code', '/clear_unit_test_outputs', '/get_unit_test_state',
    '/run_unit_test_cell', '/set_unit_test_validation_visibility',
    '/generate_unit_test_cell_code', '/validate_unit_test_code',
    '/execute_cell', '/execute_test_cell', '/reset_kernel', '/interrupt_kernel',
]


def _route_decorators():
    """{route path: [decorator names]} for every @post route in main.py."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        path, names = None, []
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute):
                name = target.attr
            elif isinstance(target, ast.Name):
                name = target.id
            else:
                continue
            names.append(name)
            if name in ("post", "get") and isinstance(dec, ast.Call) and dec.args:
                arg = dec.args[0]
                if isinstance(arg, ast.Constant):
                    path = arg.value
        if path:
            out[path] = names
    return out


ROUTE_DECORATORS = _route_decorators()


class TestDenyList:

    def test_routes_were_parsed(self):
        assert len(ROUTE_DECORATORS) > 50

    @pytest.mark.parametrize("route,reason", sorted(DENIED_ROUTES.items()))
    def test_denied_route_carries_the_guard(self, route, reason):
        assert route in ROUTE_DECORATORS, f"{route} no longer exists"
        assert "study_denied" in ROUTE_DECORATORS[route], (
            f"{route} lost its @study_denied guard. In --unit-tests-only mode it "
            f"{reason}, which breaks the study."
        )

    @pytest.mark.parametrize("route", ALLOWED_ROUTES)
    def test_allowed_route_is_not_denied(self, route):
        assert route in ROUTE_DECORATORS, f"{route} no longer exists"
        assert "study_denied" not in ROUTE_DECORATORS[route], (
            f"{route} is needed to write and run unit tests; denying it leaves "
            f"nothing for a participant to do."
        )

    def test_crossover_routes_check_the_target_role(self):
        """These two stay enabled, so the role check is the only boundary."""
        tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
        callers = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Name)
                        and inner.func.id == "deny_target_role"):
                    callers.add(node.name)
        assert callers == {"generate_unit_test_code", "validate_unit_test_code"}, (
            "Both routes delegate to main-cell AI when role == 'target', so each "
            f"needs its own deny_target_role(role) call. Found: {sorted(callers)}"
        )


class TestCodeIsNeverRegenerated:
    """Property 1: stored main-cell code is executed as it stands.

    The client asks the server to generate a cell exactly when
    last_valid_code_cell has dropped below it, so pinning that watermark is what
    makes regeneration impossible without also making the notebook unrunnable.
    """

    @staticmethod
    def _write_notebook(path, sources, input_files=None):
        import nbformat
        nb = nbformat.v4.new_notebook()
        for src, expl in sources:
            cell = nbformat.v4.new_code_cell(source=src)
            cell.metadata['explanation'] = expl
            nb.cells.append(cell)
        nb.metadata['last_valid_code_cell'] = -1     # as if never generated
        if input_files is not None:
            nb.metadata['input_files'] = input_files
        with open(path, 'w') as f:
            nbformat.write(nb, f)

    def test_watermark_is_pinned_on_load(self, tmp_notebook_path):
        self._write_notebook(tmp_notebook_path, [('x = 1', 'set x'), ('y = 2', 'set y')])
        nb = Plainbook(tmp_notebook_path, unit_tests_only=True)
        try:
            assert nb.last_valid_code_cell == len(nb.nb.cells) - 1
        finally:
            nb._shutdown()

    def test_without_the_flag_the_watermark_is_not_pinned(self, tmp_notebook_path):
        """Guards against the pin leaking into normal operation."""
        self._write_notebook(tmp_notebook_path, [('x = 1', 'set x')])
        nb = Plainbook(tmp_notebook_path)
        try:
            assert nb.last_valid_code_cell == -1
        finally:
            nb._shutdown()

    def test_a_missing_input_file_does_not_invalidate_cells(self, tmp_notebook_path):
        """The load-time hazard: a study notebook opened on a participant's
        laptop, whose paths differ, would otherwise have its cells marked stale
        and regenerated by the first run."""
        self._write_notebook(
            tmp_notebook_path,
            [('df = pd.read_csv("/nowhere/absent.csv")', 'load the data')],
            input_files=[{'path': '/nowhere/absent.csv', 'name': 'absent.csv'}])
        nb = Plainbook(tmp_notebook_path, unit_tests_only=True)
        try:
            assert nb.last_valid_code_cell == 0
            cell = nb.nb.cells[0]
            assert 'absent.csv' in cell.source, "the stored source must be untouched"
        finally:
            nb._shutdown()

    def test_running_does_not_change_stored_source(self, tmp_notebook_path):
        """The property the whole study rests on: execute every cell and the
        source must come back byte-identical, bug and all."""
        buggy = "wins = {'a': 0}\nwins['a'] = wins['a'] - 1   # the planted bug"
        self._write_notebook(tmp_notebook_path, [('x = 1', 'set x to 1'), (buggy, 'count the wins')])
        nb = Plainbook(tmp_notebook_path, unit_tests_only=True)
        try:
            before = [c.source for c in nb.nb.cells]
            for i in range(len(nb.nb.cells)):
                nb.execute_cell(i)
            after = [c.source for c in nb.nb.cells]
            assert after == before
            assert 'the planted bug' in after[1]
        finally:
            nb._shutdown()

    def test_cells_are_executable_despite_a_stale_watermark(self, tmp_notebook_path):
        """Refusing generation without pinning would make execute_cell raise
        ('Executed a cell that is not valid') and strand the participant."""
        self._write_notebook(tmp_notebook_path, [('x = 1', 'set x'), ('y = x + 1', 'add one')])
        nb = Plainbook(tmp_notebook_path, unit_tests_only=True)
        try:
            # Executed in order, as Plainbook requires. Without the pin the first
            # call raises ExecutionError("Executed a cell that is not valid"),
            # because the notebook ships with last_valid_code_cell == -1.
            for i in range(len(nb.nb.cells)):
                _outputs, details = nb.execute_cell(i)
                assert details != 'CellExecutionError', f"cell {i} failed: {_outputs}"
        finally:
            nb._shutdown()
