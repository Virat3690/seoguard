"""SQLite storage: one row per crawled URL, grouped by crawl run."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .crawler import FetchResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    label       TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    crawl_id          INTEGER NOT NULL REFERENCES crawls(id),
    url               TEXT NOT NULL,
    final_url         TEXT,
    status            INTEGER,
    redirects         TEXT,      -- JSON list
    content_type      TEXT,
    x_robots_tag      TEXT,
    elapsed_ms        INTEGER,
    title             TEXT,
    meta_description  TEXT,
    canonical         TEXT,
    meta_robots       TEXT,
    h1                TEXT,      -- JSON list
    hreflang          TEXT,      -- JSON list of [lang, href]
    internal_links    INTEGER,
    external_links    INTEGER,
    word_count        INTEGER,
    error             TEXT,
    PRIMARY KEY (crawl_id, url)
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def new_crawl(self, label: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO crawls (started_at, label) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), label),
        )
        self.conn.commit()
        return cur.lastrowid

    def save(self, crawl_id: int, r: FetchResult) -> None:
        s = r.signals
        self.conn.execute(
            """INSERT OR REPLACE INTO pages VALUES
               (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                crawl_id, r.url, r.final_url, r.status, json.dumps(r.redirects),
                r.content_type, r.x_robots_tag, r.elapsed_ms,
                s.title if s else None,
                s.meta_description if s else None,
                s.canonical if s else None,
                s.meta_robots if s else None,
                json.dumps(s.h1) if s else None,
                json.dumps(s.hreflang) if s else None,
                s.internal_links if s else None,
                s.external_links if s else None,
                s.word_count if s else None,
                r.error,
            ),
        )

    def commit(self) -> None:
        self.conn.commit()

    def latest_crawl_id(self) -> int | None:
        row = self.conn.execute("SELECT MAX(id) FROM crawls").fetchone()
        return row[0]

    def pages(self, crawl_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pages WHERE crawl_id = ? ORDER BY url", (crawl_id,)
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
