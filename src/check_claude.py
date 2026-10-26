"""One-off smoke test: confirms the key, model and cost tracking work (costs well under $0.001)."""
import logging

from src.config import load_settings
from src.services import ClaudeService, CostTracker, LLMError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    s = load_settings()
    tracker = CostTracker()
    try:
        claude = ClaudeService(s.anthropic_api_key, s.claude_model, s.max_output_tokens, cost_tracker=tracker)
        reply = claude.generate("You are a terse assistant.", "In five words, what is Apache Spark?",
                                max_tokens=50, purpose="smoke-test")
    except LLMError as exc:
        print(f"FAILED: {exc}")
        raise SystemExit(1)
    print(f"Model: {reply.model}\nReply: {reply.text}\nUsage: {tracker.summary()}")


if __name__ == "__main__":
    main()
