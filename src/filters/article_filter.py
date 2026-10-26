"""Cheap, deterministic filters that run before any LLM is involved."""
import logging
import re
from datetime import datetime, timedelta, timezone

from src.filters.keywords import ALL_KEYWORDS
from src.models import Article

log = logging.getLogger(__name__)


class ArticleFilter:
    def __init__(self, lookback_days: int = 7, keywords: list[str] | None = None) -> None:
        self.lookback_days = lookback_days
        self.keywords = keywords if keywords is not None else ALL_KEYWORDS
        # Whole-word match: "spark" must not match "sparkling"; "rag" must not match "storage".
        self._patterns = {
            kw: re.compile(rf"(?<!\w){re.escape(kw)}(?!\w)", re.IGNORECASE) for kw in self.keywords
        }

    def filter_by_date(self, articles: list[Article], now: datetime | None = None) -> list[Article]:
        """Keep articles published within the lookback window. Undated items are dropped."""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.lookback_days)
        kept = [a for a in articles if a.published_date and cutoff <= a.published_date <= now + timedelta(days=1)]
        log.info("Date filter: %d -> %d (last %d days)", len(articles), len(kept), self.lookback_days)
        return kept

    def filter_by_keywords(self, articles: list[Article]) -> list[Article]:
        """Keep articles that mention at least one keyword; record which ones matched."""
        kept: list[Article] = []
        for article in articles:
            matches = self.match_keywords(article)
            if matches:
                kept.append(article.model_copy(update={"matched_keywords": matches}))
        log.info("Keyword filter: %d -> %d", len(articles), len(kept))
        return kept

    def match_keywords(self, article: Article) -> list[str]:
        # The source is included so a bare "v4.0.1" from "Apache Spark Releases" still matches.
        haystack = f"{article.title} {article.source} {article.description}"
        return [kw for kw, pattern in self._patterns.items() if pattern.search(haystack)]
