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

        # HF cursor 过滤：对每个 HF 源，记录历史上见过的最大 createdAt。
        # 凡是 createdAt <= cursor 的条目静默吞掉（不入库不推送），
        # 这样可彻底消除 HF API "延迟暴露"导致的旧模型重新出现在 top-N 的噪音。
        # 同时记录本轮看到的最大 createdAt，跑完之后单调推进 cursor。
        def _naive(d: datetime | None) -> datetime | None:
            if d is None:
                return None
            return d.replace(tzinfo=None) if d.tzinfo else d

        hf_max_seen: dict[str, datetime] = {}
        cursor_filtered_count = 0
        post_cursor_items: list[NewsItem] = []
        for it in all_items:
            is_hf = "huggingface.co/" in it.url
            if is_hf and it.published_at:
                pub = _naive(it.published_at)
                cur = hf_max_seen.get(it.source)
                if cur is None or pub > cur:
                    hf_max_seen[it.source] = pub
                cursor = dedup.get_cursor(it.source)
                if cursor and pub <= cursor:
                    cursor_filtered_count += 1
                    continue
            post_cursor_items.append(it)
        if cursor_filtered_count:
            logger.info(f"HF cursor: filtered {cursor_filtered_count} items <= last-seen createdAt")
        all_items = post_cursor_items

        # 去重 → 新条目
        new_items = [it for it in all_items if dedup.is_new(it)]
        logger.info(f"New items: {len(new_items)}")

        if seed_only:
            for it in all_items:
                dedup.mark_seen(it, pushed=False)
            for source, max_dt in hf_max_seen.items():
                dedup.update_cursor(source, max_dt)
            logger.info("Seed done, no push.")
            dedup.cleanup(settings.storage.retention_days)
            dedup.close()
            return

        # 全局过期窗口：所有源的所有新条目，如果有 published_at 且老于 N 天，
        # 静默 mark_seen 不推送。避免「老模型今天才被 HF API 排出来」这种延迟暴露
        # 的内容打扰用户。没有 published_at 的条目仍会推（许多 HTML parser 拿不到日期）。
        window_days = settings.storage.first_run_window_days
        cutoff = datetime.utcnow() - timedelta(days=window_days)

        suppressed_count = 0
        kept: list[NewsItem] = []
        for it in new_items:
            pub = _naive(it.published_at)
            if pub is None or pub >= cutoff:
                kept.append(it)
            else:
                dedup.mark_seen(it, pushed=False)
                suppressed_count += 1
        if suppressed_count:
            logger.info(
                f"Freshness window: suppressed {suppressed_count} items "
                f"with published_at older than {window_days}d"
            )
        new_items = kept

        def _sort_key(it: NewsItem):
            d = _naive(it.published_at)
            return d or datetime.min

        # HF 模型批量发布合并：同一组织在一次运行中放出多个模型变体
        # （例如 1.25bit / 2bit / GGUF / FP8 等量化版本），合并成一张卡片避免刷屏。
        # 触发阈值：同源 ≥ 3 条
        hf_groups: dict[str, list[NewsItem]] = {}
        for it in new_items:
            if "huggingface.co/" in it.url:
                hf_groups.setdefault(it.source, []).append(it)

        merged_originals: list[NewsItem] = []
        kept_after_collapse: list[NewsItem] = []
        for it in new_items:
            grp = hf_groups.get(it.source, [])
            if len(grp) >= 3 and "huggingface.co/" in it.url:
                continue
            kept_after_collapse.append(it)

        for source, grp in hf_groups.items():
            if len(grp) < 3:
                continue
            grp.sort(key=_sort_key, reverse=True)
            org = source.replace(" HF Models", "").strip()
            names = [g.url.rsplit("/", 1)[-1] for g in grp]
            kept_after_collapse.append(NewsItem(
                source=source,
                title=f"🤗 {org} 一次性发布 {len(grp)} 个模型",
                url=f"https://huggingface.co/{grp[0].url.split('huggingface.co/')[-1].split('/')[0]}",
                published_at=grp[0].published_at,
                summary=f"{org} 在 HF 上传了 {len(grp)} 个模型（量化/格式变体）：" + "、".join(names[:5]) + ("..." if len(names) > 5 else ""),
                content="\n".join(f"• {n}" for n in names),
            ))
            merged_originals.extend(grp)
            logger.info(f"Collapsed {len(grp)} HF uploads from {source} into one card")

        new_items = kept_after_collapse
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

        # 入库（包括被合并掉的原始 HF 条目，避免下次再被判为 new）
        for it in new_items:
            dedup.mark_seen(it, pushed=True)
        for it in merged_originals:
            dedup.mark_seen(it, pushed=True)

        # HF cursor 推进：本轮见过的最大 createdAt（包括被 cursor/dedup 过滤掉的），
        # 实现严格单调推进，防止下一轮同 createdAt 旧模型再被 API 排上来。
        for source, max_dt in hf_max_seen.items():
            dedup.update_cursor(source, max_dt)

        dedup.cleanup(settings.storage.retention_days)
    dedup.close()
