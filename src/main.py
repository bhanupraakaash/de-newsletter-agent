import logging

from src.collectors import FEEDS, RSSCollector
from src.config import load_settings
from src.filters import ArticleFilter, DeduplicationService
from src.services import ArticleNormalizer, StorageService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence per-request noise
log = logging.getLogger("datapulse")


def main() -> None:
    settings = load_settings()
    log.info("DataPulse AI starting (model=%s, lookback=%dd)", settings.claude_model, settings.lookback_days)
    log.info("API key configured: %s", bool(settings.anthropic_api_key))  # never log the key itself

    collector = RSSCollector(FEEDS)
    raw_articles = collector.collect()
    discovered = len(raw_articles)

    articles = ArticleNormalizer(settings.max_article_chars).normalize_all(raw_articles)

    article_filter = ArticleFilter(lookback_days=settings.lookback_days)
    recent = article_filter.filter_by_date(articles)
    relevant = article_filter.filter_by_keywords(recent)

    with StorageService(settings.db_path) as storage:
        candidates = DeduplicationService().deduplicate(relevant, storage.get_sent_ids())
        storage.save_new(candidates)
        total_stored = storage.count()

    log.info(
        "Funnel: discovered=%d normalized=%d recent=%d keyword_match=%d unique_unsent=%d "
        "(failed feeds: %d, rows in DB: %d)",
        discovered, len(articles), len(recent), len(relevant), len(candidates),
        len(collector.failed_feeds), total_stored,
    )
    for a in candidates[:8]:
        log.info("  [%s] %s  <- %s", a.source, a.title, ", ".join(a.matched_keywords[:4]))


if __name__ == "__main__":
    main()
