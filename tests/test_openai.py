"""Tests for the OpenAI request helper, using a fake client (no network)."""
import openai as openai_sdk
import pytest

import plainbook.openai as po
from plainbook import ai_common


class FakeResponse:
    def __init__(self, text, status="completed", reason=None):
        self.output_text = text
        self.status = status
        self.incomplete_details = None if reason is None else type("D", (), {"reason": reason})()
        self.usage = type("U", (), {"input_tokens": 11, "output_tokens": 7})()


class FakeClient:
    """Records requests; rejects `reasoning` when `accepts_reasoning` is False,
    the way non-reasoning models do."""
    def __init__(self, accepts_reasoning=True, text="hello"):
        self.accepts_reasoning = accepts_reasoning
        self.text = text
        self.requests = []
        self.responses = self

    def create(self, **request):
        self.requests.append(request)
        if "reasoning" in request and not self.accepts_reasoning:
            raise openai_sdk.BadRequestError(
                "Unsupported parameter: 'reasoning'", response=_fake_http_response(), body=None)
        return FakeResponse(self.text)


def _fake_http_response():
    import httpx
    return httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


@pytest.fixture(autouse=True)
def reset_tokens(monkeypatch):
    monkeypatch.setattr(ai_common, "_session_tokens", {"input": 0, "output": 0})
    yield


class TestRespond:
    def test_sends_system_prompt_and_cap(self):
        client = FakeClient(text="  out  ")
        text = po._respond(client, "gpt-x", "SYS", "PROMPT", 123, "label")
        assert text == "  out  "
        (req,) = client.requests
        assert req == {"model": "gpt-x", "instructions": "SYS", "input": "PROMPT",
                       "max_output_tokens": 123}

    def test_reasoning_effort_sent_when_accepted(self):
        client = FakeClient(accepts_reasoning=True)
        po._respond(client, "gpt-x", "S", "P", 10, "l", reasoning_effort="minimal")
        assert len(client.requests) == 1
        assert client.requests[0]["reasoning"] == {"effort": "minimal"}

    def test_reasoning_effort_retried_without_when_rejected(self):
        client = FakeClient(accepts_reasoning=False)
        text = po._respond(client, "gpt-x", "S", "P", 10, "l", reasoning_effort="minimal")
        assert text == "hello"
        assert len(client.requests) == 2
        assert "reasoning" in client.requests[0]
        assert "reasoning" not in client.requests[1]

    def test_other_bad_requests_propagate(self):
        client = FakeClient(accepts_reasoning=False)
        # Without a reasoning parameter there is nothing to retry.
        client.accepts_reasoning = False
        def bad(**request):
            raise openai_sdk.BadRequestError("nope", response=_fake_http_response(), body=None)
        client.create = bad
        with pytest.raises(openai_sdk.BadRequestError):
            po._respond(client, "gpt-x", "S", "P", 10, "l")

    def test_tokens_are_accounted(self):
        po._respond(FakeClient(), "gpt-x", "S", "P", 10, "l")
        assert ai_common.get_session_tokens()["input"] == 11
        assert ai_common.get_session_tokens()["output"] == 7


class TestPublicFunctions:
    def test_generate_cell_name_uses_minimal_reasoning(self, monkeypatch):
        client = FakeClient(text=" Load data \n")
        monkeypatch.setattr(po, "_get_client", lambda key: client)
        assert po.openai_generate_cell_name("key", "Load the CSV file") == "Load data"
        assert client.requests[0]["reasoning"] == {"effort": "minimal"}
        assert client.requests[0]["model"] == po.OPENAI_MODEL

    def test_generate_code_strips_fences_and_uses_model(self, monkeypatch):
        client = FakeClient(text="```python\nx = 1\n```")
        monkeypatch.setattr(po, "_get_client", lambda key: client)
        code, questions = po.openai_generate_code("key", instructions="set x", model="gpt-9")
        assert code.strip() == "x = 1"
        assert questions is None
        assert client.requests[0]["model"] == "gpt-9"
        assert "set x" in client.requests[0]["input"]
