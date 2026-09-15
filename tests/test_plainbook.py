import hashlib
import os

import nbformat
import pytest
from plainbook.plainbook import (CellExecutionError, ExecutionError, Plainbook,
                                 check_notebook_file, normalize_notebook_name,
                                 unique_notebook_path)


@pytest.fixture
def notebook(tmp_notebook_path):
    """Creates a Plainbook instance and shuts it down after the test."""
    nb = Plainbook(tmp_notebook_path)
    yield nb
    nb._shutdown()


def _add_code_cell(notebook, source, index=None):
    """Insert a code cell with source and mark it valid for execution."""
    if index is None:
        index = len(notebook.nb.cells)
    cell, idx = notebook.insert_cell(index, 'code')
    notebook.set_cell_source(idx, source)
    notebook.last_valid_code_cell = max(notebook.last_valid_code_cell, idx)
    return idx


def _add_markdown_cell(notebook, source, index=None):
    """Insert a markdown cell with source."""
    if index is None:
        index = len(notebook.nb.cells)
    cell, idx = notebook.insert_cell(index, 'markdown')
    notebook.set_cell_source(idx, source)
    return idx


def _add_test_cell(notebook, source, index=None):
    """Insert a test cell with source."""
    if index is None:
        index = len(notebook.nb.cells)
    cell, idx = notebook.insert_cell(index, 'test')
    notebook.set_cell_source(idx, source)
    return idx


# === Notebook lifecycle ===


class TestNotebookLifecycle:

    def test_create_empty_notebook(self, notebook):
        """Creating from non-existent path yields an empty notebook."""
        assert len(notebook.nb.cells) == 0
        assert notebook.last_executed_cell == -1

    def test_get_state(self, notebook):
        """get_state returns all expected keys."""
        state = notebook.get_state()
        expected_keys = {
            'name', 'path', 'num_cells',
            'last_executed_cell', 'last_valid_code_cell',
            'last_valid_output_cell', 'last_valid_test_cell', 'is_locked',
            'share_output_with_ai', 'ai_tokens',
            'verification_status',
        }
        assert set(state.keys()) == expected_keys
        assert state['num_cells'] == 0
        assert state['last_executed_cell'] == -1
        assert state['is_locked'] is False

    def test_get_json(self, notebook):
        """get_json returns the notebook object."""
        nb_json = notebook.get_json()
        assert hasattr(nb_json, 'cells')
        assert len(nb_json.cells) == 0

    def test_get_cell_json(self, notebook):
        """get_cell_json returns cell by index."""
        _add_code_cell(notebook, 'x = 1')
        cell = notebook.get_cell_json(0)
        assert cell.cell_type == 'code'
        assert cell.source == 'x = 1'

    def test_get_cell_json_out_of_range(self, notebook):
        """get_cell_json raises IndexError for invalid index."""
        with pytest.raises(IndexError):
            notebook.get_cell_json(0)


# === Cell manipulation ===


class TestCellManipulation:

    def test_insert_code_cell(self, notebook):
        cell, idx = notebook.insert_cell(0, 'code')
        assert idx == 0
        assert cell.cell_type == 'code'
        assert len(notebook.nb.cells) == 1

    def test_insert_markdown_cell(self, notebook):
        cell, idx = notebook.insert_cell(0, 'markdown')
        assert idx == 0
        assert cell.cell_type == 'markdown'
        assert len(notebook.nb.cells) == 1

    def test_delete_code_cell(self, notebook):
        _add_code_cell(notebook, 'x = 1')
        assert len(notebook.nb.cells) == 1
        notebook.delete_cell(0)
        assert len(notebook.nb.cells) == 0

    def test_delete_markdown_cell(self, notebook):
        _add_markdown_cell(notebook, '# Title')
        assert len(notebook.nb.cells) == 1
        notebook.delete_cell(0)
        assert len(notebook.nb.cells) == 0

    def test_delete_out_of_range(self, notebook):
        with pytest.raises(IndexError):
            notebook.delete_cell(0)

    def test_move_cell(self, notebook):
        _add_code_cell(notebook, 'a = 1')
        _add_code_cell(notebook, 'b = 2')
        assert notebook.nb.cells[0].source == 'a = 1'
        assert notebook.nb.cells[1].source == 'b = 2'
        notebook.move_cell(0, 1)
        assert notebook.nb.cells[0].source == 'b = 2'
        assert notebook.nb.cells[1].source == 'a = 1'

    def test_set_cell_source_code(self, notebook):
        _add_code_cell(notebook, 'x = 1')
        notebook.set_cell_source(0, 'x = 2')
        assert notebook.nb.cells[0].source == 'x = 2'

    def test_set_cell_source_markdown(self, notebook):
        _add_markdown_cell(notebook, '# Title')
        notebook.set_cell_source(0, '# New Title')
        assert notebook.nb.cells[0].source == '# New Title'

    def test_set_cell_explanation(self, notebook):
        _add_code_cell(notebook, 'x = 1')
        notebook.set_cell_explanation(0, 'Set x to 1')
        assert notebook.nb.cells[0].metadata['explanation'] == 'Set x to 1'

    def test_lock_unlock(self, notebook):
        assert notebook.get_state()['is_locked'] is False
        notebook.lock(True)
        assert notebook.get_state()['is_locked'] is True
        notebook.lock(False)
        assert notebook.get_state()['is_locked'] is False


# === Execution ===


class TestExecution:

    def test_execute_simple_cell(self, notebook):
        """Execute x = 1; print(x) and verify stdout output."""
        idx = _add_code_cell(notebook, 'x = 1\nprint(x)')
        outputs, status = notebook.execute_cell(idx)
        assert status == 'ok'
        assert len(outputs) > 0
        text = ''.join(
            o.get('text', '') for o in outputs if o.get('output_type') == 'stream'
        )
        assert '1' in text

    def test_execute_multiple_cells(self, notebook):
        """Execute two cells; the second uses the first's variable."""
        _add_code_cell(notebook, 'x = 42')
        _add_code_cell(notebook, 'print(x + 1)')
        notebook.execute_cell(0)
        outputs, status = notebook.execute_cell(1)
        assert status == 'ok'
        text = ''.join(
            o.get('text', '') for o in outputs if o.get('output_type') == 'stream'
        )
        assert '43' in text

    def test_execute_error_cell(self, notebook):
        """Executing a cell with a runtime error raises CellExecutionError."""
        idx = _add_code_cell(notebook, '1/0')
        with pytest.raises(CellExecutionError):
            notebook.execute_cell(idx)

    def test_execute_error_does_not_advance(self, notebook):
        """Executing a cell with error doesn't advance last_executed_cell."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, '1/0')
        notebook.execute_cell(0)
        assert notebook.last_executed_cell == 0
        with pytest.raises(CellExecutionError):
            notebook.execute_cell(1)
        assert notebook.last_executed_cell == 0

    def test_cached_execution(self, notebook):
        """Re-executing an already-executed cell returns Cached."""
        idx = _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(idx)
        outputs, status = notebook.execute_cell(idx)
        assert status == 'Cached'

    def test_out_of_order_execution(self, notebook):
        """Skipping an unexecuted code cell raises ExecutionError."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, 'y = 2')
        _add_code_cell(notebook, 'z = 3')
        notebook.execute_cell(0)
        with pytest.raises(ExecutionError, match="out of order"):
            notebook.execute_cell(2)

    def test_edit_executed_cell_invalidates(self, notebook):
        """Editing an executed cell's source triggers invalidation."""
        idx = _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(idx)
        assert notebook.last_executed_cell == 0
        notebook.set_cell_source(0, 'x = 2')
        # Snapshot kernel: _invalidate_from(0) sets last_executed_cell = min(0, -1) = -1
        assert notebook.last_executed_cell == -1

    def test_insert_code_before_executed_invalidates(self, notebook):
        """Inserting a code cell before executed cells triggers invalidation."""
        _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(0)
        assert notebook.last_executed_cell == 0
        notebook.insert_cell(0, 'code')
        assert notebook.last_executed_cell == -1

    def test_delete_executed_code_cell_invalidates(self, notebook):
        """Deleting an executed code cell triggers invalidation."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, 'y = 2')
        notebook.execute_cell(0)
        notebook.execute_cell(1)
        assert notebook.last_executed_cell == 1
        notebook.delete_cell(0)
        assert notebook.last_executed_cell == -1

    def test_execute_markdown_cell(self, notebook):
        """Executing a markdown cell returns 'Not a code cell'."""
        _add_markdown_cell(notebook, '# Hello')
        _add_code_cell(notebook, 'x = 1')  # makes last_valid_code_cell >= 0
        outputs, status = notebook.execute_cell(0)
        assert outputs is None
        assert status == 'Not a code cell'

    def test_execute_not_valid_cell(self, notebook):
        """Executing a cell beyond last_valid_code_cell raises ExecutionError."""
        notebook.insert_cell(0, 'code')
        with pytest.raises(ExecutionError, match="not valid"):
            notebook.execute_cell(0)


class TestTestExecution:

    def test_execute_test_cell_simple(self, notebook):
        """Execute a test cell that asserts a simple condition."""
        _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(0)
        idx = _add_test_cell(notebook, 'assert 1 == 1')
        outputs = notebook.execute_test_cell(idx)
        assert not any(o.get('output_type') == 'error' for o in outputs)

    def test_execute_test_cell_failure(self, notebook):
        """Execute a test cell that fails its assertion."""
        _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(0)
        idx = _add_test_cell(notebook, 'assert 1 == 2')
        with pytest.raises(CellExecutionError) as excinfo:
            notebook.execute_test_cell(idx)
        assert 'AssertionError' in str(excinfo.value)
        # Check that outputs contains the error
        cell = notebook.nb.cells[idx]
        assert any(o.get('output_type') == 'error' for o in cell.outputs)

    def test_execute_test_cell_state_access(self, notebook):
        """Execute a test cell that accesses state from a named code cell."""
        idx_c = _add_code_cell(notebook, 'x = 42')
        notebook.nb.cells[idx_c].metadata['name'] = 'my_cell'
        notebook.execute_cell(idx_c)

        idx_t = _add_test_cell(notebook, 'assert __state__my_cell.x == 42')
        outputs = notebook.execute_test_cell(idx_t)
        assert not any(o.get('output_type') == 'error' for o in outputs)

    def test_execute_test_cell_multiple_states(self, notebook):
        """Execute a test cell that accesses state from multiple named code cells."""
        idx0 = _add_code_cell(notebook, 'a = 10')
        notebook.nb.cells[idx0].metadata['name'] = 'cell0'
        notebook.execute_cell(idx0)

        idx1 = _add_code_cell(notebook, 'b = 20')
        notebook.nb.cells[idx1].metadata['name'] = 'cell1'
        notebook.execute_cell(idx1)

        idx_t = _add_test_cell(notebook, 'assert __state__cell0.a + __state__cell1.b == 30')
        outputs = notebook.execute_test_cell(idx_t)
        assert not any(o.get('output_type') == 'error' for o in outputs)

    def test_execute_test_cell_invalid_state_access(self, notebook):
        """Assertion fails when accessing state that doesn't exist or is wrong."""
        idx_c = _add_code_cell(notebook, 'x = 42')
        notebook.nb.cells[idx_c].metadata['name'] = 'my_cell'
        notebook.execute_cell(idx_c)

        idx_t = _add_test_cell(notebook, 'assert __state__my_cell.x == 100')
        with pytest.raises(CellExecutionError):
            notebook.execute_test_cell(idx_t)


