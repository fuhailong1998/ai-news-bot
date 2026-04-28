"""飞书 Webhook 推送（交互卡片 + 签名 + 限速 + 重试）。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time

import httpx
from loguru import logger

from ..models import NewsItem, Settings


class FeishuNotifier:
    def __init__(self, settings: Settings):
        self.url = settings.feishu_webhook_url
        self.secret = settings.feishu_secret
        self.cfg = settings.push

    def _sign(self, ts: int) -> str:
        string_to_sign = f"{ts}\n{self.secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def _build_card(self, item: NewsItem) -> dict:
        date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else "—"
        body = item.ai_summary or item.summary or ""
        if len(body) > 300:
            body = body[:300] + "…"
        tags_str = " ".join(f"`{t}`" for t in item.tags) if item.tags else ""
        md = f"📅 {date_str}  {tags_str}\n\n{body}"
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"🤖 {item.source}"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "markdown", "content": f"**[{item.title}]({item.url})**"},
                    {"tag": "markdown", "content": md},
                    {
                        "tag": "action",
                        "actions": [{
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔗 查看原文"},
                            "type": "primary",
                            "url": item.url,
                        }],
                    },
                ],
            },
        }

    async def _post(self, client: httpx.AsyncClient, payload: dict) -> bool:
        if self.secret:
            ts = int(time.time())
            payload = {**payload, "timestamp": str(ts), "sign": self._sign(ts)}
        for attempt in range(1, self.cfg.max_retry + 1):
            try:
                resp = await client.post(self.url, json=payload, timeout=15)
                data = resp.json()
                if resp.status_code == 200 and data.get("code", data.get("StatusCode", 0)) == 0:
                    return True
                logger.warning(f"[feishu] resp={data}, attempt {attempt}")
            except Exception as e:
                logger.warning(f"[feishu] error: {e}, attempt {attempt}")
            await asyncio.sleep(2 ** (attempt - 1))
        return False

    async def push_many(self, items: list[NewsItem], client: httpx.AsyncClient) -> int:
        if not self.url:
            logger.error("FEISHU_WEBHOOK_URL not configured, skip push")
            return 0
        sent = 0
        for item in items[: self.cfg.per_run_limit]:
            ok = await self._post(client, self._build_card(item))
            if ok:
                sent += 1
            await asyncio.sleep(self.cfg.interval_seconds)
        # 若还有剩余，发一条 digest
        rest = items[self.cfg.per_run_limit:]
        if rest:
            await self._post(client, self._build_digest(rest))
        return sent

    def _build_digest(self, items: list[NewsItem]) -> dict:
        lines = [f"- **[{i.source}]** [{i.title}]({i.url})" for i in items[:30]]
        md = "本轮还有以下更新（未单独发卡片）：\n\n" + "\n".join(lines)
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": f"🗂 其余 {len(items)} 条 AI 动态"},
                           "template": "grey"},
                "elements": [{"tag": "markdown", "content": md}],
            },
        }
