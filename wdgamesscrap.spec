# -*- mode: python ; coding: utf-8 -*-
# Build: pip install pyinstaller pyperclip playwright
#        pyinstaller wdgamesscrap.spec
# Output: dist/wdgamesscrap.exe

import os
import playwright

# Playwright's Node-based driver (node.exe + driver scripts) is a data
# folder, not Python modules, so PyInstaller's import-based Analysis won't
# find it on its own - it must be listed explicitly or fetch_html_via_brave's
# headless-Brave Cloudflare fallback silently has nothing to launch at runtime.
_playwright_driver_dir = os.path.join(os.path.dirname(playwright.__file__), "driver")

a = Analysis(
    ['game_launcher_multi_site.py'],
    pathex=[],
    binaries=[],
    datas=[(_playwright_driver_dir, 'playwright/driver')],
    hiddenimports=[],
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
    name='wdgamesscrap',
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