# === Kernel operations ===


class TestKernelOps:

    def test_reset_kernel(self, notebook):
        idx = _add_code_cell(notebook, 'x = 1')
        notebook.execute_cell(idx)
        assert notebook.last_executed_cell == 0
        notebook.reset_kernel()
        assert notebook.last_executed_cell == -1

    def test_interrupt_kernel(self, notebook):
        """interrupt_kernel should not crash."""
        notebook.interrupt_kernel()


# === Metadata ===


class TestMetadata:

    def test_set_get_input_files(self, notebook):
        files = [{'name': 'data.csv', 'path': '/tmp/data.csv'}]
        missing = [{'name': 'gone.csv', 'path': '/tmp/gone.csv'}]
        notebook.set_input_files(files, missing)
        result = notebook.get_input_files()
        assert result['input_files'] == files
        assert result['missing_input_files'] == missing

    def test_set_validation_visibility(self, notebook):
        _add_code_cell(notebook, 'x = 1')
        notebook.set_validation_visibility(0, True)
        assert notebook.nb.cells[0].metadata['validation']['is_hidden'] is True
        notebook.set_validation_visibility(0, False)
        assert notebook.nb.cells[0].metadata['validation']['is_hidden'] is False


# === Snapshot-kernel-specific tests ===


class TestSnapshotKernelSpecific:

    def test_is_alive(self, notebook):
        """Snapshot kernel subprocess is running after init."""
        assert notebook.is_alive() is True

    def test_kc_compat(self, notebook):
        """kc property returns self for compatibility."""
        assert notebook.kc is not None
        assert notebook.kc is notebook

    def test_km_compat(self, notebook):
        """km property returns self with is_alive() for compatibility."""
        assert notebook.km is not None
        assert notebook.km.is_alive() is True

    def test_selective_invalidation(self, notebook):
        """Editing cell 1's source preserves cell 0's snapshot, clears 1-2."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, 'y = x + 1')
        _add_code_cell(notebook, 'z = y + 1')

        notebook.execute_cell(0)
        notebook.execute_cell(1)
        notebook.execute_cell(2)

        state_0 = notebook._cell_states.get(notebook.nb.cells[0].id)
        assert state_0 is not None
        assert notebook._cell_states.get(notebook.nb.cells[1].id) is not None
        assert notebook._cell_states.get(notebook.nb.cells[2].id) is not None

        # Edit cell 1 -> invalidates cells 1-2, preserves cell 0
        notebook.set_cell_source(1, 'y = x + 10')
        notebook.last_valid_code_cell = max(notebook.last_valid_code_cell, 1)

        # Cell 0's state is preserved
        assert notebook._cell_states.get(notebook.nb.cells[0].id) == state_0
        # Cells 1-2 keep their dict entries (for name reuse), but
        # last_executed_cell == 0 means they are not valid in the kernel
        assert notebook.last_executed_cell == 0

    def test_reexecute_from_snapshot(self, notebook):
        """After invalidation, re-execute cell 1 from cell 0's preserved snapshot."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, 'y = x + 1\nprint(y)')

        notebook.execute_cell(0)
        notebook.execute_cell(1)

        # Edit cell 1, invalidating it but preserving cell 0's state
        notebook.set_cell_source(1, 'y = x + 10\nprint(y)')
        notebook.last_valid_code_cell = max(notebook.last_valid_code_cell, 1)

        # Re-execute from cell 0's snapshot
        outputs, status = notebook.execute_cell(1)
        assert status == 'ok'
        text = ''.join(
            o.get('text', '') for o in outputs if o.get('output_type') == 'stream'
        )
        assert '11' in text

    def test_snapshot_state_stored_after_execution(self, notebook):
        """Each executed code cell stores its state name in _cell_states."""
        _add_code_cell(notebook, 'x = 1')
        assert notebook._cell_states.get(notebook.nb.cells[0].id) is None
        notebook.execute_cell(0)
        assert notebook._cell_states.get(notebook.nb.cells[0].id) is not None

    def test_reset_clears_all_snapshot_states(self, notebook):
        """reset_kernel clears _cell_states dictionary."""
        _add_code_cell(notebook, 'x = 1')
        _add_code_cell(notebook, 'y = 2')
        notebook.execute_cell(0)
        notebook.execute_cell(1)
        assert notebook._cell_states.get(notebook.nb.cells[0].id) is not None

        notebook.reset_kernel()

        assert len(notebook._cell_states) == 0
        assert notebook.last_executed_cell == -1


# === Unit test validity propagation ===


def _all_valid():
    """Return a validity dict with all flags True."""
    return {
        'setup_code_valid': True,
        'setup_output_valid': True,
        'target_output_valid': True,
        'test_code_valid': True,
        'test_output_valid': True,
    }


def _attach_unit_test(notebook, cell_index, test_name='test1'):
    """Attach a unit test with all-valid flags to a cell."""
    cell = notebook.nb.cells[cell_index]
    if 'unit_tests' not in cell.metadata:
        cell.metadata['unit_tests'] = {}
    cell.metadata['unit_tests'][test_name] = {
        'validity': _all_valid(),
        'cells': {
            'setup': {'cell_type': 'code', 'source': '', 'metadata': {}},
            'test': {'cell_type': 'code', 'source': '', 'metadata': {}},
        },
    }


def _is_all_valid(notebook, cell_index, test_name='test1'):
    """Check if all validity flags are True for a unit test."""
    v = notebook.nb.cells[cell_index].metadata['unit_tests'][test_name]['validity']
    return all(v.values())


def _is_invalid_from(notebook, cell_index, from_point, test_name='test1'):
    """Check that flags from from_point onward are False, earlier ones are True."""
    cascade = ['setup_code', 'setup_output', 'target_output', 'test_code', 'test_output']
    v = notebook.nb.cells[cell_index].metadata['unit_tests'][test_name]['validity']
    start = cascade.index(from_point)
    for i, point in enumerate(cascade):
        if i < start:
            if not v[point + '_valid']:
                return False
        else:
            if v[point + '_valid']:
                return False
    return True


