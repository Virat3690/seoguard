"""Turn stored page rows into SEO issues.

Each rule is a small function: row in, issue message out (or None).
Add new rules by writing a function and listing it in RULES.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

Row = Mapping[str, Any]


@dataclass(frozen=True)
class Issue:
    url: str
    rule: str
    severity: str  # "error" | "warning" | "notice"
    message: str


def _status(row: Row) -> tuple[str, str] | None:
    if row["error"]:
        return "error", f"Fetch failed: {row['error']}"
    if row["status"] and row["status"] >= 400:
        return "error", f"HTTP {row['status']}"
    return None


def _redirects(row: Row) -> tuple[str, str] | None:
    hops = json.loads(row["redirects"] or "[]")
    if len(hops) >= 2:
        return "warning", f"Redirect chain of {len(hops)} hops"
    if len(hops) == 1:
        return "notice", f"Redirects to {row['final_url']}"
    return None


def _title(row: Row) -> tuple[str, str] | None:
    if row["status"] != 200 or row["word_count"] is None:
        return None
    t = row["title"]
    if not t:
        return "error", "Missing <title>"
    if len(t) > 60:
        return "notice", f"Title is {len(t)} chars (often truncated past ~60)"
    return None


def _description(row: Row) -> tuple[str, str] | None:
    if row["status"] == 200 and row["word_count"] is not None and not row["meta_description"]:
        return "warning", "Missing meta description"
    return None


def _canonical(row: Row) -> tuple[str, str] | None:
    if row["status"] != 200 or row["word_count"] is None:
        return None
    c = row["canonical"]
    if not c:
        return "warning", "No canonical tag"
    if c.rstrip("/") != (row["final_url"] or "").rstrip("/"):
        return "notice", f"Canonical points elsewhere: {c}"
    return None


def _indexable(row: Row) -> tuple[str, str] | None:
    for source, value in (("meta robots", row["meta_robots"]), ("X-Robots-Tag", row["x_robots_tag"])):
        if value and "noindex" in value.lower():
            return "error", f"noindex via {source}"
    return None


def _h1(row: Row) -> tuple[str, str] | None:
    if row["status"] != 200 or row["h1"] is None:
        return None
    h1 = json.loads(row["h1"])
    if not h1:
        return "warning", "No <h1>"
    if len(h1) > 1:
        return "notice", f"{len(h1)} <h1> tags"
    return None


def _thin(row: Row) -> tuple[str, str] | None:
    wc = row["word_count"]
    if row["status"] == 200 and wc is not None and wc < 100:
        return "warning", f"Only {wc} words in raw HTML (thin, or content rendered by JavaScript)"
    return None


RULES: dict[str, Callable[[Row], tuple[str, str] | None]] = {
    "status": _status,
    "redirects": _redirects,
    "title": _title,
    "description": _description,
    "canonical": _canonical,
    "indexable": _indexable,
    "h1": _h1,
    "thin-content": _thin,
}

SEVERITY_ORDER = {"error": 0, "warning": 1, "notice": 2}


def audit(rows: list[Row]) -> list[Issue]:
    issues = []
    for row in rows:
        for name, rule in RULES.items():
            if found := rule(row):
                severity, message = found
                issues.append(Issue(row["url"], name, severity, message))
    return sorted(issues, key=lambda i: (SEVERITY_ORDER[i.severity], i.rule, i.url))
