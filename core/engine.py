"""
PianoPlayer / core / engine.py
─────────────────────────────────────────────────────────────────────────
Playback engine. Two independent playback paths:

    SheetEngine.play(events, bpm, cfg)
        Plays a parsed sheet using our timing engine (BPM-driven, with
        notation: hold/fermata/staccato, sustain/gap/swing/human knobs).
        Uses a deferred-release scheduler so long notes ring underneath.

    MidiEngine.play(schedule)
        Plays a native-MIDI schedule with the file's ORIGINAL timing.
        No BPM/sustain/gap/swing/human modifications — what you hear IS
        the MIDI file. Same deferred-release scheduler.

Both engines support pause/resume that doesn't backlog notes, and stop.
"""

from __future__ import annotations
import time
import threading
import random

try:
    import ctypes
    _HAS_WINMM = hasattr(ctypes, 'windll')
except Exception:
    _HAS_WINMM = False

from .keys import press_keys, press_keys_down, release_keys


# ─────────────────────────────────────────────────────────────────────────────
#  Common Engine base
# ─────────────────────────────────────────────────────────────────────────────
class _BaseEngine:
    """Shared infrastructure: stop/pause/abort, hi-res timer, callbacks."""

    def __init__(self, callbacks=None):
        self.cb            = callbacks or {}
        self.playing       = False
        self.stop_event    = threading.Event()
        self._pause_event  = threading.Event()
        self._abort        = False
        self._thread       = None
        self._timer_hi     = False
        self._pause_started_at = None

    # ── lifecycle ──────────────────────────────────────────────────────
    def stop(self):
        """Stop playback as soon as possible."""
        self.stop_event.set()
        self._abort = True
        self._pause_event.clear()

    def toggle_pause(self):
        """Toggle paused state. Returns the new paused bool."""
        if not self.playing:
            return False
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._fire('resumed')
            return False
        else:
            self._pause_event.set()
            self._fire('paused')
            return True

    @property
    def is_paused(self):
        return self._pause_event.is_set()

    @property
    def is_playing(self):
        return self.playing

    # ── helpers ────────────────────────────────────────────────────────
    def _begin(self):
        self._abort = False
        self.stop_event.clear()
        self._pause_event.clear()
        self.playing = True
        # boost timer resolution on Windows
        if _HAS_WINMM:
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
                self._timer_hi = True
            except Exception:
                self._timer_hi = False
        # boost thread priority (Windows)
        self._fire('started')

    def _end(self):
        self.playing = False
        if self._timer_hi and _HAS_WINMM:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
            self._timer_hi = False
        self._fire('finished')

    def _fire(self, name, *args, **kwargs):
        cb = self.cb.get(name)
        if cb:
            try:
                cb(*args, **kwargs)
            except Exception as e:
                print(f'[engine] callback {name} failed: {e}')

    def _boost_thread_priority(self):
        if not _HAS_WINMM or self._thread is None:
            return
        try:
            h = ctypes.windll.kernel32.OpenThread(
                0x0200, False, self._thread.ident)
            ctypes.windll.kernel32.SetThreadPriority(h, 2)
            ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Sheet Engine