class TestUnitTestInvalidationPropagation:
    """Tests that upstream changes properly invalidate downstream unit tests."""

    def test_set_explanation_upstream_invalidates_downstream_ut(self, notebook):
        """Changing cell A's explanation invalidates unit tests on cell C."""
        _add_code_cell(notebook, 'x = 1')  # cell 0 (A)
        _add_code_cell(notebook, 'y = x + 1')  # cell 1 (B)
        _add_code_cell(notebook, 'z = y + 1')  # cell 2 (C)
        _attach_unit_test(notebook, 2)
        assert _is_all_valid(notebook, 2)

        notebook.set_cell_explanation(0, 'Set x to 10')

        assert _is_invalid_from(notebook, 2, 'setup_code')

    def test_set_explanation_own_cell_invalidates_own_ut(self, notebook):
        """Changing cell C's own explanation invalidates its unit tests."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        _attach_unit_test(notebook, 1)
        assert _is_all_valid(notebook, 1)

        notebook.set_cell_explanation(1, 'Changed explanation')

        assert _is_invalid_from(notebook, 1, 'setup_code')

    def test_set_explanation_does_not_invalidate_upstream_ut(self, notebook):
        """Changing cell B's explanation does NOT invalidate unit tests on cell A."""
        _add_code_cell(notebook, 'x = 1')  # cell 0 (A)
        _add_code_cell(notebook, 'y = x + 1')  # cell 1 (B)
        _attach_unit_test(notebook, 0)
        assert _is_all_valid(notebook, 0)

        notebook.set_cell_explanation(1, 'Changed explanation')

        assert _is_all_valid(notebook, 0)

    def test_set_source_invalidates_via_invalidate_from(self, notebook):
        """Editing cell B's code invalidates unit tests on cell C from setup_code."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        _add_code_cell(notebook, 'z = y + 1')  # cell 2
        notebook.execute_cell(0)
        notebook.execute_cell(1)
        notebook.execute_cell(2)
        _attach_unit_test(notebook, 2)
        assert _is_all_valid(notebook, 2)

        notebook.set_cell_source(1, 'y = x + 10')

        # _invalidate_from(1) should invalidate from setup_code
        assert _is_invalid_from(notebook, 2, 'setup_code')

    def test_invalidate_from_uses_setup_code_not_setup_output(self, notebook):
        """_invalidate_from invalidates from setup_code, not setup_output."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        notebook.execute_cell(0)
        notebook.execute_cell(1)
        _attach_unit_test(notebook, 1)
        assert _is_all_valid(notebook, 1)

        notebook.set_cell_source(0, 'x = 10')

        assert _is_invalid_from(notebook, 1, 'setup_code')

    def test_set_explanation_invalidates_multiple_downstream(self, notebook):
        """Changing cell A's explanation invalidates unit tests on both B and C."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        _add_code_cell(notebook, 'z = y + 1')  # cell 2
        _attach_unit_test(notebook, 1)
        _attach_unit_test(notebook, 2)
        assert _is_all_valid(notebook, 1)
        assert _is_all_valid(notebook, 2)

        notebook.set_cell_explanation(0, 'Changed explanation')

        assert _is_invalid_from(notebook, 1, 'setup_code')
        assert _is_invalid_from(notebook, 2, 'setup_code')

    def test_generate_code_invalidates_downstream_ut_without_execution(self, notebook):
        """generate_code_cell invalidates downstream unit tests even if cell was never executed.

        We can't call generate_code_cell directly (needs AI), so we verify the
        invalidation logic by calling the internal path: set code + invalidate downstream.
        Instead, we test the set_cell_source path which also goes through _invalidate_from
        when the cell was executed."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        _add_code_cell(notebook, 'z = y + 1')  # cell 2
        # Execute all cells
        notebook.execute_cell(0)
        notebook.execute_cell(1)
        notebook.execute_cell(2)
        _attach_unit_test(notebook, 2)
        assert _is_all_valid(notebook, 2)

        # Edit cell 0 source triggers _invalidate_from(0) which should
        # invalidate cell 2's unit tests from setup_code
        notebook.set_cell_source(0, 'x = 10')

        assert _is_invalid_from(notebook, 2, 'setup_code')

    def test_double_invalidation_is_idempotent(self, notebook):
        """Invalidating already-invalid tests is a no-op (idempotent)."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _add_code_cell(notebook, 'y = x + 1')  # cell 1
        _attach_unit_test(notebook, 1)

        notebook.set_cell_explanation(0, 'First change')
        assert _is_invalid_from(notebook, 1, 'setup_code')

        # Second invalidation should not crash or change anything
        notebook.set_cell_explanation(0, 'Second change')
        assert _is_invalid_from(notebook, 1, 'setup_code')

    def test_set_explanation_test_cell_does_not_invalidate_code_cell_ut(self, notebook):
        """Changing a test cell's explanation does not invalidate code cell unit tests."""
        _add_code_cell(notebook, 'x = 1')  # cell 0
        _attach_unit_test(notebook, 0)
        _add_test_cell(notebook, 'assert True')  # cell 1
        assert _is_all_valid(notebook, 0)

        notebook.set_cell_explanation(1, 'Changed test explanation')

        # Unit tests on cell 0 should be unaffected
        assert _is_all_valid(notebook, 0)


class TestUnitTestSubCellExplanation:
    """Tests that changing a unit test sub-cell explanation invalidates
    validity flags and kernel states."""

    def test_setup_explanation_change_invalidates_all_from_setup_code(self, notebook):
        """Changing setup cell explanation invalidates all validity flags from setup_code."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        assert _is_all_valid(notebook, idx)

        notebook.save_unit_test_explanation(idx, 'test1', 'setup', 'New setup explanation')

        assert _is_invalid_from(notebook, idx, 'setup_code')

    def test_setup_explanation_change_deletes_kernel_states(self, notebook):
        """Changing setup explanation deletes kernel states for setup, target, and test."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        # Simulate kernel states being stored
        cell_id = notebook.nb.cells[idx].id
        notebook._unit_test_states[f"{cell_id}:test1:setup"] = "state_setup"
        notebook._unit_test_states[f"{cell_id}:test1:target"] = "state_target"
        notebook._unit_test_states[f"{cell_id}:test1:test"] = "state_test"

        notebook.save_unit_test_explanation(idx, 'test1', 'setup', 'New setup explanation')

        # All three kernel states should be deleted
        assert f"{cell_id}:test1:setup" not in notebook._unit_test_states
        assert f"{cell_id}:test1:target" not in notebook._unit_test_states
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states

    def test_test_explanation_change_invalidates_from_test_code(self, notebook):
        """Changing test cell explanation invalidates from test_code only."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        assert _is_all_valid(notebook, idx)

        notebook.save_unit_test_explanation(idx, 'test1', 'test', 'New test explanation')

        assert _is_invalid_from(notebook, idx, 'test_code')

    def test_test_explanation_change_preserves_setup_and_target_states(self, notebook):
        """Changing test explanation preserves setup and target kernel states."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        cell_id = notebook.nb.cells[idx].id
        notebook._unit_test_states[f"{cell_id}:test1:setup"] = "state_setup"
        notebook._unit_test_states[f"{cell_id}:test1:target"] = "state_target"
        notebook._unit_test_states[f"{cell_id}:test1:test"] = "state_test"

        notebook.save_unit_test_explanation(idx, 'test1', 'test', 'New test explanation')

        # Setup and target states should be preserved
        assert f"{cell_id}:test1:setup" in notebook._unit_test_states
        assert f"{cell_id}:test1:target" in notebook._unit_test_states
        # Test state should be deleted
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states


class TestUnitTestCodeRegenAndClear:
    """Tests that regenerating or clearing unit test sub-cell code
    properly invalidates validity flags and kernel states."""

    def _setup_with_kernel_states(self, notebook):
        """Helper: create a code cell with a unit test and fake kernel states."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        cell_id = notebook.nb.cells[idx].id
        notebook._unit_test_states[f"{cell_id}:test1:setup"] = "state_setup"
        notebook._unit_test_states[f"{cell_id}:test1:target"] = "state_target"
        notebook._unit_test_states[f"{cell_id}:test1:test"] = "state_test"
        return idx, cell_id

    # --- save_unit_test_code (user edits code directly) ---

    def test_save_setup_code_invalidates_from_setup_output(self, notebook):
        """Saving setup code invalidates from setup_output (code itself stays valid)."""
        idx, _ = self._setup_with_kernel_states(notebook)
        notebook.save_unit_test_code(idx, 'test1', 'setup', 'new_var = 1')
        assert _is_invalid_from(notebook, idx, 'setup_output')

    def test_save_setup_code_deletes_all_kernel_states(self, notebook):
        """Saving setup code deletes kernel states for setup, target, and test."""
        idx, cell_id = self._setup_with_kernel_states(notebook)
        notebook.save_unit_test_code(idx, 'test1', 'setup', 'new_var = 1')
        assert f"{cell_id}:test1:setup" not in notebook._unit_test_states
        assert f"{cell_id}:test1:target" not in notebook._unit_test_states
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states

    def test_save_test_code_invalidates_from_test_output(self, notebook):
        """Saving test code invalidates from test_output only."""
        idx, _ = self._setup_with_kernel_states(notebook)
        notebook.save_unit_test_code(idx, 'test1', 'test', 'assert True')
        assert _is_invalid_from(notebook, idx, 'test_output')

    def test_save_test_code_preserves_setup_and_target_states(self, notebook):
        """Saving test code only deletes test kernel state, not setup or target."""
        idx, cell_id = self._setup_with_kernel_states(notebook)
        notebook.save_unit_test_code(idx, 'test1', 'test', 'assert True')
        assert f"{cell_id}:test1:setup" in notebook._unit_test_states
        assert f"{cell_id}:test1:target" in notebook._unit_test_states
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states

    # --- clear_unit_test_code ---

    def test_clear_setup_code_invalidates_from_setup_code(self, notebook):
        """Clearing setup code invalidates from setup_code."""
        idx, _ = self._setup_with_kernel_states(notebook)
        notebook.clear_unit_test_code(idx, 'test1', 'setup')
        assert _is_invalid_from(notebook, idx, 'setup_code')

    def test_clear_setup_code_deletes_all_kernel_states(self, notebook):
        """Clearing setup code deletes all kernel states."""
        idx, cell_id = self._setup_with_kernel_states(notebook)
        notebook.clear_unit_test_code(idx, 'test1', 'setup')
        assert f"{cell_id}:test1:setup" not in notebook._unit_test_states
        assert f"{cell_id}:test1:target" not in notebook._unit_test_states
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states

    def test_clear_test_code_invalidates_from_test_code(self, notebook):
        """Clearing test code invalidates from test_code."""
        idx, _ = self._setup_with_kernel_states(notebook)
        notebook.clear_unit_test_code(idx, 'test1', 'test')
        assert _is_invalid_from(notebook, idx, 'test_code')

    def test_clear_test_code_preserves_setup_and_target_states(self, notebook):
        """Clearing test code only deletes test kernel state."""
        idx, cell_id = self._setup_with_kernel_states(notebook)
        notebook.clear_unit_test_code(idx, 'test1', 'test')
        assert f"{cell_id}:test1:setup" in notebook._unit_test_states
        assert f"{cell_id}:test1:target" in notebook._unit_test_states
        assert f"{cell_id}:test1:test" not in notebook._unit_test_states


class TestUnitTestValidationVisibility:
    """Tests for set_unit_test_validation_visibility."""

    def test_set_visibility_setup(self, notebook):
        """Setting validation visibility on setup sub-cell stores correctly."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        cell = notebook.nb.cells[idx]
        cell.metadata['unit_tests']['test1']['cells']['setup']['metadata']['validation'] = {
            'is_valid': True, 'message': 'ok', 'is_hidden': False
        }
        notebook.set_unit_test_validation_visibility(idx, 'test1', 'setup', True)
        v = cell.metadata['unit_tests']['test1']['cells']['setup']['metadata']['validation']
        assert v['is_hidden'] is True

    def test_set_visibility_test(self, notebook):
        """Setting validation visibility on test sub-cell stores correctly."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        cell = notebook.nb.cells[idx]
        cell.metadata['unit_tests']['test1']['cells']['test']['metadata']['validation'] = {
            'is_valid': False, 'message': 'bad', 'is_hidden': False
        }
        notebook.set_unit_test_validation_visibility(idx, 'test1', 'test', True)
        v = cell.metadata['unit_tests']['test1']['cells']['test']['metadata']['validation']
        assert v['is_hidden'] is True

    def test_set_visibility_creates_validation_dict_if_missing(self, notebook):
        """If no validation dict exists, it is created with just is_hidden."""
        idx = _add_code_cell(notebook, 'x = 1')
        _attach_unit_test(notebook, idx)
        notebook.set_unit_test_validation_visibility(idx, 'test1', 'setup', True)
        v = notebook.nb.cells[idx].metadata['unit_tests']['test1']['cells']['setup']['metadata']['validation']
        assert v['is_hidden'] is True


# === Execution-skip (rebuild successor state without re-executing) ===

def _set_generated_code(nb, index, source):
    """Simulate a generated cell: set the source plus a matching description hash,
    so the execution-skip's `output_hash == code_description_hash` precondition holds."""
    nb.set_cell_source(index, source)
    h = hashlib.sha256(source.encode()).hexdigest()
    nb.nb.cells[index].metadata['description_hash'] = h
    nb.nb.cells[index].metadata['code_description_hash'] = h


