# AI Sidebar Rework

Hybrid **GNOME Shell Extension** + **Python Daemon** architecture for a multi-monitor AI sidebar.

## Why This Rework?

The original Python/PyQt6 sidebar uses XWayland + `_NET_WM_WINDOW_TYPE_DOCK` + raw X11 ctypes +
`wmctrl` + `XSetInputFocus` hacks to work around Wayland's security restrictions. These hacks:

- **Break on multi-monitor** across different workspaces
- **Fight Mutter** for focus, causing flickering
- **Leak X11 resources** via repeated ctypes calls
- **Fail silently** when xprop/wmctrl are missing

This rework splits the problem cleanly:

| Responsibility                       | Owner                 | Technology             |
|--------------------------------------|-----------------------|------------------------|
| Hot-zone detection / multi-monitor   | GNOME Shell Extension | GJS + Mutter API       |
| Window positioning on correct screen | GNOME Shell Extension | D-Bus → Python         |
| WebView, navigation, menus, resize   | Python Daemon         | PyQt6 + QWebEngineView |
| IPC between them                     | D-Bus                 | `com.smartai.Sidebar`  |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  GNOME Shell (Mutter compositor)                                │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  AI Sidebar Extension (alienware-smart-ai-position-define@hsx2coder.com)        │     │
│  │  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │     │
│  │  │ Cursor Track │─►│ D-Bus Proxy │─►│ Signal List. │  │     │
│  │  │ (per-monitor)│  │             │  │ (state sync) │  │     │
│  │  └──────────────┘  └──────┬──────┘  └──────────────┘  │     │
│  └───────────────────────────┼────────────────────────────┘     │
└──────────────────────────────┼──────────────────────────────────┘
                               │ D-Bus session bus
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Python Daemon (XWayland via QT_QPA_PLATFORM=xcb)               │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ D-Bus Service │  │ Sidebar Window  │  │ QWebEngineView   │  │
│  │ (GLib thread) │─►│ (positioning)   │─►│ (ChatGPT/Claude) │  │
│  └──────────────┘  └──────────────────┘  └──────────────────┘  │
│                    ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│                    │ Nav Bar  │  │ Resize   │  │ Menus    │   │
│                    └──────────┘  └──────────┘  └──────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### What Changed (vs. Original)

**Removed (no longer needed):**

- `import ctypes` for X11 `_NET_WM_WINDOW_TYPE_DOCK`
- `import subprocess` / `import shutil` for `wmctrl`
- `_set_as_dock_linux()` — X11 DOCK type
- `_grab_focus_linux()` — `XSetInputFocus` hack
- `_make_sticky_linux()` — `wmctrl` sticky
- `_focus_watchdog_check()` — polling focus timer
- Fake QKeyEvent simulation for Chromium focus
- `QT_QPA_PLATFORM=xcb` is **kept** (still need XWayland for positioning)

**Added:**

- D-Bus service (`com.smartai.Sidebar`) with:
    - `ShowOnScreen(int)`, `Hide()`, `Toggle()`, `Ping()`, `IsVisible()`
    - `StateChanged(bool)`, `WidthChanged(int)`, `PopupState(bool)`
- `show_on_screen(index)` method in Sidebar
- `stateChanged`, `widthChanged`, `popupStateChanged` PyQtSignals
- GNOME Shell extension (`alienware-smart-ai-position-define@hsx2coder.com`)
- D-Bus reconnection logic in extension (8s retry)

**Preserved (identical behavior):**

- All WebView logic (Chrome compat, auth redirects, download handling)
- Navigation bar with drag-to-reorder, add/edit/delete buttons
- Context menus (nav buttons + webview)
- Resize handle with 20%-80% ratio constraints
- Gesture detection (down-up swing to show from hidden pillar)
- Auto-hide stability watchdog (2s timeout)
- Fullscreen detection via `xprop`
- Popup windows for OAuth flows
- Tray icon with manual screen override
- `Ctrl+Shift+F` hotkey toggle

## File Structure

