from src.models import RawArticle
from src.services.normalizer import ArticleNormalizer, clean_text, make_id, normalize_url, truncate


def raw(**kw) -> RawArticle:
    base = dict(source="S", title="T", url="https://ex.com/a")
    return RawArticle(**{**base, **kw})


def test_clean_text_strips_html_entities_and_whitespace():
    html_in = "<p>Hello&nbsp;<b>world</b></p><p>Tom &amp; Jerry</p><script>x()</script>"
    assert clean_text(html_in) == "Hello world Tom & Jerry"


def test_normalize_url_removes_tracking_fragment_and_slash():
    url = "HTTP://Ex.com/post/?utm_source=x&b=2&a=1&fbclid=z#section"
    assert normalize_url(url) == "https://ex.com/post?a=1&b=2"


def test_same_article_different_urls_same_id():
    a = normalize_url("https://ex.com/p?utm_medium=rss")
    b = normalize_url("http://EX.com/p/")
    assert make_id(a) == make_id(b)


def test_truncate_at_word_boundary():
    out = truncate("alpha beta gamma delta", 12)
    assert out == "alpha beta…"
    assert truncate("short", 12) == "short"


def test_normalize_builds_clean_article():
    n = ArticleNormalizer(max_description_chars=20)
    art = n.normalize(raw(title=" <b>Spark</b> 4 ", description="<p>" + "word " * 20 + "</p>"))
    assert art.title == "Spark 4"
    assert len(art.description) <= 21
    assert art.description.endswith("…")
    assert len(art.id) == 16


def test_unusable_items_are_dropped():
    n = ArticleNormalizer()
    assert n.normalize(raw(title="  ")) is None
    assert n.normalize(raw(url="javascript:alert(1)")) is None
    assert n.normalize_all([raw(), raw(title="")]) != []
    assert len(n.normalize_all([raw(), raw(title="")])) == 1
