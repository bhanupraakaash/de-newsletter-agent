"""Entry point: python -m src.main [--dry-run] [--no-llm]"""
import argparse
import logging
import sys

from src.agents import NewsletterAgent
from src.collectors import FEEDS, RSSCollector
from src.config import load_settings
from src.logging_setup import configure_logging
from src.services import ClaudeService, CostTracker, EmailService, StorageService

log = logging.getLogger("datapulse")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DataPulse AI weekly newsletter agent")
    parser.add_argument("--dry-run", action="store_true", help="build the newsletter but do not email it")
    parser.add_argument("--no-llm", action="store_true", help="skip Claude entirely (free; Python ranking only)")
    args = parser.parse_args(argv)

    configure_logging()
    settings = load_settings()

    if not args.dry_run:
        missing = settings.missing_email_settings()
        if missing:
            log.error("Cannot send email; missing settings: %s (use --dry-run to skip sending)", ", ".join(missing))
            return 2

    tracker = CostTracker()
    llm = None
    if args.no_llm:
        log.info("--no-llm: Claude disabled")
    elif not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY not set: running without Claude")
    else:
        llm = ClaudeService(
            settings.anthropic_api_key, settings.claude_model, settings.max_output_tokens, cost_tracker=tracker
        )

    email = None if args.dry_run else EmailService.from_settings(settings)
    log.info("DataPulse AI starting (model=%s, dry_run=%s, claude=%s)", settings.claude_model, args.dry_run, llm is not None)

    with StorageService(settings.db_path) as storage:
        agent = NewsletterAgent(settings, RSSCollector(FEEDS), storage, llm=llm, cost_tracker=tracker, email=email)
        stats = agent.run(dry_run=args.dry_run)

    return 0 if stats.status in ("success", "no_content") else 1


if __name__ == "__main__":
    sys.exit(main())
