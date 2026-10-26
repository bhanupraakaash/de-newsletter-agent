from datetime import datetime, timedelta, timezone

from src.filters import ArticleRanker
from src.models import Article

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def art(title="x", description="", source="S", kws=(), days_ago=1.0, id=None) -> Article:
    return Article(id=id or title, title=title, source=source, url="https://ex.com/" + (id or title),
                   published_date=NOW - timedelta(days=days_ago), description=description,
                   matched_keywords=list(kws))


def test_title_hit_beats_description_beats_source_only():
    r = ArticleRanker()
    in_title = r.score(art("Spark tuning", kws=["spark"]), NOW)
    in_body = r.score(art("Tuning guide", "all about spark", kws=["spark"]), NOW)
    source_only = r.score(art("v4.0.1", source="Apache Spark Releases", kws=["spark"]), NOW)
    assert in_title > in_body > source_only


def test_newer_scores_higher():
    r = ArticleRanker(lookback_days=7)
    assert r.score(art("Spark", kws=["spark"], days_ago=0.5), NOW) > r.score(art("Spark", kws=["spark"], days_ago=6), NOW)


def test_trusted_source_bonus():
    r = ArticleRanker(source_trust={"Good": 1.5})
    a, b = art("Spark", source="Good", kws=["spark"]), art("Spark", source="Other", kws=["spark"])
    assert r.score(a, NOW) - r.score(b, NOW) == 1.5


def test_multiple_topics_get_bonus_and_score_is_capped():
    r = ArticleRanker()
    one = r.score(art("Spark", kws=["spark"]), NOW)
    two = r.score(art("Spark on Databricks", kws=["spark", "databricks"]), NOW)
    assert two > one
    many = art("a", kws=["spark", "databricks", "kafka", "airflow", "delta lake", "dbt"])
    many = many.model_copy(update={"title": "spark databricks kafka airflow delta lake dbt"})
    assert r.score(many, NOW) <= 10


def test_undated_gets_no_recency_and_does_not_crash():
    r = ArticleRanker()
    a = art("Spark", kws=["spark"]).model_copy(update={"published_date": None})
    assert r._recency(a, NOW) == 0.0


def test_rank_sorts_descending_and_does_not_mutate():
    r = ArticleRanker()
    items = [art("Cooking", kws=["sql"], id="1"), art("Spark and Databricks", kws=["spark", "databricks"], id="2")]
    ranked = r.rank(items, NOW)
    assert [a.id for a in ranked] == ["2", "1"]
    assert items[0].relevance_score == 0.0 and ranked[0].relevance_score > 0


def test_select_top_enforces_per_source_cap_and_limit():
    r = ArticleRanker()
    items = [art(f"Spark {i}", source="Big", kws=["spark"], id=f"b{i}") for i in range(5)]
    items.append(art("Kafka news", source="Small", kws=["kafka"], id="s1"))
    top = r.select_top(items, limit=4, max_per_source=2, now=NOW)
    assert len(top) == 3  # 2 from Big + 1 from Small; nothing else eligible
    assert sum(a.source == "Big" for a in top) == 2
