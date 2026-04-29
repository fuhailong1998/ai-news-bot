"""主流程：抓取 → 去重 → 摘要 → 推送。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
from loguru import logger

from .dedup import Dedup
from .fetcher.factory import build_fetcher
from .models import NewsItem, Settings, SourceConfig, load_settings, load_sources
from .notifier.feishu import FeishuNotifier
from .notifier.telegram import TelegramNotifier
from .summarizer import Summarizer


async def _noop() -> int:
    return 0


async def _fetch_one(source: SourceConfig, client: httpx.AsyncClient) -> list[NewsItem]:
    try:
        fetcher = build_fetcher(source, client)
        return await fetcher.fetch()
    except Exception as e:
        logger.error(f"[{source.name}] fetch failed: {type(e).__name__}: {e}")
        return []


async def run(seed_only: bool = False) -> None:
    settings = load_settings()
    sources = [s for s in load_sources() if s.enabled]
    logger.info(f"Loaded {len(sources)} enabled sources, seed={seed_only}")

    dedup = Dedup(settings.storage.db_path)
    summarizer = Summarizer(settings)
    feishu = FeishuNotifier(settings)
    telegram = TelegramNotifier(settings)

    sem = asyncio.Semaphore(settings.fetch.concurrency)
    headers = {"User-Agent": settings.fetch.user_agent}

    async with httpx.AsyncClient(timeout=settings.fetch.timeout_seconds, headers=headers) as client:
        async def guarded(s: SourceConfig) -> list[NewsItem]:
            async with sem:
                return await _fetch_one(s, client)

        all_items_lists = await asyncio.gather(*(guarded(s) for s in sources))
        all_items = [it for sub in all_items_lists for it in sub]
        logger.info(f"Total fetched: {len(all_items)} items")

        # 去重 → 新条目
        new_items = [it for it in all_items if dedup.is_new(it)]
        logger.info(f"New items: {len(new_items)}")

        if seed_only:
            for it in all_items:
                dedup.mark_seen(it, pushed=False)
            logger.info("Seed done, no push.")
            dedup.cleanup(settings.storage.retention_days)
            dedup.close()
            return

        # 折中方案：新加的数据源只推近 N 天内发布的条目，其余历史 backlog 静默入库
        # 避免新加 RSS 时把整个历史一次性轰炸到群里。
        known = dedup.known_sources()
        window_days = settings.storage.first_run_window_days
        cutoff = datetime.utcnow() - timedelta(days=window_days)

        def _naive(d: datetime | None) -> datetime | None:
            if d is None:
                return None
            return d.replace(tzinfo=None) if d.tzinfo else d

        suppressed_count = 0
        kept: list[NewsItem] = []
        for it in new_items:
            if it.source in known:
                kept.append(it)
                continue
            pub = _naive(it.published_at)
            if pub is None or pub >= cutoff:
                kept.append(it)
            else:
                dedup.mark_seen(it, pushed=False)
                suppressed_count += 1
        if suppressed_count:
            logger.info(
                f"First-run window: suppressed {suppressed_count} backlog items "
                f"older than {window_days}d from newly added sources"
            )
        new_items = kept

        # 排序：有日期的按日期倒序，其余追加（统一去掉 tzinfo 避免比较错误）
        def _sort_key(it):
            d = it.published_at
            if d is None:
                return datetime.min
            return d.replace(tzinfo=None) if d.tzinfo else d
        new_items.sort(key=_sort_key, reverse=True)

        # LLM 摘要
        if summarizer.enabled and new_items:
            await asyncio.gather(*(summarizer.summarize(it, client) for it in new_items))

        # 推送（飞书 + Telegram 并发）
        sent = 0
        if new_items:
            results = await asyncio.gather(
                feishu.push_many(new_items, client),
                telegram.push_many(new_items, client) if telegram.enabled else _noop(),
            )
            sent = max(results)
        logger.info(f"Pushed {sent}/{len(new_items)} items "
                    f"(feishu={len(feishu.targets)}, tg={len(telegram.targets)})")

        # 入库
        for it in new_items:
            dedup.mark_seen(it, pushed=True)

        dedup.cleanup(settings.storage.retention_days)
    dedup.close()
