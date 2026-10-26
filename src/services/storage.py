"""SQLite persistence: remembers every candidate seen and whether it was delivered."""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.models import Article, RunStats

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    source           TEXT NOT NULL,
    url              TEXT NOT NULL,
    published_date   TEXT,
    description      TEXT NOT NULL DEFAULT '',
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    technologies     TEXT NOT NULL DEFAULT '[]',
    category         TEXT NOT NULL DEFAULT '',
    relevance_score  REAL NOT NULL DEFAULT 0,
    summary          TEXT NOT NULL DEFAULT '',
    why_it_matters   TEXT NOT NULL DEFAULT '',
    processed        INTEGER NOT NULL DEFAULT 0,
    sent             INTEGER NOT NULL DEFAULT 0,
    first_seen       TEXT NOT NULL,
    sent_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_sent ON articles(sent);

CREATE TABLE IF NOT EXISTS runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    status            TEXT NOT NULL,
    dry_run           INTEGER NOT NULL,
    llm_used          INTEGER NOT NULL,
    discovered        INTEGER NOT NULL,
    after_filtering   INTEGER NOT NULL,
    sent_to_claude    INTEGER NOT NULL,
    selected          INTEGER NOT NULL,
    failed_feeds      INTEGER NOT NULL,
    input_tokens      INTEGER NOT NULL,
    output_tokens     INTEGER NOT NULL,
    cost_usd          REAL NOT NULL,
    duration_seconds  REAL NOT NULL
);
"""


class StorageService:
    def __init__(self, db_path: str | Path = "data/datapulse.db") -> None:
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StorageService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- writes -----------------------------------------------------------

    def save_new(self, articles: list[Article]) -> int:
        """Insert articles not seen before. Existing rows (and their sent flag) are untouched."""
        now = _now()
        before = self.conn.total_changes
        with self.conn:  # one transaction
            self.conn.executemany(
                """INSERT OR IGNORE INTO articles
                   (id, title, source, url, published_date, description, matched_keywords, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        a.id, a.title, a.source, a.url,
                        a.published_date.isoformat() if a.published_date else None,
                        a.description, json.dumps(a.matched_keywords), now,
                    )
                    for a in articles
                ],
            )
        inserted = self.conn.total_changes - before
        log.info("Storage: %d new articles saved (%d already known)", inserted, len(articles) - inserted)
        return inserted

    def mark_sent(self, ids: list[str]) -> None:
        with self.conn:
            self.conn.executemany(
                "UPDATE articles SET sent = 1, sent_at = ? WHERE id = ?", [(_now(), i) for i in ids]
            )

    def mark_processed(self, ids: list[str]) -> None:
        with self.conn:
            self.conn.executemany("UPDATE articles SET processed = 1 WHERE id = ?", [(i,) for i in ids])

    def update_enrichment(self, article: Article) -> None:
        """Persist what later phases add (category, scores, summary...)."""
        with self.conn:
            self.conn.execute(
                """UPDATE articles SET category=?, technologies=?, relevance_score=?,
                   summary=?, why_it_matters=? WHERE id=?""",
                (
                    article.category, json.dumps(article.technologies), article.relevance_score,
                    article.summary, article.why_it_matters, article.id,
                ),
            )

    def save_run(self, stats: RunStats) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO runs (started_at, status, dry_run, llm_used, discovered, after_filtering,
                   sent_to_claude, selected, failed_feeds, input_tokens, output_tokens, cost_usd, duration_seconds)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stats.started_at.isoformat(), stats.status, int(stats.dry_run), int(stats.llm_used),
                    stats.articles_discovered, stats.articles_after_filtering, stats.articles_sent_to_claude,
                    stats.articles_selected, stats.failed_feeds, stats.input_tokens, stats.output_tokens,
                    stats.estimated_cost_usd, stats.duration_seconds,
                ),
            )

    # --- reads ------------------------------------------------------------

    def total_cost(self) -> float:
        """Estimated API spend recorded across all runs so far (USD)."""
        return self.conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM runs").fetchone()[0]

    def run_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def get_sent_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT id FROM articles WHERE sent = 1").fetchall()
        return {r["id"] for r in rows}

    def get_article(self, article_id: str) -> Article | None:
        row = self.conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return _row_to_article(row) if row else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=row["id"], title=row["title"], source=row["source"], url=row["url"],
        published_date=datetime.fromisoformat(row["published_date"]) if row["published_date"] else None,
        description=row["description"],
        matched_keywords=json.loads(row["matched_keywords"]),
        technologies=json.loads(row["technologies"]),
        category=row["category"], relevance_score=row["relevance_score"],
        summary=row["summary"], why_it_matters=row["why_it_matters"],
        processed=bool(row["processed"]), sent=bool(row["sent"]),
    )
