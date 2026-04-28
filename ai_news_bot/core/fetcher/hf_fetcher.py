"""HuggingFace 组织模型上传 Fetcher。

国产 AI lab 既不发 Releases 也不打 tags，但都会把新模型上传到 HF。
监控 https://huggingface.co/api/models?author=ORG 是最稳定的发布信号。
"""
from __future__ import annotations

from datetime import datetime

from loguru import logger

from ..models import NewsItem
from .base import BaseFetcher


class HuggingFaceOrgFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        org = self.source.repo  # 复用 repo 字段存 HF 组织名
        assert org, f"huggingface_org source {self.source.name} missing repo (org name)"
        api = "https://huggingface.co/api/models"
        params = {"author": org, "sort": "createdAt", "direction": "-1", "limit": 10}
        resp = await self.client.get(api, params=params, follow_redirects=True)
        resp.raise_for_status()
        items: list[NewsItem] = []
        for m in resp.json():
            model_id = m.get("id", "")
            if not model_id:
                continue
            created = _parse_iso(m.get("createdAt"))
            downloads = m.get("downloads", 0)
            likes = m.get("likes", 0)
            items.append(NewsItem(
                source=self.source.name,
                title=f"🤗 New model: {model_id}",
                url=f"https://huggingface.co/{model_id}",
                published_at=created,
                summary=f"Downloads: {downloads:,} | Likes: {likes}",
            ))
        logger.debug(f"[{self.source.name}] HF fetched {len(items)} models for org={org}")
        return items


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
