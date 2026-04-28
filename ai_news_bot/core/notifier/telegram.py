"""Telegram Bot 推送（HTML 文本消息 + 限速 + 重试 + 多 chat 广播）。"""
from __future__ import annotations

import asyncio
import html as html_lib

import httpx
from loguru import logger

from ..models import NewsItem, Settings, TelegramTarget


class TelegramNotifier:
    API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, settings: Settings):
        self.targets: list[TelegramTarget] = list(settings.telegram_targets)
        self.cfg = settings.push

    @property
    def enabled(self) -> bool:
        return bool(self.targets)

    @staticmethod
    def _esc(s: str) -> str:
        return html_lib.escape(s or "", quote=False)

    def _build_text(self, item: NewsItem) -> str:
        title = self._esc(item.title)[:200]
        url = item.url
        date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else "—"
        body = item.ai_summary or item.summary or ""
        if len(body) > 350:
            body = body[:350] + "…"
        body = self._esc(body)
        source = self._esc(item.source)
        tags = " ".join(f"#{self._esc(t)}" for t in item.tags) if item.tags else ""
        # Telegram HTML supports a subset; <a>, <b>, <i>, <code>, <pre>
        return (
            f"🤖 <b>{source}</b>\n"
            f"<a href=\"{url}\"><b>{title}</b></a>\n"
            f"📅 {date_str}  {tags}\n\n"
            f"{body}"
        ).strip()

    async def _post_to(self, client: httpx.AsyncClient, target: TelegramTarget, text: str) -> bool:
        url = self.API.format(token=target.bot_token)
        payload = {
            "chat_id": target.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        label = target.name or f"chat:{target.chat_id}"
        for attempt in range(1, self.cfg.max_retry + 1):
            try:
                resp = await client.post(url, json=payload, timeout=15)
                data = resp.json()
                if resp.status_code == 200 and data.get("ok"):
                    return True
                logger.warning(f"[tg:{label}] resp={data}, attempt {attempt}")
            except Exception as e:
                logger.warning(f"[tg:{label}] error: {e}, attempt {attempt}")
            await asyncio.sleep(2 ** (attempt - 1))
        return False

    async def _broadcast(self, client: httpx.AsyncClient, text: str) -> int:
        if not self.targets:
            return 0
        results = await asyncio.gather(*(self._post_to(client, t, text) for t in self.targets))
        return sum(1 for ok in results if ok)

    async def push_many(self, items: list[NewsItem], client: httpx.AsyncClient) -> int:
        if not self.targets:
            return 0
        logger.info(f"[tg] broadcasting to {len(self.targets)} chat(s)")
        sent = 0
        for item in items[: self.cfg.per_run_limit]:
            ok = await self._broadcast(client, self._build_text(item))
            if ok > 0:
                sent += 1
            await asyncio.sleep(self.cfg.interval_seconds)
        rest = items[self.cfg.per_run_limit:]
        if rest:
            await self._broadcast(client, self._build_digest(rest))
        return sent

    def _build_digest(self, items: list[NewsItem]) -> str:
        lines = []
        for it in items[:30]:
            t = self._esc(it.title)[:120]
            s = self._esc(it.source)
            lines.append(f"• <b>[{s}]</b> <a href=\"{it.url}\">{t}</a>")
        body = "\n".join(lines)
        return f"🗂 <b>其余 {len(items)} 条 AI 动态</b>\n\n{body}"
