# Contributing Guide

[English](./CONTRIBUTING.md) | [中文](./CONTRIBUTING.zh-CN.md)

Welcome contributions to ai-news-bot! The main extension point of this project is **adding new AI news sources**.

## 🚀 Getting Started

### Local development setup

```bash
git clone https://github.com/fuhailong1998/ai-news-bot.git
cd ai-news-bot/ai_news_bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure Feishu webhook (for local testing)
cp .env.example .env
vi .env

# Run tests
pytest

# One-shot fetch (seed first to avoid flooding)
export $(grep -v '^#' .env | xargs)
python main.py --seed
python main.py --once
```

---

## 🧩 Adding a New Data Source

There are **5 fetcher types**, ordered by ease of use:

| Type | Difficulty | Use Case |
|---|:---:|---|
| `rss` | ⭐ | Vendor publishes RSS / Atom feed |
| `huggingface_org` | ⭐ | Vendor has an HF org (great for Chinese labs) |
| `github_releases` | ⭐ | Open-source project ships GitHub Releases |
| `github_tags` | ⭐⭐ | No Releases but pushes git tags |
| `html` | ⭐⭐⭐ | Static HTML page (SPA not supported) |

### Method 1: Add an RSS source (easiest)

Add a single line to `ai_news_bot/config/sources.yaml`:

```yaml
- {name: "Your Source Name", type: rss, url: "https://example.com/feed.xml", priority: high}
```

Fields:
- `name`: shown in the Feishu card title
- `priority`: `high` / `medium` / `low` (no behavioral difference yet, reserved for future)
- `enabled`: optional, defaults to `true`

### Method 2: Monitor a HuggingFace organization

The `repo` field is the HF org name (not GitHub):

```yaml
- {name: "YourVendor HF Models", type: huggingface_org, repo: "OrgName", priority: high}
```

How to find the org name: visit `https://huggingface.co/OrgName` — that path segment is the name.

### Method 3: Monitor GitHub Releases

```yaml
- {name: "ProjectName GitHub", type: github_releases, repo: "owner/repo", priority: medium}
```

⚠️ The repo must **actually publish Releases** (not just tags). Verify with `curl https://api.github.com/repos/OWNER/REPO/releases` — should be non-empty.

### Method 4: Monitor GitHub Tags

```yaml
- {name: "ProjectName tags", type: github_tags, repo: "owner/repo", priority: medium}
```

### Method 5: Add an HTML parser (most complex)

If the target site is **static HTML** (not a SPA), you can write a custom parser.

#### Step 1: Check if it's a SPA

```bash
curl -s "https://target-site.com/news" | grep -c "<script"
# Many <script> tags and no visible news titles → likely a SPA → give up
# Use RSSHub bridge or HF instead
```

#### Step 2: Write a parser in `core/fetcher/html_fetcher.py`

```python
def parse_yourorg(html: str, base_url: str) -> list[dict]:
    """Parse YourOrg news listing page."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for card in soup.select(".news-card"):  # ← actual CSS selector
        title_el = card.find("h2")
        link_el = card.find("a")
        date_el = card.find("time")
        if not (title_el and link_el):
            continue
        out.append({
            "title": title_el.get_text(strip=True),
            "url": urljoin(base_url, link_el.get("href")),
            "summary": (card.find("p") or "").get_text(strip=True)[:300],
            "published_at": dateparser.parse(date_el.get("datetime")) if date_el else None,
        })
    return _dedup_dicts(out)
```

#### Step 3: Register in `PARSERS`

```python
PARSERS: dict[str, Callable[[str, str], list[dict]]] = {
    "anthropic": parse_anthropic,
    "yourorg": parse_yourorg,   # ← new
}
```

#### Step 4: Reference in sources.yaml

```yaml
- {name: "YourOrg", type: html, url: "https://yourorg.com/news", parser: yourorg}
```

#### Step 5: Local verification

