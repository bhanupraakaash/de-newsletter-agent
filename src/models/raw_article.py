"""The unprocessed shape of an item as it arrives from a feed."""
from datetime import datetime

from pydantic import BaseModel


class RawArticle(BaseModel):
    source: str
    title: str
    url: str
    published: datetime | None = None  # timezone-aware UTC when present
    description: str = ""
    feed_url: str = ""