# ─────────────────────────────────────────────────────────────────────────────
class SheetEngine(_BaseEngine):
    """Plays parsed sheet events using our timing engine."""

    def play(self, events, bpm, cfg=None):
        if self.playing:
            return
        cfg = dict(cfg or {})
        self._begin()

        def loop():
            try:
                self._run(events, bpm, cfg)
            finally:
                self._end()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        self._boost_thread_priority()

    # ── the loop ───────────────────────────────────────────────────────
    def _run(self, events, base_bpm, cfg):
        bpm        = base_bpm
        interval   = 60.0 / max(1, bpm)
        base_hold  = min(0.025, interval * 0.4)
        sustain    = cfg.get('sustain', 1.0)
        gap_mult   = cfg.get('gap', 1.0)
        swing      = cfg.get('swing', 0.0) / 100.0
        human      = cfg.get('human', 0.0)

        timing_jit  = 0.08  * human
        hold_jit    = 0.018 * human
        miss_chance = 0.015 * human

        pending = []   # (release_perf_time, token)

        def drain_releases(now_t):
            still = []
            for rel_t, token in pending:
                if rel_t <= now_t:
                    release_keys(token)
                else:
                    still.append((rel_t, token))
            pending[:] = still

        def release_all_pending():
            while pending:
                _, token = pending.pop()
                release_keys(token)

        def wait_through_pause():
            """If paused, sleep until resumed. Returns elapsed pause time
            and shifts every pending release forward by that amount."""
            if not self._pause_event.is_set():
                return 0.0
            t0 = time.perf_counter()
            while self._pause_event.is_set() \
                    and not self.stop_event.is_set() \
                    and not self._abort:
                time.sleep(0.05)
            delta = time.perf_counter() - t0
            for i, (rt, tok) in enumerate(pending):
                pending[i] = (rt + delta, tok)
            return delta

        deadline = time.perf_counter()
        note_idx = 0
        bar_num  = 1
        swing_tog = 0
        notes_total = sum(1 for e in events if e['type'] == 'note')

        try:
            for i, ev in enumerate(events):
                if self.stop_event.is_set() or self._abort:
                    break

                if self._pause_event.is_set():
                    delta = wait_through_pause()
                    deadline += delta
                if self.stop_event.is_set() or self._abort:
                    break

                drain_releases(time.perf_counter())
                et = ev['type']

                if et == 'tempo':
                    bpm = ev['bpm']
                    interval = 60.0 / max(1, bpm)
                    base_hold = min(0.025, interval * 0.4)
                    self._fire('event', i, ev, note_idx, notes_total,
                                bar_num, bpm)
                    continue
                if et == 'bar':
                    bar_num += 1
                    self._fire('event', i, ev, note_idx, notes_total,
                                bar_num, bpm)
                    continue
                if et == 'rest':
                    dur = ev['len'] * interval * gap_mult
                    deadline += dur
                    self._fire('event', i, ev, note_idx, notes_total,
                                bar_num, bpm)
                    while time.perf_counter() < deadline:
                        if self.stop_event.is_set() or self._abort:
                            break
                        if self._pause_event.is_set():
                            delta = wait_through_pause()
                            deadline += delta
                            continue
                        drain_releases(time.perf_counter())
                        remaining = deadline - time.perf_counter()
                        if pending:
                            next_rel = min(rt for rt, _ in pending)
                            remaining = min(remaining,
                                            next_rel - time.perf_counter())
                        if remaining > 0.005:
                            time.sleep(remaining - 0.002)
                        else:
                            time.sleep(0.0005)
                    continue

                # ── note / chord ──
                art           = ev.get('art', 'normal')
                hold_beats    = ev.get('hold_beats', 1.0)
                advance_beats = ev.get('advance_beats', 1.0)

                timing_offset = (random.uniform(-timing_jit, timing_jit)
                                  * interval if human > 0 else 0.0)
                target = deadline + timing_offset

                while time.perf_counter() < target:
                    if self.stop_event.is_set() or self._abort:
                        break
                    if self._pause_event.is_set():
                        delta = wait_through_pause()
                        target += delta
                        deadline += delta
                        continue
                    drain_releases(time.perf_counter())
                    remaining = target - time.perf_counter()
                    if pending:
                        next_rel = min(rt for rt, _ in pending)
                        remaining = min(remaining,
                                        next_rel - time.perf_counter())
                    if remaining > 0.005:
                        time.sleep(remaining - 0.002)
                    else:
                        time.sleep(0.0005)

                if self.stop_event.is_set() or self._abort:
                    break

                note_idx += 1
                self._fire('event', i, ev, note_idx, notes_total,
                            bar_num, bpm)

                if human > 0 and random.random() < miss_chance:
                    press_keys(ev['keys'], 0.012)
                    time.sleep(0.014)

                # fire keys
                if art == 'hold':
                    token = press_keys_down(ev['keys'])
                    hold_sec = hold_beats * interval * sustain
                    if human > 0:
                        hold_sec += random.uniform(0, hold_jit)
                    pending.append(
                        (time.perf_counter() + hold_sec, token))
                elif art == 'fermata':
                    hold_sec = hold_beats * interval * sustain
                    if human > 0:
                        hold_sec += random.uniform(0, hold_jit)
                    press_keys(ev['keys'], hold_sec)
                else:
                    if art == 'staccato':
                        hold_sec = base_hold * 0.35 * sustain
                    else:
                        hold_sec = base_hold * sustain
                    if human > 0:
                        hold_sec += random.uniform(0, hold_jit)
                    press_keys(ev['keys'], hold_sec)

                step = advance_beats * interval * gap_mult
                if swing > 0:
                    step *= ((1.0 + swing) if swing_tog % 2 == 0
                              else (1.0 - swing))
                    swing_tog += 1
                deadline += step

            # Drain pending after the last event
            while pending and not self.stop_event.is_set() \
                    and not self._abort:
                if self._pause_event.is_set():
                    wait_through_pause()
                    continue
                drain_releases(time.perf_counter())
                if not pending:
                    break
                next_rel = min(rt for rt, _ in pending)
                remaining = next_rel - time.perf_counter()
                if remaining > 0.005:
                    time.sleep(min(remaining - 0.002, 0.05))
                else:
                    time.sleep(0.0005)
        finally:
            release_all_pending()


