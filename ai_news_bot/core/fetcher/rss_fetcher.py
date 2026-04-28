"""通用 RSS / Atom Fetcher。"""
from __future__ import annotations

from datetime import datetime
from time import mktime

import feedparser
from loguru import logger

from ..models import NewsItem
from .base import BaseFetcher


class RssFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        url = self.source.url
        assert url, f"RSS source {self.source.name} missing URL"
        resp = await self.client.get(url, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items: list[NewsItem] = []
        for entry in feed.entries:
            published = None
            for key in ("published_parsed", "updated_parsed"):
                if entry.get(key):
                    published = datetime.fromtimestamp(mktime(entry[key]))
                    break
            link = entry.get("link", "")
            title = entry.get("title", "").strip()
            if not link or not title:
                continue
            items.append(NewsItem(
                source=self.source.name,
                title=title,
                url=link,
                published_at=published,
                summary=_clean_html(entry.get("summary", "") or entry.get("description", "")),
            ))
        logger.debug(f"[{self.source.name}] RSS fetched {len(items)} items")
        return items


def _clean_html(html: str) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    return text[:500]
