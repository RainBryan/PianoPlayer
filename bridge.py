"""
PianoPlayer / bridge.py
─────────────────────────────────────────────────────────────────────────
The JS ↔ Python API surface.

Architecture:
    `state`  — a module-level singleton holding songs, settings, engines.
    `Api`    — a thin class with ONLY methods (no fancy attributes).
                pywebview binds methods of this class as `window.pywebview.api.*`

Crucially, all `_emit` calls (which push UI events from playback threads
back to JS) go through a background dispatcher queue so they NEVER block
the audio engine.  pywebview's `evaluate_js` is synchronous and waits
for the WebView to execute — calling it from inside the playback loop
made every note wait 5-50ms on Windows, which is what made MIDI files
sound "slow and wrong."
"""

from __future__ import annotations
import sys
import threading
import queue
from pathlib import Path

from core import (
    parse_sheet, sheet_stats, estimate_duration, format_time,
    midi_load, midi_native_schedule, midi_suggest_transpose,
    SheetEngine, MidiEngine,
    load_songs, save_songs, load_settings, save_settings,
    store_midi_file, delete_midi_file, midi_path,
    DATA_DIR, MIDI_DIR,
    SHEET_DEFAULTS, APP_DEFAULTS,
    KEY_AVAILABLE,
)


# ─────────────────────────────────────────────────────────────────────────────
#  STATE  (module-level singleton)
# ─────────────────────────────────────────────────────────────────────────────
class _State:
    def __init__(self):
        self.window      = None
        self.songs       = load_songs()
        self.settings    = load_settings()
        self.selected    = -1
        self.sheet_eng   = SheetEngine()
        self.midi_eng    = MidiEngine()
        self._lock       = threading.Lock()
        self._cancel_play = False
        # ── Autoplay queue ─────────────────────────────────────────────
        self.queue        = []       # list of song indices (ints)
        self.autoplay     = False    # if True, advance on finished
        self.autoplay_gap = 2        # seconds between songs in autoplay
        # ── Dispatcher: keeps evaluate_js calls off the audio thread ──
        # The playback engines push events here; a worker thread sends
        # them to JS at its own pace. Coalesces backlog automatically:
        # high-frequency events (sheet_event, midi_event) get dropped
        # if the queue is full, but playback_state and countdown never
        # get dropped.
        self._js_queue = queue.Queue(maxsize=256)
        self._js_thread = threading.Thread(
            target=self._js_dispatcher_loop, daemon=True)
        self._js_thread.start()
        # wire engine callbacks
        self.sheet_eng.cb = self._sheet_callbacks()
        self.midi_eng.cb  = self._midi_callbacks()

    def _sheet_callbacks(self):
        return {
            'started':  lambda: self._emit('playback_state', state='started',
                                            kind='sheet'),
            'finished': lambda: self._on_song_finished('sheet'),
            'paused':   lambda: self._emit('playback_state', state='paused'),
            'resumed':  lambda: self._emit('playback_state', state='resumed'),
            'event':    self._on_sheet_event,
        }

    def _midi_callbacks(self):
        return {
            'started':  lambda: self._emit('playback_state', state='started',
                                            kind='midi'),
            'finished': lambda: self._on_song_finished('midi'),
            'paused':   lambda: self._emit('playback_state', state='paused'),
            'resumed':  lambda: self._emit('playback_state', state='resumed'),
            'event':    self._on_midi_event,
        }

    def _on_song_finished(self, kind):
        """Engine finished. Fire the UI event, then maybe advance the queue."""
        self._emit('playback_state', state='finished', kind=kind)
        if self.autoplay and self.queue:
            # find the song that just played; advance to the next one
            try:
                cur_pos = self.queue.index(self.selected)
                next_pos = cur_pos + 1
            except ValueError:
                next_pos = 0
            if next_pos < len(self.queue):
                next_idx = self.queue[next_pos]
                # Schedule the next song on a background thread so we don't
                # block the dispatcher
                threading.Thread(
                    target=self._autoplay_next, args=(next_idx,),
                    daemon=True).start()
            else:
                # End of queue
                self.autoplay = False
                self._emit('queue_finished')

    def _autoplay_next(self, next_idx):
        import time
        # Brief gap between songs
        time.sleep(max(0, self.autoplay_gap))
        if not self.autoplay:           # user stopped autoplay during gap
            return
        # Build whichever engine this song needs and start it.
        # We call _play_index directly to skip the countdown, so the gap
        # is exactly what the user asked for.
        self._emit('autoplay_advancing', index=next_idx)
        self._play_index(next_idx, skip_countdown=True)

    def _play_index(self, index, skip_countdown=False):
        """Internal: start playback of song at `index`. Used by both the
        public play() method and the autoplay advance logic."""
        if not (0 <= index < len(self.songs)):
            return False
        song = self.songs[index]
        kind = song.get('kind', 'sheet')
        self.selected = index
        if kind == 'midi':
            sched = self.build_midi_schedule(song)
            if not sched:
                return False
            self._cancel_play = False
            def go():
                if not skip_countdown:
                    self.do_countdown()
                if not self._cancel_play:
                    self.midi_eng.play(sched)
            threading.Thread(target=go, daemon=True).start()
        else:
            events = parse_sheet(song.get('sheet', ''),
                                  song.get('notation', False))
            cfg = {k: song.get(k, SHEET_DEFAULTS[k])
                   for k in ('sustain', 'gap', 'swing', 'human')}
            bpm = int(song.get('bpm', 200))
            self._cancel_play = False
            def go():
                if not skip_countdown:
                    self.do_countdown()
                if not self._cancel_play:
                    self.sheet_eng.play(events, bpm=bpm, cfg=cfg)
            threading.Thread(target=go, daemon=True).start()
        return True

    def _on_sheet_event(self, i, ev, note_idx, notes_total, bar_num, bpm):
        self._emit('sheet_event',
                   i=i, kind=ev.get('type'), keys=ev.get('keys', []),
                   note_idx=note_idx, notes_total=notes_total,
                   bar=bar_num, bpm=bpm)

    def _on_midi_event(self, i, ev, cluster_idx, total, start_t):
        self._emit('midi_event',
                   i=i, keys=ev.get('keys', []),
                   time=ev.get('time', 0),
                   duration=ev.get('duration', 0),
                   cluster_idx=cluster_idx, total=total)

    def _emit(self, event, **kwargs):
        """Non-blocking emit. Pushes the event to the dispatcher queue;
        a background thread sends it to JS at its own pace.
        Critical for audio timing — calling evaluate_js from the playback
        thread blocks for 5-50ms per call on Windows. This way, audio
        timing is never affected by WebView responsiveness."""
        if self.window is None:
            return
        # Drop-friendly events: high-frequency, latest-wins. If the queue
        # is full, just drop them — UI catches up on the next one.
        DROP_OK = {'sheet_event', 'midi_event'}
        item = (event, kwargs)
        try:
            if event in DROP_OK:
                # If queue is full, drop. Audio comes first.
                try:
                    self._js_queue.put_nowait(item)
                except queue.Full:
                    return
            else:
                # Important events (countdown, started/finished/paused):
                # block briefly but never hold up audio for more than 50ms.
                self._js_queue.put(item, timeout=0.05)
        except queue.Full:
            pass

    def _js_dispatcher_loop(self):
        """Background worker: pops events and forwards them to JS via
        evaluate_js. The audio engine never waits for this."""
        import json
        while True:
            try:
                item = self._js_queue.get()
            except Exception:
                continue
            if item is None:        # sentinel for shutdown
                break
            if self.window is None:
                continue
            event, kwargs = item
            try:
                payload = json.dumps(kwargs)
            except Exception:
                payload = '{}'
            try:
                self.window.evaluate_js(
                    f'window.dispatchEvent(new CustomEvent('
                    f'"piano:{event}", {{detail: {payload}}}));')
            except Exception as e:
                # don't spam — just print once in a while
                print(f'[bridge] dispatcher: {e}')

    def song_summary(self, idx, song):
        return {
            'index': idx,
            'name':  song.get('name', '(untitled)'),
            'kind':  song.get('kind', 'sheet'),
            'bpm':   song.get('bpm', 200),
            'favorite': bool(song.get('favorite', False)),
        }

    def song_full(self, idx):
        song = dict(self.songs[idx])
        song['_index'] = idx
        if song.get('kind') == 'midi':
            sched = self.build_midi_schedule(self.songs[idx])
            song['_cluster_count'] = len(sched)
            song['_duration_seconds'] = (
                sched[-1]['time'] + sched[-1]['duration']
                if sched else 0)
            song['_midi_roll'] = self.roll_payload(sched)
        else:
            events = parse_sheet(song.get('sheet', ''),
                                  song.get('notation', False))
            notes, chords, _, _, _ = sheet_stats(events)
            song['_notes_count'] = len(notes)
            song['_chord_count'] = chords
            song['_duration_seconds'] = estimate_duration(
                events, song.get('bpm', 200))
        return song

    def build_midi_schedule(self, song):
        fname = song.get('midi_file')
        if not fname:
            return song.get('midi_schedule', [])
        path = midi_path(fname)
        if not path or not path.exists():
            return []
        try:
            data = midi_load(path, native=True)
            return midi_native_schedule(
                data,
                transpose=int(song.get('midi_transpose', 0)),
                max_poly=0)
        except Exception as e:
            print(f'[bridge] schedule build failed: {e}')
            return []

    def roll_payload(self, schedule):
        if not schedule:
            return {'notes': [], 'duration': 0, 'keys': []}
        seen = set()
        keys_in_order = []
        for ev in schedule:
            for k in ev['keys']:
                if k not in seen:
                    seen.add(k); keys_in_order.append(k)
        from core.midi import ROBLOX_PIANO_KEYS, MIDI_LOW
        idx = {k: i for i, k in enumerate(ROBLOX_PIANO_KEYS)}
        keys_in_order.sort(key=lambda k: idx.get(k, 999))
        # Build rich key info: pitch label (C4, F#5...) + black/white flag
        NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F',
                       'F#', 'G', 'G#', 'A', 'A#', 'B']
        BLACK_FLAGS = [False, True, False, True, False, False,
                        True, False, True, False, True, False]
        rich_keys = []
        for k in keys_in_order:
            i = idx.get(k)
            if i is None:
                rich_keys.append({'k': k, 'label': k.upper(),
                                   'black': False, 'midi': 0})
                continue
            midi = MIDI_LOW + i
            note_in_oct = midi % 12
            octave = midi // 12 - 1
            rich_keys.append({
                'k': k,
                'label': NOTE_NAMES[note_in_oct] + str(octave),
                'black': BLACK_FLAGS[note_in_oct],
                'midi': midi,
            })
        # Flat note list
        notes = []
        for ev in schedule:
            for k in ev['keys']:
                notes.append({'k': k, 't': round(ev['time'], 4),
                              'd': round(max(0.05, ev['duration']), 4)})
        last = schedule[-1]
        return {
            'notes': notes,
            'duration': round(last['time'] + max(0.1, last['duration']) + 0.5,
                              4),
            'keys': keys_in_order,        # kept for back-compat
            'rich_keys': rich_keys,       # new: full pitch info
        }

    def do_countdown(self):
        import time
        secs = int(self.settings.get('countdown', 3))
        for n in range(secs, 0, -1):
            if self._cancel_play:
                return
            self._emit('countdown', value=n)
            time.sleep(1)
        self._emit('countdown', value=0)