# ─────────────────────────────────────────────────────────────────────────────
#  MIDI Engine — native, no cfg
# ─────────────────────────────────────────────────────────────────────────────
class MidiEngine(_BaseEngine):
    """Plays a native-MIDI schedule with original timing. No cfg knobs."""

    def play(self, schedule):
        if self.playing:
            return
        self._begin()

        def loop():
            try:
                self._run(schedule)
            finally:
                self._end()

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        self._boost_thread_priority()

    def _run(self, schedule):
        total = len(schedule)
        pending = []

        def drain_releases(now_t):
            still = []
            for rel_t, token in pending:
                if rel_t <= now_t:
                    release_keys(token)
                else:
                    still.append((rel_t, token))
            pending[:] = still

        def release_all_pending():
            while pending:
                _, token = pending.pop()
                release_keys(token)

        start = time.perf_counter()
        pause_offset = 0.0

        try:
            for i, ev in enumerate(schedule):
                if self.stop_event.is_set() or self._abort:
                    break

                # handle pause
                if self._pause_event.is_set():
                    t0 = time.perf_counter()
                    while self._pause_event.is_set() \
                            and not self.stop_event.is_set() \
                            and not self._abort:
                        time.sleep(0.05)
                    pdelta = time.perf_counter() - t0
                    pause_offset += pdelta
                    for j, (rt, tok) in enumerate(pending):
                        pending[j] = (rt + pdelta, tok)
                if self.stop_event.is_set() or self._abort:
                    break

                t_target = start + ev['time'] + pause_offset

                while time.perf_counter() < t_target:
                    if self.stop_event.is_set() or self._abort:
                        break
                    if self._pause_event.is_set():
                        break
                    drain_releases(time.perf_counter())
                    remaining = t_target - time.perf_counter()
                    if pending:
                        next_rel = min(rt for rt, _ in pending)
                        remaining = min(remaining,
                                        next_rel - time.perf_counter())
                    if remaining > 0.005:
                        time.sleep(remaining - 0.002)
                    else:
                        time.sleep(0.0005)

                if self.stop_event.is_set() or self._abort:
                    break
                if self._pause_event.is_set():
                    continue

                self._fire('event', i, ev, i + 1, total, start)

                duration = ev['duration']
                if duration <= 0:
                    duration = 0.020
                token = press_keys_down(ev['keys'])
                pending.append((time.perf_counter() + duration, token))

            # Keep draining pending releases after last event
            while pending and not self.stop_event.is_set() \
                    and not self._abort:
                if self._pause_event.is_set():
                    t0 = time.perf_counter()
                    while self._pause_event.is_set():
                        time.sleep(0.05)
                    pdelta = time.perf_counter() - t0
                    for j, (rt, tok) in enumerate(pending):
                        pending[j] = (rt + pdelta, tok)
                    continue
                drain_releases(time.perf_counter())
                if not pending:
                    break
                next_rel = min(rt for rt, _ in pending)
                remaining = next_rel - time.perf_counter()
                if remaining > 0.005:
                    time.sleep(min(remaining - 0.002, 0.05))
                else:
                    time.sleep(0.0005)
        finally:
            release_all_pending()
