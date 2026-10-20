from seoguard.audit import audit
from seoguard.crawler import FetchResult
from seoguard.extract import extract_signals
from seoguard.storage import Store


def _rows(tmp_path, *results):
    store = Store(tmp_path / "t.db")
    cid = store.new_crawl("test")
    for r in results:
        store.save(cid, r)
    store.commit()
    rows = store.pages(cid)
    store.close()
    return rows


def test_clean_page_has_no_issues(tmp_path):
    body = "word " * 150
    html = (f"<title>Good</title><meta name=description content=x>"
            f"<link rel=canonical href=https://a.test/><body><h1>H</h1>{body}</body>")
    r = FetchResult(url="https://a.test/", final_url="https://a.test/", status=200,
                    content_type="text/html", signals=extract_signals(html, "https://a.test/"))
    assert audit(_rows(tmp_path, r)) == []


def test_broken_page_flags_expected_rules(tmp_path):
    html = "<meta name=robots content=noindex><body><p>tiny</p></body>"
    bad = FetchResult(url="https://a.test/x", final_url="https://a.test/x", status=200,
                      content_type="text/html", signals=extract_signals(html, "https://a.test/x"))
    gone = FetchResult(url="https://a.test/gone", status=404)
    rules = {(i.url, i.rule, i.severity) for i in audit(_rows(tmp_path, bad, gone))}

    assert ("https://a.test/gone", "status", "error") in rules
    assert ("https://a.test/x", "indexable", "error") in rules
    assert ("https://a.test/x", "title", "error") in rules
    assert ("https://a.test/x", "canonical", "warning") in rules
    assert ("https://a.test/x", "h1", "warning") in rules
    assert ("https://a.test/x", "thin-content", "warning") in rules


def test_long_description_flagged(tmp_path):
    def page(url, desc):
        html = (f'<title>T</title><meta name="description" content="{desc}">'
                f"<link rel=canonical href={url}><body><h1>H</h1>{'word ' * 150}</body>")
        return FetchResult(url=url, final_url=url, status=200, content_type="text/html",
                           signals=extract_signals(html, url))

    long_page = page("https://a.test/long", "x" * 200)
    ok_page = page("https://a.test/ok", "x" * 160)
    hits = [i for i in audit(_rows(tmp_path, long_page, ok_page)) if i.rule == "description-length"]

    assert [(i.url, i.severity) for i in hits] == [("https://a.test/long", "notice")]
    assert "200 chars" in hits[0].message


def test_errors_sort_first(tmp_path):
    ok = FetchResult(url="https://a.test/r", final_url="https://a.test/", status=200,
                     redirects=["https://a.test/r"], content_type="text/html",
                     signals=extract_signals("<title>t</title><body>" + "w " * 200, "https://a.test/"))
    gone = FetchResult(url="https://a.test/gone", status=500)
    issues = audit(_rows(tmp_path, ok, gone))
    assert issues[0].severity == "error"
