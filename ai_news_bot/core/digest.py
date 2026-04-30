"""每日总结：扫描 dedup db 中过去 24h 的条目，生成一张「今日总结」卡片
并通过飞书 / Telegram 推送。即使是「今日 AI 圈安静」也会推一张占位卡。
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from .models import NewsItem, load_settings
from .notifier.feishu import FeishuNotifier
from .notifier.telegram import TelegramNotifier


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_QUIET_QUOTES = [
    "今日 AI 圈难得安静一天，正好可以摸鱼 ☕",
    "今日 AI 圈风平浪静，建议精读昨天没看完的论文 📚",
    "今天大厂们都在憋大招，明天可能就有 GPT-X 了 🚀",
    "今日无新增推送，看来今晚可以早点睡 🌙",
]


def _today_window_utc(window_hours: int = 24) -> tuple[str, str]:
    end = _utcnow_naive()
    start = end - timedelta(hours=window_hours)
    return start.isoformat(), end.isoformat()


def _load_today_items(db_path: str, window_hours: int) -> list[tuple]:
    start_iso, _end_iso = _today_window_utc(window_hours)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT source, title, url, pushed_at FROM seen
           WHERE pushed_at >= ? ORDER BY pushed_at DESC""",
        (start_iso,),
    ).fetchall()
    conn.close()
    return rows


def _build_card_payload(rows: list[tuple], date_label: str) -> tuple[dict, str]:
    """Returns (feishu_card_dict, telegram_html_text)."""
    if not rows:
        import random
        quote = random.choice(_QUIET_QUOTES)
        feishu_card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"📅 {date_label} · 今日 AI 总结"},
                    "template": "grey",
                },
                "elements": [{"tag": "markdown", "content": f"**今日 0 条 AI 资讯入库**\n\n{quote}"}],
            },
        }
        tg_text = f"📅 <b>{date_label} · 今日 AI 总结</b>\n\n今日 0 条 AI 资讯入库\n\n<i>{quote}</i>"
        return feishu_card, tg_text

    by_source: dict[str, list[tuple]] = {}
    for r in rows:
        by_source.setdefault(r[0], []).append(r)

    md_lines = [f"**今日共 {len(rows)} 条 AI 资讯，覆盖 {len(by_source)} 个来源：**\n"]
    tg_lines = [f"📅 <b>{date_label} · 今日 AI 总结</b>", "",
                f"今日共 <b>{len(rows)}</b> 条资讯，覆盖 <b>{len(by_source)}</b> 个来源：", ""]

    for source, items in sorted(by_source.items(), key=lambda x: -len(x[1])):
        md_lines.append(f"\n**[{source}]** ({len(items)} 条)")
        tg_lines.append(f"\n<b>{source}</b> ({len(items)} 条)")
        for it in items[:5]:
            title = it[1]
            url = it[2]
            md_lines.append(f"  - [{title}]({url})")
            from html import escape
            tg_lines.append(f'  • <a href="{escape(url, quote=True)}">{escape(title, quote=False)}</a>')
        if len(items) > 5:
            md_lines.append(f"  - ... 还有 {len(items) - 5} 条")
            tg_lines.append(f"  • ... 还有 {len(items) - 5} 条")

    feishu_card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📅 {date_label} · 今日 AI 总结"},
                "template": "blue",
            },
            "elements": [{"tag": "markdown", "content": "\n".join(md_lines)}],
        },
    }
    tg_text = "\n".join(tg_lines)
    if len(tg_text) > 4000:  # Telegram limit 4096
        tg_text = tg_text[:3950] + "\n\n... (truncated)"
    return feishu_card, tg_text


async def _noop() -> int:
    return 0


async def run_digest(window_hours: int = 24) -> None:
    settings = load_settings()
    feishu = FeishuNotifier(settings)
    telegram = TelegramNotifier(settings)

    rows = _load_today_items(settings.storage.db_path, window_hours)
    date_label = (_utcnow_naive() + timedelta(hours=8)).strftime("%Y-%m-%d")  # Beijing
    feishu_card, tg_text = _build_card_payload(rows, date_label)

    logger.info(f"[digest] {len(rows)} items in last {window_hours}h, broadcasting...")
    headers = {"User-Agent": settings.fetch.user_agent}
    async with httpx.AsyncClient(timeout=settings.fetch.timeout_seconds, headers=headers) as client:
        tasks = []
        if feishu.targets:
            tasks.append(feishu._broadcast(client, feishu_card))
        else:
            tasks.append(_noop())
        if telegram.enabled:
            tasks.append(telegram._broadcast(client, tg_text))
        else:
            tasks.append(_noop())
        await asyncio.gather(*tasks)
    logger.info("[digest] done.")
