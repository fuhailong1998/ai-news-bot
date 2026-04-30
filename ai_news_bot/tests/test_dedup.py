from datetime import datetime
from pathlib import Path

import pytest

from core.dedup import Dedup
from core.models import NewsItem


@pytest.fixture
def dedup(tmp_path: Path):
    d = Dedup(tmp_path / "test.db")
    yield d
    d.close()


def _item(url="https://x.com/a", title="A", summary="hello") -> NewsItem:
    return NewsItem(source="OpenAI", title=title, url=url,
                    published_at=datetime(2026, 1, 1), summary=summary)


def test_new_then_seen(dedup):
    it = _item()
    assert dedup.is_new(it) is True
    dedup.mark_seen(it, pushed=True)
    assert dedup.is_new(it) is False


def test_same_url_not_new_even_if_content_changes(dedup):
    """Same URL should never re-push, even if summary mutates (e.g. HF download counts,
    OpenAI Status incident progressing). Avoids spamming users with duplicates."""
    it1 = _item(summary="v1")
    dedup.mark_seen(it1, pushed=True)
    it2 = _item(summary="v2")
    assert dedup.is_new(it2) is False


def test_cleanup(dedup):
    it = _item()
    dedup.mark_seen(it, pushed=True)
    assert dedup.cleanup(retention_days=0) >= 1


def test_known_sources(dedup):
    assert dedup.known_sources() == set()
    dedup.mark_seen(_item(url="https://x.com/a"), pushed=True)
    dedup.mark_seen(NewsItem(source="Other", title="T", url="https://y.com/b",
                             published_at=datetime(2026, 1, 1), summary="s"))
    assert dedup.known_sources() == {"OpenAI", "Other"}


def test_cursor_initial_none(dedup):
    assert dedup.get_cursor("Qwen HF Models") is None


def test_cursor_set_and_get(dedup):
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 28, 10, 0, 0))
    assert dedup.get_cursor("Qwen HF Models") == datetime(2026, 4, 28, 10, 0, 0)


def test_cursor_monotonic(dedup):
    """Cursor must never go backwards even if a smaller value is supplied."""
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 28, 10, 0, 0))
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 27, 10, 0, 0))
    assert dedup.get_cursor("Qwen HF Models") == datetime(2026, 4, 28, 10, 0, 0)


def test_cursor_advances_on_larger_value(dedup):
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 28, 10, 0, 0))
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 29, 10, 0, 0))
    assert dedup.get_cursor("Qwen HF Models") == datetime(2026, 4, 29, 10, 0, 0)


def test_cursor_per_source_independent(dedup):
    dedup.update_cursor("Qwen HF Models", datetime(2026, 4, 28))
    dedup.update_cursor("xAI HF Models", datetime(2026, 4, 25))
    assert dedup.get_cursor("Qwen HF Models") == datetime(2026, 4, 28)
    assert dedup.get_cursor("xAI HF Models") == datetime(2026, 4, 25)
