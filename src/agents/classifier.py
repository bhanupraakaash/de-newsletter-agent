"""Phase 8: one Claude call classifies and scores all candidates; Python then selects the winners."""
import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.agents.json_utils import extract_json_objects
from src.filters.keywords import KEYWORD_TOPIC
from src.models import CATEGORIES, TOPIC_TO_CATEGORY, Article
from src.services.llm import LLMError, LLMProvider

log = logging.getLogger(__name__)

Category = Literal[
    "Databricks & Spark", "Azure Data Engineering", "Data & AI",
    "Tools / Open Source", "Architecture & Practices",
]

SYSTEM_PROMPT = (
    "You are the editor of a weekly newsletter for professional data engineers "
    "(Databricks, Spark, PySpark, Azure data services, SQL, Delta Lake, Airflow, Kafka, "
    "architecture, data quality, GenAI for data work). Judge articles strictly on usefulness "
    "to a working data engineer. Respond with ONLY a JSON array and no other text."
)

USER_TEMPLATE = """Rate each article below.

Categories (use exactly one of these strings): {categories}

Return a JSON array with one object per article, in this exact shape:
{{"id": <number>, "category": "<category>", "relevance_score": <1-10>, "technologies": ["<up to 4 names>"], "recommended": <true|false>, "is_tutorial": <true|false>}}

Scoring guide: 9-10 = important news or a must-read technical deep dive; 6-8 = solid and useful; \
1-4 = marketing, off-topic, trivial release candidates or patch notes.
recommended = true only if it deserves a place in this week's issue.
is_tutorial = true if it teaches how to do something (guide, walkthrough, deep dive).

Articles:
{articles}"""


class ArticleClassification(BaseModel):
    """Validated shape of one item in Claude's answer. Invalid items are dropped, not trusted."""

    id: int
    category: Category
    relevance_score: float = Field(ge=1, le=10)
    technologies: list[str] = Field(default_factory=list)
    recommended: bool
    is_tutorial: bool = False

    @field_validator("technologies")
    @classmethod
    def _clean_technologies(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if isinstance(t, str) and t.strip()][:6]


class ArticleClassifier:
    def __init__(
        self, llm: LLMProvider, max_selected: int = 10, description_chars: int = 400, min_selected: int = 8
    ) -> None:
        self.llm = llm
        self.max_selected = max_selected
        self.min_selected = min(min_selected, max_selected)
        self.description_chars = description_chars

    def classify_and_select(self, candidates: list[Article]) -> list[Article]:
        """Classify with Claude, then pick the final articles. Raises LLMError if Claude is unusable."""
        results = self._classify(candidates)

        rows = []  # (article enriched with Claude's view, classification, python score)
        for idx, article in enumerate(candidates, start=1):
            cls = results.get(idx)
            if cls is None:
                continue  # Claude skipped or garbled this one
            enriched = article.model_copy(update={
                "category": cls.category,
                "relevance_score": cls.relevance_score,
                "technologies": cls.technologies,
                "is_learning_resource": cls.is_tutorial,
                "processed": True,
            })
            rows.append((enriched, cls, article.relevance_score))

        def best_first(r):
            return (-r[1].relevance_score, -r[2])

        chosen = sorted((r for r in rows if r[1].recommended), key=best_first)[: self.max_selected]
        if len(chosen) < self.min_selected:  # pad with solid-but-unrecommended items
            extras = sorted(
                (r for r in rows if not r[1].recommended and r[1].relevance_score >= 5), key=best_first
            )
            chosen += extras[: self.min_selected - len(chosen)]
        log.info("Classifier: %d classified of %d, %d selected", len(results), len(candidates), len(chosen))
        return [r[0] for r in chosen]

    def _classify(self, candidates: list[Article]) -> dict[int, ArticleClassification]:
        lines = [
            f"[{i}] {a.title} | {a.source} | {_clip(a.description, self.description_chars)}"
            for i, a in enumerate(candidates, start=1)
        ]
        prompt = USER_TEMPLATE.format(categories="; ".join(CATEGORIES), articles="\n".join(lines))

        for attempt in (1, 2):  # one retry only: every retry costs money
            response = self.llm.generate(SYSTEM_PROMPT, prompt, purpose="classify")
            if response.truncated:
                log.warning("Classification output was truncated; salvaging complete items")
            parsed = parse_classifications(response.text, valid_ids=set(range(1, len(candidates) + 1)))
            if parsed:
                return parsed
            log.warning("Classification attempt %d produced no valid items", attempt)
        raise LLMError("Claude returned no valid classifications")


def parse_classifications(text: str, valid_ids: set[int]) -> dict[int, ArticleClassification]:
    out: dict[int, ArticleClassification] = {}
    for obj in extract_json_objects(text):
        try:
            item = ArticleClassification.model_validate(obj)
        except ValidationError as exc:
            log.warning("Dropping invalid classification %r: %s", obj.get("id"), exc.errors()[0]["msg"])
            continue
        if item.id in valid_ids and item.id not in out:
            out[item.id] = item
    return out


def fallback_select(candidates: list[Article], limit: int) -> list[Article]:
    """No-LLM path: trust the Python score and infer category/technologies from keywords."""
    selected = []
    for a in candidates[:limit]:  # candidates arrive already ranked
        topics = [KEYWORD_TOPIC[k] for k in a.matched_keywords if k in KEYWORD_TOPIC]
        category = TOPIC_TO_CATEGORY.get(topics[0], "Tools / Open Source") if topics else "Tools / Open Source"
        techs = list(dict.fromkeys(topics))[:4]
        selected.append(a.model_copy(update={"category": category, "technologies": techs}))
    return selected


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"
