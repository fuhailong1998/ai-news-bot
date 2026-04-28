from datetime import datetime

from core.models import NewsItem, Settings, TelegramTarget, load_settings
from core.notifier.telegram import TelegramNotifier


def test_disabled_when_no_targets():
    n = TelegramNotifier(Settings())
    assert n.enabled is False
    assert n.targets == []


def test_text_structure():
    s = Settings(telegram_targets=[{"bot_token": "X", "chat_id": "-100"}])
    n = TelegramNotifier(s)
    it = NewsItem(source="OpenAI", title="<GPT-X> released",
                  url="https://openai.com/x", published_at=datetime(2026, 4, 27),
                  ai_summary="发布新模型", tags=["模型发布"])
    text = n._build_text(it)
    assert "OpenAI" in text and "&lt;GPT-X&gt;" in text  # html escaped
    assert "https://openai.com/x" in text
    assert "2026-04-27" in text
    assert "#模型发布" in text


def test_load_telegram_simple(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "-100111, -100222, @my_channel")
    monkeypatch.delenv("TELEGRAM_TARGETS", raising=False)
    s = load_settings()
    assert len(s.telegram_targets) == 3
    assert s.telegram_targets[0].chat_id == "-100111"
    assert s.telegram_targets[2].chat_id == "@my_channel"
    assert all(t.bot_token == "1234:abc" for t in s.telegram_targets)


def test_load_telegram_json(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TARGETS",
                       '[{"bot_token":"t1","chat_id":"-100","name":"team-a"},'
                       '{"bot_token":"t2","chat_id":"@chan"}]')
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_IDS", raising=False)
    s = load_settings()
    assert len(s.telegram_targets) == 2
    assert s.telegram_targets[0].name == "team-a"


def test_load_telegram_unset(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_TARGETS", raising=False)
    s = load_settings()
    assert s.telegram_targets == []