def _add_generated_cell(nb, source):
    """Insert a code cell and give it a matching code/description hash."""
    idx = _add_code_cell(nb, source)
    _set_generated_code(nb, idx, source)
    return idx


class TestExecutionSkip:

    def _spy_rebuilds(self, notebook):
        counts = {"rebuild": 0}
        orig = notebook._sk_request

        def spy(method, path, json_body=None):
            if path == "/rebuild_state":
                counts["rebuild"] += 1
            return orig(method, path, json_body)

        notebook._sk_request = spy
        return counts

    def _probe(self, notebook, index, code):
        state = notebook._cell_states[notebook.nb.cells[index].id]
        r = notebook._sk_request("POST", "/execute", {
            "code": code, "exec_id": "probe", "state_name": state})
        return "".join(o["text"] for o in r.get("output", [])
                       if o.get("output_type") == "stream").strip()

    def test_independent_downstream_cell_is_rebuilt(self, notebook):
        """After an upstream value changes, a downstream cell that does not read
        the changed variable is rebuilt (not executed), and stays correct."""
        _add_generated_cell(notebook, "x = 1\nw = 1")
        _add_generated_cell(notebook, "y = x + 1")         # reads x only
        _add_generated_cell(notebook, "z = w + 1")         # reads w only
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        counts = self._spy_rebuilds(notebook)
        # Upstream edit: w changes 1 -> 100 (x unchanged).
        _set_generated_code(notebook, 0, "x = 1\nw = 100")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        # Cell 1 (reads only x) must be rebuilt; the chain stays correct.
        assert counts["rebuild"] >= 1
        assert self._probe(notebook, 1, "print(y, w)") == "2 100"
        assert self._probe(notebook, 2, "print(z)") == "101"

    def test_changed_read_forces_execution(self, notebook):
        """A cell whose read variable actually changed is not skipped."""
        _add_generated_cell(notebook, "a = 1")
        _add_generated_cell(notebook, "b = a + 1")         # reads a
        notebook.last_valid_code_cell = 1
        for i in range(2):
            notebook.execute_cell(i)

        counts = self._spy_rebuilds(notebook)
        _set_generated_code(notebook, 0, "a = 50")         # a changes
        notebook.last_valid_code_cell = 1
        for i in range(2):
            notebook.execute_cell(i)

        assert counts["rebuild"] == 0                       # cell 1 re-executed
        assert self._probe(notebook, 1, "print(b)") == "51"

    def test_output_preserved_across_skip(self, notebook):
        """A skipped cell keeps its previously produced output."""
        _add_generated_cell(notebook, "a = 1\nw = 1")
        _add_generated_cell(notebook, "print('KEEP', a)")      # reads a only
        _add_generated_cell(notebook, "z = w + 1")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        counts = self._spy_rebuilds(notebook)
        _set_generated_code(notebook, 0, "a = 1\nw = 100")     # w changes, a unchanged
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        assert counts["rebuild"] >= 1
        text = "".join(o.get("text", "") for o in notebook.nb.cells[1].outputs
                       if o.get("output_type") == "stream").strip()
        assert text == "KEEP 1"

    def test_force_disables_skip(self, notebook):
        """execute_cell(force=True) always really runs the cell.

        This is what a "Force Run" needs: cells whose inputs the skip cannot see
        (the clock, random numbers, external files) must be re-executed even
        though nothing tracked about them changed."""
        _add_generated_cell(notebook, "x = 1\nw = 1")
        _add_generated_cell(notebook, "y = x + 1")
        _add_generated_cell(notebook, "z = w + 1")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        counts = self._spy_rebuilds(notebook)
        _set_generated_code(notebook, 0, "x = 1\nw = 100")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i, force=True)

        assert counts["rebuild"] == 0                       # nothing skipped
        assert self._probe(notebook, 2, "print(z)") == "101"

    def test_force_run_invalidates_later_cells(self, notebook):
        """Re-running a cell makes everything after it stale.

        The states of the following cells were computed from this cell's
        previous value, so they cannot keep reading as up to date -- otherwise a
        Force Run on cell 0 would leave cells 1 and 2 claiming valid output
        derived from a value that no longer exists."""
        _add_generated_cell(notebook, "import itertools; c = itertools.count()")
        _add_generated_cell(notebook, "y = next(c)")
        _add_generated_cell(notebook, "z = y")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)
        assert notebook.last_executed_cell == 2
        assert notebook.last_valid_output_cell == 2

        # Force-run the first cell only; the rest must drop back to stale.
        notebook.execute_cell(0, force=True)

        assert notebook.last_executed_cell == 0
        assert notebook.last_valid_output_cell == 0
        assert notebook.last_valid_test_cell <= 0

    def test_forward_execution_does_not_invalidate(self, notebook):
        """Running cells forward in order must not trip the re-execution
        invalidation: each cell is new, not a re-run."""
        _add_generated_cell(notebook, "x = 1")
        _add_generated_cell(notebook, "y = x + 1")
        _add_generated_cell(notebook, "z = y + 1")
        notebook.last_valid_code_cell = 2
        for i in range(3):
            notebook.execute_cell(i)

        assert notebook.last_executed_cell == 2
        assert notebook.last_valid_output_cell == 2
        assert self._probe(notebook, 2, "print(z)") == "3"

    def test_manual_code_edit_forces_execution(self, notebook):
        """A hand-edited cell is really re-executed, not skipped. The edit changes
        the code but not the description, so a skip keyed on the description hash
        would wrongly preserve the pre-edit output."""
        idx = _add_generated_cell(notebook, "v = 1\nprint('OLD', v)")
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)

        counts = self._spy_rebuilds(notebook)
        notebook.set_cell_source(idx, "v = 2\nprint('NEW', v)")   # manual edit only
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)

        assert counts["rebuild"] == 0                             # really executed
        text = "".join(o.get("text", "") for o in notebook.nb.cells[idx].outputs
                       if o.get("output_type") == "stream").strip()
        assert text == "NEW 2"
        assert self._probe(notebook, idx, "print(v)") == "2"

    def test_manual_edit_keeps_stale_output(self, notebook):
        """A hand-edited cell keeps the output of the pre-edit code, marked stale."""
        idx = _add_generated_cell(notebook, "print('BEFORE')")
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)

        notebook.set_cell_source(idx, "print('AFTER')")

        text = "".join(o.get("text", "") for o in notebook.nb.cells[idx].outputs
                       if o.get("output_type") == "stream").strip()
        assert text == "BEFORE"                                   # output preserved
        assert notebook.last_valid_output_cell < idx              # but stale

    # --- output_hash names the code that produced the stored output ---

    def _gen_stub(self, code):
        """AI stub that regenerates a cell to `code`."""
        calls = {"n": 0}
        def fake_generate(api_key, **kwargs):
            calls["n"] += 1
            return code, None
        _pbmod.AI_PROVIDERS["skipstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["skipstub"]["generate"] = fake_generate
        _pbmod.AI_PROVIDERS["skipstub"]["amend_explanation"] = lambda *a, **kw: None
        return calls

    def _stream_text(self, notebook, idx):
        return "".join(o.get("text", "") for o in notebook.nb.cells[idx].outputs
                       if o.get("output_type") == "stream").strip()

    def test_error_run_records_the_executed_code(self, notebook):
        """A failed run records the code that produced the error, not the code of
        the last successful run. Otherwise restoring that earlier code makes the
        skip's precondition hold against an output it never produced."""
        good, bad = "v = 1\nprint('OK', v)", "v = 1\nprint('OK', nope)"
        idx = _add_generated_cell(notebook, good)
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)
        assert notebook._live(notebook.nb.cells[idx]).output_hash == notebook._hash_text(good)

        notebook.set_cell_source(idx, bad)
        notebook.last_valid_code_cell = idx
        with pytest.raises(CellExecutionError):
            notebook.execute_cell(idx)

        assert notebook._live(notebook.nb.cells[idx]).output_hash == notebook._hash_text(bad)

    def test_skip_declines_after_error_then_fix(self, notebook):
        """The "Fix Code" sequence: break a working cell by hand, run it (error),
        regenerate back to the original source. The next run must really execute
        rather than hand back the output the regeneration discarded."""
        good = "v = 1\nprint('OK', v)"
        self._gen_stub(good)
        idx = _add_generated_cell(notebook, good)
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)

        notebook.set_cell_source(idx, "v = 1\nprint('OK', nope)")
        notebook.last_valid_code_cell = idx
        with pytest.raises(CellExecutionError):
            notebook.execute_cell(idx)

        notebook.generate_code_cell("key", idx, ai_provider="skipstub")
        assert notebook.nb.cells[idx].source == good      # restored, byte-identical
        assert notebook.last_valid_output_cell < idx      # and marked stale

        counts = self._spy_rebuilds(notebook)
        notebook.execute_cell(idx)

        assert counts["rebuild"] == 0                     # really executed
        assert self._stream_text(notebook, idx) == "OK 1"
        assert notebook.last_valid_output_cell == idx

    def test_skip_declines_after_outputs_discarded(self, notebook):
        """Regenerating to byte-identical code still discards the output, so the
        skip must not hand the now-empty output back as though it were current.
        Recording the executed code on error runs does not cover this case."""
        good = "print('HELLO')"
        self._gen_stub(good)
        idx = _add_generated_cell(notebook, good)
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(idx)                        # succeeds, output stored
        # Unpin the code from its description so generation calls the AI.
        notebook.nb.cells[idx].metadata.pop('code_description_hash', None)

        notebook.generate_code_cell("key", idx, ai_provider="skipstub")
        assert notebook.nb.cells[idx].source == good      # identical code
        assert notebook.nb.cells[idx].outputs == []       # output discarded

        counts = self._spy_rebuilds(notebook)
        notebook.execute_cell(idx)

        assert counts["rebuild"] == 0                     # really executed
        assert self._stream_text(notebook, idx) == "HELLO"

    def test_errored_cell_reruns_with_unchanged_code(self, notebook):
        """A cell that failed re-runs even though nothing about it changed: what
        fixed it may be outside the notebook (a pip install, a repaired file).
        Here the missing name is supplied by an earlier cell instead."""
        _add_generated_cell(notebook, "a = 1")
        idx = _add_generated_cell(notebook, "print('GOT', later_var)")
        notebook.last_valid_code_cell = idx
        notebook.execute_cell(0)
        with pytest.raises(CellExecutionError):
            notebook.execute_cell(idx)

        # Supply the missing name out of band, leaving the failed cell untouched.
        notebook._sk_request("POST", "/execute", {
            "code": "later_var = 7", "exec_id": "fixup",
            "state_name": notebook._cell_states[notebook.nb.cells[0].id],
            "new_state_name": notebook._cell_states[notebook.nb.cells[0].id]})

        counts = self._spy_rebuilds(notebook)
        notebook.execute_cell(idx)                        # same code, must re-run

        assert counts["rebuild"] == 0
        assert self._stream_text(notebook, idx) == "GOT 7"

    def test_restart_clears_all_kernel_states_and_forces_execution(self, notebook):
        """reset_kernel clears every kernel snapshot; the next run re-executes."""
        _add_generated_cell(notebook, "a = 1")
        _add_generated_cell(notebook, "b = a + 1")
        notebook.last_valid_code_cell = 1
        for i in range(2):
            notebook.execute_cell(i)

        # Kernel holds per-cell snapshots before restart.
        states = notebook._sk_request("GET", "/states")["states"]
        assert len(states) > 1                              # more than just 'initial'

        notebook.reset_kernel()

        # All snapshots gone; only 'initial' remains; bookkeeping cleared.
        states = notebook._sk_request("GET", "/states")["states"]
        assert states == ["initial"]
        assert notebook._live_states == set()
        assert notebook._cell_states == {}
        assert notebook.last_executed_cell == -1

        # The next run re-executes (no rebuild) and is correct.
        counts = self._spy_rebuilds(notebook)
        notebook.last_valid_code_cell = 1
        for i in range(2):
            notebook.execute_cell(i)
        assert counts["rebuild"] == 0
        assert self._probe(notebook, 1, "print(b)") == "2"

    def test_no_skip_after_reload(self, tmp_notebook_path):
        """After reopening (fresh kernel), nothing is skipped; the chain rebuilds
        by real execution."""
        nb = Plainbook(tmp_notebook_path)
        try:
            _add_generated_cell(nb, "a = 1")
            _add_generated_cell(nb, "b = a + 1")
            nb.last_valid_code_cell = 1
            for i in range(2):
                nb.execute_cell(i)
        finally:
            nb._shutdown()

        nb2 = Plainbook(tmp_notebook_path)
        counts = self._spy_rebuilds(nb2)
        try:
            nb2.last_valid_code_cell = 1
            for i in range(2):
                nb2.execute_cell(i)
            assert counts["rebuild"] == 0
        finally:
            nb2._shutdown()


