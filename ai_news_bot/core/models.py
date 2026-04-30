"""数据模型与配置加载。"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from loguru import logger
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).parent.parent / "config"


# ===== 运行时数据模型 =====

@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    content: str = ""
    ai_summary: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return hashlib.sha256(f"{self.source}|{self.url}".encode("utf-8")).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        material = (self.title + "|" + (self.summary or self.content[:500]))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


# ===== 配置模型 =====

class SourceConfig(BaseModel):
    name: str
    type: Literal["rss", "html", "github_releases", "github_tags", "huggingface_org"]
    url: str | None = None
    repo: str | None = None
    parser: str | None = None
    enabled: bool = True
    priority: Literal["high", "medium", "low"] = "high"


class StorageCfg(BaseModel):
    db_path: str = "storage/seen.db"
    retention_days: int = 30
    first_run_window_days: int = 7  # global freshness window: items with published_at older than this are silently dropped


class PushCfg(BaseModel):
    per_run_limit: int = 10
    interval_seconds: float = 0.8
    max_retry: int = 3


class SummarizerCfg(BaseModel):
    enabled: bool = False
    model: str = "deepseek-chat"
    max_input_chars: int = 2000
    max_summary_chars: int = 80


class FetchCfg(BaseModel):
    timeout_seconds: int = 20
    user_agent: str = "Mozilla/5.0 (compatible; AINewsBot/0.1)"
    concurrency: int = 8


class FeishuWebhook(BaseModel):
    url: str
    secret: str = ""
    name: str = ""  # optional label, only for logging


class TelegramTarget(BaseModel):
    bot_token: str
    chat_id: str
    name: str = ""  # optional label


class Settings(BaseModel):
    storage: StorageCfg = Field(default_factory=StorageCfg)
    push: PushCfg = Field(default_factory=PushCfg)
    summarizer: SummarizerCfg = Field(default_factory=SummarizerCfg)
    fetch: FetchCfg = Field(default_factory=FetchCfg)

    # 环境变量
    feishu_webhook_url: str = ""
    feishu_secret: str = ""
    feishu_webhooks: list[FeishuWebhook] = Field(default_factory=list)
    telegram_targets: list[TelegramTarget] = Field(default_factory=list)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "deepseek-chat"


def _parse_feishu_webhooks_env() -> list[FeishuWebhook]:
    """Parse FEISHU_WEBHOOKS env var.

    Supported formats (auto-detected):
      1. JSON list:  '[{"url":"...","secret":"..."},{"url":"..."}]'
      2. Pipe/comma: 'url1|secret1,url2|,url3|secret3'
                     (secret may be empty after pipe; comma separates targets)
      3. Newline-separated lines of form 'url|secret' or just 'url'.
    Empty / unset returns [].
    """
    raw = (os.getenv("FEISHU_WEBHOOKS") or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            return [FeishuWebhook(**item) for item in arr if item.get("url")]
        except Exception as e:
            logger.error(f"FEISHU_WEBHOOKS JSON parse error: {e}")
            return []
    # delimited form
    parts: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    out: list[FeishuWebhook] = []
    for p in parts:
        if "|" in p:
            url, _, secret = p.partition("|")
            out.append(FeishuWebhook(url=url.strip(), secret=secret.strip()))
        else:
            out.append(FeishuWebhook(url=p))
    return out


def _parse_telegram_targets_env() -> list[TelegramTarget]:
    """Parse Telegram targets from env vars.

    Two configurations supported:
      Mode A (simple, one bot N chats):
        TELEGRAM_BOT_TOKEN=123:abc
        TELEGRAM_CHAT_IDS=-100123,-100456,@my_channel

      Mode B (multi-bot or per-chat names; JSON, takes precedence):
        TELEGRAM_TARGETS=[{"bot_token":"...","chat_id":"-100123","name":"team-a"}, ...]
    Empty / unset returns [].
    """
    raw = (os.getenv("TELEGRAM_TARGETS") or "").strip()
    if raw:
        try:
            arr = json.loads(raw) if raw.startswith("[") else None
            if arr:
                return [TelegramTarget(**item) for item in arr if item.get("bot_token") and item.get("chat_id")]
        except Exception as e:
            logger.error(f"TELEGRAM_TARGETS JSON parse error: {e}")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chats_raw = (os.getenv("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chats_raw:
        return []
    chat_ids = [c.strip() for c in chats_raw.replace("\n", ",").split(",") if c.strip()]
    return [TelegramTarget(bot_token=token, chat_id=cid) for cid in chat_ids]


def load_settings(path: Path | None = None) -> Settings:
    path = path or (CONFIG_DIR / "settings.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    s = Settings(**data)
    s.feishu_webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")
    s.feishu_secret = os.getenv("FEISHU_SECRET", "")
    s.llm_api_key = os.getenv("LLM_API_KEY", "")
    s.llm_base_url = os.getenv("LLM_BASE_URL", s.llm_base_url)
    s.llm_model = os.getenv("LLM_MODEL", s.llm_model)

    # Resolve webhook targets: prefer FEISHU_WEBHOOKS multi-target env;
    # fall back to single FEISHU_WEBHOOK_URL/FEISHU_SECRET pair.
    multi = _parse_feishu_webhooks_env()
    if multi:
        s.feishu_webhooks = multi
    elif s.feishu_webhook_url:
        s.feishu_webhooks = [FeishuWebhook(url=s.feishu_webhook_url, secret=s.feishu_secret)]

    # Telegram targets
    s.telegram_targets = _parse_telegram_targets_env()
    return s


def load_sources(path: Path | None = None) -> list[SourceConfig]:
    path = path or (CONFIG_DIR / "sources.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SourceConfig(**item) for item in data.get("sources", [])]
