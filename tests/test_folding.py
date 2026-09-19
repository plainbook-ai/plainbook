import pytest

import plainbook.plainbook as pb
from plainbook.plainbook import Plainbook


@pytest.fixture
def notebook(tmp_notebook_path):
    """Creates a Plainbook instance and shuts it down after the test."""
    nb = Plainbook(tmp_notebook_path)
    yield nb
    nb._shutdown()


def _add_action_cell(notebook, explanation, source="print(1)"):
    """Insert a code (action) cell with an explanation and valid code/output."""
    cell, idx = notebook.insert_cell(len(notebook.nb.cells), 'code')
    notebook.set_cell_explanation(idx, explanation)
    notebook.set_cell_source(idx, source)
    notebook.last_valid_code_cell = idx
    notebook.last_valid_output_cell = idx
    return idx


class TestProposeAmend:

    def test_passes_explanation_and_text_to_provider(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Plot revenue.")
        captured = {}

        def fake_fold(api_key, explanation=None, additions=None, model=None,
                      debug=False, dump_ai_requests=False):
            captured['explanation'] = explanation
            captured['additions'] = additions
            return "Plot revenue on log axes."

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'fold', fake_fold)
        result = notebook.propose_amend("key", idx, "make the axes log scale",
                                        ai_provider='gemini')
        assert result == "Plot revenue on log axes."
        assert captured['explanation'] == "Plot revenue."
        assert captured['additions'] == ["make the axes log scale"]

    def test_does_not_mutate_the_cell(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Plot revenue.")
        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'fold',
                            lambda *a, **k: "Plot revenue on log axes.")
        notebook.propose_amend("key", idx, "log scale", ai_provider='gemini')
        cell = notebook.nb.cells[idx]
        assert cell.metadata['explanation'] == "Plot revenue."
        assert 'explanation_prefold' not in cell.metadata
        assert notebook.last_valid_code_cell == idx

    def test_empty_text_returns_base_without_calling_ai(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Plot revenue.")

        def boom(*a, **k):
            raise AssertionError("AI must not be called for an empty amendment")

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'fold', boom)
        assert notebook.propose_amend("key", idx, "   ", ai_provider='gemini') == "Plot revenue."


