"""
PianoPlayer / core / midi.py
─────────────────────────────────────────────────────────────────────────
MIDI loading and native-schedule generation for the Roblox piano.

The Roblox piano has 61 keys. Each MIDI note number is mapped to a
single character that, when typed (with Shift for the sharp/flat keys),
produces that pitch in-game. See ROBLOX_PIANO_KEYS below.

Native playback path:
    midi_load(path, native=True) -> dict with on/off events + tempo map
    midi_native_schedule(data, transpose, max_poly) -> playable schedule
       [ {'time': sec, 'keys': [char,...], 'duration': sec}, ... ]
"""

from __future__ import annotations
from pathlib import Path


# ── The 61 Roblox piano keys, in MIDI-pitch order (low → high) ──────────────
ROBLOX_PIANO_KEYS = (
    # octave 0  — MIDI 36..47
    '1', '!', '2', '@', '3', '4', '$', '5', '%', '6', '^', '7',
    # octave 1  — MIDI 48..59
    '8', '*', '9', '(', '0', 'q', 'Q', 'w', 'W', 'e', 'E', 'r',
    # octave 2 (middle C)  — MIDI 60..71
    't', 'T', 'y', 'Y', 'u', 'i', 'I', 'o', 'O', 'p', 'P', 'a',
    # octave 3  — MIDI 72..83
    's', 'S', 'd', 'D', 'f', 'g', 'G', 'h', 'H', 'j', 'J', 'k',
    # octave 4  — MIDI 84..95
    'l', 'L', 'z', 'Z', 'x', 'c', 'C', 'v', 'V', 'b', 'B', 'n',
    # top key — MIDI 96
    'm',
)

MIDI_LOW  = 36
MIDI_HIGH = MIDI_LOW + len(ROBLOX_PIANO_KEYS) - 1   # = 96


def midi_to_key(note, transpose=0):
    """Translate a MIDI note number → a Roblox piano character.
    Returns None if it falls outside the 61-key range after transpose."""
    n = note + transpose
    if MIDI_LOW <= n <= MIDI_HIGH:
        return ROBLOX_PIANO_KEYS[n - MIDI_LOW]
    return None


def midi_suggest_transpose(on_events):
    """Suggest a transpose (in semitones) that fits the MIDI's pitch
    range into the Roblox keyboard. Returns 0 if the file already fits."""
    if not on_events:
        return 0
    notes = [n for _, n, _ in on_events]
    lo, hi = min(notes), max(notes)
    if lo >= MIDI_LOW and hi <= MIDI_HIGH:
        return 0
    # try transposes from -36 to +36, pick the one that loses fewest notes
    best_t, best_loss = 0, len(notes)
    for t in range(-36, 37):
        loss = sum(1 for n in notes
                    if not (MIDI_LOW <= n + t <= MIDI_HIGH))
        if loss < best_loss:
            best_loss = loss
            best_t = t
    return best_t


def midi_load(path, *, native=False):
    """
    Read a MIDI file from disk.

    native=False  ->  (events, ticks_per_beat, default_bpm)  (legacy)
                      events: [(tick, midi_note, velocity)]
    native=True   ->  dict for native playback:
                       {'on_events':  [(tick, note, velocity)],
                        'off_events': [(tick, note)],
                        'tempo_map':  [(tick, microseconds_per_beat)],
                        'tpb': int,
                        'default_bpm': int}
    """
    try:
        import mido
    except ImportError:
        raise RuntimeError(
            "The 'mido' package is required for MIDI import.\n"
            "Install it with:  pip install mido")

    midi = mido.MidiFile(str(path))
    tpb  = midi.ticks_per_beat or 480
    default_bpm = 120

    on_events  = []
    off_events = []
    tempo_map  = [(0, 500_000)]   # default 120 BPM at tick 0

    for track in midi.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == 'set_tempo':
                tempo_map.append((t, msg.tempo))
                if default_bpm == 120 and t == 0:
                    default_bpm = max(20, min(500,
                                         int(round(60_000_000 / msg.tempo))))
            elif msg.type == 'note_on' and msg.velocity > 0:
                on_events.append((t, msg.note, msg.velocity))
            elif msg.type == 'note_off' or (
                    msg.type == 'note_on' and msg.velocity == 0):
                off_events.append((t, msg.note))

    on_events.sort(key=lambda e: e[0])
    off_events.sort(key=lambda e: e[0])
    tempo_map.sort(key=lambda e: e[0])

    if native:
        return {'on_events': on_events, 'off_events': off_events,
                'tempo_map': tempo_map, 'tpb': tpb,
                'default_bpm': default_bpm}
    return on_events, tpb, default_bpm


def midi_tick_to_seconds(ticks, tempo_map, tpb):
    """Convert an absolute tick into seconds using the tempo map."""
    seconds = 0.0
    last_tick = 0
    last_us_per_beat = 500_000
    for ev_tick, us_per_beat in tempo_map:
        if ev_tick >= ticks:
            break
        seconds += (ev_tick - last_tick) * last_us_per_beat / (tpb * 1_000_000)
        last_tick = ev_tick
        last_us_per_beat = us_per_beat
    seconds += (ticks - last_tick) * last_us_per_beat / (tpb * 1_000_000)
    return seconds


def midi_native_schedule(midi_data, transpose=0, max_poly=0):
    """
    Build a timed Roblox-keypress schedule from native MIDI data.

    Returns a list of clusters:
        {'time': sec_from_start,
         'keys': [char, ...],
         'duration': sec}

    Notes that don't map to the 61-key range are silently skipped after
    transpose. Pass max_poly=0 (default) for unrestricted polyphony.
    """
    tpb       = midi_data['tpb']
    tempo_map = midi_data['tempo_map']
    on_evs    = midi_data['on_events']
    off_evs   = midi_data['off_events']

    # Pair each note_on with the next matching note_off
    off_index = {}
    for tick, note in off_evs:
        off_index.setdefault(note, []).append(tick)
    for n in off_index:
        off_index[n].sort()

    paired = []
    for tick, note, vel in on_evs:
        offs = off_index.get(note, [])
        end_tick = None
        for i, ot in enumerate(offs):
            if ot >= tick:
                end_tick = ot
                offs.pop(i)
                break
        if end_tick is None:
            end_tick = tick + tpb  # fall-back: 1 beat
        paired.append((tick, end_tick, note, vel))

    # Translate ticks to seconds and notes to Roblox keys
    schedule = []
    for tick, end_tick, note, vel in paired:
        ch = midi_to_key(note, transpose)
        if ch is None:
            continue
        t_start = midi_tick_to_seconds(tick, tempo_map, tpb)
        t_end   = midi_tick_to_seconds(end_tick, tempo_map, tpb)
        dur     = t_end - t_start
        schedule.append({'time': t_start, 'keys': [ch], 'duration': dur})

    schedule.sort(key=lambda e: e['time'])

    # Merge keys whose onsets are within 25ms into one chord
    CHORD_WINDOW = 0.025
    merged = []
    for ev in schedule:
        if merged and ev['time'] - merged[-1]['time'] < CHORD_WINDOW:
            for k in ev['keys']:
                if k not in merged[-1]['keys']:
                    merged[-1]['keys'].append(k)
            merged[-1]['duration'] = max(merged[-1]['duration'], ev['duration'])
        else:
            merged.append({'time': ev['time'],
                            'keys': list(ev['keys']),
                            'duration': ev['duration']})

    # Polyphony cap — only if max_poly > 0
    if max_poly and max_poly > 0:
        for ev in merged:
            if len(ev['keys']) > max_poly:
                ev['keys'] = ev['keys'][:max_poly]

    return merged
