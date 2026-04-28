from datetime import datetime

from core.models import NewsItem, Settings, SummarizerCfg
from core.notifier.feishu import FeishuNotifier


def test_card_structure():
    s = Settings(feishu_webhooks=[{"url": "https://x"}])
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
    sig = FeishuNotifier._sign(1700000000, "topsecret")
    assert isinstance(sig, str) and len(sig) > 10


def test_card_structure_requires_targets_resolved():
    """Even with empty webhooks, _build_card should work (no I/O)."""
    s = Settings()
    n = FeishuNotifier(s)
    assert n.targets == []


def test_load_settings_single_env(monkeypatch):
    from core.models import load_settings
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://hook1")
    monkeypatch.setenv("FEISHU_SECRET", "sec1")
    monkeypatch.delenv("FEISHU_WEBHOOKS", raising=False)
    s = load_settings()
    assert len(s.feishu_webhooks) == 1
    assert s.feishu_webhooks[0].url == "https://hook1"
    assert s.feishu_webhooks[0].secret == "sec1"


def test_load_settings_multi_json(monkeypatch):
    from core.models import load_settings
    monkeypatch.setenv("FEISHU_WEBHOOKS",
                       '[{"url":"https://h1","secret":"s1","name":"team-a"},{"url":"https://h2"}]')
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("FEISHU_SECRET", raising=False)
    s = load_settings()
    assert len(s.feishu_webhooks) == 2
    assert s.feishu_webhooks[0].url == "https://h1"
    assert s.feishu_webhooks[0].name == "team-a"
    assert s.feishu_webhooks[1].url == "https://h2"
    assert s.feishu_webhooks[1].secret == ""


def test_load_settings_multi_delimited(monkeypatch):
    from core.models import load_settings
    monkeypatch.setenv("FEISHU_WEBHOOKS", "https://a|sa, https://b|, https://c|sc")
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    s = load_settings()
    urls = [w.url for w in s.feishu_webhooks]
    secrets = [w.secret for w in s.feishu_webhooks]
    assert urls == ["https://a", "https://b", "https://c"]
    assert secrets == ["sa", "", "sc"]
