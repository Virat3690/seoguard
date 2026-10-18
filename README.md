# seoguard

Async SEO crawler. Fetches many URLs at once, pulls out the signals search engines care about, saves them to SQLite and reports issues.

Phase 0 of a bigger plan: later versions diff production against preview deploys and run in CI.

## Install (dev)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

## Use

```bash
# A few URLs
seoguard crawl https://example.com https://example.com/about

# From a sitemap (follows sitemap indexes), first 500 URLs, 20 at a time
seoguard crawl --sitemap https://example.com/sitemap.xml --limit 500 -c 20

# From a file, one URL per line
seoguard crawl -f urls.txt --label "before-redesign"

# Audit the latest crawl
seoguard report
seoguard report --severity error
```

Results land in `seoguard.db` (change with `--db`). Open it with any SQLite tool to explore:

```sql
SELECT url, status, title, word_count FROM pages WHERE crawl_id = 1 ORDER BY word_count;
```

## What it records per URL

Status code, redirect chain, final URL, content type, `X-Robots-Tag`, response time, `<title>`, meta description, canonical, meta robots, `<h1>` list, hreflang, internal/external link counts, word count of raw HTML.

## Rules in `seoguard report`

| Rule | Flags |
|---|---|
| status | fetch errors, 4xx/5xx |
| redirects | redirects and chains of 2+ hops |
| title | missing, or over 60 chars |
| description | missing meta description |
| canonical | missing, or pointing to a different URL |
| indexable | `noindex` in meta robots or `X-Robots-Tag` |
| h1 | missing or multiple |
| thin-content | under 100 words in raw HTML (thin, or rendered by JavaScript) |

Add a rule: write a function in `src/seoguard/audit.py` and register it in `RULES`.

## Layout

```
src/seoguard/
  crawler.py   async fetching (httpx), sitemap reader
  extract.py   HTML → SEO signals (selectolax), pure functions
  storage.py   SQLite schema and writes
  audit.py     rules that turn rows into issues
  cli.py       typer commands
tests/         pytest + respx (no real network)
```

## Test

```bash
pytest
```

## Be polite

Crawl sites you own or have permission to crawl. Keep `--concurrency` low on small sites. robots.txt support is on the roadmap.
