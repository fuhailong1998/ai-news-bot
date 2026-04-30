# AI News Bot 🤖

[English](./README.md) | [中文](./README.zh-CN.md)

Automatically fetch updates from major AI companies, **summarize them in Chinese with an LLM**, and push to your **Feishu (Lark) groups + Telegram chats** in parallel via webhook bots.
Runs entirely on **GitHub Actions** — no server required.

## Features
- ✅ **24 data sources** (OpenAI / Anthropic / Google / Meta / xAI / DeepSeek / Qwen / Kimi / GLM / MiniMax …)
- ✅ Multiple fetcher types: RSS / HTML parser / GitHub Releases / GitHub Tags / HuggingFace org
- ✅ SQLite-based deduplication, persisted by committing back to the repo
- ✅ **Multi-channel broadcast**: any number of Feishu groups + any number of Telegram chats / channels in parallel
- ✅ **Chinese summarization + auto tags** via OpenAI-compatible LLM (DeepSeek / Kimi / Qwen / GLM / GPT)
- ✅ Rate limiting + exponential-backoff retry; per-target failures don't abort others
- ✅ Auto-runs every 5 minutes (GitHub Actions cron)

## Output Preview

A Feishu card (or equivalent Telegram message) looks like:

```
┌─────────────────────────────────────┐
│ 🤖 DeepSeek HF Models               │
├─────────────────────────────────────┤
│ 🤗 New model: deepseek-ai/DeepSeek-V4│
│                                     │
│ 📅 2026-04-28  `模型发布` `开源`      │
│                                     │
│ DeepSeek 推出 V4-Pro，支持 200K 上下  │
│ 文，推理速度比 V3 提升 40%，已开源至  │
│ HuggingFace。                       │
│                                     │
│ [🔗 查看原文]                        │
└─────────────────────────────────────┘
```

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
| `FEISHU_WEBHOOKS` | ⬜ | **Multiple webhooks** (broadcast to many Feishu groups). See [Multiple Feishu webhooks](#multiple-feishu-webhooks) |
| `TELEGRAM_BOT_TOKEN` | ⬜ | Telegram bot token (from @BotFather). See [Telegram setup](#telegram-setup) |
| `TELEGRAM_CHAT_IDS` | ⬜ | Comma-separated Telegram chat IDs (e.g. `-100123,-100456,@my_channel`) |
| `TELEGRAM_TARGETS` | ⬜ | (advanced) Multi-bot JSON list, overrides the pair above |
| `LLM_API_KEY` | ⬜ | LLM key for **Chinese summarization**. See [LLM summarizer](#llm-summarizer) |
| `LLM_BASE_URL` | ⬜ | OpenAI-compatible base URL. Default `https://api.openai.com/v1` |
| `LLM_MODEL` | ⬜ | Model name. e.g. `deepseek-chat` / `gpt-4o-mini` / `glm-4-flash` |

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

### Telegram setup

The bot can additionally push to **Telegram** chats / channels in parallel with Feishu (independent — you can use either or both).

**Step 1 — create a bot:**
1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the bot **token** (looks like `1234567890:AAH...`)
2. Add the bot to your group / channel; in a channel, give it **post messages** permission

**Step 2 — get chat IDs:**
- For a group: add **@userinfobot** to the group, it will reply with the group's chat ID (negative number like `-100123456789`)
- For a public channel: use `@channel_username` (with the `@`)
- For a personal chat: message the bot, then `curl https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `"chat":{"id":...}`

**Step 3 — configure secrets:**

Simple (one bot, multiple chats):
```
TELEGRAM_BOT_TOKEN=1234567890:AAH...
TELEGRAM_CHAT_IDS=-100111,@my_channel,-100222
```

Advanced (multiple bots; JSON, takes precedence):
```json
TELEGRAM_TARGETS=[{"bot_token":"t1","chat_id":"-100111","name":"team-a"},{"bot_token":"t2","chat_id":"@my_channel"}]
```

### LLM summarizer

The bot ships with an **OpenAI-compatible** LLM client that produces a **≤80-char Chinese summary + 1-3 tags** for every news item. It's enabled by default in `config/settings.yaml` but only **activates when `LLM_API_KEY` is set** (no key → silently skipped, raw summary is used).

Recommended providers:

| Provider | `LLM_BASE_URL` | `LLM_MODEL` | Note |
|---|---|---|---|
| **DeepSeek** ⭐ | `https://api.deepseek.com/v1` | `deepseek-chat` | Cheap (~¥0.001/item), great Chinese |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | **Free tier** (1M tokens/day) |
| Alibaba Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | Domestic friendly |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | Strong Chinese |
| OpenAI | `https://api.openai.com/v1` (default) | `gpt-4o-mini` | Most reliable, needs intl card |

Tags are picked from: `模型发布 / 融资 / 开源 / 论文 / 产品 / 政策 / 其它`.
The prompt and char limits are in `core/summarizer.py` and `config/settings.yaml`.
To disable, set `summarizer.enabled: false` in `config/settings.yaml`.

### 4. Initial seed (important!)
Actions tab → AI News Bot → Run workflow → choose `seed`.
This loads all current items into the dedup DB **without pushing**, to avoid flooding the group.

### 5. Auto-run
The bot then runs every 5 minutes; new items are pushed **simultaneously** to all configured Feishu groups and Telegram chats / channels.
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

> 💡 **Global freshness window**: any item with `published_at` older than
> `storage.first_run_window_days` (default **7 days**) is silently dropped.
> This protects against:
> 1. Adding a brand-new source whose RSS contains years of history
> 2. HF API occasionally surfacing models days after they were uploaded
>    (e.g. private→public flips, ranking instability)
>
> Items with no `published_at` (some HTML parsers can't extract dates) are
> still pushed.

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
