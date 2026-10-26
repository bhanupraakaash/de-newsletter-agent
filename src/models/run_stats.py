from datetime import datetime

from pydantic import BaseModel, Field


class RunStats(BaseModel):
    """What happened in one execution. Persisted to SQLite and rendered as a summary."""

    started_at: datetime
    status: str = "running"  # success | no_content | email_failed | failed
    dry_run: bool = False
    llm_used: bool = False

    articles_discovered: int = 0
    articles_after_filtering: int = 0
    articles_sent_to_claude: int = 0
    articles_selected: int = 0
    failed_feeds: int = 0

    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    notes: list[str] = Field(default_factory=list)
