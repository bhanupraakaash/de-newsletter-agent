import smtplib
from datetime import date, datetime, timezone

import pytest

from src.models import Article, RunStats
from src.services import EmailError, EmailService, NewsletterBuilder, render_run_summary

DAY = date(2026, 10, 26)


def art(i, score=8, cat="Databricks & Spark", **kw) -> Article:
    return Article(id=f"a{i}", title=f"Title {i}", source="Src", url=f"https://ex.com/p{i}",
                   published_date=datetime(2026, 10, 24, tzinfo=timezone.utc), relevance_score=score,
                   category=cat, summary=f"Summary {i}", why_it_matters=f"Matters {i}",
                   technologies=["Spark", "Delta"], **kw)


# --- newsletter --------------------------------------------------------------

def test_layout_top_stories_sections_and_learning_pick():
    items = [
        art(1, 10), art(2, 9), art(3, 8),                       # top stories
        art(4, 7, "Azure Data Engineering"),
        art(5, 6, "Data & AI"),
        art(6, 5, "Tools / Open Source", is_learning_resource=True),
    ]
    nl = NewsletterBuilder().build(items, DAY)
    html = nl.html
    assert "TOP STORIES" in html and "AZURE DATA ENGINEERING" in html and "DATA &amp; AI" in html
    assert "WEEKLY LEARNING PICK" in html
    assert "TOOLS / OPEN SOURCE" not in html  # its only article became the learning pick
    assert html.index("TOP STORIES") < html.index("AZURE DATA ENGINEERING") < html.index("WEEKLY LEARNING PICK")
    for i in range(1, 7):
        assert f'href="https://ex.com/p{i}"' in html
        assert html.count(f"Title {i}</a>") == 1  # no article appears twice
    assert "Why this matters:" in html and "Spark | Delta" in html and "Read Article" in html
    assert "Oct 24, 2026" in html and "October 26, 2026" in html


def test_empty_sections_and_missing_fields_are_omitted():
    bare = Article(id="x", title="Only", source="S", url="https://ex.com/x", category="Data & AI")
    html = NewsletterBuilder().build([bare], DAY).html
    assert "LEARNING PICK" not in html and "Why this matters" not in html and "Technologies" not in html
    assert "AZURE DATA ENGINEERING" not in html


def test_untrusted_feed_content_is_escaped():
    evil = art(1).model_copy(update={"title": "<script>alert(1)</script>", "summary": "<img src=x onerror=y>"})
    html = NewsletterBuilder().build([evil], DAY).html
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html


def test_unknown_category_goes_to_more_reads():
    items = [art(i, 10 - i) for i in range(1, 4)] + [art(4, 1, "Something Else")]
    assert "MORE READS" in NewsletterBuilder().build(items, DAY).html


def test_subject_and_plain_text():
    nl = NewsletterBuilder().build([art(1), art(2)], DAY)
    assert "DataPulse AI" in nl.subject and "Oct 26, 2026" in nl.subject
    assert "TOP STORIES" in nl.text and "https://ex.com/p1" in nl.text and "<" not in nl.text.replace("<<", "")


def test_run_summary_report():
    stats = RunStats(started_at=datetime(2026, 10, 26, tzinfo=timezone.utc), status="success",
                     articles_discovered=150, articles_selected=9, input_tokens=5000, output_tokens=900,
                     estimated_cost_usd=0.00095, notes=["a note"])
    report = render_run_summary(stats, lifetime_cost=0.0123, lifetime_budget=5.0)
    assert "150" in report and "$0.00095" in report and "$0.0123 of $5.00" in report and "- a note" in report


# --- email -------------------------------------------------------------------

class FakeSMTP:
    instances = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.sent, self.tls, self.login_args = host, port, [], False, None
        FakeSMTP.instances.append(self)

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.tls = True

    def login(self, u, p):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.login_args = (u, p)

    def send_message(self, msg): self.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail_login = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def service(**kw):
    args = dict(host="smtp.test", port=587, username="u@x.com", password="pw", sender="", recipients=["a@x.com", "b@x.com"])
    return EmailService(**{**args, **kw})


def test_send_builds_multipart_message(smtp):
    service().send("Subj", "<p>hi</p>", "hi")
    (server,) = smtp.instances
    assert server.tls and server.login_args == ("u@x.com", "pw")
    (msg,) = server.sent
    assert msg["Subject"] == "Subj" and msg["From"] == "u@x.com" and msg["To"] == "a@x.com, b@x.com"
    types = [p.get_content_type() for p in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]


def test_port_465_uses_implicit_ssl_without_starttls(smtp):
    service(port=465).send("S", "<p>x</p>", "x")
    assert smtp.instances[0].tls is False


def test_bad_credentials_give_helpful_error(smtp):
    smtp.fail_login = True
    with pytest.raises(EmailError, match="App Password"):
        service().send("S", "h", "t")


def test_network_failure_becomes_email_error(monkeypatch):
    def boom(*a, **k): raise OSError("unreachable")
    monkeypatch.setattr(smtplib, "SMTP", boom)
    with pytest.raises(EmailError, match="unreachable"):
        service().send("S", "h", "t")


def test_unconfigured_service_refuses_to_build():
    with pytest.raises(EmailError):
        service(password="")
    with pytest.raises(EmailError):
        service(recipients=[])
