import httpx
import respx

from seoguard.crawler import crawl, fetch_one, urls_from_sitemap

HTML = "<html><head><title>Hi</title></head><body><h1>Hi</h1></body></html>"


@respx.mock
async def test_crawl_follows_redirects_and_extracts():
    respx.get("https://a.test/old").mock(
        return_value=httpx.Response(301, headers={"Location": "https://a.test/new"}))
    respx.get("https://a.test/new").mock(
        return_value=httpx.Response(200, html=HTML, headers={"X-Robots-Tag": "noindex"}))
    respx.get("https://a.test/missing").mock(return_value=httpx.Response(404, text="nope"))

    results = {r.url: r async for r in crawl(["https://a.test/old", "https://a.test/missing"])}

    old = results["https://a.test/old"]
    assert old.status == 200
    assert old.final_url == "https://a.test/new"
    assert old.redirects == ["https://a.test/old"]
    assert old.x_robots_tag == "noindex"
    assert old.signals.title == "Hi"

    missing = results["https://a.test/missing"]
    assert missing.status == 404
    assert missing.signals is None  # text/plain is not parsed


@respx.mock
async def test_crawl_records_network_errors():
    respx.get("https://down.test/").mock(side_effect=httpx.ConnectError("refused"))
    [r] = [r async for r in crawl(["https://down.test/"])]
    assert r.status is None
    assert r.error.startswith("ConnectError")


@respx.mock
async def test_fetch_retries_on_429():
    route = respx.get("https://busy.test/").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "5"}),
        httpx.Response(200, html=HTML),
    ])
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    async with httpx.AsyncClient() as client:
        r = await fetch_one(client, "https://busy.test/", sleep=fake_sleep)
    assert r.status == 200 and route.call_count == 2 and waits == [5.0]


@respx.mock
async def test_crawl_dedupes_urls():
    route = respx.get("https://a.test/").mock(return_value=httpx.Response(200, html=HTML))
    results = [r async for r in crawl(["https://a.test/"] * 3)]
    assert len(results) == 1 and route.call_count == 1


@respx.mock
async def test_sitemap_index():
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    respx.get("https://a.test/sitemap.xml").mock(return_value=httpx.Response(
        200, text=f"<sitemapindex {ns}><sitemap><loc>https://a.test/s1.xml</loc></sitemap></sitemapindex>"))
    respx.get("https://a.test/s1.xml").mock(return_value=httpx.Response(
        200, text=f"<urlset {ns}><url><loc>https://a.test/1</loc></url><url><loc>https://a.test/2</loc></url></urlset>"))

    assert await urls_from_sitemap("https://a.test/sitemap.xml") == ["https://a.test/1", "https://a.test/2"]
    assert await urls_from_sitemap("https://a.test/sitemap.xml", limit=1) == ["https://a.test/1"]
