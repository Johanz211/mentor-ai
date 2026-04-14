#!/usr/bin/env bash
# ─────────────────────────────────────────────
# Mentor AI — Setup Script
# Sets up venv, aliases, cron, and directories
# ─────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
BASHRC="$HOME/.bashrc"
LOG_DIR="$PROJECT_DIR/logs"
HEALTH_SCRIPT="$PROJECT_DIR/healthcheck.sh"
PORT=8888

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
error() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo "  ┌─────────────────────────────────────┐"
echo "  │       🎓  Mentor AI Setup           │"
echo "  └─────────────────────────────────────┘"
echo ""

# ── 1. Python venv + dependencies ──
echo "  [1/5] Python environment"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    info "Created virtual environment"
else
    info "Virtual environment already exists"
fi
source "$VENV_DIR/bin/activate"
pip install -q -r "$PROJECT_DIR/requirements.txt"
info "Dependencies installed"

# ── 2. Create directories ──
echo "  [2/5] Project directories"
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/uploads" "$LOG_DIR"
touch "$PROJECT_DIR/data/.gitkeep" "$PROJECT_DIR/uploads/.gitkeep"
info "data/, uploads/, logs/ ready"

# ── 3. Shell aliases ──
echo "  [3/5] Shell aliases"
ALIAS_MENTOR="alias mentor=\"cd $PROJECT_DIR && source venv/bin/activate && python3 mentor.py\""
ALIAS_CLI="alias mentor-cli=\"cd $PROJECT_DIR && source venv/bin/activate && python3 mentor.py cli\""

add_alias() {
    local alias_line="$1"
    local alias_name
    alias_name=$(echo "$alias_line" | grep -oP 'alias \K[^=]+')

    # Remove any existing alias with same name
    if grep -q "^alias ${alias_name}=" "$BASHRC" 2>/dev/null; then
        sed -i "/^alias ${alias_name}=/d" "$BASHRC"
    fi

    echo "$alias_line" >> "$BASHRC"
    info "Added alias: $alias_name"
}

# Add marker comment if not present
if ! grep -q "# Mentor AI aliases" "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# Mentor AI aliases" >> "$BASHRC"
fi

add_alias "$ALIAS_MENTOR"
add_alias "$ALIAS_CLI"

# ── 4. Cron job (healthcheck every 3 min) ──
echo "  [4/5] Cron job"
chmod +x "$HEALTH_SCRIPT"
CRON_CMD="*/3 * * * * $HEALTH_SCRIPT >> $LOG_DIR/health.log 2>&1"

CURRENT_CRON=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT_CRON" | grep -qF "$HEALTH_SCRIPT"; then
    # Replace existing entry
    NEW_CRON=$(echo "$CURRENT_CRON" | grep -vF "$HEALTH_SCRIPT")
    echo "$NEW_CRON" | { cat; echo "$CRON_CMD"; } | crontab -
    info "Updated healthcheck cron (every 3 min)"
else
    echo "$CURRENT_CRON" | { cat; echo "$CRON_CMD"; } | crontab -
    info "Added healthcheck cron (every 3 min)"
fi

# ── 5. Verify Ollama ──
echo "  [5/5] Ollama check"
if curl -sf --max-time 3 "http://localhost:11434/api/tags" > /dev/null 2>&1; then
    info "Ollama is running"
    if curl -sf --max-time 3 "http://localhost:11434/api/tags" | grep -q "qwen2.5-coder"; then
        info "Model qwen2.5-coder found"
    else
        warn "Model qwen2.5-coder:7b not found — run: ollama pull qwen2.5-coder:7b"
    fi
else
    warn "Ollama not running — start it with: ollama serve"
fi

echo ""
echo "  ─────────────────────────────────────"
echo "  Setup complete! Usage:"
echo ""
echo "    mentor           # Web UI at http://localhost:$PORT"
echo "    mentor cli       # Terminal chat"
echo "    mentor-cli       # Terminal chat (shortcut)"
echo "    mentor-cli -m qa # Jump to QA mentor"
echo ""
echo "  Run 'source ~/.bashrc' or open a new terminal"
echo "  to activate the aliases."
echo "  ─────────────────────────────────────"
echo ""
