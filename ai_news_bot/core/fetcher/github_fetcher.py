"""GitHub Releases / Tags Fetcher。"""
from __future__ import annotations

import os
from datetime import datetime

from loguru import logger

from ..models import NewsItem
from .base import BaseFetcher


class GithubReleasesFetcher(BaseFetcher):
    """监控 GitHub Releases。仓库未发布 Releases 时返回空，
    国产模型仓库建议改用 github_tags。"""

    async def fetch(self) -> list[NewsItem]:
        repo = self.source.repo
        assert repo, f"github_releases source {self.source.name} missing repo"
        api = f"https://api.github.com/repos/{repo}/releases"
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = await self.client.get(api, headers=headers, params={"per_page": 10}, follow_redirects=True)
        resp.raise_for_status()
        items: list[NewsItem] = []
        for rel in resp.json():
            if rel.get("draft"):
                continue
            published_at = _parse_iso(rel.get("published_at") or rel.get("created_at"))
            title = f"{repo} {rel.get('name') or rel.get('tag_name', '')}".strip()
            items.append(NewsItem(
                source=self.source.name,
                title=title,
                url=rel.get("html_url", ""),
                published_at=published_at,
                summary=(rel.get("body") or "")[:500],
            ))
        logger.debug(f"[{self.source.name}] GitHub fetched {len(items)} releases")
        return items


class GithubTagsFetcher(BaseFetcher):
    """监控 Git tags（适合不发 Releases 的国产仓库）。"""

    async def fetch(self) -> list[NewsItem]:
        repo = self.source.repo
        assert repo, f"github_tags source {self.source.name} missing repo"
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # 用 GraphQL 不方便，用 REST tags + commits 二次查询
        api = f"https://api.github.com/repos/{repo}/tags"
        resp = await self.client.get(api, headers=headers, params={"per_page": 10}, follow_redirects=True)
        resp.raise_for_status()
        items: list[NewsItem] = []
        for tag in resp.json():
            tag_name = tag.get("name", "")
            sha = tag.get("commit", {}).get("sha", "")
            commit_url = f"https://github.com/{repo}/releases/tag/{tag_name}"
            items.append(NewsItem(
                source=self.source.name,
                title=f"{repo} tag {tag_name}",
                url=commit_url,
                published_at=None,  # tags 没有原生时间戳，可惜
                summary=f"commit: {sha[:7]}",
            ))
        logger.debug(f"[{self.source.name}] GitHub fetched {len(items)} tags")
        return items


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None

