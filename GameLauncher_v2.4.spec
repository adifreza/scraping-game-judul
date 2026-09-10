# -*- mode: python ; coding: utf-8 -*-
# Build: pip install pyinstaller pyperclip
#        pyinstaller GameLauncher_v2.4.spec
# Output: dist/GameLauncher_v2.4.exe
# v2.4: PS2 disc serials resolve to real titles (match + rename), and any
# saved order list can be checked against a customer's own drive.

a = Analysis(
    ['game_launcher_multi_site.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['game_archiveorg', 'game_ps2_serials'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GameLauncher_v2.4',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
