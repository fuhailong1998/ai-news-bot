# AI News Bot 🤖

[English](./README.md) | [中文](./README.zh-CN.md)

Automatically fetch updates from major AI companies and push them to your **Feishu (Lark)** group via webhook bot.
Runs entirely on **GitHub Actions** — no server required.

## Features
- ✅ **23+ data sources** (OpenAI / Anthropic / Google / Meta / DeepSeek / Qwen / Kimi / GLM / MiniMax …)
- ✅ Multiple fetcher types: RSS / HTML parser / GitHub Releases / GitHub Tags / HuggingFace org
- ✅ SQLite-based deduplication, persisted by committing back to the repo
- ✅ Feishu interactive cards (title + summary + tags + "Read more" button)
- ✅ Optional LLM summarization (OpenAI-compatible: DeepSeek / Kimi / Qwen / GPT)
- ✅ Rate limiting + exponential-backoff retry
- ✅ Auto runs every 30 minutes (GitHub Actions cron)

## Quick Start (5 steps)

### 1. Fork this repo
**Public repo recommended** (GitHub Actions is free forever for public repos).

### 2. Create a Feishu bot
Group settings → Group bots → Add custom bot → copy the Webhook URL.
(Optional) Enable signature verification and copy the secret.

### 3. Configure Secrets
Settings → Secrets and variables → Actions → New repository secret:

| Name | Required | Description |
|---|---|---|
| `FEISHU_WEBHOOK_URL` | ✅ (or `FEISHU_WEBHOOKS`) | Single Feishu bot webhook URL |
| `FEISHU_SECRET` | ⬜ | Signature secret for the single webhook above |
| `FEISHU_WEBHOOKS` | ⬜ | **Multiple webhooks** (broadcast same news to many groups). Takes precedence over the single pair. See [Multiple Feishu webhooks](#multiple-feishu-webhooks) below. |
| `LLM_API_KEY` | ⬜ | API key when summarization is enabled (e.g. DeepSeek) |
| `LLM_BASE_URL` | ⬜ | Default `https://api.openai.com/v1`; can be `https://api.deepseek.com/v1` |
| `LLM_MODEL` | ⬜ | e.g. `deepseek-chat` / `gpt-4o-mini` |

### Multiple Feishu webhooks

To broadcast the **same news** to multiple Feishu groups (e.g. several teams want the feed), set the `FEISHU_WEBHOOKS` secret. Two formats are accepted:

**Format A — JSON list (recommended, supports per-target signature secret + label):**
```json
[
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/XXX", "secret": "secretA", "name": "team-a"},
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/YYY", "secret": "secretB", "name": "team-b"},
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/ZZZ"}
]
```

**Format B — pipe/comma delimited (simpler, one line):**
```
https://open.feishu.cn/.../XXX|secretA, https://open.feishu.cn/.../YYY|secretB, https://open.feishu.cn/.../ZZZ|
```
- Use `|` between url and secret (secret may be empty after pipe)
- Use `,` (or newline) between targets

Each card / digest is sent to **every** target. A single target's failure does **not** affect others. If neither `FEISHU_WEBHOOKS` nor `FEISHU_WEBHOOK_URL` is set, the bot logs an error and skips push.

### 4. Initial seed (important!)
Actions tab → AI News Bot → Run workflow → choose `seed`.
This loads all current items into the dedup DB **without pushing**, to avoid flooding the group.

### 5. Auto-run
The bot then runs every 30 minutes; only newly-published items will be pushed.
You can also manually `Run workflow` → `once` for an immediate run.

## Deployment Options

### Option A: GitHub Actions (serverless, recommended for personal use)

See "Quick Start" above. Pros: zero cost, zero maintenance. Cons: trigger delay 5–15 min; dedup DB is persisted via commits.

### Option B: Local

```bash
cd ai_news_bot
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # fill in webhook
export $(grep -v '^#' .env | xargs)
python main.py --seed   # first time only
python main.py --once   # subsequent runs
```

Add cron:
```bash
crontab -e
*/30 * * * * cd /path/to/ai_news_bot && /path/to/.venv/bin/python main.py --once >> logs/cron.log 2>&1
```

### Option C: VPS systemd timer (recommended for production)

Clone the repo to any Linux VPS, then:

```bash
sudo bash deploy/install_vps.sh
sudo vi /etc/ai_news_bot.env   # fill in FEISHU_WEBHOOK_URL etc.
sudo systemctl restart ai-news-bot.timer
```

The script will:
1. Install to `/opt/ai_news_bot`, create venv, install deps
2. Generate `/etc/ai_news_bot.env` template
3. Register systemd timer (every 30 min, 2-min boot delay)
4. Auto-seed on first run

Common commands:
```bash
sudo systemctl start ai-news-bot.service          # run once now
sudo journalctl -u ai-news-bot -f                  # tail logs
systemctl list-timers ai-news-bot.timer           # next trigger time
sudo systemctl disable --now ai-news-bot.timer    # stop
```

### Option D: Local Docker
If you really want Docker, write a small Dockerfile based on `python:3.11-slim` + `pip install -e .` + `CMD python main.py --once`, triggered by external cron.

## Add / Modify Data Sources

Edit `ai_news_bot/config/sources.yaml`. See [CONTRIBUTING.md](./CONTRIBUTING.md) for details.

- **RSS**: just add `{name, type: rss, url}`
- **HuggingFace org**: `{name, type: huggingface_org, org: "Qwen"}` — best for Chinese labs
- **GitHub Releases**: `{name, type: github_releases, repo: "owner/repo"}`
- **GitHub Tags**: `{name, type: github_tags, repo: "owner/repo"}`
- **HTML**: register a parser function in `core/fetcher/html_fetcher.py`'s `PARSERS` dict

> ⚠️ HTML sources default to `enabled: false`; enable them after writing the parser.

## Tuning Push Strategy

Edit `ai_news_bot/config/settings.yaml`:
- `push.per_run_limit`: max individual cards per run (the rest are merged into a digest)
- `push.interval_seconds`: delay between cards (Feishu limit: 100/min)
- `summarizer.enabled`: enable LLM summarization

## Project Structure

```
ai_news_bot/
├── config/{sources,settings}.yaml
├── core/
│   ├── fetcher/{base,rss,html,github,hf,factory}.py
│   ├── notifier/feishu.py
│   ├── models.py     # NewsItem + Settings
│   ├── dedup.py      # SQLite
│   ├── summarizer.py # optional LLM
│   └── runner.py     # main pipeline
├── storage/seen.db   # dedup DB (committed back to repo)
├── tests/
└── main.py
.github/workflows/run.yml
```

## Contributing

PRs welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add new sources.

## License
[MIT](./LICENSE)