# === Targeted code invalidation on input-file delete/replace ===

def _file_entries(*paths):
    return [{'name': p.rsplit('/', 1)[-1], 'path': p, 'type': 'file'}
            for p in paths]


class TestInputFileInvalidation:

    def test_delete_invalidates_only_citing_cells(self, notebook):
        """Deleting a file invalidates only the code cells whose source cites it
        (clearing their code_description_hash and lowering the watermark to just
        before the earliest citing cell); unrelated earlier cells are untouched."""
        _add_generated_cell(notebook, "setup = 1")                  # 0: no cite
        _add_generated_cell(notebook, "a = open('/p/data.csv')")    # 1: cites
        _add_generated_cell(notebook, "b = 2")                      # 2: no cite
        _add_generated_cell(notebook, "c = open('/p/data.csv')")    # 3: cites
        notebook.last_valid_code_cell = 3
        notebook.last_valid_output_cell = 3
        notebook.set_input_files(_file_entries('/p/data.csv'))      # register (add: no-op)
        assert notebook.last_valid_code_cell == 3

        notebook.set_input_files([])                                # delete the file

        assert notebook.last_valid_code_cell == 0                   # first citer is index 1
        assert notebook.last_valid_output_cell == 0
        # Citing cells: code_description_hash cleared -> regeneration forced.
        assert 'code_description_hash' not in notebook.nb.cells[1].metadata
        assert 'code_description_hash' not in notebook.nb.cells[3].metadata
        assert notebook._code_matches_description(notebook.nb.cells[1]) is False
        # Non-citing cells keep their code_description_hash (and description-match).
        assert 'code_description_hash' in notebook.nb.cells[0].metadata
        assert 'code_description_hash' in notebook.nb.cells[2].metadata
        assert notebook._code_matches_description(notebook.nb.cells[0]) is True

    def test_pure_add_is_noop(self, notebook):
        """Adding a new file does not invalidate any cell."""
        _add_generated_cell(notebook, "a = 1")
        notebook.last_valid_code_cell = 0
        h = notebook.nb.cells[0].metadata['code_description_hash']
        notebook.set_input_files(_file_entries('/p/new.csv'))
        assert notebook.last_valid_code_cell == 0
        assert notebook.nb.cells[0].metadata['code_description_hash'] == h

    def test_remove_unreferenced_is_noop(self, notebook):
        """Removing a file that no cell cites invalidates nothing."""
        _add_generated_cell(notebook, "a = 1")
        notebook.last_valid_code_cell = 0
        notebook.set_input_files(_file_entries('/p/x.csv'))
        h = notebook.nb.cells[0].metadata['code_description_hash']
        notebook.set_input_files([])
        assert notebook.last_valid_code_cell == 0
        assert notebook.nb.cells[0].metadata['code_description_hash'] == h

    def test_replace_with_different_path_invalidates_old_citers(self, notebook):
        """Replacing a file with a different-path file invalidates cells citing
        the old path, but not unrelated cells."""
        _add_generated_cell(notebook, "a = open('/p/old.csv')")     # 0: cites old
        _add_generated_cell(notebook, "b = 2")                      # 1: no cite
        notebook.last_valid_code_cell = 1
        notebook.set_input_files(_file_entries('/p/old.csv'))
        notebook.set_input_files(_file_entries('/p/new.csv'))       # replace old -> new
        assert notebook.last_valid_code_cell == -1                  # cell 0 cites old
        assert 'code_description_hash' not in notebook.nb.cells[0].metadata
        assert 'code_description_hash' in notebook.nb.cells[1].metadata


# === Session-only skip metadata is not serialized ===

import nbformat as _nbf

_EPHEMERAL = ('output_hash', 'input_group_fingerprints', 'accessed_symbols',
              'accessed_symbol_hashes', 'modified_symbols', 'deleted_symbols')


