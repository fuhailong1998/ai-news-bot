"""SQLite 去重存储。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from .models import NewsItem


class Dedup:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                uid TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                pushed_at TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_source_seen ON seen(source, first_seen_at)")
        self.conn.commit()

    def is_new(self, item: NewsItem) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen WHERE uid = ?", (item.uid,)
        ).fetchone()
        return row is None

    def mark_seen(self, item: NewsItem, pushed: bool = False) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO seen(uid, source, url, title, content_hash, first_seen_at, pushed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                content_hash = excluded.content_hash,
                title = excluded.title,
                pushed_at = COALESCE(excluded.pushed_at, seen.pushed_at)
        """, (
            item.uid, item.source, item.url, item.title, item.content_hash,
            now, now if pushed else None,
        ))
        self.conn.commit()

    def cleanup(self, retention_days: int) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        cur = self.conn.execute("DELETE FROM seen WHERE first_seen_at < ?", (cutoff,))
        self.conn.commit()
        if cur.rowcount:
            logger.info(f"Cleaned up {cur.rowcount} old dedup records")
        return cur.rowcount

    def close(self) -> None:
        self.conn.close()
