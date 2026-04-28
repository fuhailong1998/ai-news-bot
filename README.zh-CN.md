# AI News Bot 🤖

[English](./README.md) | [中文](./README.zh-CN.md)

定时抓取全球主流 AI 公司更新新闻，**用 LLM 生成中文摘要 + 标签**，并通过 **飞书 (Lark) 群 + Telegram 群 / 频道** 多通道并发推送。
完全运行在 **GitHub Actions** 上，无需自己部署服务器。

## 特性
- ✅ 27+ 个数据源（OpenAI / Anthropic / Google / Meta / DeepSeek / Qwen / Kimi / GLM / MiniMax …）
- ✅ 5 种抓取方式：RSS / HTML parser / GitHub Releases / GitHub Tags / HuggingFace org
- ✅ SQLite 去重，commit 回仓库实现持久化
- ✅ **多通道广播**：任意多个飞书群 + 任意多个 Telegram 群 / 频道并发推送
- ✅ **中文摘要 + 自动标签**（OpenAI 兼容 LLM：DeepSeek / Kimi / Qwen / GLM / GPT）
- ✅ 限速 + 指数退避重试；单个目标失败不影响其他
- ✅ 5 分钟自动运行（GitHub Actions cron）

## 推送效果预览

飞书卡片 / Telegram 消息样式：

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

## 快速开始（5 步）

### 1. Fork 本仓库
建议设为 **公开仓库**（GitHub Actions 永久免费）。

### 2. 创建飞书机器人
群设置 → 群机器人 → 添加自定义机器人 → 复制 Webhook URL。
（可选）开启签名校验，复制 secret。

### 3. 配置 Secrets
Settings → Secrets and variables → Actions → New repository secret：

