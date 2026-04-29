# Game Launcher Multi-Site

Automated game downloader yang mendukung multiple websites sekaligus:
- **romsfun.com** → untuk game dengan tag `(PS2)`
- **steamrip.com** → untuk game tanpa tag khusus (PC, Console lain)

## Fitur

✨ **Auto-routing berdasarkan tag**
- Deteksi otomatis game PS2 vs game lainnya
- Routing ke website yang tepat

✨ **Dual-site support**
- romsfun.com untuk PS2 ROM
- steamrip.com untuk PC/Console games

✨ **Clipboard integration**
- Auto-load daftar game dari clipboard
- Parse dan filter otomatis
- Real-time search filtering

✨ **Multi-select & batch processing**
- Pilih game individual atau semua
- Selection counter real-time
- Batch download workflow

✨ **Dark theme UI**
- Dark mode design untuk kenyamanan mata
- Responsive interface
- Status logging real-time

## Usage

### ⚡ Method 1: Direct EXE (Recommended)

**Windows users** - Jalankan langsung:
```
dist/GameLauncher.exe
```

atau double-click `dist/RunGameLauncher.bat`

**Steps:**
1. Paste daftar game ke text box (atau gunakan "Auto Load" dari clipboard)
2. Klik "Parse Text" untuk parsing
3. Select games yang ingin didownload
4. Klik "Run All" atau "Start Selected"
5. Program akan buka tab di Brave Browser
6. Manual click "Download" untuk setiap game
7. IDM akan auto-capture download link

### Method 2: Run Python Script

Jika ingin menjalankan dari source code:
```bash
python game_launcher_multi_site.py
```

Pastikan sudah install dependencies:
```bash
pip install pyperclip
```

### Method 3: Direct Core Usage

```python
from game_scraper_multi_site import open_game_search_tabs

games = [
    ("Grand Theft Auto V Legacy", "romsfun"),     # PS2 ROM
    ("Cyberpunk 2077", "steamrip"),               # PC Game
    ("WRC 10", "steamrip"),                       # PC Game
]

open_game_search_tabs(games)
```

## Game List Format

### Mixed Sources (PS2 + PC)

```
Daftar Game Pesanan

1. Grand Theft Auto San Andreas (PS2)
2. Cyberpunk 2077
3. FIFA 23
4. Shadow of the Colossus (PS2)
5. Farming Simulator 25
```

**Hasil:**
- Game #1, #4 → romsfun.com (PS2 tag)
- Game #2, #3, #5 → steamrip.com (no tag)

### PS2 Only (Original)

```
1. Ghost Rider (PS2)
2. FIFA Street 2 (PS2)
3. Tony Hawk's Underground (PS2)
```

**Semua akan ke romsfun.com**

## File Structure

```
d:\autoopentabbrave\
├── game_launcher_multi_site.py      # GUI Launcher (tkinter)
├── game_scraper_multi_site.py       # Core engine (multi-site support)
├── open_romsfun_tabs.py             # Legacy PS2-only engine
├── romsfun_launcher.py              # Legacy PS2-only launcher
└── README.md                         # This file
```

## Requirements

### Untuk menjalankan EXE (Recommended)
- ✅ **TIDAK perlu install apapun!**
- Brave Browser dengan IDM Extension

### Untuk menjalankan dari Python source
- Python 3.10+
- tkinter (included dengan Python)
- pyperclip (clipboard support)

Install dependencies:
```bash
pip install pyperclip
```

### Common Requirements
- Brave Browser (dapat download di https://brave.com)
- IDM Extension di Brave (untuk auto-capture download)

## Features Detail

### Auto-Site Detection

| Game List | Destination |
|-----------|------------|
| `Title (PS2)` | romsfun.com PS2 search |
| `Title` | steamrip.com search |
| `Title (XBOX 360)` | steamrip.com search |
| `Title - Special Edition` | steamrip.com search |

### Game Search Logic

**RomsFun (PS2):**
- Scoring: Redump (1000pts) > CHD (500pts)
- Region: EU (400pts) > USA (300pts) > JP (200pts) > Asia (100pts)
- Demo: Hard exclude (-10000)

**SteamRip (PC/Console):**
- Format priority scoring
- Language preference (avoid Japanese if others available)
- Demo/Trial exclusion

### UI Components

1. **Left Panel**
   - Text input area (paste games here)
   - Parse buttons
   - Control buttons

2. **Right Panel**
   - Game list (parsed & filtered)
   - Filter search box
   - Selection counter
   - Status log
   - Action buttons (Start/Run All)

## Workflow

```
1. User pastes game list
   ↓
2. Parser detects (PS2) tags
   ↓
3. Auto-routes to correct website:
   - romsfun.com (PS2)
   - steamrip.com (others)
   ↓
4. User selects games
   ↓
5. Click "Run All" atau "Start Selected"
   ↓
6. Browser opens search results
   ↓
7. User manually clicks "Download Now"
   ↓
8. IDM captures download link
   ↓
9. Continue to next game
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Return` | Run All games |

## Known Limitations

- ⚠️ Cloudflare requires manual browser verification
- ⚠️ Manual download click needed (by design, for safety)
- ⚠️ IDM Extension must be enabled in Brave
- ⚠️ Character sanitization might affect exact title matching

## Troubleshooting

### Launcher tidak merespons?
- Pastikan Brave browser sudah running
- Cek apakah IDM Extension aktif di Brave

### Games tidak ketemu di search?
- Pastikan judul game benar (cek spelling)
- Coba hapus karakter khusus dari judul
- Gunakan judul yang lebih singkat

### Download tidak auto-trigger?
- Ini by design - klik "Download Now" secara manual
- IDM Extension akan auto-capture link
- Pastikan IDM integration aktif di Brave

## Migration from Legacy

**Old (PS2 only):**
```bash
python romsfun_launcher.py
```

**New (Multi-site):**
```bash
python game_launcher_multi_site.py
```

Legacy files masih bisa digunakan untuk PS2-only workflow.

## Create Desktop Shortcut (Windows)

### Option 1: PowerShell Script (Automatic)
Jalankan PowerShell sebagai Admin:
```powershell
$ExePath = "D:\autoopentabbrave\dist\GameLauncher.exe"
$ShortcutPath = "$env:USERPROFILE\Desktop\GameLauncher.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.IconLocation = $ExePath
$Shortcut.Save()
Write-Host "Shortcut created at $ShortcutPath"
```

### Option 2: Manual
1. Buka Windows Explorer
2. Navigate ke `dist` folder
3. Right-click pada `GameLauncher.exe`
4. Pilih "Send to" → "Desktop (create shortcut)"
5. Double-click shortcut untuk jalankan

Sekarang bisa double-click di Desktop untuk jalankan program! 🎮

## Future Enhancements

- [ ] Support website lain (GOG, Epic Games)
- [ ] Auto-download via API (jika available)
- [ ] Proxy support untuk regional access
- [ ] Game library caching
- [ ] Download history tracking

## Support

Untuk issues atau improvements, silakan submit via GitHub.

---

**Version:** 2.0 (Multi-Site)  
**Last Updated:** April 29, 2026  
**Status:** Production Ready
