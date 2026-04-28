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
