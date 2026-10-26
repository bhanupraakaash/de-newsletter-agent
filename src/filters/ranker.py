"""Free, deterministic relevance scoring. Decides which articles are worth paying Claude for."""
import logging
import re
from datetime import datetime, timezone

from src.filters.keywords import KEYWORD_TOPIC, TOPIC_WEIGHTS
from src.models import Article

log = logging.getLogger(__name__)

# Extra trust for curated/primary sources. Unlisted sources get 0.
SOURCE_TRUST: dict[str, float] = {
    "Data Engineering Weekly": 1.5,
    "Databricks Blog": 1.0,
    "Microsoft Fabric Blog": 1.0,
    "Azure Blog": 0.8,
    "Confluent Blog": 0.8,
    "dbt Blog": 0.8,
    "Netflix Tech Blog": 0.8,
    "Seattle Data Guy": 0.6,
}

TITLE_HIT, BODY_HIT, SOURCE_HIT = 3.0, 1.0, 0.5
KEYWORD_CAP = 6.0       # keyword evidence can contribute at most this much
TOPIC_BONUS = 0.5       # per additional distinct topic beyond the first
RECENCY_MAX = 2.0       # linear: brand new = 2.0, edge of the window = 0


class ArticleRanker:
    def __init__(self, lookback_days: int = 7, source_trust: dict[str, float] | None = None) -> None:
        self.lookback_days = lookback_days
        self.source_trust = SOURCE_TRUST if source_trust is None else source_trust

    def score(self, article: Article, now: datetime | None = None) -> float:
        """Score on a 0-10 scale. Higher = more likely to matter to a data engineer."""
        now = now or datetime.now(timezone.utc)
        title, body, source = article.title, article.description, article.source

        keyword_points = 0.0
        topics: set[str] = set()
        for kw in article.matched_keywords:
            topic = KEYWORD_TOPIC.get(kw)
            weight = TOPIC_WEIGHTS.get(topic, 0.7)
            if _contains(title, kw):
                base = TITLE_HIT
            elif _contains(body, kw):
                base = BODY_HIT
            else:
                base = SOURCE_HIT  # matched only via the source name
            keyword_points += base * weight
            if topic:
                topics.add(topic)
        keyword_points += TOPIC_BONUS * max(len(topics) - 1, 0)
        keyword_points = min(keyword_points, KEYWORD_CAP)

        total = keyword_points + self._recency(article, now) + self.source_trust.get(source, 0.0)
        return round(min(total, 10.0), 2)

    def _recency(self, article: Article, now: datetime) -> float:
        if not article.published_date:
            return 0.0
        age_days = max((now - article.published_date).total_seconds() / 86400, 0)
        return round(max(0.0, 1 - age_days / self.lookback_days) * RECENCY_MAX, 3)

    def rank(self, articles: list[Article], now: datetime | None = None) -> list[Article]:
        """Return copies with relevance_score set, best first. Ties: newer, then title (stable)."""
        scored = [a.model_copy(update={"relevance_score": self.score(a, now)}) for a in articles]
        scored.sort(
            key=lambda a: (
                -a.relevance_score,
                -(a.published_date.timestamp() if a.published_date else 0),
                a.title,
            )
        )
        return scored

    def select_top(
        self, articles: list[Article], limit: int, max_per_source: int = 4, now: datetime | None = None
    ) -> list[Article]:
        """Top `limit` by score, with a per-source cap so one prolific feed can't take every slot."""
        picked: list[Article] = []
        per_source: dict[str, int] = {}
        for a in self.rank(articles, now):
            if per_source.get(a.source, 0) >= max_per_source:
                continue
            per_source[a.source] = per_source.get(a.source, 0) + 1
            picked.append(a)
            if len(picked) == limit:
                break
        log.info("Ranker: %d candidates -> top %d (cap %d/source)", len(articles), len(picked), max_per_source)
        return picked


def _contains(text: str, keyword: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.IGNORECASE) is not None
