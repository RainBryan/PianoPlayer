"""
PianoPlayer / app.py
─────────────────────────────────────────────────────────────────────────
Application entry point. Spawns a borderless pywebview window that hosts
the HTML/CSS/JS UI, and starts a global hotkey listener (F6 play /
F7 pause / F8 stop).

Run with:
    python app.py

Packaged with PyInstaller:
    pyinstaller build/PianoPlayer.spec
"""

from __future__ import annotations
import sys
import os
import threading
from pathlib import Path

# ── Make `core` importable whether we're running from source or a frozen exe ─
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# When frozen by PyInstaller, the UI files live inside _MEIPASS
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    BUNDLE_DIR = APP_DIR

UI_DIR = BUNDLE_DIR / 'ui'
ENTRY  = UI_DIR / 'index.html'

import webview

from bridge import api, state


# ─────────────────────────────────────────────────────────────────────────────
#  Global hotkeys  (F6 play / F7 pause / F8 stop)
# ─────────────────────────────────────────────────────────────────────────────
def start_hotkeys():
    """Listen for F6/F7/F8 even when Roblox has focus."""
    try:
        from pynput import keyboard as pkb
    except ImportError:
        print('[app] pynput unavailable — hotkeys disabled')
        return

    def on_press(key):
        try:
            if key == pkb.Key.f6:
                idx = state.selected
                if idx >= 0:
                    api.play(idx)
            elif key == pkb.Key.f7:
                api.toggle_pause()
            elif key == pkb.Key.f8:
                api.stop()
        except Exception as e:
            print(f'[hotkey] {e}')

    listener = pkb.Listener(on_press=on_press, daemon=True)
    listener.start()


# ─────────────────────────────────────────────────────────────────────────────
#  Window setup
# ─────────────────────────────────────────────────────────────────────────────
def main():
    start_hotkeys()

    # pywebview window.
    # easy_drag=False — we implement drag ourselves so only the titlebar
    # is draggable (easy_drag=True makes the whole window draggable,
    # which breaks click interactions).
    window = webview.create_window(
        title='Piano Player',
        url=str(ENTRY),
        js_api=api,
        width=1180,
        height=780,
        min_size=(960, 640),
        frameless=True,
        easy_drag=False,
        background_color='#0a0a0c',
        resizable=True,
        confirm_close=False,
        text_select=True,
    )
    state.window = window

    debug = os.environ.get('PIANOPLAYER_DEBUG') == '1'

    # Block until the window closes. Keep things simple: no http_server
    # (file:// works fine with our small UI footprint).
    webview.start(
        debug=debug,
        gui=None,
    )


if __name__ == '__main__':
    main()
