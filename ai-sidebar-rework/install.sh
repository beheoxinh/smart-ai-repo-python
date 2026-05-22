#!/usr/bin/env bash
set -euo pipefail

# AI Sidebar Rework - Install Script
#
# This script installs both the Python daemon and the GNOME Shell extension.
#
# Usage:
#   ./install.sh                    — system-wide install
#   ./install.sh --user             — user-local install (default)
#   ./install.sh --copy-icons      — copy SVG icons from the parent project
#   ./install.sh --help            — this message

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Targets ────────────────────────────────────────────────────────────
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ai-sidebar"
EXTENSION_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/alienware-smart-ai-position-define@hsx2coder.com"
BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${HOME}/.smartAI"
EXT_UUID="alienware-smart-ai-position-define@hsx2coder.com"

echo "=========================================="
echo " AI Sidebar Rework — Installer"
echo "=========================================="

# ── Disk guard ─────────────────────────────────────────────────────────
df -h / | awk 'NR==2{if($5+0>90) exit 1}' || {
    echo "ERROR: Disk usage >90% — aborting."
    exit 1
}

# ── Check dependencies ─────────────────────────────────────────────────
echo ""
echo "[Check] Dependencies..."
MISSING=""
command -v python3        >/dev/null 2>&1 || MISSING="$MISSING python3"
command -v pip3           >/dev/null 2>&1 || MISSING="$MISSING pip3"
python3 -c "import gi"    >/dev/null 2>&1 || MISSING="$MISSING python3-gi (PyGObject)"
python3 -c "import dbus"  >/dev/null 2>&1 || MISSING="$MISSING python3-dbus"

if [[ -n "$MISSING" ]]; then
    echo "Missing:$MISSING"
    echo ""
    echo "Install them with:"
    echo "  sudo dnf5 install -y python3-pip python3-gobject python3-dbus"
    echo ""
    read -r -p "Continue anyway? [y/N] " REPLY
    if [[ "$REPLY" != "y" && "$REPLY" != "Y" ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# ── Create directories ─────────────────────────────────────────────────
echo ""
echo "[Install] Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$EXTENSION_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/config"

# ── Copy Python source ─────────────────────────────────────────────────
echo "[Install] Copying Python daemon to $INSTALL_DIR..."
cp -r "$SCRIPT_DIR/src/"* "$INSTALL_DIR/"
chmod -R u+rX "$INSTALL_DIR"

# ── Install Python dependencies ────────────────────────────────────────
echo "[Install] Installing Python packages..."
pip3 install -q --no-input PyQt6 PyQt6-WebEngine requests 2>/dev/null || {
    echo "WARNING: PyQt6 install failed. Try:"
    echo "  sudo dnf5 install -y python3-qt6 python3-qt6-webengine"
}

# ── Install GNOME Extension ────────────────────────────────────────────
echo "[Install] Installing GNOME Shell extension..."
cp "$SCRIPT_DIR/gnome-extension/alienware-smart-ai-position-define@hsx2coder.com/extension.js"  "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/gnome-extension/alienware-smart-ai-position-define@hsx2coder.com/metadata.json" "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/gnome-extension/alienware-smart-ai-position-define@hsx2coder.com/stylesheet.css" "$EXTENSION_DIR/"

# ── Optional: copy icons from parent project ───────────────────────────
if [[ "${1:-}" == "--copy-icons" ]]; then
    if [[ -d "$PARENT_DIR/images" ]]; then
        echo "[Install] Copying icons from parent project..."
        cp "$PARENT_DIR/images/"*.svg "$INSTALL_DIR/images/" 2>/dev/null || true
    fi
fi

# ── Create wrapper script ──────────────────────────────────────────────
echo "[Install] Creating launcher at $BIN_DIR/ai-sidebar..."
cat > "$BIN_DIR/ai-sidebar" << 'WRAPPER'
#!/usr/bin/env bash
export QT_QPA_PLATFORM="xcb"
export CI="true"
exec python3 "$HOME/.local/share/ai-sidebar/main.py" "$@"
WRAPPER
chmod +x "$BIN_DIR/ai-sidebar"

# ── Done ───────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo " ✅  Installation complete!"
echo "=========================================="
echo ""
echo "  1. Restart GNOME Shell:"
echo "     Alt+F2 → type 'r' → Enter"
echo ""
echo "  2. Enable the extension:"
echo "     gnome-extensions enable $EXT_UUID"
echo ""
echo "  3. Start the daemon:"
echo "     ai-sidebar"
echo ""
echo "  4. (Optional) Autostart:"
echo "     cp $SCRIPT_DIR/SmartAI.desktop \\"
echo "        ~/.config/autostart/"
echo ""
echo "  Or run in-place for development:"
echo "     ./run.sh --extension && ./run.sh"
echo ""
