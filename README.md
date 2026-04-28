# AI News Bot 🤖

定时抓取全球主流 AI 公司更新新闻，去重后通过**飞书 Webhook 机器人**推送到群聊。
完全运行在 **GitHub Actions** 上，无需自己部署服务器。

## 特性
- ✅ 27 个数据源（OpenAI / Anthropic / Google / Meta / DeepSeek / Qwen / Kimi …）
- ✅ RSS / HTML / GitHub Releases 三种抓取方式
- ✅ SQLite 去重，commit 回仓库实现持久化
- ✅ 飞书交互式卡片（标题 + 摘要 + 标签 + 原文按钮）
- ✅ 可选 LLM 摘要（兼容 DeepSeek / Kimi / Qwen / OpenAI）
- ✅ 限速 + 指数退避重试
- ✅ 30 分钟自动运行（GitHub Actions cron）

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
| `FEISHU_WEBHOOK_URL` | ✅ | 飞书机器人 webhook |
| `FEISHU_SECRET` | ⬜ | 飞书签名校验密钥 |
| `LLM_API_KEY` | ⬜ | 开启摘要时填，如 DeepSeek API key |
| `LLM_BASE_URL` | ⬜ | 默认 `https://api.openai.com/v1`，可改 `https://api.deepseek.com/v1` |
| `LLM_MODEL` | ⬜ | 如 `deepseek-chat` / `gpt-4o-mini` |

### 4. 首次 seed（重要！）
Actions 标签页 → AI News Bot → Run workflow → 选择 `seed`。
这会把当前所有新闻入库但**不推送**，避免首次刷屏。

### 5. 自动运行
之后每 30 分钟自动跑一次，新增的新闻会推送到飞书群。
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
