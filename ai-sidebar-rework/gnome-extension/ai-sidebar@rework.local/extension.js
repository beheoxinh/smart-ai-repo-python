'use strict';

/*
 * AI Sidebar Coordinator — GNOME Shell Extension
 *
 * WHAT IT DOES:
 *   Listens to global cursor position. When the mouse enters a configurable
 *   "hot zone" at the right edge of any monitor, it tells the Python daemon
 *   (com.smartai.Sidebar on the session D-Bus) to show the sidebar on that
 *   specific monitor.
 *
 * WHY THIS WORKS:
 *   Under Wayland, no application can position itself — the compositor
 *   (Mutter) owns all placement.  But a GNOME Shell extension runs
 *   *inside* the compositor and can call the D-Bus service of the
 *   Python app, telling it exactly which screen geometry to occupy.
 *
 * COMPATIBILITY:
 *   - GNOME Shell 45 / 46 / 47
 *   - Requires the python-daemon from the same project to be running
 *     (see src/main.py — registers com.smartai.Sidebar on session bus)
 *
 * PROTOCOL (JSON D-Bus):
 *   Methods called:
 *     ShowOnScreen(screen_index: int)  — show on a specific monitor
 *     Hide()                           — hide the sidebar
 *     Toggle()                         — toggle visibility
 *
 *   Signals listened:
 *     StateChanged(visible: bool)      — visibility state from daemon
 *     PopupState(open: bool)           — popup window state
 */

const { Clutter, GLib, Gio, Meta, Shell, St } = imports.gi;
const Main = imports.ui.main;
const ExtensionUtils = imports.misc.extensionUtils;


/* ──────────────── Config ──────────────── */
const TRIGGER_WIDTH_PX   = 8;   // how many pixels from the right edge are "hot"
const HIDE_DELAY_MS      = 600; // ms before auto-hiding after cursor leaves zone
const DBUS_NAME          = 'com.smartai.Sidebar';
const DBUS_OBJECT_PATH   = '/com/smartai/Sidebar';
const DBUS_IFACE         = 'com.smartai.Sidebar';
const RECONNECT_MS       = 8000; // retry D-Bus connection every 8 s if daemon is down


/* ──────────────── State ──────────────── */
let dbusProxy        = null;
let cursorHandlerId  = 0;
let monitorHandlerId = 0;
let hideTimeoutId    = 0;
let reconnectTimerId = 0;
let sidebarVisible   = false;
let insideHotZone    = false;
let isConnecting     = false;


/* ──────────────── Entry-points ──────────────── */

function init() {
    return new SidebarCoordinator();
}


/* ──────────────── The Extension Class ──────────────── */

function SidebarCoordinator() {
    this._init();
}

SidebarCoordinator.prototype = {

    _init() {},

    enable() {
        log('[AI-Sidebar] enable()');

        // 1. Track cursor movement
        cursorHandlerId = global.display.connect('cursor-moved',
            _onCursorMoved);

        // 2. React when monitors are plugged / unplugged
        monitorHandlerId = global.display.connect('monitors-changed',
            _onMonitorsChanged);

        // 3. Try to connect to the Python daemon via D-Bus
        _connectDBus();

        // 4. Periodically retry if daemon isn't running yet
        if (!dbusProxy) {
            reconnectTimerId = GLib.timeout_add(
                GLib.PRIORITY_DEFAULT, RECONNECT_MS, () => {
                    if (!dbusProxy) {
                        log('[AI-Sidebar] Retrying D-Bus connection...');
                        _connectDBus();
                    }
                    return GLib.SOURCE_CONTINUE; // keep re-trying
                });
        }

        log('[AI-Sidebar] Extension enabled');
    },

    disable() {
        log('[AI-Sidebar] disable()');

        // Disconnect cursor tracking
        if (cursorHandlerId) {
            global.display.disconnect(cursorHandlerId);
            cursorHandlerId = 0;
        }

        // Disconnect monitor events
        if (monitorHandlerId) {
            global.display.disconnect(monitorHandlerId);
            monitorHandlerId = 0;
        }

        // Cancel any pending hide timers
        if (hideTimeoutId) {
            GLib.source_remove(hideTimeoutId);
            hideTimeoutId = 0;
        }

        // Stop reconnection timer
        if (reconnectTimerId) {
            GLib.source_remove(reconnectTimerId);
            reconnectTimerId = 0;
        }

        dbusProxy = null;
        isConnecting = false;

        log('[AI-Sidebar] Extension disabled');
    }
};


/* ──────────────── Cursor Hot-Zone Logic ──────────────── */