state = _State()


def _open_in_explorer(path):
    import os, subprocess
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == 'win32':
            os.startfile(str(p))
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(p)])
        else:
            subprocess.run(['xdg-open', str(p)])
        return True
    except Exception as e:
        print(f'[bridge] could not open folder: {e}')
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Version-check helpers
# ─────────────────────────────────────────────────────────────────────────────
# To switch update sources, edit these constants:
GITHUB_REPO   = 'RainBryan/PianoPlayer'
WEBSITE_VERSION_URL = 'https://rainbryan.com/pianoplayer/version.json'
UPDATE_TIMEOUT_SEC  = 4

def _parse_version(v):
    """Parse 'v1.2.3' or '1.2.3' into a (1, 2, 3) tuple. Anything we can't
    parse becomes (0,0,0) so comparisons fail safely."""
    if not v:
        return (0, 0, 0)
    s = str(v).strip().lstrip('vV')
    parts = []
    for x in s.split('.'):
        try:
            # accept '0', '0a', '1-rc' etc — strip trailing non-digits
            num = ''
            for ch in x:
                if ch.isdigit(): num += ch
                else: break
            parts.append(int(num) if num else 0)
        except Exception:
            parts.append(0)
    while len(parts) < 3: parts.append(0)
    return tuple(parts[:3])

