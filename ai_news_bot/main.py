"""CLI 入口。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from core.digest import run_digest
from core.runner import run


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    logger.add("logs/bot_{time:YYYY-MM-DD}.log", rotation="00:00", retention="14 days",
               level="DEBUG", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Bot")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="单次执行（默认）")
    g.add_argument("--seed", action="store_true", help="仅初始化，标记现有条目为已见但不推送")
    g.add_argument("--digest", action="store_true", help="发送过去 24h 的「今日总结」（不抓新内容）")
    args = parser.parse_args()

    setup_logging()
    if args.digest:
        asyncio.run(run_digest())
    else:
        asyncio.run(run(seed_only=args.seed))


if __name__ == "__main__":
    main()
