"""Tracks token usage and estimated dollar cost across all LLM calls in one run."""
import logging

from src.services.llm import LLMResponse

log = logging.getLogger(__name__)

# USD per 1M tokens: (input, output). Verify against Anthropic's pricing page; prices change.
# Haiku 5.5 rates apply to prompts up to 100K tokens, far above anything we send.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
FALLBACK_PRICE = (4.00, 20.00)  # unknown model: assume expensive so we never under-report


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICING.get(model, FALLBACK_PRICE)
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


class CostTracker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, response: LLMResponse, purpose: str = "") -> None:
        cost = calculate_cost(response.model, response.input_tokens, response.output_tokens)
        if response.model not in PRICING:
            log.warning("No pricing for model %r; using conservative fallback", response.model)
        self.calls.append(
            {"purpose": purpose, "model": response.model, "input_tokens": response.input_tokens,
             "output_tokens": response.output_tokens, "cost_usd": cost}
        )

    @property
    def input_tokens(self) -> int:
        return sum(c["input_tokens"] for c in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(c["output_tokens"] for c in self.calls)

    @property
    def total_cost(self) -> float:
        return sum(c["cost_usd"] for c in self.calls)

    def summary(self) -> str:
        return (f"{len(self.calls)} calls, {self.input_tokens} in / {self.output_tokens} out tokens, "
                f"~${self.total_cost:.5f}")