def _version_at_least(current, latest):
    """True if current >= latest (i.e. user IS up to date)."""
    return _parse_version(current) >= _parse_version(latest)

def _fetch_github_release():
    """Hit api.github.com for the latest release. Returns dict or None."""
    import json, urllib.request, urllib.error
    url = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
    try:
        req = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'PianoPlayer-UpdateCheck/1.0',
        })
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT_SEC) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode('utf-8'))
        tag = data.get('tag_name') or data.get('name', '')
        if not tag:
            return None
        # Find a .exe asset (Windows installer) if present
        download_url = None
        for asset in data.get('assets', []) or []:
            name = (asset.get('name') or '').lower()
            if name.endswith('.exe'):
                download_url = asset.get('browser_download_url')
                break
        return {
            'version': tag.lstrip('vV'),
            'html_url': data.get('html_url'),
            'download_url': download_url,
        }
    except urllib.error.HTTPError as e:
        # 404 = no releases yet; not an error worth alarming about
        if e.code != 404:
            print(f'[update] github HTTP {e.code}')
        return None
    except Exception as e:
        print(f'[update] github failed: {e}')
        return None

def _fetch_website_version():
    """Fallback: pull version.json from rainbryan.com. Returns dict or None.

    Expected JSON format (you publish this file yourself):
        {
          "version": "1.0.1",
          "download_url": "https://rainbryan.com/downloads/PianoPlayer.exe",
          "release_url":  "https://rainbryan.com/pianoplayer"
        }
    """
    import json, urllib.request
    try:
        req = urllib.request.Request(WEBSITE_VERSION_URL, headers={
            'User-Agent': 'PianoPlayer-UpdateCheck/1.0',
        })
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT_SEC) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode('utf-8'))
        if not data.get('version'):
            return None
        return {
            'version':      str(data['version']).lstrip('vV'),
            'download_url': data.get('download_url'),
            'release_url':  data.get('release_url'),
        }
    except Exception as e:
        print(f'[update] website failed: {e}')
        return None



