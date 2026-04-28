"""HTML 抓取 - 每个源一个 parse_xxx 函数。

新增源步骤：
1. 在 PARSERS 字典注册 parser 名 → 解析函数
2. 解析函数签名: (html: str, base_url: str) -> list[dict]
   返回 [{"title": ..., "url": ..., "summary": ..., "published_at": datetime|None}, ...]

注：智谱 / Kimi / 豆包 / 腾讯混元 / MiniMax / 华为 / 百度 等是前端 SPA，
class 名经过打包混淆（如 _activeSlogan_15se9_108），无 headless browser
抓不到内容。建议改用其 GitHub 组织的 Releases 替代。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from loguru import logger

from ..models import NewsItem
from .base import BaseFetcher


# ============= 解析函数 =============

def parse_anthropic(html: str, base_url: str) -> list[dict]:
    """Anthropic 新闻列表页 - <a href='/news/...'>。
    每个卡片文本格式：[分类] | [日期 e.g. Apr 24, 2026] | [标题] | [摘要]
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    date_re = re.compile(r"\b([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\b")
    for a in soup.select("a[href*='/news/']"):
        href = a.get("href")
        if not href or href.rstrip("/").endswith("/news"):
            continue
        text = a.get_text(" | ", strip=True)
        # 解析日期
        published_at = None
        m = date_re.search(text)
        if m:
            try:
                published_at = dateparser.parse(m.group(1))
            except Exception:
                pass
        # 提取标题：优先 h2/h3，否则取除分类/日期外的最长片段
        h = a.find(["h2", "h3"])
        if h:
            title = h.get_text(strip=True)
        else:
            parts = [p.strip() for p in text.split("|")]
            CATEGORIES = {"Product", "Announcements", "Policy", "Research",
                          "Interpretability", "Societal Impacts", "Education",
                          "Security", "Customer Stories"}
            parts = [p for p in parts if p and not date_re.fullmatch(p) and p not in CATEGORIES]
            # 取第一个看起来像标题的片段（首字母大写 + 不超过 200 字符）
            title = parts[0] if parts else ""
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 5 or len(title) > 200:
            continue
        # summary：标题之后的部分
        summary = ""
        if title in text:
            after = text.split(title, 1)[1].strip(" |")
            summary = after[:300]
        out.append({
            "title": title,
            "url": urljoin(base_url, href),
            "summary": summary,
            "published_at": published_at,
        })
    return _dedup_dicts(out)


def parse_mistral(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for a in soup.select("a[href*='/news/']"):
        href = a.get("href")
        if not href or href.rstrip("/").endswith("/news"):
            continue
        title = a.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or len(title) < 5:
            continue
        out.append({
            "title": title[:200],
            "url": urljoin(base_url, href),
            "summary": "",
            "published_at": None,
        })
    return _dedup_dicts(out)


def parse_cursor(html: str, base_url: str) -> list[dict]:
    """Cursor changelog - 每篇是一个 <article>，含日期+标题。"""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for art in soup.find_all("article"):
        h1 = art.find(["h1", "h2"])
        if not h1:
            continue
        title = h1.get_text(strip=True)
        text = art.get_text(" ", strip=True)
        # 日期格式：Apr 24, 2026
        date_match = re.search(r"\b([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\b", text[:200])
        published_at = None
        if date_match:
            try:
                published_at = dateparser.parse(date_match.group(1))
            except Exception:
                pass
        # 找锚点链接做 url
        anchor = h1.find("a") or art.find("a", href=re.compile(r"#"))
        href = anchor.get("href") if anchor else None
        url = urljoin(base_url, href) if href else f"{base_url}#{title.lower().replace(' ', '-')}"
        summary = text[:300]
        out.append({
            "title": title[:200],
            "url": url,
            "summary": summary,
            "published_at": published_at,
        })
    return _dedup_dicts(out)


def parse_deepseek(html: str, base_url: str) -> list[dict]:
    """⚠️ /news/news 路径已不存在，请改用 fetch_deepseek_via_sitemap。
    保留兼容性，直接返回空。"""
    return []


def parse_deepseek_sitemap(html: str, base_url: str) -> list[dict]:
    """从 https://api-docs.deepseek.com/sitemap.xml 提取 /news/* 路径。"""
    soup = BeautifulSoup(html, "lxml-xml")
    out: list[dict] = []
    for loc in soup.find_all("loc"):
        url = loc.get_text(strip=True)
        if "/news/" not in url:
            continue
        slug = url.rsplit("/", 1)[-1]  # news260424 / news0725
        digits = re.search(r"news(\d{4,6})$", slug)
        published_at = None
        title_suffix = slug
        if digits:
            d = digits.group(1)
            try:
                if len(d) == 6:
                    published_at = datetime.strptime(d, "%y%m%d")
                elif len(d) == 4:
                    # MMDD，假设为去年/今年中较近的（保守用今年）
                    published_at = datetime.strptime(f"{datetime.now().year}{d}", "%Y%m%d")
                title_suffix = published_at.strftime("%Y-%m-%d")
            except ValueError:
                pass
        out.append({
            "title": f"DeepSeek API Update {title_suffix}",
            "url": url,
            "summary": "",
            "published_at": published_at,
        })
    return _dedup_dicts(out)


def _dedup_dicts(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    return out


# ============= 注册表 =============

PARSERS: dict[str, Callable[[str, str], list[dict]]] = {
    "anthropic": parse_anthropic,
    "mistral": parse_mistral,
    "cursor": parse_cursor,
    "deepseek": parse_deepseek_sitemap,  # url 应填 sitemap.xml
    # SPA 站点暂不支持（需 headless browser）：
    # gemini_changelog, anthropic_release, azure_openai, baidu,
    # tencent_hunyuan, doubao, huawei, moonshot, zhipu, minimax
}


# ============= Fetcher =============

class HtmlFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        url = self.source.url
        parser_name = self.source.parser
        assert url and parser_name, f"HTML source {self.source.name} missing url/parser"
        if parser_name not in PARSERS:
            logger.warning(f"[{self.source.name}] parser '{parser_name}' not implemented, skip")
            return []
        resp = await self.client.get(url, follow_redirects=True)
        resp.raise_for_status()
        records = PARSERS[parser_name](resp.text, url)
        items = [
            NewsItem(
                source=self.source.name,
                title=r["title"],
                url=r["url"],
                published_at=r.get("published_at"),
                summary=r.get("summary", ""),
            )
            for r in records
        ]
        logger.debug(f"[{self.source.name}] HTML fetched {len(items)} items")
        return items



# ============= Fetcher =============

class HtmlFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        url = self.source.url
        parser_name = self.source.parser
        assert url and parser_name, f"HTML source {self.source.name} missing url/parser"
        if parser_name not in PARSERS:
            logger.warning(f"[{self.source.name}] parser '{parser_name}' not implemented, skip")
            return []
        resp = await self.client.get(url, follow_redirects=True)
        resp.raise_for_status()
        records = PARSERS[parser_name](resp.text, url)
        items = [
            NewsItem(
                source=self.source.name,
                title=r["title"],
                url=r["url"],
                published_at=r.get("published_at"),
                summary=r.get("summary", ""),
            )
            for r in records
        ]
        logger.debug(f"[{self.source.name}] HTML fetched {len(items)} items")
        return items
