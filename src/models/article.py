"""The clean, validated article that flows through the rest of the pipeline."""
from datetime import datetime

from pydantic import BaseModel, Field


class Article(BaseModel):
    id: str  # stable hash of the normalized URL
    title: str
    source: str
    url: str  # normalized
    published_date: datetime | None = None  # timezone-aware UTC
    description: str = ""  # plain text, truncated

    # Filled in by later phases
    matched_keywords: list[str] = Field(default_factory=list)  # Phase 4
    relevance_score: float = 0.0  # Phase 6 (Python), then Phase 8 (Claude, 1-10)
    category: str = ""  # Phase 8
    technologies: list[str] = Field(default_factory=list)  # Phase 8
    is_learning_resource: bool = False  # Phase 8: tutorial/deep-dive, eligible for "Learning Pick"
    summary: str = ""  # Phase 9
    why_it_matters: str = ""  # Phase 9
    processed: bool = False
    sent: bool = False