```
ai-sidebar-rework/
├── README.md
├── install.sh                        # Install to ~/.local
├── run.sh                            # Development runner
├── Pipfile                           # Python deps (PyQt6 + WebEngine)
├── .gitignore
│
├── gnome-extension/
│   └── alienware-smart-ai-position-define@hsx2coder.com/
│       ├── extension.js              # Hot-zone cursor tracking + D-Bus proxy
│       ├── metadata.json             # GNOME Shell 45/46/47
│       └── stylesheet.css
│
└── src/
    ├── main.py                       # Entry point + D-Bus service thread
    ├── sidebar.py                    # Sidebar QMainWindow (cleaned)
    ├── utils.py                      # AppPaths + helpers
    ├── components/
    │   ├── __init__.py
    │   ├── web_view.py               # QWebEngineView (full features)
    │   ├── title_bar.py              # Page title display
    │   ├── bottom_bar.py             # Status bar
    │   ├── resize_handle.py          # Left-edge resize
    │   ├── content_widget.py         # Layout composer
    │   ├── navigation_bar.py         # AI provider buttons
    │   └── menu_setting_dialog.py    # Add/edit nav items
    ├── config/
    │   └── nav_config.json           # Default nav buttons
    └── images/
        ├── tray.svg                  # System tray icon
        ├── claude.svg                # Claude AI
        ├── gemini.svg                # Gemini AI
        ├── ollama.svg                # Ollama local
        ├── chatgpt.svg               # ChatGPT
        ├── copilot.svg               # GitHub Copilot
        ├── hugging.svg               # Hugging Face
        └── mistral.svg               # Mistral AI
```

## Quick Start

### 1. Dependencies

```bash
# Nobara / Fedora
sudo dnf5 install -y python3-pip python3-gobject python3-dbus python3-qt6 python3-qt6-webengine

# Optional: development tools
sudo dnf5 install -y gnome-extensions-app
```

### 2. Install

```bash
cd ai-sidebar-rework
./install.sh
./install.sh --copy-icons   # if you have SVGs in the parent project
```

### 3. Enable GNOME Extension

```bash
# Restart GNOME Shell
# Alt+F2 → type 'r' → Enter

# Enable the extension
gnome-extensions enable alienware-smart-ai-position-define@hsx2coder.com

# Verify
gnome-extensions info alienware-smart-ai-position-define@hsx2coder.com
```

### 4. Run

```bash
ai-sidebar
```

Or for development:

```bash
./run.sh --extension   # one-time: install + enable extension
./run.sh               # start daemon
```

## D-Bus Protocol

Interface: `com.smartai.Sidebar` (session bus, path: `/com/smartai/Sidebar`)

```dbus
<interface name="com.smartai.Sidebar">
  <method name="ShowOnScreen">
    <arg type="i" name="screen_index" direction="in"/>
  </method>
  <method name="Hide"/>
  <method name="Toggle"/>
  <method name="Ping"/>
  <method name="IsVisible">
    <arg type="b" direction="out"/>
  </method>
  <signal name="StateChanged">
    <arg type="b" name="visible"/>
  </signal>
  <signal name="WidthChanged">
    <arg type="i" name="width"/>
  </signal>
  <signal name="PopupState">
    <arg type="b" name="open"/>
  </signal>
</interface>
```

Test from shell:

```bash
gdbus call --session \
  --dest com.smartai.Sidebar \
  --object-path /com/smartai/Sidebar \
  --method com.smartai.Sidebar.ShowOnScreen 0

gdbus call --session \
  --dest com.smartai.Sidebar \
  --object-path /com/smartai/Sidebar \
  --method com.smartai.Sidebar.Hide

gdbus call --session \
  --dest com.smartai.Sidebar \
  --object-path /com/smartai/Sidebar \
  --method com.smartai.Sidebar.IsVisible

gdbus monitor --session --dest com.smartai.Sidebar
```

## How the Extension Hot-Zone Works

1. GNOME Shell's `global.display.connect('cursor-moved', handler)` fires on every
   pointer movement.
2. The handler checks `global.get_pointer()` against every monitor's geometry.
3. When the cursor is ≤8px from the right edge of any monitor, it calls
   `dbusProxy.ShowOnScreenSync(monitorIndex)`.
4. When the cursor leaves the zone, a 600ms hide timer starts (cancellable on
   re-entry).
5. The extension retries D-Bus connection every 8 seconds if the daemon is
   not running yet.

## Fallback Mode (no Extension)

If the GNOME Shell extension is not installed or D-Bus fails:

- The tray icon's **Display Screen** submenu works as manual override
- Auto-detection selects the rightmost monitor (same as original code)
- The `Ctrl+Shift+F` hotkey still toggles visibility

## License

MIT
