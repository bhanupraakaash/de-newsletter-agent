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

    # Spend guards (USD)
    max_run_cost_usd: float = Field(default=0.25, gt=0)
    lifetime_budget_usd: float = Field(default=5.0, gt=0)

    # Email (SMTP; e.g. Gmail with an app password)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""  # comma-separated

    db_path: Path = Path("data/datapulse.db")
    output_dir: Path = Path("output")

    @property
    def recipients(self) -> list[str]:
        return [e.strip() for e in self.email_to.split(",") if e.strip()]

    @property
    def sender(self) -> str:
        return self.email_from or self.smtp_username

    def missing_email_settings(self) -> list[str]:
        missing = []
        if not self.smtp_username:
            missing.append("SMTP_USERNAME")
        if not self.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.recipients:
            missing.append("EMAIL_TO")
        return missing


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
        max_run_cost_usd=float(os.getenv("MAX_RUN_COST_USD", 0.25)),
        lifetime_budget_usd=float(os.getenv("LIFETIME_BUDGET_USD", 5.0)),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", 587)),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        db_path=Path(os.getenv("DB_PATH", "data/datapulse.db")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
    )
