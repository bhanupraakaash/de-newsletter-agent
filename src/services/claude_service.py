"""Claude implementation of the LLMProvider contract. The only file that imports `anthropic`."""
import logging

import anthropic

from src.services.cost_tracker import CostTracker
from src.services.llm import LLMError, LLMResponse

log = logging.getLogger(__name__)


class ClaudeService:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-5-5",
        max_output_tokens: int = 2000,
        effort: str = "low",
        cost_tracker: CostTracker | None = None,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if not api_key and client is None:
            raise LLMError("ANTHROPIC_API_KEY is not set (put it in .env locally or GitHub Secrets in CI)")
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.effort = effort
        self.cost_tracker = cost_tracker

    def generate(self, system: str, user: str, max_tokens: int | None = None, purpose: str = "") -> LLMResponse:
        # The configured cap is a hard ceiling: a caller can ask for less, never more.
        limit = min(max_tokens or self.max_output_tokens, self.max_output_tokens)
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=limit,
                system=system,
                messages=[{"role": "user", "content": user}],
                # Haiku 5.5 thinks by default and thinking bills as output tokens; our tasks
                # are classification/summaries, so keep it off and effort low.
                thinking={"type": "disabled"},
                output_config={"effort": self.effort},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Rate limited by Anthropic (SDK retries exhausted)") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Could not reach Anthropic: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc

        if resp.stop_reason == "refusal":
            raise LLMError("Claude declined to answer this request")

        text = "".join(b.text for b in resp.content if b.type == "text")
        result = LLMResponse(
            text=text,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            stop_reason=resp.stop_reason or "",
            truncated=resp.stop_reason == "max_tokens",
        )
        if self.cost_tracker:
            self.cost_tracker.record(result, purpose)
        log.info("Claude call (%s): %d in / %d out tokens", purpose or "-", result.input_tokens, result.output_tokens)
        return result
