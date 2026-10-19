"""Async fetching: many URLs at once, with a cap on concurrency."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from xml.etree import ElementTree

import httpx

from .extract import PageSignals, extract_signals

DEFAULT_UA = "seoguard/0.1 (+https://github.com/Virat3690/seoguard)"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_BODY_BYTES = 5 * 1024 * 1024  # skip parsing anything bigger than 5 MB


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    redirects: list[str] = field(default_factory=list)
    content_type: str | None = None
    x_robots_tag: str | None = None
    elapsed_ms: int | None = None
    signals: PageSignals | None = None
    error: str | None = None


RETRY_STATUSES = {429, 503}
MAX_RETRIES = 3


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    """Honour Retry-After (seconds form) when the server sends it, else back off 1s, 2s, 4s."""
    header = resp.headers.get("retry-after", "")
    if header.isdigit():
        return min(float(header), 30.0)
    return float(2 ** attempt)


async def fetch_one(client: httpx.AsyncClient, url: str, sleep=asyncio.sleep) -> FetchResult:
    result = FetchResult(url=url)
    start = time.perf_counter()
    try:
        for attempt in range(MAX_RETRIES + 1):
            resp = await client.get(url)
            if resp.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                break
            await sleep(_retry_delay(resp, attempt))
    except httpx.HTTPError as exc:
        result.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        return result
    finally:
        result.elapsed_ms = round((time.perf_counter() - start) * 1000)

    result.status = resp.status_code
    result.final_url = str(resp.url)
    result.redirects = [str(r.url) for r in resp.history]
    result.content_type = resp.headers.get("content-type")
    result.x_robots_tag = resp.headers.get("x-robots-tag")

    is_html = "html" in (result.content_type or "").lower()
    if is_html and len(resp.content) <= MAX_BODY_BYTES:
        result.signals = extract_signals(resp.text, result.final_url)
    return result


async def crawl(
    urls: Iterable[str],
    concurrency: int = 10,
    timeout: float = 15.0,
    user_agent: str = DEFAULT_UA,
) -> AsyncIterator[FetchResult]:
    """Fetch every URL, yielding results as they finish (not in input order)."""
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=10,
        timeout=timeout,
        limits=limits,
        headers={"User-Agent": user_agent},
        http2=False,
    ) as client:

        async def guarded(u: str) -> FetchResult:
            async with sem:
                return await fetch_one(client, u)

        tasks = [asyncio.create_task(guarded(u)) for u in dict.fromkeys(urls)]
        for done in asyncio.as_completed(tasks):
            yield await done


async def urls_from_sitemap(
    sitemap_url: str, limit: int | None = None, timeout: float = 15.0, _depth: int = 0
) -> list[str]:
    """Read a sitemap or sitemap index and return page URLs."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout,
                                 headers={"User-Agent": DEFAULT_UA}) as client:
        resp = await client.get(sitemap_url)
        resp.raise_for_status()
    if b"<!DOCTYPE" in resp.content[:2048] or b"<!ENTITY" in resp.content[:4096]:
        raise ValueError("Sitemap contains a DTD; refusing to parse it.")
    root = ElementTree.fromstring(resp.content)

    if root.tag == f"{SITEMAP_NS}sitemapindex":
        if _depth >= 2:
            return []
        urls: list[str] = []
        for loc in root.iter(f"{SITEMAP_NS}loc"):
            if limit is not None and len(urls) >= limit:
                break
            child = (loc.text or "").strip()
            if child:
                remaining = None if limit is None else limit - len(urls)
                urls += await urls_from_sitemap(child, remaining, timeout, _depth + 1)
        return urls

    urls = [(loc.text or "").strip() for loc in root.iter(f"{SITEMAP_NS}loc")]
    urls = [u for u in urls if u]
    return urls[:limit] if limit is not None else urls
