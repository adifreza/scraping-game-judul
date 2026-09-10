# -*- mode: python ; coding: utf-8 -*-
# Build: pip install pyinstaller pyperclip
#        pyinstaller GameLauncher_v2.5.spec
# Output: dist/GameLauncher_v2.5.exe
# v2.5: new "Bersih-bersih" tab - scans the LOCAL install folder only (not the
# external HDD) against every saved order list and permanently deletes games no
# customer wants (extracted or not).

a = Analysis(
    ['game_launcher_multi_site.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['game_archiveorg', 'game_ps2_serials', 'game_cleanup'],
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
    name='GameLauncher_v2.5',
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