# ─────────────────────────────────────────────────────────────────────────────
#  API  (the class pywebview binds — ONLY methods)
# ─────────────────────────────────────────────────────────────────────────────
class Api:
    """JS-callable methods — kept lean for reliable pywebview binding."""

    def ping(self):
        """JS calls this first to confirm the bridge attached."""
        return 'pong'

    def app_info(self):
        return {
            'name':    'Piano Player',
            'version': '1.0.0',
            'author':  'RainBryan',
            'roblox':  '@RainBryan192',
            'data_dir': str(DATA_DIR),
            'midi_dir': str(MIDI_DIR),
            'platform': sys.platform,
            'key_available': KEY_AVAILABLE,
        }

    # ── window controls ──
    def minimize(self):
        if state.window:
            try: state.window.minimize(); return True
            except Exception as e: print(f'[bridge] minimize: {e}')
        return False

    def close_window(self):
        if state.window:
            try: state.window.destroy(); return True
            except Exception as e: print(f'[bridge] close: {e}')
        return False

    def get_window_rect(self):
        """Return {x,y,w,h} for the current window. JS uses this as the
        baseline before a drag/resize gesture."""
        if not state.window:
            return None
        try:
            return {
                'x': int(state.window.x),
                'y': int(state.window.y),
                'w': int(state.window.width),
                'h': int(state.window.height),
            }
        except Exception as e:
            print(f'[bridge] get_window_rect: {e}')
            return None

    def move_window(self, x, y):
        """Move the window to absolute screen coords (x, y)."""
        if state.window:
            try:
                state.window.move(int(x), int(y))
                return True
            except Exception as e:
                print(f'[bridge] move_window: {e}')
        return False

    def resize_window(self, w, h):
        """Resize the window to (w, h) pixels."""
        if state.window:
            try:
                # respect min-size
                w = max(960, int(w))
                h = max(640, int(h))
                state.window.resize(w, h)
                return True
            except Exception as e:
                print(f'[bridge] resize_window: {e}')
        return False

    def move_resize(self, x, y, w, h):
        """Combined: move + resize in one round-trip.
        Used for top/left edges where resizing also moves the window."""
        if state.window:
            try:
                w = max(960, int(w))
                h = max(640, int(h))
                state.window.resize(w, h)
                state.window.move(int(x), int(y))
                return True
            except Exception as e:
                print(f'[bridge] move_resize: {e}')
        return False

    # ── songs ──
    def list_songs(self):
        return [state.song_summary(i, s)
                for i, s in enumerate(state.songs)]

    def get_song(self, index):
        if 0 <= index < len(state.songs):
            return state.song_full(index)
        return None

    def select_song(self, index):
        if 0 <= index < len(state.songs):
            state.selected = index
            return state.song_full(index)
        state.selected = -1
        return None

    def save_song(self, record):
        with state._lock:
            idx = record.get('_index', -1)
            existing = (state.songs[idx]
                         if 0 <= idx < len(state.songs) else None)
            if existing and existing.get('kind') == 'midi':
                existing['name'] = record.get('name', existing.get('name'))
                existing['bpm']  = int(record.get('bpm',
                                                   existing.get('bpm', 120)))
                if 'midi_transpose' in record:
                    existing['midi_transpose'] = int(record['midi_transpose'])
            elif existing:
                for k in ('name', 'bpm', 'sheet', 'notation',
                          'sustain', 'gap', 'swing', 'human'):
                    if k in record:
                        existing[k] = record[k]
            else:
                new = {k: record.get(k, SHEET_DEFAULTS.get(k))
                       for k in ('name', 'bpm', 'sheet', 'notation',
                                  'sustain', 'gap', 'swing', 'human')}
                new['name']  = record.get('name') or 'Untitled'
                new['kind']  = 'sheet'
                state.songs.append(new)
                state.selected = len(state.songs) - 1
            save_songs(state.songs)
            return self.list_songs()

    def new_song(self):
        return {
            'name': 'New Song',
            'kind': 'sheet',
            'bpm':  200,
            'sheet': '',
            'notation': False,
            'sustain': 1.0, 'gap': 1.0, 'swing': 0.0, 'human': 0.0,
            '_index': -1,
        }

    def delete_song(self, index):
        with state._lock:
            if not (0 <= index < len(state.songs)):
                return self.list_songs()
            song = state.songs[index]
            if song.get('kind') == 'midi':
                delete_midi_file(song.get('midi_file'))
            state.songs.pop(index)
            if state.selected == index:
                state.selected = -1
            elif state.selected > index:
                state.selected -= 1
            save_songs(state.songs)
            return self.list_songs()

    # ── favorites ─────────────────────────────────────────────────────
    def toggle_favorite(self, index):
        """Toggle the favorite flag on a song. Returns the new value."""
        with state._lock:
            if not (0 <= index < len(state.songs)):
                return False
            song = state.songs[index]
            song['favorite'] = not bool(song.get('favorite', False))
            save_songs(state.songs)
            return bool(song['favorite'])

    # ── queue / autoplay ──────────────────────────────────────────────
    def get_queue(self):
        return list(state.queue)

    def queue_add(self, index):
        """Append a song to the autoplay queue."""
        if 0 <= index < len(state.songs) and index not in state.queue:
            state.queue.append(index)
        return list(state.queue)

    def queue_remove(self, index):
        """Remove a specific song index from the queue."""
        if index in state.queue:
            state.queue.remove(index)
        return list(state.queue)

    def queue_clear(self):
        state.queue.clear()
        return []

    def queue_move(self, from_pos, to_pos):
        """Reorder: move queue[from_pos] to queue[to_pos]."""
        if not (0 <= from_pos < len(state.queue)):
            return list(state.queue)
        item = state.queue.pop(from_pos)
        to_pos = max(0, min(len(state.queue), to_pos))
        state.queue.insert(to_pos, item)
        return list(state.queue)

    def queue_play(self, gap_seconds=2):
        """Start playing the queue. Sets autoplay mode so when each song
        finishes, the next one starts after a small gap."""
        if not state.queue:
            return {'error': 'queue is empty'}
        state.autoplay = True
        state.autoplay_gap = max(0, int(gap_seconds))
        # Play the first song in the queue; the 'finished' callback will
        # advance to the next one (handled in _State)
        idx = state.queue[0]
        return self.play(idx)

    def queue_stop_autoplay(self):
        """Stop auto-advance. The current song keeps playing."""
        state.autoplay = False
        return True

    # ── sheet preview ──
    def preview_sheet(self, sheet_text, notation=False, bpm=200):
        events = parse_sheet(sheet_text or '', bool(notation))
        notes, chords, rests, tempos, bars = sheet_stats(events)
        dur = estimate_duration(events, int(bpm))
        return {
            'notes':  len(notes),
            'chords': chords,
            'rests':  rests,
            'bars':   bars,
            'tempos': tempos,
            'duration_seconds': dur,
            'duration_text':    format_time(dur),
        }

    # ── MIDI import ──
    def open_midi_dialog(self):
        if state.window is None:
            return ''
        try:
            import webview
            res = state.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=('MIDI files (*.mid;*.midi)', 'All files (*.*)'))
            if not res:
                return ''
            return res[0] if isinstance(res, (list, tuple)) else res
        except Exception as e:
            print(f'[bridge] file dialog: {e}')
            return ''

    def midi_preview(self, path):
        try:
            data = midi_load(path, native=True)
        except Exception as e:
            return {'error': str(e)}
        suggested = midi_suggest_transpose(data['on_events'])
        sched = midi_native_schedule(data, transpose=suggested, max_poly=0)
        return {
            'note_count': len(data['on_events']),
            'cluster_count': len(sched),
            'default_bpm':  data['default_bpm'],
            'suggested_transpose': suggested,
            'duration_seconds': (sched[-1]['time'] + sched[-1]['duration']
                                  if sched else 0),
            'filename': Path(path).name,
        }

    def midi_import_native(self, path, name, transpose):
        if not path:
            return {'error': 'no file selected'}
        try:
            data = midi_load(path, native=True)
        except Exception as e:
            return {'error': str(e)}
        schedule = midi_native_schedule(data,
                                          transpose=int(transpose),
                                          max_poly=0)
        if not schedule:
            return {'error': 'No notes mapped to the Roblox piano range. '
                              'Try adjusting Transpose.'}
        try:
            filename = store_midi_file(path)
        except Exception as e:
            return {'error': str(e)}
        record = {
            'name': name or Path(path).stem,
            'kind': 'midi',
            'bpm':  data['default_bpm'],
            'midi_file':      filename,
            'midi_transpose': int(transpose),
        }
        state.songs.append(record)
        save_songs(state.songs)
        return {'ok': True, 'index': len(state.songs) - 1,
                'songs': self.list_songs()}

    # ── playback ──
    def play(self, index):
        if not (0 <= index < len(state.songs)):
            return {'error': 'no such song'}
        # If the user manually picks a song that's NOT in the queue,
        # disable autoplay. (If it IS in the queue, keep autoplay running.)
        if index not in state.queue:
            state.autoplay = False
        if state._play_index(index, skip_countdown=False):
            return {'ok': True, 'index': index}
        return {'error': 'failed to start playback'}

    def stop(self):
        state._cancel_play = True
        state.autoplay = False    # explicit user stop kills autoplay
        state.sheet_eng.stop()
        state.midi_eng.stop()
        state._emit('playback_state', state='stopped')
        return {'ok': True}

    def toggle_pause(self):
        paused = False
        if state.sheet_eng.is_playing:
            paused = state.sheet_eng.toggle_pause()
        elif state.midi_eng.is_playing:
            paused = state.midi_eng.toggle_pause()
        return {'paused': paused}

    def playback_state(self):
        return {
            'sheet_playing': state.sheet_eng.is_playing,
            'midi_playing':  state.midi_eng.is_playing,
            'paused': state.sheet_eng.is_paused or state.midi_eng.is_paused,
        }

    # ── settings ──
    def get_settings(self):
        return dict(state.settings)

    def update_setting(self, key, value):
        state.settings[key] = value
        save_settings(state.settings)
        return dict(state.settings)

    def open_data_folder(self):
        return _open_in_explorer(DATA_DIR)

    def open_midi_folder(self):
        return _open_in_explorer(MIDI_DIR)

    def open_url(self, url):
        """Open a URL in the user's default external browser. Only allows
        a small list of trusted hosts to prevent JS-side URL injection."""
        ALLOWED_HOSTS = {
            'rainbryan.com',
            'www.rainbryan.com',
            'roblox.com',
            'www.roblox.com',
            'github.com',
            'www.github.com',
        }
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                print(f'[bridge] refused non-http URL: {url}')
                return False
            host = (parsed.hostname or '').lower()
            if host not in ALLOWED_HOSTS:
                print(f'[bridge] refused untrusted host: {host}')
                return False
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception as e:
            print(f'[bridge] open_url failed: {e}')
            return False

    def check_for_updates(self):
        """Check if a newer release is available.

        Strategy:
            1. Hit GitHub Releases API (the source of truth for new builds).
            2. Fall back to rainbryan.com/pianoplayer/version.json.

        Returns a dict:
            {
              'ok': bool,
              'source': 'github' | 'website' | None,
              'current': '1.0.0',
              'latest':  '1.0.1'  | None,
              'up_to_date': bool,
              'download_url': str | None,
              'release_url':  str | None,
              'error': str | None,
            }
        """
        current = '1.0.0'
        try:
            current = self.app_info()['version']
        except Exception:
            pass

        result = {
            'ok': False, 'source': None,
            'current': current, 'latest': None,
            'up_to_date': True,
            'download_url': None, 'release_url': None,
            'error': None,
        }

        # Try GitHub first
        gh = _fetch_github_release()
        if gh:
            result['source']  = 'github'
            result['latest']  = gh['version']
            result['release_url'] = gh.get('html_url')
            result['download_url'] = gh.get('download_url') or gh.get('html_url')
            result['up_to_date'] = _version_at_least(current, gh['version'])
            result['ok'] = True
            return result

        # Fall back to website
        web = _fetch_website_version()
        if web:
            result['source']  = 'website'
            result['latest']  = web['version']
            result['download_url'] = web.get('download_url') \
                or 'https://rainbryan.com'
            result['release_url']  = web.get('release_url') \
                or 'https://rainbryan.com'
            result['up_to_date'] = _version_at_least(current, web['version'])
            result['ok'] = True
            return result

        # Both failed
        result['error'] = 'Could not reach update servers'
        return result


api = Api()

# Back-compat: anyone importing `Bridge` still gets the same class
Bridge = Api
