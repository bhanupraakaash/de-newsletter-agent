import httpx

from src.collectors import FeedConfig, RSSCollector

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
  <item><title>Spark 4 released</title><link>https://ex.com/a</link>
    <pubDate>Mon, 20 Oct 2026 10:00:00 GMT</pubDate><description>Big news</description></item>
  <item><title>No link here</title></item>
  <item><title>No date</title><link>https://ex.com/b</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Rel</title>
  <entry><title>v1.2.0</title><link href="https://gh.com/r/1.2.0"/>
    <updated>2026-10-21T08:30:00Z</updated></entry>
</feed>"""

FEED_A = FeedConfig(name="A", url="https://a.test/feed")
FEED_B = FeedConfig(name="B", url="https://b.test/feed")


def make_collector(handler, feeds, **kw) -> RSSCollector:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RSSCollector(feeds, client=client, backoff_seconds=0, **kw)


def test_parse_rss_skips_items_without_link():
    items = RSSCollector.parse(RSS, FEED_A)
    assert [a.title for a in items] == ["Spark 4 released", "No date"]
    assert items[0].published.year == 2026 and items[0].published.tzinfo is not None
    assert items[0].description == "Big news"
    assert items[1].published is None


def test_parse_atom_uses_updated_date():
    (item,) = RSSCollector.parse(ATOM, FEED_A)
    assert item.url == "https://gh.com/r/1.2.0"
    assert item.published.day == 21


def test_failing_feed_does_not_stop_others():
    def handler(req):
        if req.url.host == "a.test":
            return httpx.Response(404)
        return httpx.Response(200, content=ATOM)

    c = make_collector(handler, [FEED_A, FEED_B])
    articles = c.collect()
    assert len(articles) == 1 and articles[0].source == "B"
    assert c.failed_feeds == ["A"]


def test_retries_transient_errors_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, content=ATOM)

    c = make_collector(handler, [FEED_A])
    assert len(c.collect()) == 1
    assert calls["n"] == 3


def test_does_not_retry_404():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(404)

    make_collector(handler, [FEED_A]).collect()
    assert calls["n"] == 1


def test_garbage_content_marks_feed_failed():
    c = make_collector(lambda r: httpx.Response(200, content=b"<html>not a feed"), [FEED_A])
    assert c.collect() == []
    assert c.failed_feeds == ["A"]
