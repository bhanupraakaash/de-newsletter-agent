"""Converts loose RawArticle objects into clean, validated Articles."""
import hashlib
import html
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.models import Article, RawArticle

log = logging.getLogger(__name__)

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</?(p|br|div|li|h[1-6]|tr)\b[^>]*>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str) -> str:
    """HTML -> plain text: drop scripts/tags, decode entities, collapse whitespace."""
    text = _SCRIPT_STYLE_RE.sub(" ", raw)
    text = _BLOCK_RE.sub(" ", text)  # keep words from adjacent blocks apart
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def truncate(text: str, max_chars: int) -> str:
    """Cut at a word boundary so we never send half a word onward."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.-") + "…"


def normalize_url(url: str) -> str:
    """Canonical form so the same article always yields the same URL (and ID)."""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, parts.netloc.lower(), path, urlencode(query), ""))  # fragment dropped


def make_id(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]


class ArticleNormalizer:
    def __init__(self, max_description_chars: int = 1500) -> None:
        self.max_description_chars = max_description_chars

    def normalize(self, raw: RawArticle) -> Article | None:
        """Return a clean Article, or None if the item is unusable."""
        title = clean_text(raw.title)
        url = raw.url.strip()
        if not title or not url.lower().startswith(("http://", "https://")):
            return None
        norm_url = normalize_url(url)
        return Article(
            id=make_id(norm_url),
            title=title,
            source=raw.source,
            url=norm_url,
            published_date=raw.published,
            description=truncate(clean_text(raw.description), self.max_description_chars),
        )

    def normalize_all(self, raws: list[RawArticle]) -> list[Article]:
        articles: list[Article] = []
        for raw in raws:
            try:
                article = self.normalize(raw)
            except Exception as exc:  # one bad item must not sink the batch
                log.warning("Could not normalize %r: %s", raw.url, exc)
                continue
            if article:
                articles.append(article)
        return articles
