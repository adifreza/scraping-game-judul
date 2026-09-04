# -*- mode: python ; coding: utf-8 -*-
# Build: pip install pyinstaller pyperclip
#        pyinstaller GameLauncher_v2.2.spec
# Output: dist/GameLauncher_v2.2.exe
# Adds archive.org Redump PS2 exact-match source (game_archiveorg.py).

a = Analysis(
    ['game_launcher_multi_site.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['game_archiveorg'],
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
    name='GameLauncher_v2.2',
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