class TestLiveCellMetaNotSerialized:

    def test_skip_baselines_are_not_written_to_file(self, notebook):
        """After executing, the saved .plnb contains persisted hashes
        (code_hash/code_description_hash/description_hash) but none of the
        session-only skip keys."""
        _add_generated_cell(notebook, "a = 1")
        _add_generated_cell(notebook, "b = a + 1")
        notebook.last_valid_code_cell = 1
        for i in range(2):
            notebook.execute_cell(i)
        # In memory, the baselines live off cell.metadata.
        assert notebook._live(notebook.nb.cells[1]).modified_symbols is not None
        for cell in notebook.nb.cells:
            for k in _EPHEMERAL:
                assert k not in cell.metadata

        # On disk: ephemeral keys absent, persisted content hashes present.
        saved = _nbf.read(notebook.path, as_version=4)
        for cell in saved.cells:
            for k in _EPHEMERAL:
                assert k not in cell.metadata
            assert 'code_hash' in cell.metadata
            assert 'code_description_hash' in cell.metadata
            assert 'description_hash' in cell.metadata

    def test_load_strips_stale_ephemeral_keys(self, tmp_notebook_path):
        """Opening a notebook whose cells carry stale skip keys (from an older
        version) drops them from cell.metadata."""
        nb = _nbf.v4.new_notebook()
        cell = _nbf.v4.new_code_cell("x = 1")
        cell.metadata['output_hash'] = 'stale'
        cell.metadata['input_group_fingerprints'] = ['stale']
        cell.metadata['accessed_symbols'] = ['x']
        nb.cells = [cell]
        with open(tmp_notebook_path, 'w') as f:
            _nbf.write(nb, f)

        pb = Plainbook(tmp_notebook_path)
        try:
            md = pb.nb.cells[0].metadata
            for k in _EPHEMERAL:
                assert k not in md
        finally:
            pb._shutdown()


# === Unit-test code regeneration is skipped when the context is unchanged ===

import plainbook.plainbook as _pbmod