class TestCommitAmend:

    def test_snapshots_explanation_and_source(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        cell = notebook.nb.cells[idx]
        assert cell.metadata['explanation'] == "Plot revenue on log axes."
        snap = cell.metadata['explanation_prefold']
        assert snap['explanation'] == "Plot revenue."
        assert snap['source'] == "plot(df)"

    def test_marks_code_stale_so_the_pipeline_regenerates(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.")
        notebook.last_valid_code_cell = idx
        notebook.last_valid_output_cell = idx
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        # The folded text has never generated code. It must not be left
        # standing next to code produced by the old explanation.
        assert notebook.last_valid_code_cell == idx - 1
        assert notebook.last_valid_output_cell == idx - 1


class TestUnfold:

    def test_restores_explanation_and_source(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        notebook.set_cell_source(idx, "plot(df, logy=True)")
        result = notebook.unfold(idx)
        cell = notebook.nb.cells[idx]
        assert cell.metadata['explanation'] == "Plot revenue."
        assert cell.source == "plot(df)"
        assert 'explanation_prefold' not in cell.metadata
        assert result == {'explanation': "Plot revenue.", 'source': "plot(df)"}

    def test_calls_no_provider(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        notebook.commit_amend(idx, "Plot revenue on log axes.")

        def boom(*a, **k):
            raise AssertionError("unfold must not call the AI")

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'fold', boom)
        notebook.unfold(idx)

    def test_marks_only_the_output_stale(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        notebook.last_valid_code_cell = idx
        notebook.last_valid_output_cell = idx
        notebook.unfold(idx)
        # The restored pair already ran together, so only the output is stale.
        assert notebook.last_valid_code_cell == idx
        assert notebook.last_valid_output_cell == idx - 1

    def test_without_snapshot_returns_none(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.")
        assert notebook.unfold(idx) is None

    def test_legacy_snapshot_without_source_marks_code_stale(self, notebook):
        idx = _add_action_cell(notebook, "Folded text.", source="plot(df)")
        # Written by the previous version: no source, so no true undo.
        notebook.nb.cells[idx].metadata['explanation_prefold'] = {
            'explanation': "Plot revenue.",
            'additions': [{'id': 'a1', 'text': "log scale"}],
        }
        notebook.last_valid_code_cell = idx
        notebook.last_valid_output_cell = idx
        result = notebook.unfold(idx)
        cell = notebook.nb.cells[idx]
        assert cell.metadata['explanation'] == "Plot revenue."
        assert result['source'] is None
        # No code to restore, so it must be regenerated rather than trusted.
        assert notebook.last_valid_code_cell == idx - 1


class TestFoldingDrivesTheGenerationSkip:
    """The generator skips regeneration when a cell's code was already produced
    from its current description. Folding rewrites the description, so it has to
    keep those hashes honest or the amendment never reaches the code."""

    def _mark_code_generated_from_explanation(self, notebook, idx):
        cell = notebook.nb.cells[idx]
        cell.metadata['code_description_hash'] = cell.metadata['description_hash']

    def test_commit_amend_forces_regeneration(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        self._mark_code_generated_from_explanation(notebook, idx)
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        # The code came from the pre-fold text, so the skip must decline.
        assert not notebook._code_matches_description(notebook.nb.cells[idx])

    def test_unfold_restores_a_matching_pair(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        self._mark_code_generated_from_explanation(notebook, idx)
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        notebook.set_cell_source(idx, "plot(df, logy=True)")
        notebook.unfold(idx)
        # Explanation and code were generated together, so no AI call is owed.
        assert notebook._code_matches_description(notebook.nb.cells[idx])

    def test_unfold_retires_the_output_recorded_for_the_folded_code(self, notebook):
        idx = _add_action_cell(notebook, "Plot revenue.", source="plot(df)")
        self._mark_code_generated_from_explanation(notebook, idx)
        notebook.commit_amend(idx, "Plot revenue on log axes.")
        notebook.set_cell_source(idx, "plot(df, logy=True)")
        cell = notebook.nb.cells[idx]
        cell.metadata['code_description_hash'] = cell.metadata['description_hash']
        # Stand in for a run of the folded code: the execution-skip trusts the
        # stored output only while this hash still matches the cell.
        notebook._live(cell).output_hash = cell.metadata['code_description_hash']
        notebook.unfold(idx)
        assert notebook._live(cell).output_hash != cell.metadata['code_description_hash']

    def test_legacy_unfold_forces_regeneration(self, notebook):
        idx = _add_action_cell(notebook, "Folded text.", source="plot(df)")
        self._mark_code_generated_from_explanation(notebook, idx)
        notebook.nb.cells[idx].metadata['explanation_prefold'] = {
            'explanation': "Plot revenue.",
            'additions': [{'id': 'a1', 'text': "log scale"}],
        }
        notebook.unfold(idx)
        # No code was saved, so the restored text must regenerate rather than
        # keep the code the folded text produced.
        assert not notebook._code_matches_description(notebook.nb.cells[idx])


class TestGeneratorReadsExplanationDirectly:

    def test_no_additions_machinery_remains(self, notebook):
        assert not hasattr(notebook, 'add_cell_addition')
        assert not hasattr(notebook, 'delete_cell_addition')
        assert not hasattr(notebook, '_explanation_with_additions')


class TestLegacyMigration:

    def test_leftover_additions_are_folded_onto_the_explanation(self, tmp_notebook_path):
        nb = Plainbook(tmp_notebook_path)
        idx = _add_action_cell(nb, "Plot revenue.")
        nb.nb.cells[idx].metadata['additions'] = [
            {'id': 'a1', 'text': "Color the bars blue."},
            {'id': 'a2', 'text': "Drop null rows first."},
        ]
        nb._write()
        nb._shutdown()

        reloaded = Plainbook(tmp_notebook_path)
        try:
            cell = reloaded.nb.cells[idx]
            explanation = cell.metadata['explanation']
            assert "Plot revenue." in explanation
            assert "Color the bars blue." in explanation
            assert "Drop null rows first." in explanation
            assert 'additions' not in cell.metadata
        finally:
            reloaded._shutdown()

    def test_empty_additions_leave_the_explanation_alone(self, tmp_notebook_path):
        nb = Plainbook(tmp_notebook_path)
        idx = _add_action_cell(nb, "Plot revenue.")
        nb.nb.cells[idx].metadata['additions'] = []
        nb._write()
        nb._shutdown()

        reloaded = Plainbook(tmp_notebook_path)
        try:
            cell = reloaded.nb.cells[idx]
            assert cell.metadata['explanation'] == "Plot revenue."
            assert 'additions' not in cell.metadata
        finally:
            reloaded._shutdown()
