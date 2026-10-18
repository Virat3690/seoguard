"""Pull SEO signals out of one HTML page.

Pure functions only: no network, no disk. That keeps them fast and easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser


@dataclass
class PageSignals:
    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    meta_robots: str | None = None
    h1: list[str] = field(default_factory=list)
    hreflang: list[tuple[str, str]] = field(default_factory=list)  # (lang, href)
    internal_links: int = 0
    external_links: int = 0
    word_count: int = 0

    @property
    def noindex(self) -> bool:
        return bool(self.meta_robots and "noindex" in self.meta_robots.lower())


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    return text or None


def _same_site(host_a: str, host_b: str) -> bool:
    """Treat www.example.com and example.com as the same site."""
    strip = lambda h: h.lower().removeprefix("www.")
    return strip(host_a) == strip(host_b)


def extract_signals(html: str, page_url: str) -> PageSignals:
    tree = HTMLParser(html)
    s = PageSignals()

    if (node := tree.css_first("head > title")) or (node := tree.css_first("title")):
        s.title = _clean(node.text())

    for meta in tree.css("meta[name]"):
        name = (meta.attributes.get("name") or "").lower()
        content = _clean(meta.attributes.get("content"))
        if name == "description" and s.meta_description is None:
            s.meta_description = content
        elif name == "robots" and s.meta_robots is None:
            s.meta_robots = content

    for link in tree.css("link[rel]"):
        rel = (link.attributes.get("rel") or "").lower().split()
        href = link.attributes.get("href")
        if not href:
            continue
        if "canonical" in rel and s.canonical is None:
            s.canonical = urljoin(page_url, href.strip())
        elif "alternate" in rel and (lang := link.attributes.get("hreflang")):
            s.hreflang.append((lang, urljoin(page_url, href.strip())))

    s.h1 = [t for n in tree.css("h1") if (t := _clean(n.text()))]

    page_host = urlsplit(page_url).hostname or ""
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        host = urlsplit(urljoin(page_url, href)).hostname or ""
        if _same_site(host, page_host):
            s.internal_links += 1
        else:
            s.external_links += 1

    # Word count of visible body text: drop script/style/noscript first.
    body = tree.body
    if body is not None:
        for junk in body.css("script, style, noscript, template"):
            junk.decompose()
        s.word_count = len(body.text(separator=" ").split())

    return s
