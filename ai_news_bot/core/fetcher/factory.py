"""Fetcher 工厂。"""
from __future__ import annotations

import httpx

from ..models import SourceConfig
from .base import BaseFetcher
from .github_fetcher import GithubReleasesFetcher, GithubTagsFetcher
from .hf_fetcher import HuggingFaceOrgFetcher
from .html_fetcher import HtmlFetcher
from .rss_fetcher import RssFetcher


def build_fetcher(source: SourceConfig, client: httpx.AsyncClient) -> BaseFetcher:
    match source.type:
        case "rss":
            return RssFetcher(source, client)
        case "html":
            return HtmlFetcher(source, client)
        case "github_releases":
            return GithubReleasesFetcher(source, client)
        case "github_tags":
            return GithubTagsFetcher(source, client)
        case "huggingface_org":
            return HuggingFaceOrgFetcher(source, client)
        case _:
            raise ValueError(f"Unknown source type: {source.type}")
