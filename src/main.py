import logging

from src.collectors import FEEDS, RSSCollector
from src.config import load_settings
from src.filters import ArticleFilter, ArticleRanker, DeduplicationService
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
        unique = DeduplicationService().deduplicate(relevant, storage.get_sent_ids())
        storage.save_new(unique)
        total_stored = storage.count()

    # Only the best few reach Claude (Phase 8); everything else stays free.
    candidates = ArticleRanker(settings.lookback_days).select_top(unique, settings.max_articles_to_claude)

    log.info(
        "Funnel: discovered=%d normalized=%d recent=%d keyword_match=%d unique_unsent=%d "
        "top_candidates=%d (failed feeds: %d, rows in DB: %d)",
        discovered, len(articles), len(recent), len(relevant), len(unique), len(candidates),
        len(collector.failed_feeds), total_stored,
    )
    for a in candidates:
        log.info("  %.2f [%s] %s", a.relevance_score, a.source, a.title)


if __name__ == "__main__":
    main()
