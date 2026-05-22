#!/usr/bin/env bash
set -euo pipefail

# Development runner for AI Sidebar rework (hybrid mode).
#
# Usage:
#   ./run.sh                  — start the Python daemon (standalone)
#   ./run.sh --extension      — also symlink + enable the GNOME extension
#   ./run.sh --help           — this message
#
# Environment:
#   QT_QPA_PLATFORM=xcb      — forced for XWayland positioning
#   CI=true, PAGER=cat       — non-interactive safety
#

cd "$(dirname "$0")"
export QT_QPA_PLATFORM="xcb"
export CI="true"
export PAGER="cat"
export GIT_PAGER="cat"
export PIP_NO_INPUT="1"
export GIT_TERMINAL_PROMPT="0"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXT_SRC="$SCRIPT_DIR/gnome-extension/alienware-smart-ai-position-define@hsx2coder.com"
EXT_DST="$HOME/.local/share/gnome-shell/extensions/alienware-smart-ai-position-define@hsx2coder.com"
EXT_UUID="alienware-smart-ai-position-define@hsx2coder.com"

HELP="Usage: $0 [--extension] [--help]

Options:
  --extension   Symlink the GNOME Shell extension and show enable instructions
  --help        Show this message

Examples:
  $0                          # run Python daemon only
  $0 --extension              # run daemon with GNOME extension enabled
"

if [[ "${1:-}" == "--help" ]]; then
    echo "$HELP"
    exit 0
fi

if [[ "${1:-}" == "--extension" ]]; then
    echo "[Setup] Installing GNOME Shell extension..."
    mkdir -p "$(dirname "$EXT_DST")"
    if [[ -L "$EXT_DST" ]] || [[ -d "$EXT_DST" ]]; then
        echo "[Setup] Extension already exists at $EXT_DST"
    else
        ln -sf "$EXT_SRC" "$EXT_DST"
        echo "[Setup] Symlinked $EXT_SRC -> $EXT_DST"
    fi

    if command -v gnome-extensions &>/dev/null; then
        echo "[Setup] Enabling extension via gnome-extensions..."
        gnome-extensions enable "$EXT_UUID" 2>/dev/null || true
        echo "[Setup] Done. Restart GNOME Shell (Alt+F2 → r) if needed."
    else
        echo "[Setup] gnome-extensions not found. Enable via GNOME Extensions app."
    fi
fi

echo "[Daemon] Starting AI Sidebar Python daemon..."
echo "[Daemon] D-Bus service: com.smartai.Sidebar"
echo "[Daemon] Press Ctrl+C to stop."
echo ""

cd "$SCRIPT_DIR/src"
python3 main.py "$@"
