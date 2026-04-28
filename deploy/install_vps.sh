#!/usr/bin/env bash
# VPS 一键部署脚本（Ubuntu/Debian/CentOS 通用）
# 使用：sudo bash deploy/install_vps.sh
set -euo pipefail

INSTALL_DIR="/opt/ai_news_bot"
ENV_FILE="/etc/ai_news_bot.env"
SERVICE_DIR="/etc/systemd/system"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_ROOT/ai_news_bot/." "$INSTALL_DIR/"

echo "==> Creating venv & installing deps"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR" -q

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating $ENV_FILE (please edit!)"
  cat > "$ENV_FILE" <<'EOF'
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_SECRET=
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
EOF
  chmod 600 "$ENV_FILE"
fi

echo "==> Installing systemd units"
cp "$PROJECT_ROOT/deploy/ai-news-bot.service" "$SERVICE_DIR/"
cp "$PROJECT_ROOT/deploy/ai-news-bot.timer"   "$SERVICE_DIR/"
systemctl daemon-reload

echo "==> Running seed (one-time, no push)"
cd "$INSTALL_DIR"
set -a; source "$ENV_FILE"; set +a
"$INSTALL_DIR/.venv/bin/python" main.py --seed || true

echo "==> Enabling timer"
systemctl enable --now ai-news-bot.timer

echo ""
echo "✅ Done!"
echo "  Edit secrets:   sudo vi $ENV_FILE"
echo "  Run now:        sudo systemctl start ai-news-bot.service"
echo "  View logs:      sudo journalctl -u ai-news-bot -f"
echo "  Timer status:   systemctl list-timers ai-news-bot.timer"
echo "  Stop:           sudo systemctl disable --now ai-news-bot.timer"
