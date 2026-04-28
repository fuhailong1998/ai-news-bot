"""可选的 LLM 摘要模块（OpenAI 兼容接口）。"""
from __future__ import annotations

import json

import httpx
from loguru import logger

from .models import NewsItem, Settings

PROMPT_TEMPLATE = """你是一名 AI 行业资讯编辑。请阅读以下新闻，输出一个 JSON：
{{"summary": "用一句中文不超过 {max_chars} 字概括核心要点", "tags": ["从此列表中选 1-3 个：模型发布/融资/开源/论文/产品/政策/其它"]}}

标题：{title}
来源：{source}
正文摘要：{content}

只返回 JSON，不要任何额外说明。"""


class Summarizer:
    def __init__(self, settings: Settings):
        self.cfg = settings.summarizer
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled and bool(self.api_key)

    async def summarize(self, item: NewsItem, client: httpx.AsyncClient) -> None:
        if not self.enabled:
            return
        content = (item.content or item.summary)[: self.cfg.max_input_chars]
        prompt = PROMPT_TEMPLATE.format(
            max_chars=self.cfg.max_summary_chars,
            title=item.title,
            source=item.source,
            content=content,
        )
        try:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(text)
            item.ai_summary = data.get("summary", "")[: self.cfg.max_summary_chars]
            tags = data.get("tags", [])
            if isinstance(tags, list):
                item.tags = [str(t) for t in tags][:3]
        except Exception as e:
            logger.warning(f"[summarizer] {item.source} failed: {e}")
