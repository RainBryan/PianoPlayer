"""
PianoPlayer / core / storage.py
─────────────────────────────────────────────────────────────────────────
Persistent storage for songs, settings, and imported MIDI files.

Layout (~/PianoPlayer/):
    songs.json       — list of song records
    settings.json    — app-wide settings (countdown, theme, hotkeys)
    midi/            — imported MIDI files (one per native-MIDI song)
"""

from __future__ import annotations
import json, shutil, re, uuid
from pathlib import Path


# ── Data root  (Windows: %USERPROFILE%\PianoPlayer ;  macOS/Linux: ~/PianoPlayer) ──
DATA_DIR     = Path.home() / 'PianoPlayer'
SONGS_FILE   = DATA_DIR / 'songs.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'
MIDI_DIR     = DATA_DIR / 'midi'


# ── Defaults ──────────────────────────────────────────────────────────────
SHEET_DEFAULTS = {
    'bpm': 200,
    'sustain': 1.0,
    'gap': 1.0,
    'swing': 0.0,
    'human': 0.0,
    'notation': False,
}

APP_DEFAULTS = {
    'countdown': 3,             # seconds before playback starts
    'play_hotkey':  'F6',
    'pause_hotkey': 'F7',
    'stop_hotkey':  'F8',
    'theme':  'system',         # 'system' | 'dark' | 'light'
    'preset': 'default',        # 'default' | 'emerald' | 'ocean' | …
    'accent': None,             # custom hex like '#ff5a67' or null
    'autoplay_gap': 2,          # seconds between songs in autoplay
}


# ── Songs ─────────────────────────────────────────────────────────────────
def load_songs():
    if not SONGS_FILE.exists():
        return []
    try:
        with open(SONGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f'[storage] failed to load songs: {e}')
    return []


def save_songs(songs):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SONGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(songs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f'[storage] failed to save songs: {e}')


# ── Settings ──────────────────────────────────────────────────────────────
def load_settings():
    if not SETTINGS_FILE.exists():
        return dict(APP_DEFAULTS)
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        merged = dict(APP_DEFAULTS)
        if isinstance(data, dict):
            merged.update(data)
        return merged
    except Exception as e:
        print(f'[storage] failed to load settings: {e}')
        return dict(APP_DEFAULTS)


def save_settings(settings):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f'[storage] failed to save settings: {e}')


# ── MIDI file management ──────────────────────────────────────────────────
def store_midi_file(src_path):
    """Copy a MIDI file into MIDI_DIR with a safe unique filename.
    Returns the bare filename (no path) for the song record."""
    MIDI_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(src_path)
    safe_stem = re.sub(r'[^A-Za-z0-9_\-]+', '_', src.stem)[:60] or 'midi'
    dest_name = f'{safe_stem}_{uuid.uuid4().hex[:8]}{src.suffix.lower()}'
    dest = MIDI_DIR / dest_name
    try:
        shutil.copy2(src, dest)
    except Exception as e:
        raise RuntimeError(f'Could not copy MIDI file:\n{e}')
    return dest_name


def delete_midi_file(filename):
    """Remove a previously-imported .mid file (no error if missing)."""
    if not filename:
        return
    try:
        (MIDI_DIR / filename).unlink(missing_ok=True)
    except Exception as e:
        print(f'[storage] could not remove {filename}: {e}')


def midi_path(filename):
    """Return the full Path for an imported MIDI filename."""
    return MIDI_DIR / filename if filename else None