| Name | 必填 | 说明 |
|---|---|---|
| `FEISHU_WEBHOOK_URL` | ✅（或 `FEISHU_WEBHOOKS`） | 单个飞书机器人 webhook |
| `FEISHU_SECRET` | ⬜ | 上面单 webhook 的签名密钥 |
| `FEISHU_WEBHOOKS` | ⬜ | **多个 webhook**（广播到多个飞书群）。详见 [多飞书 webhook 配置](#多飞书-webhook-配置) |
| `TELEGRAM_BOT_TOKEN` | ⬜ | Telegram bot token（从 @BotFather 获取）。详见 [Telegram 配置](#telegram-配置) |
| `TELEGRAM_CHAT_IDS` | ⬜ | Telegram chat IDs，逗号分隔（如 `-100123,-100456,@my_channel`） |
| `TELEGRAM_TARGETS` | ⬜ | (高级) 多 bot JSON 列表，优先级高于上面两项 |
| `LLM_API_KEY` | ⬜ | LLM key，**开启中文摘要**。详见 [LLM 中文摘要](#llm-中文摘要) |
| `LLM_BASE_URL` | ⬜ | OpenAI 兼容 base URL。默认 `https://api.openai.com/v1` |
| `LLM_MODEL` | ⬜ | 模型名，如 `deepseek-chat` / `gpt-4o-mini` / `glm-4-flash` |

### 多飞书 webhook 配置

如果想把**同一条新闻**同时广播到多个飞书群（多个部门都要收），配置 `FEISHU_WEBHOOKS` Secret。支持两种格式：

**格式 A — JSON 列表（推荐，每个目标可单独配签名 + 标签）：**
```json
[
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/XXX", "secret": "secretA", "name": "team-a"},
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/YYY", "secret": "secretB", "name": "team-b"},
  {"url": "https://open.feishu.cn/open-apis/bot/v2/hook/ZZZ"}
]
```

**格式 B — 管道/逗号分隔（一行搞定，简单场景）：**
```
https://open.feishu.cn/.../XXX|secretA, https://open.feishu.cn/.../YYY|secretB, https://open.feishu.cn/.../ZZZ|
```
- `|` 分隔 url 和 secret（没签名就 `|` 后留空）
- `,`（或换行）分隔多个目标

每张卡片 / digest 都会**并发发送到全部目标**。单个目标失败不影响其他。两个变量都没配，日志会报错并跳过推送。

### Telegram 配置

机器人可以额外推送到 **Telegram** 群 / 频道，与飞书并行（独立，开任意一个都行）。

**步骤 1 — 创建 bot：**
1. 在 Telegram 里给 **@BotFather** 发 `/newbot`，按提示走，**复制 bot token**（类似 `1234567890:AAH...`）
2. 把 bot 拉进你的群 / 频道；如果是频道，给 bot **post messages** 权限

**步骤 2 — 拿 chat ID：**
- 群组：把 **@userinfobot** 加进群，它会回复群的 chat ID（负数，如 `-100123456789`）
- 公开频道：直接用 `@channel_username`（带 `@`）
- 私聊：先给 bot 发条消息，然后 `curl https://api.telegram.org/bot<TOKEN>/getUpdates` 看 `"chat":{"id":...}`

**步骤 3 — 配置 Secrets：**

简单形式（单 bot，多个 chat）：
```
TELEGRAM_BOT_TOKEN=1234567890:AAH...
TELEGRAM_CHAT_IDS=-100111,@my_channel,-100222
```

高级形式（多 bot，JSON，优先级更高）：
```json
TELEGRAM_TARGETS=[{"bot_token":"t1","chat_id":"-100111","name":"team-a"},{"bot_token":"t2","chat_id":"@my_channel"}]
```

### LLM 中文摘要

机器人内置 **OpenAI 兼容** LLM 客户端，为每条新闻生成 **≤80 字中文摘要 + 1-3 个标签**。`config/settings.yaml` 默认已开启，**只在配置了 `LLM_API_KEY` 时才生效**（没有 key 则静默跳过，使用原始英文 summary）。

推荐 LLM 服务：

| 服务 | `LLM_BASE_URL` | `LLM_MODEL` | 备注 |
|---|---|---|---|
| **DeepSeek** ⭐ | `https://api.deepseek.com/v1` | `deepseek-chat` | 便宜（约 ¥0.001/条），中文好 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | **免费层**（每天 100 万 tokens） |
| 阿里 Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | 国内畅通 |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | 中文强 |
| OpenAI | `https://api.openai.com/v1`（默认） | `gpt-4o-mini` | 最稳定，需海外信用卡 |

标签从 `模型发布 / 融资 / 开源 / 论文 / 产品 / 政策 / 其它` 中选取。
prompt 和字数限制在 `core/summarizer.py` 和 `config/settings.yaml`。
要禁用，把 `summarizer.enabled` 改为 `false`。

### 4. 首次 seed（重要！）
Actions 标签页 → AI News Bot → Run workflow → 选择 `seed`。
这会把当前所有新闻入库但**不推送**，避免首次刷屏。

### 5. 自动运行
之后每 5 分钟自动跑一次，新增的新闻会**同时**推送到所有飞书群和 Telegram 群 / 频道。
也可手动 `Run workflow` → `once` 立即触发。

## 部署方式（任选其一）

### 方案 A：GitHub Actions（无服务器，推荐个人）

详见上方"快速开始"。优点：0 成本免维护；缺点：触发延迟 5-15 min，去重 db 通过 commit 持久化。

### 方案 B：本地直接跑

```bash
cd ai_news_bot
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # 填 webhook
export $(grep -v '^#' .env | xargs)
python main.py --seed   # 首次
python main.py --once   # 之后每次
```

加 cron 自动跑：
```bash
crontab -e
*/30 * * * * cd /path/to/ai_news_bot && /path/to/.venv/bin/python main.py --once >> logs/cron.log 2>&1
```

### 方案 C：VPS systemd timer（推荐生产）

把代码 clone 到 VPS（任意 Linux），然后：

```bash
sudo bash deploy/install_vps.sh
sudo vi /etc/ai_news_bot.env   # 填入 FEISHU_WEBHOOK_URL 等
sudo systemctl restart ai-news-bot.timer
```

脚本会：
1. 安装到 `/opt/ai_news_bot` + 创建 venv + 装依赖
2. 在 `/etc/ai_news_bot.env` 生成 secrets 模板
3. 注册 systemd timer（每 30 分钟跑一次，开机延迟 2 min）
4. 首次自动 seed

常用命令：
```bash
sudo systemctl start ai-news-bot.service          # 立即跑一次
sudo journalctl -u ai-news-bot -f                  # 看实时日志
systemctl list-timers ai-news-bot.timer           # 看下次触发时间
sudo systemctl disable --now ai-news-bot.timer    # 停止
```

### 方案 D：本地 Docker（如果你坚持要 Docker，可自己写 Dockerfile，结构很简单）
基础镜像 `python:3.11-slim` + `pip install -e .` + `CMD python main.py --once`，配合外部 cron 触发。


## 添加 / 修改数据源

编辑 `ai_news_bot/config/sources.yaml`。

- **RSS 源**：直接加一行 `{name, type: rss, url}`
- **HTML 源**：在 `core/fetcher/html_fetcher.py` 的 `PARSERS` 注册一个解析函数，
  签名 `(html: str, base_url: str) -> list[dict]`，返回字典列表。
- **GitHub Releases**：`{name, type: github_releases, repo: "owner/repo"}`

> ⚠️ HTML 源默认 `enabled: false`，需要你写完 parser 再开启。

## 调整推送策略

编辑 `ai_news_bot/config/settings.yaml`：
- `push.per_run_limit`：每轮最多单独发几张卡片（其余归并成 digest）
- `push.interval_seconds`：每条间隔（飞书限速 100 条/分钟）
- `summarizer.enabled`：是否启用 LLM 摘要

## 项目结构

```
ai_news_bot/
├── config/{sources,settings}.yaml
├── core/
│   ├── fetcher/{base,rss,html,github,factory}.py
│   ├── notifier/feishu.py
│   ├── models.py     # NewsItem + Settings
│   ├── dedup.py      # SQLite
│   ├── summarizer.py # 可选 LLM
│   └── runner.py     # 主流程
├── storage/seen.db   # 去重库（commit 回仓库）
├── tests/
└── main.py
.github/workflows/run.yml
```

## License
MIT
