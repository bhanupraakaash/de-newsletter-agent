from datetime import datetime, timezone

import pytest

from src.filters import DeduplicationService
from src.models import Article
from src.services import StorageService


def art(id="a1", title="Spark 4 released", description="", url=None, **kw) -> Article:
    return Article(
        id=id, title=title, source="S", url=url or f"https://ex.com/{id}",
        published_date=datetime(2026, 10, 25, tzinfo=timezone.utc), description=description, **kw,
    )


@pytest.fixture
def db():
    with StorageService(":memory:") as s:
        yield s


# --- deduplication ---------------------------------------------------------

def test_removes_already_sent():
    out = DeduplicationService().deduplicate([art("a1"), art("a2", title="Other")], sent_ids={"a1"})
    assert [a.id for a in out] == ["a2"]


def test_same_id_collapses():
    out = DeduplicationService().dedupe_batch([art("a1"), art("a1", title="Different title")])
    assert len(out) == 1


def test_same_title_different_url_collapses_and_keeps_richest():
    short = art("a1", title="Spark 4.0: What's New?", description="x")
    long = art("a2", title="spark 4 0 whats new", description="a much longer description")
    out = DeduplicationService().dedupe_batch([short, long])
    assert [a.id for a in out] == ["a2"]


def test_distinct_articles_survive_in_order():
    items = [art("a1", title="One"), art("a2", title="Two"), art("a3", title="Three")]
    assert [a.id for a in DeduplicationService().dedupe_batch(items)] == ["a1", "a2", "a3"]


# --- storage ---------------------------------------------------------------

def test_save_and_roundtrip(db):
    a = art(matched_keywords=["spark"], description="desc")
    assert db.save_new([a]) == 1
    loaded = db.get_article("a1")
    assert loaded == a


def test_save_new_is_idempotent(db):
    assert db.save_new([art("a1"), art("a2", title="Two")]) == 2
    assert db.save_new([art("a1"), art("a3", title="Three")]) == 1
    assert db.count() == 3


def test_mark_sent_persists_and_survives_resave(db):
    db.save_new([art("a1")])
    db.mark_sent(["a1"])
    db.save_new([art("a1")])  # a later run sees the same article again
    assert db.get_sent_ids() == {"a1"}
    assert db.get_article("a1").sent is True


def test_update_enrichment(db):
    a = art("a1")
    db.save_new([a])
    db.update_enrichment(a.model_copy(update={
        "category": "Spark", "technologies": ["Spark"], "relevance_score": 8.5,
        "summary": "s", "why_it_matters": "w",
    }))
    got = db.get_article("a1")
    assert (got.category, got.technologies, got.relevance_score) == ("Spark", ["Spark"], 8.5)


def test_sent_articles_filtered_end_to_end(db):
    db.save_new([art("a1"), art("a2", title="Two")])
    db.mark_sent(["a1"])
    out = DeduplicationService().deduplicate([art("a1"), art("a2", title="Two")], db.get_sent_ids())
    assert [a.id for a in out] == ["a2"]


def test_file_database_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "x.db"
    with StorageService(path) as s:
        s.save_new([art()])
    assert path.exists()
