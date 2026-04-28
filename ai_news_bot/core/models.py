"""数据模型与配置加载。"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
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


class Settings(BaseModel):
    storage: StorageCfg = Field(default_factory=StorageCfg)
    push: PushCfg = Field(default_factory=PushCfg)
    summarizer: SummarizerCfg = Field(default_factory=SummarizerCfg)
    fetch: FetchCfg = Field(default_factory=FetchCfg)

    # 环境变量
    feishu_webhook_url: str = ""
    feishu_secret: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "deepseek-chat"


def load_settings(path: Path | None = None) -> Settings:
    path = path or (CONFIG_DIR / "settings.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    s = Settings(**data)
    s.feishu_webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")
    s.feishu_secret = os.getenv("FEISHU_SECRET", "")
    s.llm_api_key = os.getenv("LLM_API_KEY", "")
    s.llm_base_url = os.getenv("LLM_BASE_URL", s.llm_base_url)
    s.llm_model = os.getenv("LLM_MODEL", s.llm_model)
    return s


def load_sources(path: Path | None = None) -> list[SourceConfig]:
    path = path or (CONFIG_DIR / "sources.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SourceConfig(**item) for item in data.get("sources", [])]
