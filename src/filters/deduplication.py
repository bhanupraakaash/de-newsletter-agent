"""Removes repeats within a batch and articles already delivered in earlier runs."""
import logging
import re

from src.models import Article

log = logging.getLogger(__name__)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def title_key(title: str) -> str:
    """'Spark 4.0: What's New?' and 'spark 4 0 whats new' collapse to similar keys."""
    return _NON_ALNUM.sub(" ", title.lower().replace("'", "")).strip()


class DeduplicationService:
    def deduplicate(self, articles: list[Article], sent_ids: set[str] | None = None) -> list[Article]:
        """Drop already-sent articles, then collapse duplicates within the batch."""
        sent_ids = sent_ids or set()
        fresh = [a for a in articles if a.id not in sent_ids]
        unique = self.dedupe_batch(fresh)
        log.info(
            "Dedup: %d in, %d already sent, %d batch duplicates, %d out",
            len(articles), len(articles) - len(fresh), len(fresh) - len(unique), len(unique),
        )
        return unique

    @staticmethod
    def dedupe_batch(articles: list[Article]) -> list[Article]:
        """Same ID (same URL) or same normalized title = duplicate. Keep the richest copy."""
        chosen: dict[str, Article] = {}  # key -> best article, in first-seen order
        for a in articles:
            key = title_key(a.title) or a.id
            current = chosen.get(key)
            if current is None or len(a.description) > len(current.description):
                chosen[key] = a
        # Same URL but different titles would escape the title key, so also guard on ID.
        seen_ids: set[str] = set()
        result: list[Article] = []
        for a in chosen.values():
            if a.id not in seen_ids:
                seen_ids.add(a.id)
                result.append(a)
        return result
