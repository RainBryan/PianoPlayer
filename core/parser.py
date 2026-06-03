"""
PianoPlayer / core / parser.py
─────────────────────────────────────────────────────────────────────────
Sheet → event-list parser.

Two modes:
    PLAIN     (default)  Every char is a literal key. Only [chords]
                         are recognised. Nothing is ever skipped.
    NOTATION             Musician symbols are interpreted:
        c d e            single notes
        [ec]             chord
        -                rest (one beat of silence per dash)
        c=  c==          hold (key rings under next notes)
        c~  c~~          fermata (song freezes while key is held)
        c.               staccato
        (160)            tempo change
        |                bar line (visual only)
        : ... :x3        repeat section three times

Event shape:
    {'type': 'note', 'keys': ['c'], 'chord': False,
     'len': 1.0,                  # how many beats this occupies visually
     'art': 'normal'|'hold'|'fermata'|'staccato',
     'hold_beats': 1.0,           # how long to physically hold
     'advance_beats': 1.0}        # how long until next event
    {'type': 'rest',  'len': N}
    {'type': 'tempo', 'bpm': N}
    {'type': 'bar'}
"""

from __future__ import annotations
import re

_TEMPO_RE = re.compile(r'^\((\d{2,3})\)$')


def _make_note(keys, suffix):
    """Build a note event from keys + an articulation suffix string."""
    art = 'normal'
    hold_beats = 1.0
    advance_beats = 1.0
    length_for_ui = 1.0

    eq  = suffix.count('=')
    tld = suffix.count('~')

    if eq and not tld:
        # press key, KEEP HELD while song advances eq beats underneath
        art = 'hold'
        hold_beats = 1.0 + eq
        advance_beats = 1.0
        length_for_ui = 1.0 + eq
    elif tld and not eq:
        # press key, FREEZE the song for tld extra beats while it holds
        art = 'fermata'
        hold_beats = 1.0 + tld
        advance_beats = 1.0 + tld
        length_for_ui = 1.0 + tld
    elif '.' in suffix:
        art = 'staccato'
        hold_beats = 0.25
        advance_beats = 1.0

    return {'type': 'note', 'keys': keys, 'chord': len(keys) > 1,
            'len': length_for_ui, 'art': art,
            'hold_beats': hold_beats, 'advance_beats': advance_beats}


def _parse_token(tok, out):
    if tok == '|':
        out.append({'type': 'bar'}); return
    m = _TEMPO_RE.match(tok)
    if m:
        out.append({'type': 'tempo', 'bpm': int(m.group(1))}); return
    if set(tok) == {'-'}:
        out.append({'type': 'rest', 'len': float(len(tok))}); return
    if set(tok) == {'.'}:
        out.append({'type': 'rest', 'len': float(len(tok))}); return
    if tok.startswith('['):
        close = tok.find(']')
        if close == -1:
            return
        keys = list(tok[1:close])
        if keys:
            out.append(_make_note(keys, tok[close + 1:]))
        return
    # Note tokens: each char is a key; suffix uses only . ~ =
    i = 0
    while i < len(tok):
        ch = tok[i]; i += 1
        suffix = ''
        while i < len(tok) and tok[i] in '.~=':
            suffix += tok[i]; i += 1
        out.append(_make_note([ch], suffix))


def _parse_token_plain(tok, out):
    """PLAIN mode — every character is a key. Only [chords] are special."""
    if tok.startswith('[') and tok.endswith(']'):
        keys = list(tok[1:-1])
        if keys:
            out.append({'type': 'note', 'keys': keys,
                        'chord': len(keys) > 1, 'len': 1.0,
                        'art': 'normal',
                        'hold_beats': 1.0, 'advance_beats': 1.0})
        return
    for ch in tok:
        out.append({'type': 'note', 'keys': [ch], 'chord': False,
                    'len': 1.0, 'art': 'normal',
                    'hold_beats': 1.0, 'advance_beats': 1.0})


def parse_sheet(text, notation=False):
    """Parse a sheet into an event list."""
    raw = []
    if not notation:
        for tok in text.split():
            _parse_token_plain(tok, raw)
        return raw

    repeat_stack = []
    for tok in text.split():
        if tok == ':':
            repeat_stack.append(len(raw)); continue
        rep = re.match(r'^:x(\d+)$', tok)
        if rep and repeat_stack:
            start = repeat_stack.pop()
            section = raw[start:]
            for _ in range(max(1, int(rep.group(1))) - 1):
                raw.extend([dict(e) for e in section])
            continue
        _parse_token(tok, raw)
    return raw


def playable_notes(events):
    return [e for e in events if e['type'] == 'note']


def event_label(ev):
    if ev['type'] == 'note':
        body = '[' + ''.join(ev['keys']) + ']' if ev['chord'] else ev['keys'][0]
        art = ev.get('art', 'normal')
        n = max(0, int(round(ev.get('len', 1) - 1)))
        if art == 'hold':       return body + ('=' * (n or 1))
        if art == 'fermata':    return body + ('~' * (n or 1))
        if art == 'staccato':   return body + '.'
        return body
    if ev['type'] == 'rest':  return '·' * int(ev['len'])
    if ev['type'] == 'tempo': return f"({ev['bpm']})"
    if ev['type'] == 'bar':   return '|'
    return '?'


def estimate_duration(events, bpm):
    """Estimate total song length in seconds at the given BPM."""
    if bpm <= 0:
        return 0.0
    interval = 60.0 / bpm
    total = 0.0
    for e in events:
        t = e.get('type', 'note')
        if t == 'tempo':
            new_bpm = e.get('bpm', bpm)
            if new_bpm > 0:
                bpm = new_bpm
                interval = 60.0 / bpm
            continue
        if t == 'bar':
            continue
        total += e.get('len', 1.0) * interval
    return total


def format_time(seconds):
    """Format seconds as M:SS."""
    if seconds is None or seconds < 0:
        seconds = 0
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f'{m}:{s:02d}'


def sheet_stats(events):
    notes  = playable_notes(events)
    chords = sum(1 for e in notes if e['chord'])
    rests  = sum(1 for e in events if e['type'] == 'rest')
    tempos = sum(1 for e in events if e['type'] == 'tempo')
    bars   = sum(1 for e in events if e['type'] == 'bar')
    return notes, chords, rests, tempos, bars
