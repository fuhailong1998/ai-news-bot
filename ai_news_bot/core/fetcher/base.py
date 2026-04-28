"""Fetcher 抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..models import NewsItem, SourceConfig


class BaseFetcher(ABC):
    def __init__(self, source: SourceConfig, client: httpx.AsyncClient):
        self.source = source
        self.client = client

    @abstractmethod
    async def fetch(self) -> list[NewsItem]:
        ...
