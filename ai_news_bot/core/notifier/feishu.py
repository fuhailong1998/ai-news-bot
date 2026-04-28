"""飞书 Webhook 推送（交互卡片 + 签名 + 限速 + 重试 + 多群广播）。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time

import httpx
from loguru import logger

from ..models import FeishuWebhook, NewsItem, Settings


class FeishuNotifier:
    def __init__(self, settings: Settings):
        self.targets: list[FeishuWebhook] = list(settings.feishu_webhooks)
        self.cfg = settings.push

    @staticmethod
    def _sign(ts: int, secret: str) -> str:
        string_to_sign = f"{ts}\n{secret}"
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

    async def _post_to(self, client: httpx.AsyncClient, target: FeishuWebhook, payload: dict) -> bool:
        if target.secret:
            ts = int(time.time())
            payload = {**payload, "timestamp": str(ts), "sign": self._sign(ts, target.secret)}
        label = target.name or target.url[-12:]
        for attempt in range(1, self.cfg.max_retry + 1):
            try:
                resp = await client.post(target.url, json=payload, timeout=15)
                data = resp.json()
                if resp.status_code == 200 and data.get("code", data.get("StatusCode", 0)) == 0:
                    return True
                logger.warning(f"[feishu:{label}] resp={data}, attempt {attempt}")
            except Exception as e:
                logger.warning(f"[feishu:{label}] error: {e}, attempt {attempt}")
            await asyncio.sleep(2 ** (attempt - 1))
        return False

    async def _broadcast(self, client: httpx.AsyncClient, payload: dict) -> int:
        """Send a single payload to all targets. Returns number of successful targets."""
        if not self.targets:
            return 0
        results = await asyncio.gather(
            *(self._post_to(client, t, payload) for t in self.targets),
            return_exceptions=False,
        )
        return sum(1 for ok in results if ok)

    async def push_many(self, items: list[NewsItem], client: httpx.AsyncClient) -> int:
        """Push items, broadcasting each card to all configured webhooks.

        Returns the count of items considered "sent" (i.e. delivered to >=1 target).
        """
        if not self.targets:
            logger.error("No Feishu webhooks configured (set FEISHU_WEBHOOK_URL or FEISHU_WEBHOOKS), skip push")
            return 0
        logger.info(f"[feishu] broadcasting to {len(self.targets)} target(s)")
        sent = 0
        for item in items[: self.cfg.per_run_limit]:
            ok_targets = await self._broadcast(client, self._build_card(item))
            if ok_targets > 0:
                sent += 1
            await asyncio.sleep(self.cfg.interval_seconds)
        rest = items[self.cfg.per_run_limit:]
        if rest:
            await self._broadcast(client, self._build_digest(rest))
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
