"""Phase 10: turns selected articles into an HTML + plain-text newsletter."""
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from src.models import CATEGORIES, Article

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TOP_STORY_COUNT = 3


class Newsletter(BaseModel):
    subject: str
    html: str
    text: str


class NewsletterBuilder:
    def __init__(self, template_dir: Path = TEMPLATE_DIR) -> None:
        # autoescape=True explicitly: the template name ends in .j2, which Jinja's default
        # extension-based autoescape would NOT cover. Feed titles are untrusted input.
        self.env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)

    def build(self, articles: list[Article], issue_date: date) -> Newsletter:
        top, sections, learning = self._layout(articles)
        subject = f"DataPulse AI: Weekly Data Engineering Intelligence ({issue_date.strftime('%b %d, %Y')})"
        html = self.env.get_template("newsletter.html.j2").render(
            subject=subject, issue_date=issue_date,
            top_stories=top, sections=sections, learning_pick=learning,
        )
        return Newsletter(subject=subject, html=html, text=self._text(issue_date, top, sections, learning))

    @staticmethod
    def _layout(articles: list[Article]):
        ordered = sorted(articles, key=lambda a: -a.relevance_score)
        top, rest = ordered[:TOP_STORY_COUNT], ordered[TOP_STORY_COUNT:]
        learning = next((a for a in rest if a.is_learning_resource), None)
        rest = [a for a in rest if a is not learning]

        sections = [(c, [a for a in rest if a.category == c]) for c in CATEGORIES]
        other = [a for a in rest if a.category not in CATEGORIES]
        if other:
            sections.append(("More Reads", other))
        return top, [(c, items) for c, items in sections if items], learning

    @staticmethod
    def _text(issue_date, top, sections, learning) -> str:
        def block(a: Article, n: int | None = None) -> str:
            head = f"{n}. {a.title}" if n else a.title
            meta = f"   {a.source}" + (f" | {a.published_date:%b %d, %Y}" if a.published_date else "")
            lines = [head, meta]
            if a.summary:
                lines.append(f"   Summary: {a.summary}")
            if a.why_it_matters:
                lines.append(f"   Why this matters: {a.why_it_matters}")
            if a.technologies:
                lines.append(f"   Technologies: {' | '.join(a.technologies)}")
            lines.append(f"   Read: {a.url}")
            return "\n".join(lines)

        parts = [f"DataPulse AI - Weekly Data Engineering Intelligence\n{issue_date:%B %d, %Y}"]
        if top:
            parts.append("TOP STORIES\n\n" + "\n\n".join(block(a, i) for i, a in enumerate(top, 1)))
        for title, items in sections:
            parts.append(title.upper() + "\n\n" + "\n\n".join(block(a) for a in items))
        if learning:
            parts.append("WEEKLY LEARNING PICK\n\n" + block(learning))
        parts.append("Summaries are AI-generated; always check the original article.")
        return "\n\n".join(parts) + "\n"
