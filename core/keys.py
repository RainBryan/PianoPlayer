"""
PianoPlayer / core / keys.py
─────────────────────────────────────────────────────────────────────────
Roblox-piano keyboard engine. Maps every character that can appear in a
piano sheet to its physical virtual-key code, so Shift combines correctly
for capitals and !@#$%^&*().

Exports:
    press_keys(chars, hold)         press + release after `hold` seconds
    press_keys_down(chars)          press WITHOUT releasing (returns token)
    release_keys(token)             release a previously pressed group
    KEY_AVAILABLE                   True if pynput is installed & working
"""

from __future__ import annotations
import time

try:
    from pynput.keyboard import Controller, Key, KeyCode
    _KB = Controller()
    KEY_AVAILABLE = True
except Exception:
    KEY_AVAILABLE = False
    _KB = None
    Key = None
    KeyCode = None


# ── How long Shift needs after press/release to settle ─────────────────────
SHIFT_SETTLE = 0.018


# ── The Roblox piano character map ─────────────────────────────────────────
# Each entry: ch -> (virtual_key_code, needs_shift)
# Roblox piano uses: 1234567890 qwertyuiop asdfghjkl zxcvbnm  and shifted
# variants for the black keys (!@$%^ etc.) plus QWERTY uppercase.
def _build_keymap():
    m = {}

    def add(ch, vk, shift):
        m[ch] = (vk, shift)

    # Digits row (white keys) + shifted (black keys)
    digit_unshifted = '1234567890'
    digit_shifted   = '!@#$%^&*()'
    for ch, sh in zip(digit_unshifted, digit_shifted):
        vk = 0x30 + digit_unshifted.index(ch)  # 0x30 = '0'
    # remap correctly: '1'..'9','0' map to 0x31..0x39,0x30
    digit_vk = {'1':0x31,'2':0x32,'3':0x33,'4':0x34,'5':0x35,
                '6':0x36,'7':0x37,'8':0x38,'9':0x39,'0':0x30}
    for ch in digit_unshifted:
        add(ch, digit_vk[ch], False)
    for sh, ch in zip(digit_shifted, digit_unshifted):
        add(sh, digit_vk[ch], True)

    # Letter rows
    letters = 'qwertyuiopasdfghjklzxcvbnm'
    for ch in letters:
        vk = 0x41 + (ord(ch) - ord('a'))   # 0x41 = 'A'
        add(ch, vk, False)
        add(ch.upper(), vk, True)

    return m


_KEY_MAP = _build_keymap()


def _resolve(char):
    """Return (KeyCode, needs_shift) for a single Roblox-sheet character."""
    if char in _KEY_MAP:
        vk, sh = _KEY_MAP[char]
        return KeyCode.from_vk(vk), sh
    # fallback: literal character, no shift
    return KeyCode.from_char(char), False


def _press_group(codes, hold, shifted):
    """Press a group of codes simultaneously with optional shift."""
    if not _KB:
        return
    try:
        if shifted:
            _KB.press(Key.shift)
            time.sleep(SHIFT_SETTLE)
        for kc in codes:
            _KB.press(kc)
        time.sleep(hold)
        for kc in codes:
            _KB.release(kc)
        if shifted:
            time.sleep(SHIFT_SETTLE)
            _KB.release(Key.shift)
    except Exception:
        pass


def press_keys(chars, hold=0.025):
    """
    Press one or more keys for `hold` seconds, then release.
    Mixed-shift chords are split so each key plays at its correct shift state.
    BLOCKING — sleeps for `hold` seconds.
    """
    if not _KB:
        return
    shifted, plain = [], []
    for c in chars:
        kc, sh = _resolve(c)
        (shifted if sh else plain).append(kc)
    if plain:
        _press_group(plain, hold, False)
    if shifted:
        _press_group(shifted, hold, True)


def press_keys_down(chars):
    """
    Press keys WITHOUT releasing them. Returns an opaque token that
    `release_keys(token)` can use to release them later.

    This is the primitive that lets long notes ring underneath subsequent
    notes — call this, then add (release_time, token) to a pending list,
    then call release_keys when the time comes.
    """
    if not _KB:
        return ([], False)
    shifted, plain = [], []
    for c in chars:
        kc, sh = _resolve(c)
        (shifted if sh else plain).append(kc)
    all_codes = []
    used_shift = False
    try:
        if shifted:
            used_shift = True
            _KB.press(Key.shift)
            time.sleep(SHIFT_SETTLE)
            for kc in shifted:
                _KB.press(kc)
                all_codes.append(kc)
            # Release Shift — the keydown events for the shifted letters
            # have already been received by the OS, so releasing Shift
            # here doesn't "un-shift" them. They stay physically down
            # until release_keys() is called.
            _KB.release(Key.shift)
            time.sleep(SHIFT_SETTLE)
        for kc in plain:
            _KB.press(kc)
            all_codes.append(kc)
    except Exception:
        pass
    return (all_codes, used_shift)


def release_keys(token):
    """Release keys previously pressed by `press_keys_down`."""
    if not _KB or not token:
        return
    codes, _used_shift = token
    for kc in codes:
        try:
            _KB.release(kc)
        except Exception:
            pass