function _onCursorMoved() {
    let [x, y] = global.get_pointer();
    let nMonitors = global.display.get_n_monitors();
    let foundMonitor = false;
    let activeMonitorIndex = -1;

    // Check every monitor — cursor may be on any of them
    for (let i = 0; i < nMonitors; i++) {
        let rect = global.display.get_monitor_geometry(i);
        let rightEdge = rect.x + rect.width;

        if (x >= rightEdge - TRIGGER_WIDTH_PX && x <= rightEdge + 1 &&
            y >= rect.y && y < rect.y + rect.height) {
            foundMonitor = true;
            activeMonitorIndex = i;
            break;
        }
    }

    // ── SHOW trigger ──
    if (foundMonitor && !sidebarVisible && dbusProxy) {
        log(`[AI-Sidebar] Hot-zone entered on monitor ${activeMonitorIndex}`);
        insideHotZone = true;

        try {
            dbusProxy.ShowOnScreenSync(activeMonitorIndex);
            sidebarVisible = true;
        } catch (e) {
            log(`[AI-Sidebar] ShowOnScreen failed: ${e.message}`);
        }
        return;
    }

    // ── HIDE trigger (with delay) ──
    if (!foundMonitor && sidebarVisible && !insideHotZone) {
        // We only start the hide timer once per exit
        return;
    }

    if (!foundMonitor && sidebarVisible && insideHotZone) {
        insideHotZone = false;
        _startHideTimer();
        return;
    }

    // If mouse came back into the hot zone while timer is pending, cancel it
    if (foundMonitor && hideTimeoutId) {
        GLib.source_remove(hideTimeoutId);
        hideTimeoutId = 0;
        log('[AI-Sidebar] Hide cancelled — mouse re-entered hot zone');
    }
}


function _startHideTimer() {
    if (hideTimeoutId) {
        GLib.source_remove(hideTimeoutId);
    }

    hideTimeoutId = GLib.timeout_add(
        GLib.PRIORITY_DEFAULT, HIDE_DELAY_MS, () => {
            hideTimeoutId = 0;
            if (sidebarVisible && dbusProxy) {
                log('[AI-Sidebar] Hiding after timeout');
                try {
                    dbusProxy.HideSync();
                    sidebarVisible = false;
                } catch (e) {
                    log(`[AI-Sidebar] Hide failed: ${e.message}`);
                }
            }
            return GLib.SOURCE_REMOVE;
        });
}


/* ──────────────── Monitor Change Handler ──────────────── */

function _onMonitorsChanged() {
    log('[AI-Sidebar] Monitor configuration changed');
    // The Python daemon will re-query QApplication.screens() on the next
    // ShowOnScreen call, so we don't need to do anything here.
}


/* ──────────────── D-Bus Connection ──────────────── */

function _connectDBus() {
    if (isConnecting) return;
    isConnecting = true;

    try {
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            null,              // GDBusInterfaceInfo
            DBUS_NAME,
            DBUS_OBJECT_PATH,
            DBUS_IFACE,
            null,              // GCancellable
            (proxy, res) => {
                isConnecting = false;
                try {
                    dbusProxy = Gio.DBusProxy.new_for_bus_finish(res);

                    // ── Subscribe to signals from daemon ──
                    dbusProxy.connect('g-signal', (proxy, sender, signal, params) => {
                        _onDaemonSignal(signal, params);
                    });

                    // Ping the daemon to confirm it's alive
                    try {
                        dbusProxy.PingSync();
                        log('[AI-Sidebar] D-Bus connected — daemon is alive');
                    } catch (e) {
                        log(`[AI-Sidebar] Daemon not reachable yet: ${e.message}`);
                        dbusProxy = null;
                    }
                } catch (e) {
                    log(`[AI-Sidebar] D-Bus connection error: ${e.message}`);
                    dbusProxy = null;
                }
            }
        );
    } catch (e) {
        log(`[AI-Sidebar] D-Bus init error: ${e.message}`);
        isConnecting = false;
    }
}


function _onDaemonSignal(signal, params) {
    log(`[AI-Sidebar] Signal received: ${signal}`);

    switch (signal) {
        case 'StateChanged':
            if (params && params.deep_unpack) {
                let [visible] = params.deep_unpack();
                sidebarVisible = visible;
                log(`[AI-Sidebar] State: visible=${visible}`);
            }
            break;

        case 'PopupState':
            if (params && params.deep_unpack) {
                let [open] = params.deep_unpack();
                log(`[AI-Sidebar] Popup: open=${open}`);
                // When popups are open, don't auto-hide via the extension
                if (open && hideTimeoutId) {
                    GLib.source_remove(hideTimeoutId);
                    hideTimeoutId = 0;
                }
            }
            break;

        case 'WidthChanged':
            // The daemon reports resize — we could use this to sync
            // positioning if needed.
            if (params && params.deep_unpack) {
                let [w] = params.deep_unpack();
                log(`[AI-Sidebar] Width changed to ${w}`);
            }
            break;

        default:
            log(`[AI-Sidebar] Unhandled signal: ${signal}`);
    }
}
