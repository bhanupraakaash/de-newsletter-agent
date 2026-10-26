"""Provider-neutral LLM contract. The rest of the app depends on this, never on a vendor SDK."""
from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """Any failure to get a usable answer from the model (network, auth, refusal...)."""


class LLMResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str = ""
    truncated: bool = False  # True if the answer hit the output-token cap


class LLMProvider(Protocol):
    def generate(self, system: str, user: str, max_tokens: int | None = None) -> LLMResponse: ...