```bash
python -c "
import asyncio, httpx
from core.models import load_sources
from core.fetcher.factory import build_fetcher
async def go():
    src = next(s for s in load_sources() if s.name == 'YourOrg')
    async with httpx.AsyncClient(timeout=20, headers={'User-Agent':'Mozilla/5.0'}) as c:
        items = await build_fetcher(src, c).fetch()
    for it in items[:5]:
        d = it.published_at.strftime('%Y-%m-%d') if it.published_at else '----'
        print(f'[{d}] {it.title[:80]}')
asyncio.run(go())
"
```

Should print at least one item with a correct date.

---

## 🆕 Adding a New Fetcher Type

If none of the 5 above fit (e.g. Telegram channel / WeChat via RSSHub / arXiv):

### 1. Create the fetcher
`core/fetcher/your_fetcher.py`:
```python
from .base import BaseFetcher
from ..models import NewsItem

class YourFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        # Use self.client (httpx.AsyncClient) and self.source
        ...
        return [NewsItem(source=self.source.name, ...)]
```

### 2. Register in factory.py
```python
case "your_type":
    return YourFetcher(source, client)
```

### 3. Update the type Literal in models.py
```python
type: Literal["rss", "html", "github_releases", "github_tags", "huggingface_org", "your_type"]
```

### 4. Add tests `tests/test_your_fetcher.py`

See `tests/test_rss.py` for `respx`-based HTTP mocking patterns.

---

## 🎨 Customizing the Feishu Card

Edit `_build_card` in `core/notifier/feishu.py`.
Feishu card JSON docs: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/feishu-cards/card-overview

Common tweaks:
- header `template`: `blue` / `red` / `green` / `orange` / `grey` / `purple`
- Add image: `{"tag": "img", "img_key": "..."}` (need to upload via Feishu image API first)
- Mention a user: write `<at id=user_open_id></at>` inside markdown

For Telegram messages, edit `_build_text` in `core/notifier/telegram.py` (Telegram supports a small HTML subset: `<b>`, `<i>`, `<a>`, `<code>`, `<pre>`).

---

## 🤖 Customizing the LLM Summarizer

The summarizer lives in `core/summarizer.py`. It calls any **OpenAI-compatible** `/chat/completions` endpoint and asks for a JSON object with `summary` (≤80 chars Chinese) and `tags` (1-3 items from a fixed list).

**Tweak the prompt** — edit `PROMPT_TEMPLATE` in `core/summarizer.py`. Useful customizations:
- Add a custom tag set (e.g. include `Agent` / `多模态` / `Benchmark`)
- Switch output language (the bot is Chinese-first by default)
- Add few-shot examples for better consistency

**Tweak length / model** — `config/settings.yaml`:
```yaml
summarizer:
  enabled: true
  model: deepseek-chat        # overridden by LLM_MODEL env if set
  max_input_chars: 2000       # how much of item.content/summary to feed
  max_summary_chars: 80       # cap output summary
```

**Switch LLM provider** — set Secrets:

| Provider | `LLM_BASE_URL` | `LLM_MODEL` | Note |
|---|---|---|---|
| DeepSeek ⭐ | `https://api.deepseek.com/v1` | `deepseek-chat` | Cheap, great Chinese |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | **Free tier** |
| Alibaba Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | Domestic |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | Strong Chinese |
| OpenAI | (default) | `gpt-4o-mini` | Reliable |

**Fail-safe** — if the LLM call fails or `LLM_API_KEY` is missing, `ai_summary` stays empty and the card falls back to the raw `summary` field. Failures are logged at `WARNING` level but don't break the run.

---

## ✅ Pull Request Checklist

- [ ] `pytest` passes
- [ ] New source manually verified locally (≥1 item with correct date)
- [ ] Any `enabled: false` entry must fetch successfully before flipping to `true`
- [ ] Commit messages follow conventional commits (`feat:`, `fix:`, `docs:` …)
- [ ] No `.env` or any secret-bearing file committed

## 🐛 Issue Template

Please include:
- Source `name` that's broken
- Full traceback (from `journalctl` or GitHub Actions logs)
- The source URL (so others can reproduce)

## 💡 Want to add a source but can't write the parser?

Open an issue with:
- Target site URL
- Known update frequency
- Whether it's a SPA (use the `grep -c "<script"` trick above)

We can discuss alternative signals (HF / GitHub / RSSHub etc.).
