"""Collects articles from RSS/Atom feeds, tolerating individual feed failures."""
import logging
import time
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from src.collectors.feeds import FeedConfig
from src.models import RawArticle

log = logging.getLogger(__name__)

USER_AGENT = "DataPulseAI/0.1 (personal newsletter agent)"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RSSCollector:
    def __init__(
        self,
        feeds: list[FeedConfig],
        client: httpx.Client | None = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.feeds = feeds
        self.client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.failed_feeds: list[str] = []

    def collect(self) -> list[RawArticle]:
        """Fetch every feed. A broken feed is logged and skipped, never fatal."""
        self.failed_feeds = []
        articles: list[RawArticle] = []
        for feed in self.feeds:
            try:
                content = self._fetch(feed.url)
                found = self.parse(content, feed)
                log.info("%s: %d entries", feed.name, len(found))
                articles.extend(found)
            except Exception as exc:  # deliberate: isolate failures per feed
                log.warning("Feed failed: %s (%s): %s", feed.name, feed.url, exc)
                self.failed_feeds.append(feed.name)
        return articles

    def _fetch(self, url: str) -> bytes:
        """GET with retry on network errors and transient HTTP statuses."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.get(url)
                if resp.status_code in RETRYABLE_STATUS:
                    raise httpx.HTTPStatusError(
                        f"status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()  # other 4xx: raised, and not retried below
                return resp.content
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise
            except httpx.TransportError as exc:  # timeouts, DNS, connection resets
                last_exc = exc
            if attempt < self.max_retries:
                time.sleep(self.backoff_seconds * (2**attempt))
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def parse(content: bytes, feed: FeedConfig) -> list[RawArticle]:
        """Turn raw RSS/Atom bytes into RawArticle objects."""
        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"unparseable feed: {parsed.bozo_exception}")

        articles: list[RawArticle] = []
        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue  # unusable without both
            articles.append(
                RawArticle(
                    source=feed.name,
                    title=title,
                    url=link,
                    published=_entry_datetime(entry),
                    description=entry.get("summary", "") or "",
                    feed_url=feed.url,
                )
            )
        return articles


def _entry_datetime(entry) -> datetime | None:
    """feedparser gives a UTC struct_time; convert to an aware datetime."""
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return None
    return datetime.fromtimestamp(timegm(st), tz=timezone.utc)
