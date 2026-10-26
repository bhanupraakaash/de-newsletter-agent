import logging

from src.collectors import FEEDS, RSSCollector
from src.config import load_settings
from src.filters import ArticleFilter
from src.services import ArticleNormalizer

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

    log.info(
        "Funnel: discovered=%d normalized=%d recent=%d keyword_match=%d (failed feeds: %d)",
        discovered, len(articles), len(recent), len(relevant), len(collector.failed_feeds),
    )
    for a in relevant[:8]:
        log.info("  [%s] %s  <- %s", a.source, a.title, ", ".join(a.matched_keywords[:4]))


if __name__ == "__main__":
    main()
