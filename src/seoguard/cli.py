"""Command line: `seoguard crawl ...` and `seoguard report ...`."""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from .audit import audit
from .crawler import crawl as crawl_urls
from .crawler import urls_from_sitemap
from .storage import Store

app = typer.Typer(help="Async SEO crawler.", no_args_is_help=True)
console = Console()

SEVERITY_STYLE = {"error": "bold red", "warning": "yellow", "notice": "cyan"}


def _load_urls(urls: list[str], file: Optional[Path]) -> list[str]:
    out = list(urls)
    if file:
        out += [ln.strip() for ln in file.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")]
    return out


@app.command()
def crawl(
    urls: list[str] = typer.Argument(None, help="URLs to fetch."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Text file, one URL per line."),
    sitemap: Optional[str] = typer.Option(None, "--sitemap", "-s", help="Sitemap or sitemap index URL."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max URLs to crawl."),
    concurrency: int = typer.Option(10, "--concurrency", "-c", min=1, max=100),
    timeout: float = typer.Option(15.0, "--timeout"),
    db: Path = typer.Option(Path("seoguard.db"), "--db", help="SQLite file to write."),
    label: Optional[str] = typer.Option(None, "--label", help="Name for this crawl run."),
):
    """Fetch URLs, extract SEO signals, save them to SQLite."""
    targets = _load_urls(urls or [], file)
    if sitemap:
        try:
            targets += asyncio.run(urls_from_sitemap(sitemap, limit=limit))
        except httpx.HTTPStatusError as exc:
            console.print(f"[red]Sitemap returned HTTP {exc.response.status_code}:[/] {sitemap}")
            raise typer.Exit(1)
        except (httpx.HTTPError, ValueError, ElementTree.ParseError) as exc:
            console.print(f"[red]Could not read sitemap:[/] {exc}")
            raise typer.Exit(1)
    targets = list(dict.fromkeys(targets))[:limit] if limit else list(dict.fromkeys(targets))
    if not targets:
        console.print("[red]No URLs given.[/] Pass URLs, --file or --sitemap.")
        raise typer.Exit(1)

    store = Store(db)
    crawl_id = store.new_crawl(label)
    statuses: Counter[str] = Counter()

    async def run() -> None:
        with Progress(TextColumn("[bold]Crawling"), BarColumn(), MofNCompleteColumn(),
                      TimeElapsedColumn(), console=console) as bar:
            task = bar.add_task("crawl", total=len(targets))
            i = 0
            async for result in crawl_urls(targets, concurrency=concurrency, timeout=timeout):
                store.save(crawl_id, result)
                statuses[str(result.status) if result.status else "error"] += 1
                bar.advance(task)
                i += 1
                if i % 50 == 0:
                    store.commit()
        store.commit()

    asyncio.run(run())
    store.close()
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(statuses.items()))
    console.print(f"Crawl [bold]#{crawl_id}[/] saved to {db}  ({summary})")
    console.print(f"Next: [bold]seoguard report --db {db}[/]")


@app.command()
def report(
    db: Path = typer.Option(Path("seoguard.db"), "--db"),
    crawl_id: Optional[int] = typer.Option(None, "--crawl", help="Crawl id (default: latest)."),
    severity: Optional[str] = typer.Option(None, "--severity", help="Only error, warning or notice."),
):
    """Audit a saved crawl and print SEO issues."""
    if not db.exists():
        console.print(f"[red]{db} not found.[/] Run `seoguard crawl` first.")
        raise typer.Exit(1)
    store = Store(db)
    cid = crawl_id or store.latest_crawl_id()
    if cid is None:
        console.print("[red]No crawls in this database yet.[/]")
        raise typer.Exit(1)
    rows = store.pages(cid)
    store.close()

    issues = audit(rows)
    if severity:
        issues = [i for i in issues if i.severity == severity]

    table = Table(title=f"Crawl #{cid}: {len(rows)} pages, {len(issues)} issues", show_lines=False)
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("URL", overflow="fold")
    table.add_column("Issue", overflow="fold")
    for i in issues:
        table.add_row(f"[{SEVERITY_STYLE[i.severity]}]{i.severity}[/]", i.rule, i.url, i.message)
    console.print(table)

    counts = Counter(i.severity for i in issues)
    console.print(" · ".join(f"[{SEVERITY_STYLE[s]}]{counts.get(s, 0)} {s}s[/]"
                             for s in ("error", "warning", "notice")))


if __name__ == "__main__":
    app()
