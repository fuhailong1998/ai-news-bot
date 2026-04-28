from datetime import datetime

from core.models import NewsItem, Settings, SummarizerCfg
from core.notifier.feishu import FeishuNotifier


def test_card_structure():
    s = Settings(feishu_webhook_url="https://x")
    n = FeishuNotifier(s)
    it = NewsItem(source="OpenAI", title="GPT-X released", url="https://openai.com/x",
                  published_at=datetime(2026, 4, 27), ai_summary="发布新模型",
                  tags=["模型发布"])
    payload = n._build_card(it)
    assert payload["msg_type"] == "interactive"
    elements = payload["card"]["elements"]
    assert any("GPT-X released" in e.get("content", "") for e in elements)
    assert any("发布新模型" in e.get("content", "") for e in elements)


def test_sign_format():
    s = Settings(feishu_webhook_url="https://x", feishu_secret="topsecret")
    n = FeishuNotifier(s)
    sig = n._sign(1700000000)
    assert isinstance(sig, str) and len(sig) > 10
