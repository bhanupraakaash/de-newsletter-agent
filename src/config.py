"""Central configuration, loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()  # reads .env locally; in GitHub Actions, secrets arrive as real env vars


class Settings(BaseModel):
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-5-5"

    max_articles_to_claude: int = Field(default=20, ge=1, le=50)
    max_selected_articles: int = Field(default=10, ge=1, le=20)
    max_article_chars: int = Field(default=1500, ge=200)
    max_output_tokens: int = Field(default=2000, ge=100)
    lookback_days: int = Field(default=7, ge=1)

    db_path: Path = Path("data/datapulse.db")


def load_settings() -> Settings:
    """Build Settings from the environment, falling back to defaults."""
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"),
        max_articles_to_claude=int(os.getenv("MAX_ARTICLES_TO_CLAUDE", 20)),
        max_selected_articles=int(os.getenv("MAX_SELECTED_ARTICLES", 10)),
        max_article_chars=int(os.getenv("MAX_ARTICLE_CHARS", 1500)),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", 2000)),
        lookback_days=int(os.getenv("LOOKBACK_DAYS", 7)),
        db_path=Path(os.getenv("DB_PATH", "data/datapulse.db")),
    )
