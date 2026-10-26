"""End-to-end pipeline tests using fakes for every external system (feeds, Claude, SMTP)."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from src.agents import NewsletterAgent
from src.config import Settings
from src.models import RawArticle
from src.services import CostTracker, EmailError, LLMError, LLMResponse, StorageService

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class FakeCollector:
    def __init__(self, raws, failed=()):
        self.raws, self.failed_feeds = raws, list(failed)

    def collect(self):
        return list(self.raws)


class FakeLLM:
    """Answers both prompts by counting the '[n]' lines it was given."""

    def __init__(self, tracker, fail=False, bad_json=False):
        self.tracker, self.fail, self.bad_json, self.calls = tracker, fail, bad_json, []

    def generate(self, system, user, max_tokens=None, purpose=""):
        self.calls.append(purpose)
        if self.fail:
            raise LLMError("boom")
        n = len(re.findall(r"^\[(\d+)\]", user, re.M))
        if self.bad_json:
            text = "not json"
        elif purpose == "classify":
            text = json.dumps([{"id": i, "category": "Databricks & Spark", "relevance_score": 10 - i % 5,
                                "technologies": ["Spark"], "recommended": True, "is_tutorial": i == 4}
                               for i in range(1, n + 1)])
        else:
            text = json.dumps([{"id": i, "summary": f"AI summary {i}", "why_it_matters": f"AI why {i}"}
                               for i in range(1, n + 1)])
        resp = LLMResponse(text=text, model="claude-haiku-5-5", input_tokens=1000, output_tokens=200)
        self.tracker.record(resp, purpose)
        return resp


class FakeEmail:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, subject, html, text):
        if self.fail:
            raise EmailError("smtp down")
        self.sent.append((subject, html, text))


def raws(n=12, age_days=1):
    sources = ["Databricks Blog", "Azure Blog", "Confluent Blog", "dbt Blog"]  # per-source cap is 4
    return [RawArticle(source=sources[i % 4], title=f"Spark tip number {i}", url=f"https://ex.com/p{i}",
                       published=NOW - timedelta(days=age_days), description=f"All about Spark {i}.")
            for i in range(n)]


@pytest.fixture
def env(tmp_path):
    settings = Settings(max_articles_to_claude=10, max_selected_articles=6, output_dir=tmp_path / "out")
    storage = StorageService(":memory:")
    yield settings, storage, CostTracker()
    storage.close()


def make_agent(env, raw=None, llm="ok", email=None, **kw):
    settings, storage, tracker = env
    llm_obj = FakeLLM(tracker, **kw) if llm else None
    agent = NewsletterAgent(settings, FakeCollector(raw if raw is not None else raws()), storage,
                            llm=llm_obj, cost_tracker=tracker, email=email, now=NOW)
    return agent, llm_obj


def test_happy_path_sends_and_records_everything(env):
    email = FakeEmail()
    agent, llm = make_agent(env, email=email)
    stats = agent.run()

    assert stats.status == "success" and stats.llm_used
    assert (stats.articles_discovered, stats.articles_after_filtering) == (12, 12)
    assert stats.articles_sent_to_claude == 10 and stats.articles_selected == 6
    assert llm.calls == ["classify", "summarize"]  # exactly two Claude calls
    assert stats.input_tokens == 2000 and stats.output_tokens == 400
    assert stats.estimated_cost_usd == pytest.approx(2000 * 0.10 / 1e6 + 400 * 0.50 / 1e6)

    (subject, html, text), = email.sent
    assert "AI summary" in html and "AI why" in html
    out = env[0].output_dir
    assert (out / "newsletter.html").exists() and "run_summary" in (out / "run_summary.md").name
    assert len(env[1].get_sent_ids()) == 6
    assert env[1].run_count() == 1 and env[1].total_cost() == pytest.approx(stats.estimated_cost_usd)


def test_second_run_does_not_resend_delivered_articles(env):
    first = FakeEmail()
    make_agent(env, email=first)[0].run()
    sent_first = env[1].get_sent_ids()

    second = FakeEmail()
    stats = make_agent(env, email=second)[0].run()
    html = second.sent[0][1] if second.sent else ""
    for article_id in sent_first:
        assert env[1].get_article(article_id).title not in html
    assert stats.articles_after_filtering == 12 - len(sent_first)


def test_dry_run_sends_nothing_and_marks_nothing_sent(env):
    email = FakeEmail()
    stats = make_agent(env, email=email)[0].run(dry_run=True)
    assert stats.status == "success" and email.sent == []
    assert env[1].get_sent_ids() == set()
    assert (env[0].output_dir / "newsletter.html").exists()


def test_email_failure_leaves_articles_unsent_and_flags_failure(env):
    stats = make_agent(env, email=FakeEmail(fail=True))[0].run()
    assert stats.status == "email_failed"
    assert env[1].get_sent_ids() == set()  # will be retried next run


def test_claude_failure_falls_back_to_python_ranking(env):
    email = FakeEmail()
    stats = make_agent(env, email=email, fail=True)[0].run()
    assert stats.status == "success" and not stats.llm_used
    assert stats.articles_selected == 6 and len(email.sent) == 1
    assert any("failed" in n for n in stats.notes)


def test_garbage_from_claude_falls_back_without_crashing(env):
    email = FakeEmail()
    stats = make_agent(env, email=email, bad_json=True)[0].run()
    assert stats.status == "success" and len(email.sent) == 1 and stats.articles_selected == 6


def test_no_llm_configured_uses_python_ranking(env):
    email = FakeEmail()
    stats = make_agent(env, llm=None, email=email)[0].run()
    assert stats.status == "success" and not stats.llm_used and stats.articles_sent_to_claude == 0
    assert stats.estimated_cost_usd == 0


def test_lifetime_budget_blocks_claude(env):
    settings, storage, tracker = env
    from src.models import RunStats
    storage.save_run(RunStats(started_at=NOW, estimated_cost_usd=settings.lifetime_budget_usd))
    agent, llm = make_agent(env, email=FakeEmail())
    stats = agent.run()
    assert llm.calls == [] and any("Lifetime budget" in n for n in stats.notes)
    assert stats.status == "success"


def test_per_run_limit_skips_summarization_only(env):
    settings, storage, tracker = env
    settings.max_run_cost_usd = 0.0000001  # trips right after the first Claude call
    agent, llm = make_agent(env, email=FakeEmail())
    stats = agent.run()
    assert llm.calls == ["classify"] and any("Per-run cost limit" in n for n in stats.notes)


def test_stale_or_irrelevant_articles_produce_no_newsletter(env):
    email = FakeEmail()
    old = raws(5, age_days=30)
    stats = make_agent(env, raw=old, email=email)[0].run()
    assert stats.status == "no_content" and email.sent == []


def test_unexpected_error_is_recorded_not_raised(env):
    class Exploding(FakeCollector):
        def collect(self):
            raise RuntimeError("kaboom")

    settings, storage, tracker = env
    agent = NewsletterAgent(settings, Exploding([]), storage, cost_tracker=tracker, now=NOW)
    stats = agent.run()
    assert stats.status == "failed" and "kaboom" in stats.notes[0]
    assert storage.run_count() == 1
