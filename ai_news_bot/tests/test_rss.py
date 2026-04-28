import httpx
import pytest
import respx

from core.models import SourceConfig
from core.fetcher.rss_fetcher import RssFetcher

SAMPLE_RSS = """<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'><channel>
<title>Test</title>
<item>
<title>Hello World</title>
<link>https://example.com/post1</link>
<description>&lt;p&gt;Body&lt;/p&gt;</description>
<pubDate>Mon, 27 Apr 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""


@pytest.mark.asyncio
async def test_rss_parse():
    src = SourceConfig(name="Test", type="rss", url="https://feed.example.com/rss")
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://feed.example.com") as mock:
            mock.get("/rss").mock(return_value=httpx.Response(200, content=SAMPLE_RSS.encode()))
            items = await RssFetcher(src, client).fetch()
    assert len(items) == 1
    assert items[0].title == "Hello World"
    assert items[0].url == "https://example.com/post1"
    assert "Body" in items[0].summary
