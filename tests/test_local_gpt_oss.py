"""Tests for the local model provider module, with a fake backend (no server)."""
import pytest

from plainbook import ai_common, local_models
import plainbook.local_gpt_oss as lg


class FakeBackend:
    def __init__(self, text="```python\nx = 1\n```"):
        self.text = text
        self.calls = []

    def chat(self, model, system, prompt, max_tokens, think=None, timeout=None):
        self.calls.append(dict(model=model, system=system, prompt=prompt,
                               max_tokens=max_tokens, think=think))
        return self.text, "some thinking", 11, 7

    def request_payload(self, *a, **kw):
        return {}


@pytest.fixture
def backend(monkeypatch):
    b = FakeBackend()
    monkeypatch.setattr(local_models, "get_backend", lambda: b)
    monkeypatch.setattr(ai_common, "_session_tokens", {"input": 0, "output": 0})
    return b


class TestRespond:
    def test_passes_through_and_counts_tokens(self, backend):
        text = lg._respond("gpt-oss:20b", "SYS", "PROMPT", 123, "label", think="low")
        assert text == backend.text
        (call,) = backend.calls
        assert call == dict(model="gpt-oss:20b", system="SYS", prompt="PROMPT",
                            max_tokens=123, think="low")
        assert ai_common.get_session_tokens() == {"input": 11, "output": 7}

    def test_think_dropped_for_models_without_levels(self, backend, monkeypatch):
        monkeypatch.setattr(local_models, "LOCAL_MODEL_CATALOG", [
            {"id": "plain", "backend_name": "plain:1b", "supports_think_levels": False}])
        lg._respond("plain:1b", "S", "P", 10, "l", think="medium")
        assert backend.calls[0]["think"] is None

    def test_think_kept_for_unknown_models(self, backend):
        lg._respond("something-else:7b", "S", "P", 10, "l", think="medium")
        assert backend.calls[0]["think"] == "medium"


class TestProviderFunctions:
    def test_generate_code_returns_tuple_and_strips_fences(self, backend):
        code, questions = lg.local_generate_code(None, instructions="do x")
        assert code == "x = 1\n" or code == "x = 1"
        assert questions is None
        call = backend.calls[0]
        assert call["model"] == lg.LOCAL_MODEL
        assert call["think"] == lg.THINK_CODE
        assert call["system"].startswith(ai_common.SYSTEM_INSTRUCTIONS)
        assert call["system"].endswith(lg.LOCAL_OUTPUT_HINT)
        assert "do x" in call["prompt"]

    def test_generate_code_with_questions(self, backend):
        backend.text = f"{ai_common.CLARIFY_SENTINEL}\n1. Which file?\n2. Which column?"
        code, questions = lg.local_generate_code(None, instructions="do x", ask_questions=True)
        assert code is None
        assert questions and len(questions) == 2
        assert ai_common.CLARIFY_INSTRUCTIONS in backend.calls[0]["system"]

    def test_explicit_model_is_used(self, backend):
        lg.local_generate_code(None, instructions="i", model="gpt-oss:120b")
        assert backend.calls[0]["model"] == "gpt-oss:120b"

    def test_name_uses_low_effort_and_strips(self, backend):
        backend.text = "  Load Data  \n"
        assert lg.local_generate_cell_name(None, "load the data") == "Load Data"
        assert backend.calls[0]["think"] == lg.THINK_TEXT
        assert backend.calls[0]["max_tokens"] == lg.MAX_TOKENS_NAME

    def test_explain_returns_text(self, backend):
        backend.text = "It adds one."
        out = lg.local_explain_code(None, "", "x = 1", "set x", level=2, use_bullets=True)
        assert out == "It adds one."
        assert "bullet" in backend.calls[0]["prompt"]

    def test_validate_parses(self, backend):
        backend.text = "VALID"
        result = lg.local_validate_code(None, "", "x = 1", "set x")
        assert isinstance(result, dict) and "is_valid" in result

    def test_verify_parses(self, backend):
        backend.text = "PASS"
        result = lg.local_verify_notebook(None, "payload")
        assert isinstance(result, dict) and "is_valid" in result

    def test_fold_and_amend_strip(self, backend):
        backend.text = " folded \n"
        assert lg.local_fold_additions(None, explanation="e", additions=["a"]) == "folded"
        assert lg.local_amend_explanation(None, "e", "err", "old", "new") == "folded"

    def test_unit_test_code(self, backend):
        code = lg.local_generate_unit_test_code(None, instructions="test it", role="target")
        assert "x = 1" in code

    def test_test_code(self, backend):
        assert "x = 1" in lg.local_generate_test_code(None, instructions="test it")
