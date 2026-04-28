# 贡献指南 / Contributing

欢迎为 ai-news-bot 添加新的数据源！本项目的核心扩展点就是**接入新的 AI 资讯源**。

## 🚀 快速上手

### 本地开发环境

```bash
git clone https://github.com/fuhailong1998/ai-news-bot.git
cd ai-news-bot/ai_news_bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 配置飞书 webhook（用于本地测试）
cp .env.example .env
vi .env

# 跑测试
pytest

# 单次抓取（不推送，先 seed）
export $(grep -v '^#' .env | xargs)
python main.py --seed
python main.py --once
```

---

## 🧩 添加新数据源

总共有 **5 种源类型**，按可获取程度优先级：

| 类型 | 难度 | 适用场景 |
|---|:---:|---|
| `rss` | ⭐ | 官方提供 RSS / Atom feed |
| `huggingface_org` | ⭐ | 厂商在 HF 有组织（适合中国 lab）|
| `github_releases` | ⭐ | 开源项目走 GitHub Releases |
| `github_tags` | ⭐⭐ | 不发 Releases 但打 tags |
| `html` | ⭐⭐⭐ | 静态 HTML 页面（SPA 不支持） |

### 方式 1：添加 RSS 源（最简单）

只需在 `ai_news_bot/config/sources.yaml` 加一行：

```yaml
- {name: "你的源名称", type: rss, url: "https://example.com/feed.xml", priority: high}
```

字段说明：
- `name`：显示在飞书卡片标题里
- `priority`：`high` / `medium` / `low`（目前未做差异化处理，预留扩展）
- `enabled`：可选，默认 `true`

### 方式 2：添加 HuggingFace 组织监控

`repo` 字段填 HF 组织名（不是 GitHub）：

```yaml
- {name: "你的厂商 HF Models", type: huggingface_org, repo: "OrgName", priority: high}
```

如何找组织名：访问 `https://huggingface.co/OrgName`，URL 中那一段就是。

### 方式 3：添加 GitHub Releases 监控

```yaml
- {name: "项目名 GitHub", type: github_releases, repo: "owner/repo", priority: medium}
```

⚠️ 仓库必须**真的发了 Release**（不是只打 tag）。可先用 `curl https://api.github.com/repos/OWNER/REPO/releases` 验证非空。

### 方式 4：添加 GitHub Tags 监控

```yaml
- {name: "项目名 tags", type: github_tags, repo: "owner/repo", priority: medium}
```

### 方式 5：添加 HTML parser（最复杂）

如果目标站点是**静态 HTML**（不是 SPA），可以写自定义 parser。

#### 第 1 步：判断是否是 SPA

```bash
curl -s "https://target-site.com/news" | grep -c "<script"
# 如果有几十个 <script> 且看不到新闻标题文字，多半是 SPA → 放弃
# 推荐改用 RSSHub 桥接或抓 HF
```

#### 第 2 步：在 `core/fetcher/html_fetcher.py` 写 parser

```python
def parse_yourorg(html: str, base_url: str) -> list[dict]:
    """解析 YourOrg 新闻列表页。"""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for card in soup.select(".news-card"):  # ← 根据实际 CSS 选择器
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

#### 第 3 步：注册到 `PARSERS` 字典

```python
PARSERS: dict[str, Callable[[str, str], list[dict]]] = {
    "anthropic": parse_anthropic,
    "yourorg": parse_yourorg,   # ← 新增
}
```

#### 第 4 步：在 sources.yaml 引用

```yaml
- {name: "YourOrg", type: html, url: "https://yourorg.com/news", parser: yourorg}
```

#### 第 5 步：本地验证

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

输出至少 1 条带正确日期的新闻才算成功。

---

## 🆕 添加新的 Fetcher 类型

如果上述 5 种都不适用（例如你想接入 Telegram channel / 微信公众号 via RSSHub / arXiv），按以下步骤：

### 1. 创建新 fetcher 文件
`core/fetcher/your_fetcher.py`：
```python
from .base import BaseFetcher
from ..models import NewsItem

class YourFetcher(BaseFetcher):
    async def fetch(self) -> list[NewsItem]:
        # 用 self.client (httpx.AsyncClient) 和 self.source 实现
        ...
        return [NewsItem(source=self.source.name, ...)]
```

### 2. 在 factory.py 注册
```python
case "your_type":
    return YourFetcher(source, client)
```

### 3. 在 models.py 的 SourceConfig 加上 type literal
```python
type: Literal["rss", "html", "github_releases", "github_tags", "huggingface_org", "your_type"]
```

### 4. 写测试 `tests/test_your_fetcher.py`

参考 `tests/test_rss.py` 用 `respx` mock HTTP。

---

## 🎨 修改飞书卡片样式

编辑 `core/notifier/feishu.py` 的 `_build_card` 方法。
飞书卡片 JSON 文档：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/feishu-cards/card-overview

常见调整：
- header `template`：`blue` / `red` / `green` / `orange` / `grey` / `purple`
- 加图片：`{"tag": "img", "img_key": "..."}`（需先调飞书图床 API 上传）
- 加 @人：在 markdown 里写 `<at id=user_open_id></at>`

---

## ✅ Pull Request 检查清单

- [ ] `pytest` 全部通过
- [ ] 新源在本地手动跑通（输出 ≥1 条带正确日期的新闻）
- [ ] `sources.yaml` 中新增的 `enabled: false` 项必须能 fetch 成功后再开启
- [ ] commit message 用约定式（`feat:`, `fix:`, `docs:` 等）
- [ ] 不要 commit `.env` / 任何含密钥的文件

## 🐛 报 issue 模板

请提供：
- 出问题的源 name
- 完整 traceback（从 `journalctl` 或 GitHub Actions 日志）
- 该源的 URL（让别人能复现）

## 💡 想接入但写不出 parser？

提个 issue 说明：
- 目标站点 URL
- 已知的更新频率
- 是否是 SPA（用上面 `grep -c "<script"` 判断）

我们可以一起讨论是否有替代信号源（HF / GitHub / RSSHub 等）。
