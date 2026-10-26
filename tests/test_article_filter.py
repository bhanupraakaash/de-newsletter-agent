from datetime import datetime, timedelta, timezone

from src.filters import ArticleFilter
from src.models import Article

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def art(title="x", description="", source="S", days_ago: float | None = 1) -> Article:
    published = None if days_ago is None else NOW - timedelta(days=days_ago)
    return Article(id=title, title=title, source=source, url="https://ex.com/" + title,
                   published_date=published, description=description)


def test_date_filter_keeps_recent_drops_old_and_undated():
    f = ArticleFilter(lookback_days=7)
    items = [art("new", days_ago=1), art("edge", days_ago=6.9), art("old", days_ago=8), art("none", days_ago=None)]
    assert [a.title for a in f.filter_by_date(items, now=NOW)] == ["new", "edge"]


def test_date_filter_drops_far_future_dates():
    f = ArticleFilter(lookback_days=7)
    assert f.filter_by_date([art("future", days_ago=-30)], now=NOW) == []


def test_keyword_filter_is_case_insensitive_and_records_matches():
    f = ArticleFilter(keywords=["spark", "delta lake"])
    (kept,) = f.filter_by_keywords([art("Intro to SPARK and Delta Lake")])
    assert set(kept.matched_keywords) == {"spark", "delta lake"}


def test_keyword_filter_uses_whole_words():
    f = ArticleFilter(keywords=["spark", "rag", "sql"])
    items = [art("Sparkling water"), art("Cloud storage tips"), art("NoSQL stores")]
    assert f.filter_by_keywords(items) == []


def test_keyword_matches_description_and_source():
    f = ArticleFilter(keywords=["spark", "kafka"])
    items = [
        art("v4.0.1", source="Apache Spark Releases"),
        art("Release notes", description="Improvements to the Kafka client"),
        art("Cooking tips"),
    ]
    assert [a.title for a in f.filter_by_keywords(items)] == ["v4.0.1", "Release notes"]


def test_filtering_does_not_mutate_input():
    f = ArticleFilter(keywords=["spark"])
    original = art("spark news")
    f.filter_by_keywords([original])
    assert original.matched_keywords == []
