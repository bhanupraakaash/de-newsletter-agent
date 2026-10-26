"""Phase 9: one Claude call writes summaries + 'why it matters' for the selected articles only."""
import logging

from pydantic import BaseModel, ValidationError, field_validator

from src.agents.json_utils import extract_json_objects
from src.models import Article
from src.services.llm import LLMError, LLMProvider
from src.services.normalizer import truncate

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write for a weekly newsletter read by professional data engineers. Be concrete, neutral "
    "and concise. Use your own words; never copy sentences from the source. Use only facts present "
    "in the provided text; if the text is thin, stay general rather than inventing details. "
    "Respond with ONLY a JSON array and no other text."
)

USER_TEMPLATE = """For each article write:
- "summary": 1-2 sentences, at most 45 words, what the article is about.
- "why_it_matters": 1 sentence, at most 30 words, why a working data engineer should care.

Return a JSON array: {{"id": <number>, "summary": "...", "why_it_matters": "..."}}

Articles:
{articles}"""

MAX_SUMMARY_CHARS = 400
MAX_WHY_CHARS = 280


class ArticleSummary(BaseModel):
    id: int
    summary: str
    why_it_matters: str = ""

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("empty summary")
        return truncate(v, MAX_SUMMARY_CHARS)

    @field_validator("why_it_matters")
    @classmethod
    def _why(cls, v: str) -> str:
        return truncate(" ".join(v.split()), MAX_WHY_CHARS)


class ArticleSummarizer:
    def __init__(self, llm: LLMProvider | None, max_article_chars: int = 1500) -> None:
        self.llm = llm
        self.max_article_chars = max_article_chars

    def summarize(self, articles: list[Article]) -> list[Article]:
        """Never raises: any article Claude couldn't summarize gets a short feed-based fallback."""
        summaries: dict[int, ArticleSummary] = {}
        if self.llm and articles:
            try:
                summaries = self._ask_claude(articles)
            except LLMError as exc:
                log.warning("Summarization failed (%s); using fallback text", exc)

        out = []
        for idx, article in enumerate(articles, start=1):
            s = summaries.get(idx)
            if s:
                out.append(article.model_copy(update={"summary": s.summary, "why_it_matters": s.why_it_matters}))
            else:
                out.append(article.model_copy(update={"summary": fallback_summary(article)}))
        return out

    def _ask_claude(self, articles: list[Article]) -> dict[int, ArticleSummary]:
        blocks = [
            f"[{i}] {a.title} ({a.source})\n{truncate(a.description, self.max_article_chars) or '(no description)'}"
            for i, a in enumerate(articles, start=1)
        ]
        prompt = USER_TEMPLATE.format(articles="\n\n".join(blocks))
        for attempt in (1, 2):
            response = self.llm.generate(SYSTEM_PROMPT, prompt, purpose="summarize")
            parsed = parse_summaries(response.text, valid_ids=set(range(1, len(articles) + 1)))
            if parsed:
                if len(parsed) < len(articles):
                    log.warning("Only %d of %d summaries usable", len(parsed), len(articles))
                return parsed
            log.warning("Summarization attempt %d produced no valid items", attempt)
        raise LLMError("Claude returned no valid summaries")


def parse_summaries(text: str, valid_ids: set[int]) -> dict[int, ArticleSummary]:
    out: dict[int, ArticleSummary] = {}
    for obj in extract_json_objects(text):
        try:
            item = ArticleSummary.model_validate(obj)
        except ValidationError as exc:
            log.warning("Dropping invalid summary %r: %s", obj.get("id"), exc.errors()[0]["msg"])
            continue
        if item.id in valid_ids and item.id not in out:
            out[item.id] = item
    return out


def fallback_summary(article: Article) -> str:
    """A short snippet of the feed's own description (or the title), always followed by the link."""
    return truncate(article.description, 220) or article.title