class TestUnitTestCodeSkip:

    def _stub(self):
        calls = {"n": 0}
        def fake_generate_unit_test(api_key, **kwargs):
            calls["n"] += 1
            return "assert True  # generated"
        _pbmod.AI_PROVIDERS["utstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["utstub"]["generate_unit_test"] = fake_generate_unit_test
        return calls

    def _setup_meta(self, notebook, cell_index=0, test_name='test1'):
        return (notebook.nb.cells[cell_index]
                .metadata['unit_tests'][test_name]['cells']['setup']['metadata'])

    def _validity(self, notebook, cell_index=0, test_name='test1'):
        return notebook.nb.cells[cell_index].metadata['unit_tests'][test_name]['validity']

    def _prepare(self, notebook, source="x = process(data)"):
        idx = _add_code_cell(notebook, source)
        notebook.last_valid_code_cell = idx
        cell = notebook.nb.cells[idx]
        # Build sub-cells as nbformat nodes (attribute access), like the real ones.
        def sub(expl=''):
            return _nbf.from_dict({'cell_type': 'code', 'source': '', 'outputs': [],
                                   'metadata': {'explanation': expl}})
        cell.metadata['unit_tests'] = {'test1': {
            'validity': _all_valid(),
            'cells': {'setup': sub('set up the input data'), 'test': sub()},
        }}
        return idx

    def test_first_generation_calls_ai_and_stores_hash(self, notebook):
        calls = self._stub()
        self._prepare(notebook)
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        assert calls["n"] == 1
        assert self._setup_meta(notebook).get('generation_context_hash')

    def test_unchanged_context_skips_ai(self, notebook):
        """Simulating a reload/flag-flip (code_valid -> False) does not call the AI
        when nothing that determines the code has changed."""
        calls = self._stub()
        self._prepare(notebook)
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        src = notebook.nb.cells[0].metadata['unit_tests']['test1']['cells']['setup']['source']

        self._validity(notebook)['setup_code_valid'] = False        # cascade / clobber
        before = calls["n"]
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        assert calls["n"] == before                                  # AI NOT called
        assert notebook.nb.cells[0].metadata['unit_tests']['test1']['cells']['setup']['source'] == src
        assert self._validity(notebook)['setup_code_valid'] is True

    def test_target_change_forces_regeneration(self, notebook):
        calls = self._stub()
        self._prepare(notebook)
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        self._validity(notebook)['setup_code_valid'] = False
        notebook.set_cell_source(0, "x = process(data) + 1")         # target source changes
        notebook.last_valid_code_cell = 0
        before = calls["n"]
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        assert calls["n"] == before + 1                              # AI called

    def test_explanation_change_forces_regeneration(self, notebook):
        calls = self._stub()
        self._prepare(notebook)
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        self._validity(notebook)['setup_code_valid'] = False
        self._setup_meta(notebook)['explanation'] = "set up DIFFERENT input data"
        before = calls["n"]
        notebook.generate_unit_test_cell("k", 0, "test1", "setup", ai_provider="utstub")
        assert calls["n"] == before + 1                              # AI called


class TestExplainCode:
    """Backend for the AI "Explain code" feature (no kernel needed; AI stubbed)."""

    def _stub(self, text="AN EXPLANATION"):
        calls = {"n": 0, "kwargs": None}
        def fake_explain(api_key, previous_code, code_to_explain, instructions, **kwargs):
            calls["n"] += 1
            calls["kwargs"] = kwargs
            return text
        _pbmod.AI_PROVIDERS["explstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["explstub"]["explain"] = fake_explain
        return calls

    def test_all_providers_expose_explain(self):
        assert "explain" in _pbmod.AI_PROVIDERS["gemini"]
        assert "explain" in _pbmod.AI_PROVIDERS["claude"]
        assert "explain" in _pbmod.AI_PROVIDERS["openai"]
        assert "explain" in _pbmod.AI_PROVIDERS["local"]

    def test_all_providers_expose_the_same_operations(self):
        expected = set(_pbmod.AI_PROVIDERS["claude"])
        for major, fns in _pbmod.AI_PROVIDERS.items():
            assert set(fns) == expected, major

    def test_explain_stores_ai_explanation(self, notebook):
        calls = self._stub()
        idx = _add_code_cell(notebook, "a = 1")
        explanation, ret_idx = notebook.explain_code_cell(
            "key", idx, level=3, use_bullets=True, use_latex=False, ai_provider="explstub")
        assert calls["n"] == 1
        assert explanation == "AN EXPLANATION"
        assert ret_idx == idx
        cell = notebook.nb.cells[idx]
        assert cell.metadata["ai_code_explanation"] == "AN EXPLANATION"
        assert cell.metadata.get("ai_code_explanation_timestamp")
        # Options are forwarded to the provider fn.
        assert calls["kwargs"]["level"] == 3
        assert calls["kwargs"]["use_bullets"] is True
        assert calls["kwargs"]["use_latex"] is False

    def test_explain_pins_code_hash(self, notebook):
        self._stub()
        idx = _add_code_cell(notebook, "a = 1")
        notebook.explain_code_cell("key", idx, ai_provider="explstub")
        cell = notebook.nb.cells[idx]
        assert cell.metadata["code_hash_for_code_explanation"] == notebook._hash_text("a = 1")
        assert cell.metadata["code_hash_for_code_explanation"] == cell.metadata["code_hash"]

    def test_edit_keeps_explanation_when_code_identical(self, notebook):
        self._stub()
        idx = _add_code_cell(notebook, "a = 1")
        notebook.explain_code_cell("key", idx, ai_provider="explstub")
        # Re-saving byte-identical source keeps the explanation.
        notebook.set_cell_source(idx, "a = 1")
        assert notebook.nb.cells[idx].metadata.get("ai_code_explanation") == "AN EXPLANATION"

    def test_edit_drops_explanation_when_code_changes(self, notebook):
        self._stub()
        idx = _add_code_cell(notebook, "a = 1")
        notebook.explain_code_cell("key", idx, ai_provider="explstub")
        notebook.set_cell_source(idx, "a = 2")
        meta = notebook.nb.cells[idx].metadata
        for k in ("ai_code_explanation", "ai_code_explanation_timestamp",
                  "code_hash_for_code_explanation"):
            assert k not in meta

    def test_clear_code_drops_explanation(self, notebook):
        self._stub()
        idx = _add_code_cell(notebook, "a = 1")
        notebook.explain_code_cell("key", idx, ai_provider="explstub")
        notebook.clear_cell_code(idx)
        assert "ai_code_explanation" not in notebook.nb.cells[idx].metadata

    def test_regenerate_drops_explanation(self, notebook):
        # Stub both explain and code generation so no kernel/API is needed.
        self._stub()
        def fake_generate(api_key, **kwargs):
            # Generation returns (code, questions).
            return "a = 2", None
        _pbmod.AI_PROVIDERS["explstub"]["generate"] = fake_generate
        idx = _add_code_cell(notebook, "a = 1")
        notebook.explain_code_cell("key", idx, ai_provider="explstub")
        assert notebook.nb.cells[idx].metadata.get("ai_code_explanation")
        notebook.generate_code_cell("key", idx, ai_provider="explstub")
        assert "ai_code_explanation" not in notebook.nb.cells[idx].metadata
        # New source hash recorded.
        assert notebook.nb.cells[idx].metadata["code_hash"] == notebook._hash_text("a = 2")


class TestFixCodeAfterManualEdit:
    """The "Fix Code" path: a cell the user broke by hand must actually be
    regenerated, and its output must not be left deleted-but-valid.

    Regression cover for two coupled bugs. The client offers Fix Code whenever
    outputsHaveError() is true (js/errorUtils.js), which includes an error-like
    stderr stream; the server only recognised a formal error output. For a
    stderr-only error the server therefore saw nothing to fix, took the
    generation-skip fast path, and returned the broken code unchanged while
    leaving last_valid_output_cell alone — so the code stayed broken and the
    output read as up to date after the client had cleared it."""

    def _stub(self, code="v = 1\nprint('FIXED', v)"):
        calls = {"n": 0, "error_context": None}
        def fake_generate(api_key, **kwargs):
            calls["n"] += 1
            calls["error_context"] = kwargs.get("error_context")
            return code, None
        _pbmod.AI_PROVIDERS["genstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["genstub"]["generate"] = fake_generate
        return calls

    def _generated_cell(self, notebook, source, explanation="set v to 1 and print it"):
        """A cell in the state the AI leaves it in: code pinned to its description."""
        idx = _add_code_cell(notebook, source)
        cell = notebook.nb.cells[idx]
        cell.metadata['explanation'] = explanation
        h = notebook._hash_text(explanation)
        cell.metadata['description_hash'] = h
        cell.metadata['code_description_hash'] = h
        notebook.last_valid_code_cell = idx
        return idx

    def test_error_like_stderr_is_seen_as_an_error(self, notebook):
        """A warning printed to stderr counts as an error, as it does client-side."""
        idx = self._generated_cell(notebook, "v = 1")
        notebook.nb.cells[idx].outputs = [_nbf.from_dict(
            {'output_type': 'stream', 'name': 'stderr',
             'text': 'RuntimeWarning: v is suspicious'})]
        assert _pbmod.outputs_have_error(notebook.nb.cells[idx].outputs)
        assert notebook._get_error_context(idx) is not None

    def test_plain_stderr_is_not_an_error(self, notebook):
        """Ordinary stderr chatter must not be mistaken for an error."""
        idx = self._generated_cell(notebook, "v = 1")
        notebook.nb.cells[idx].outputs = [_nbf.from_dict(
            {'output_type': 'stream', 'name': 'stderr', 'text': 'downloading model...'})]
        assert not _pbmod.outputs_have_error(notebook.nb.cells[idx].outputs)
        assert notebook._get_error_context(idx) is None

    def test_fix_code_regenerates_stderr_error(self, notebook):
        """Fix Code on a stderr-only error calls the AI and replaces the code."""
        calls = self._stub()
        idx = self._generated_cell(notebook, "v = 1\nprint('OK', v)")
        # The user hand-edits the code, and running it warns on stderr.
        notebook.set_cell_source(idx, "v = 1\nimport warnings; warnings.warn('boom')")
        notebook.last_valid_code_cell = idx
        notebook.nb.cells[idx].outputs = [_nbf.from_dict(
            {'output_type': 'stream', 'name': 'stderr',
             'text': 'UserWarning: boom'})]

        new_code, success, _amended = notebook.generate_code_cell(
            "key", idx, ai_provider="genstub")

        assert calls["n"] == 1                          # the AI really ran
        assert calls["error_context"] is not None       # and was told about the error
        assert success
        assert new_code == "v = 1\nprint('FIXED', v)"
        assert notebook.nb.cells[idx].source == new_code

    def test_manual_edit_defeats_the_generation_skip(self, notebook):
        """Even with no error at all, regenerating a hand-edited cell calls the AI:
        the code is no longer what the description would produce."""
        calls = self._stub()
        idx = self._generated_cell(notebook, "v = 1\nprint('OK', v)")
        assert notebook._code_matches_description(notebook.nb.cells[idx])

        notebook.set_cell_source(idx, "v = 99\nprint('HAND EDITED', v)")
        notebook.last_valid_code_cell = idx
        assert not notebook._code_matches_description(notebook.nb.cells[idx])

        notebook.generate_code_cell("key", idx, ai_provider="genstub")
        assert calls["n"] == 1
        assert notebook.nb.cells[idx].source == "v = 1\nprint('FIXED', v)"

    def test_real_generation_marks_output_stale(self, notebook):
        """After the code is actually regenerated the output is gone and stale,
        so it can never read as up to date with nothing in it."""
        self._stub()
        idx = self._generated_cell(notebook, "v = 1\nprint('OK', v)")
        notebook.set_cell_source(idx, "v = 1\nboom")
        notebook.last_valid_code_cell = idx
        notebook.last_valid_output_cell = idx        # pretend it had a valid output
        notebook.nb.cells[idx].outputs = [_nbf.from_dict(
            {'output_type': 'error', 'ename': 'NameError',
             'evalue': "name 'boom' is not defined", 'traceback': ['NameError: boom']})]

        notebook.generate_code_cell("key", idx, ai_provider="genstub")

        assert notebook.nb.cells[idx].outputs == []
        assert notebook.last_valid_output_cell < idx


class TestForcedRegenerationAndClear:
    """The generation-skip must never swallow an explicit user request.

    Regression cover for two coupled bugs. The skip compares the description the
    code was generated from (code_description_hash) against the current
    description_hash; it never looks at the code itself. So the Regenerate
    button had no way to say "call the AI anyway" -- the client's force flag
    stopped at the client and was never sent -- and clear_cell_code left the pin
    in place, so a cleared cell still claimed to have been generated from its
    description and regenerating handed back the empty string."""

    def _stub(self, code="v = 1\nprint('GENERATED', v)"):
        calls = {"n": 0}
        def fake_generate(api_key, **kwargs):
            calls["n"] += 1
            return code, None
        _pbmod.AI_PROVIDERS["genstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["genstub"]["generate"] = fake_generate
        return calls

    def _skippable_cell(self, notebook, source="v = 1", explanation="set v to 1"):
        """A cell in the exact state where the skip fires: code pinned to its
        current description, and with a baseline of accessed variables that
        reads nothing pre-existing (so _accessed_vars_unchanged is True rather
        than merely lacking a baseline)."""
        idx = _add_code_cell(notebook, source)
        cell = notebook.nb.cells[idx]
        cell.metadata['explanation'] = explanation
        h = notebook._hash_text(explanation)
        cell.metadata['description_hash'] = h
        cell.metadata['code_description_hash'] = h
        notebook._live(cell).accessed_symbols = []
        notebook.last_valid_code_cell = idx
        return idx

    def test_skip_still_fires_for_run_driven_generation(self, notebook):
        """The optimisation survives: an unforced call on an unchanged cell
        still never reaches the AI."""
        calls = self._stub()
        idx = self._skippable_cell(notebook)

        notebook.generate_code_cell("key", idx, ai_provider="genstub")

        assert calls["n"] == 0
        assert notebook._requested_generations == 1
        assert notebook._performed_generations == 0
        assert notebook.nb.cells[idx].source == "v = 1"

    def test_skip_regeneration_off_always_calls_the_ai(self, notebook):
        """The "Skip regeneration when data is unchanged" setting off: an
        unchanged cell is regenerated anyway, without needing force."""
        calls = self._stub()
        idx = self._skippable_cell(notebook)

        notebook.generate_code_cell("key", idx, ai_provider="genstub",
                                    skip_regeneration=False)

        assert calls["n"] == 1
        assert notebook._performed_generations == 1
        assert notebook.nb.cells[idx].source == "v = 1\nprint('GENERATED', v)"

    def test_force_regenerate_bypasses_the_skip(self, notebook):
        """What the Regenerate button now sends: the AI is called even though
        the cell is unchanged and the skip would otherwise fire."""
        calls = self._stub()
        idx = self._skippable_cell(notebook)

        notebook.generate_code_cell("key", idx, ai_provider="genstub",
                                    force_regenerate=True)

        assert calls["n"] == 1
        assert notebook._performed_generations == 1
        assert notebook.nb.cells[idx].source == "v = 1\nprint('GENERATED', v)"

    def test_clear_code_unpins_the_description(self, notebook):
        """Empty source was not generated from the description, so the pin that
        makes the skip eligible has to go -- as it does for a manual edit."""
        self._stub()
        idx = self._skippable_cell(notebook)
        assert notebook._code_matches_description(notebook.nb.cells[idx])

        notebook.clear_cell_code(idx)

        assert 'code_description_hash' not in notebook.nb.cells[idx].metadata
        assert not notebook._code_matches_description(notebook.nb.cells[idx])

    def test_clear_then_generate_calls_the_ai(self, notebook):
        """Clearing the code and regenerating produces code again, even through
        the unforced (run-driven) path where the skip is still enabled."""
        calls = self._stub()
        idx = self._skippable_cell(notebook)
        notebook.clear_cell_code(idx)
        assert notebook.nb.cells[idx].source == ''
        notebook.last_valid_code_cell = idx

        notebook.generate_code_cell("key", idx, ai_provider="genstub")

        assert calls["n"] == 1
        assert notebook.nb.cells[idx].source == "v = 1\nprint('GENERATED', v)"


class TestFixErrorAmendsDescription:
    """Whether fixing an error also rewrites the cell's description.

    The "Fix errors also amends the description" setting (global, in
    settings.yaml) decides whether main.py forwards amend_description to
    generate_code_cell. These tests cover the behaviour it selects between: with
    it off the separate amend_explanation AI call is never made and the
    description the user wrote stands, and with it on the description is
    replaced and stays pinned to the new code."""

    AMENDED = "set v to 1, guarding against the missing name, and print it"

    def _stub(self, code="v = 1\nprint('FIXED', v)"):
        """Stubs BOTH generation and amendment.

        Stubbing amend_explanation matters: copying the gemini provider dict
        leaves the real gemini_amend_explanation in place, which would make a
        live API call the moment a test enables amendment."""
        calls = {"gen": 0, "amend": 0, "amend_args": None}
        def fake_generate(api_key, **kwargs):
            calls["gen"] += 1
            return code, None
        def fake_amend(api_key, *args, **kwargs):
            calls["amend"] += 1
            calls["amend_args"] = args
            return self.AMENDED
        _pbmod.AI_PROVIDERS["amendstub"] = dict(_pbmod.AI_PROVIDERS["gemini"])
        _pbmod.AI_PROVIDERS["amendstub"]["generate"] = fake_generate
        _pbmod.AI_PROVIDERS["amendstub"]["amend_explanation"] = fake_amend
        return calls

    def _errored_cell(self, notebook, explanation="set v to 1 and print it"):
        """A generated cell whose code raised, ready to be fixed."""
        idx = _add_code_cell(notebook, "v = 1\nprint(missing_name)")
        cell = notebook.nb.cells[idx]
        cell.metadata['explanation'] = explanation
        h = notebook._hash_text(explanation)
        cell.metadata['description_hash'] = h
        cell.metadata['code_description_hash'] = h
        cell.outputs = [_nbf.from_dict(
            {'output_type': 'error', 'ename': 'NameError',
             'evalue': "name 'missing_name' is not defined",
             'traceback': ["NameError: name 'missing_name' is not defined"]})]
        notebook.last_valid_code_cell = idx
        return idx

    def test_no_amendment_when_not_requested(self, notebook):
        """Setting off: the AI is never asked about the description, and the
        description the user wrote is left character-for-character alone."""
        calls = self._stub()
        idx = self._errored_cell(notebook)
        before = notebook.nb.cells[idx].metadata['explanation']

        new_code, success, amended = notebook.generate_code_cell(
            "key", idx, ai_provider="amendstub", amend_description=False)

        assert success
        assert calls["gen"] == 1                 # the code was fixed
        assert calls["amend"] == 0               # but no second AI call
        assert amended is None                   # so nothing to send the client
        assert notebook.nb.cells[idx].metadata['explanation'] == before

    def test_amendment_when_requested(self, notebook):
        """Setting on: the description is rewritten and returned to the client."""
        calls = self._stub()
        idx = self._errored_cell(notebook)

        new_code, success, amended = notebook.generate_code_cell(
            "key", idx, ai_provider="amendstub", amend_description=True)

        assert success
        assert calls["amend"] == 1
        assert amended == self.AMENDED
        assert notebook.nb.cells[idx].metadata['explanation'] == self.AMENDED

    def test_amendment_keeps_the_description_pinned(self, notebook):
        """The amended description describes the code just generated, so the two
        hashes must stay equal -- otherwise the next Run would regenerate the
        cell it has only just fixed."""
        self._stub()
        idx = self._errored_cell(notebook)

        notebook.generate_code_cell("key", idx, ai_provider="amendstub",
                                    amend_description=True)

        meta = notebook.nb.cells[idx].metadata
        assert meta['description_hash'] == notebook._hash_text(self.AMENDED)
        assert meta['code_description_hash'] == meta['description_hash']
        assert notebook._code_matches_description(notebook.nb.cells[idx])

    def test_amendment_is_best_effort(self, notebook):
        """A failing amend call must not lose the code fix: it is persisted
        before the amend runs, and the exception is swallowed."""
        calls = self._stub()
        idx = self._errored_cell(notebook)
        before = notebook.nb.cells[idx].metadata['explanation']
        def boom(*a, **kw):
            raise RuntimeError("amend provider is down")
        _pbmod.AI_PROVIDERS["amendstub"]["amend_explanation"] = boom

        new_code, success, amended = notebook.generate_code_cell(
            "key", idx, ai_provider="amendstub", amend_description=True)

        assert success
        assert new_code == "v = 1\nprint('FIXED', v)"
        assert amended is None
        assert notebook.nb.cells[idx].metadata['explanation'] == before


class TestNotebookNaming:
    """normalize_notebook_name: the shared rules for a user-typed notebook name.

    Used by rename() and by the new-plainbook route, so that "create" and
    "rename" accept exactly the same things. The basename rule matters for the
    new-notebook route in particular: a typed path must not be a way to write
    outside the current notebook's folder."""

    @pytest.mark.parametrize("typed,expected", [
        ("analysis", "analysis"),
        ("  analysis  ", "analysis"),
        ("analysis.plnb", "analysis"),
        ("analysis.ipynb", "analysis"),
        ("analysis.PLNB", "analysis"),          # extension match is case-insensitive
        ("/tmp/elsewhere/analysis.plnb", "analysis"),   # path component dropped
        ("../../etc/passwd", "passwd"),
        ("my.data.analysis", "my.data.analysis"),  # only a notebook extension is dropped
    ])
    def test_accepted_names(self, typed, expected):
        assert normalize_notebook_name(typed) == expected

    @pytest.mark.parametrize("typed", ["", "   ", None, ".plnb", ".ipynb", "/tmp/"])
    def test_rejected_names(self, typed):
        with pytest.raises(ValueError):
            normalize_notebook_name(typed)

    def test_rename_still_works(self, notebook):
        """rename() delegates to the helper; its own behaviour is unchanged."""
        _add_code_cell(notebook, "x = 1")
        original_path = notebook.path

        notebook.rename("renamed.plnb")            # typed extension is dropped

        assert notebook.name == "renamed"
        assert notebook.path == os.path.join(os.path.dirname(original_path), "renamed.plnb")
        assert os.path.exists(notebook.path)
        assert os.path.exists(original_path)       # the original is left alone

    def test_rename_avoids_a_collision(self, notebook):
        """Renaming onto an existing file takes the next free name, and must
        not overwrite the file that is already there."""
        notebook.rename("taken")
        first = notebook.path
        notebook.rename("other")
        _add_code_cell(notebook, "x = 1")      # written to the second name only

        notebook.rename("taken")

        assert notebook.name == "taken_2"
        assert notebook.path == os.path.join(os.path.dirname(first), "taken_2.plnb")
        assert os.path.exists(notebook.path)
        assert os.path.exists(first)               # the earlier file is untouched
        assert nbformat.read(first, as_version=4).cells == []

    def test_rename_to_the_current_name_is_a_noop(self, notebook):
        """Re-committing the same title must not spawn a _2 copy."""
        notebook.rename("stable")
        path = notebook.path

        notebook.rename("stable.plnb")             # same name, typed extension

        assert notebook.path == path
        assert not os.path.exists(
            os.path.join(os.path.dirname(path), "stable_2.plnb"))

    @pytest.mark.parametrize("existing,expected", [
        ([], "free"),
        (["free"], "free_2"),
        (["free", "free_2"], "free_3"),
        (["free_2"], "free"),                      # only the exact name blocks
    ])
    def test_unique_notebook_path(self, tmp_path, existing, expected):
        for name in existing:
            (tmp_path / f"{name}.plnb").write_text("")

        name, path = unique_notebook_path(str(tmp_path), "free")

        assert name == expected
        assert path == os.path.join(str(tmp_path), expected + ".plnb")

    def test_save_copy(self, notebook):
        """The copy has the same cells, and the original keeps its own name."""
        _add_code_cell(notebook, "x = 1")
        original_name, original_path = notebook.name, notebook.path

        name, path = notebook.save_copy("duplicate.plnb")

        assert (name, path) == (
            "duplicate", os.path.join(os.path.dirname(original_path), "duplicate.plnb"))
        assert (notebook.name, notebook.path) == (original_name, original_path)
        copied = nbformat.read(path, as_version=4)
        assert [c.source for c in copied.cells] == [c.source for c in notebook.nb.cells]

    def test_save_copy_avoids_a_collision(self, notebook):
        notebook.save_copy("dup")

        name, path = notebook.save_copy("dup")

        assert name == "dup_2"
        assert os.path.exists(path)

    def test_save_copy_rejects_an_empty_name(self, notebook):
        with pytest.raises(ValueError):
            notebook.save_copy("  ")

    def test_save_copy_into_another_folder(self, notebook, tmp_path):
        """The copy dialog can now choose where the copy lands."""
        _add_code_cell(notebook, "x = 1")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        original_path = notebook.path

        name, path = notebook.save_copy("moved", folder=str(elsewhere))

        assert (name, path) == ("moved", os.path.join(str(elsewhere), "moved.plnb"))
        assert os.path.exists(path)
        assert notebook.path == original_path
        assert [c.source for c in nbformat.read(path, as_version=4).cells] == \
            [c.source for c in notebook.nb.cells]

    def test_save_copy_into_another_folder_avoids_a_collision(self, notebook, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        notebook.save_copy("moved", folder=str(elsewhere))

        name, path = notebook.save_copy("moved", folder=str(elsewhere))

        assert name == "moved_2"
        assert os.path.dirname(path) == str(elsewhere)


class TestCheckNotebookFile:
    """check_notebook_file guards the "open an existing plainbook" flow.

    It runs in the process that can still tell the user what went wrong: the
    child that would open the file is detached with its output discarded, so a
    file it cannot load would make it die invisibly."""

    def test_accepts_a_plainbook(self, notebook):
        _add_code_cell(notebook, "x = 1")
        name, path = notebook.save_copy("openable")

        check_notebook_file(path)          # does not raise

    def test_accepts_a_plain_jupyter_notebook(self, tmp_path):
        path = tmp_path / "plain.ipynb"
        nb = nbformat.v4.new_notebook()
        nb.cells = [nbformat.v4.new_code_cell("print(1)")]
        nbformat.write(nb, str(path))

        check_notebook_file(str(path))     # does not raise

    def test_rejects_a_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="no file"):
            check_notebook_file(str(tmp_path / "absent.plnb"))

    def test_rejects_a_folder(self, tmp_path):
        with pytest.raises(ValueError, match="folder"):
            check_notebook_file(str(tmp_path))

    @pytest.mark.parametrize("content", [
        "this is not json at all",
        "",
        '{"foo": 1}',                      # valid JSON, no cells
        "[1, 2, 3]",                       # valid JSON, not even an object
    ])
    def test_rejects_a_non_notebook(self, tmp_path, content):
        path = tmp_path / "impostor.plnb"
        path.write_text(content)

        with pytest.raises(ValueError, match="not a notebook"):
            check_notebook_file(str(path))
