import pytest

import plainbook.plainbook as pb
from plainbook.plainbook import Plainbook, ClarificationNeeded
from plainbook.ai_common import parse_generate_response


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


class TestAskQuestions:

    def test_clarification_raises_with_the_questions(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Compute the revenue.")

        # The AI chooses to reply with questions rather than code.
        def fake_generate(api_key, ask_questions=False, **kwargs):
            assert ask_questions is True
            return parse_generate_response(
                "NEEDS_CLARIFICATION\n- Gross or net revenue?")

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'generate', fake_generate)

        with pytest.raises(ClarificationNeeded) as excinfo:
            notebook.generate_code_cell("key", idx, ai_provider='gemini',
                                        ask_questions=True)
        assert excinfo.value.questions == ["Gross or net revenue?"]
        # The cell source is left untouched.
        assert notebook.nb.cells[idx].source == "print(1)"

    def test_code_is_used_when_the_ai_asks_nothing(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Compute the revenue.")

        # Questions are enabled, but the AI has no doubts and returns code.
        def fake_generate(api_key, ask_questions=False, **kwargs):
            assert ask_questions is True
            return parse_generate_response("revenue = 42")

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'generate', fake_generate)

        new_code, success, amended = notebook.generate_code_cell(
            "key", idx, ai_provider='gemini', ask_questions=True)
        assert success is True
        assert new_code == "revenue = 42"
        assert notebook.nb.cells[idx].source == "revenue = 42"

    def test_no_clarification_when_setting_off(self, notebook, monkeypatch):
        idx = _add_action_cell(notebook, "Compute the revenue.")
        # ask_questions defaults to off; the AI is not offered the choice.

        def fake_generate(api_key, ask_questions=False, **kwargs):
            assert ask_questions is False
            return "revenue = 42", None

        monkeypatch.setitem(pb.AI_PROVIDERS['gemini'], 'generate', fake_generate)

        new_code, success, amended = notebook.generate_code_cell(
            "key", idx, ai_provider='gemini')
        assert success is True
        assert new_code == "revenue = 42"
        assert notebook.nb.cells[idx].source == "revenue = 42"
