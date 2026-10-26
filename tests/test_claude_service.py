from types import SimpleNamespace

import anthropic
import httpx
import pytest

from src.services import ClaudeService, CostTracker, LLMResponse, calculate_cost
from src.services.llm import LLMError


def fake_response(text="hello", stop="end_turn", inp=100, out=20, model="claude-haiku-5-5"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out),
        stop_reason=stop, model=model,
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self._response, self._error = response, error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def service(client, **kw):
    return ClaudeService("key", client=client, **kw)


def test_generate_parses_text_and_usage():
    out = service(FakeClient(fake_response("hi", inp=50, out=7))).generate("sys", "user")
    assert (out.text, out.input_tokens, out.output_tokens, out.truncated) == ("hi", 50, 7, False)


def test_request_is_cost_safe():
    client = FakeClient(fake_response())
    service(client, max_output_tokens=500).generate("sys", "user")
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["thinking"] == {"type": "disabled"}
    assert call["output_config"] == {"effort": "low"}
    assert call["max_tokens"] == 500
    assert call["system"] == "sys" and call["messages"][0]["content"] == "user"


def test_caller_cannot_exceed_configured_output_cap():
    client = FakeClient(fake_response())
    svc = service(client, max_output_tokens=500)
    svc.generate("s", "u", max_tokens=9999)
    svc.generate("s", "u", max_tokens=100)
    assert [c["max_tokens"] for c in client.calls] == [500, 100]


def test_truncation_is_flagged():
    out = service(FakeClient(fake_response(stop="max_tokens"))).generate("s", "u")
    assert out.truncated is True


def test_refusal_raises():
    with pytest.raises(LLMError, match="declined"):
        service(FakeClient(fake_response(stop="refusal"))).generate("s", "u")


def test_missing_key_fails_fast():
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        ClaudeService("")


def test_sdk_errors_are_wrapped():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError("bad", response=httpx.Response(401, request=req), body=None)
    with pytest.raises(LLMError, match="API key"):
        service(FakeClient(error=err)).generate("s", "u")


def test_usage_is_recorded_in_tracker():
    tracker = CostTracker()
    svc = service(FakeClient(fake_response(inp=1000, out=200)), cost_tracker=tracker)
    svc.generate("s", "u", purpose="rank")
    svc.generate("s", "u", purpose="summarize")
    assert tracker.input_tokens == 2000 and tracker.output_tokens == 400
    assert [c["purpose"] for c in tracker.calls] == ["rank", "summarize"]


# --- cost calculation --------------------------------------------------------

def test_haiku_cost_math():
    # 1M in at $0.10 + 1M out at $0.50
    assert calculate_cost("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert calculate_cost("claude-haiku-5-5", 10_000, 2_000) == pytest.approx(0.002)


def test_unknown_model_uses_conservative_price():
    assert calculate_cost("mystery", 1_000_000, 0) == pytest.approx(4.00)


def test_tracker_total_cost():
    t = CostTracker()
    t.record(LLMResponse(text="", model="claude-haiku-5-5", input_tokens=1_000_000, output_tokens=0))
    t.record(LLMResponse(text="", model="claude-haiku-5-5", input_tokens=0, output_tokens=1_000_000))
    assert t.total_cost == pytest.approx(0.60)
    assert "2 calls" in t.summary()
