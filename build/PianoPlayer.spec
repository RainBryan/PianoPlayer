# PianoPlayer / build / PianoPlayer.spec
#
# PyInstaller specification for building PianoPlayer.exe.
#
# Build:
#     cd PianoPlayer
#     pyinstaller build/PianoPlayer.spec --clean
#
# Output:
#     dist/PianoPlayer.exe   (single file, no console, ~30 MB)

# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

# Resolve project root from the spec file's location
PROJECT_ROOT = Path(SPECPATH).parent.resolve()
UI_DIR = PROJECT_ROOT / 'ui'

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / 'app.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Ship the UI assets so pywebview can load them at runtime
        (str(UI_DIR / 'index.html'), 'ui'),
        (str(UI_DIR / 'styles.css'), 'ui'),
        (str(UI_DIR / 'app.js'),     'ui'),
        (str(UI_DIR / 'rain-logo.png'), 'ui'),
    ],
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',   # Windows
        'webview.platforms.edgechromium',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'mido',
        'mido.backends.rtmidi',
        'core',
        'core.engine',
        'core.keys',
        'core.midi',
        'core.parser',
        'core.storage',
        'bridge',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PianoPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # ← no CMD window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'build' / 'icon.ico')
        if (PROJECT_ROOT / 'build' / 'icon.ico').exists() else None,
)
