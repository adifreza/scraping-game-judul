"""Small local preferences file: folder paths used for status scanning.

This is NOT a game history database - it only remembers 2-3 folder paths so
the user doesn't have to re-pick them every time. Source of truth for "is
this game already downloaded" is always the live folder scan (see
game_folder_scan.py), never a stored log.
"""
import json
import os
from pathlib import Path

# One dark theme for the whole app. Both the launcher and the embedded status
# scanner read these, so an accent changed here changes both - they used to
# keep private copies and drift apart.
APP_BG = "#070b14"        # app canvas
SIDEBAR_BG = "#0b1120"    # left nav rail
PANEL_BG = "#111a2e"      # cards / panels
PANEL_ALT = "#16203a"     # card header, button idle
TEXT_BG = "#0a0f1c"       # text inputs and tables
STRIPE_BG = "#0d1424"     # alternating table row
ACCENT = "#6366f1"        # indigo - primary
ACCENT_HOVER = "#818cf8"
ACCENT_PINK = "#e11d68"   # pink - destructive/heavy actions
OK = "#34d399"            # already extracted
WARN = "#fbbf24"          # downloaded, not extracted
DANGER = "#f87171"        # missing
TEXT_FG = "#e8edf7"
MUTED_FG = "#7d8cab"
BORDER_COLOR = "#1e2b47"


# Order-list "tabs": the default order plus 5 customer slots. Text for each is
# persisted under "order_lists" so switching never loses a list. Lives here so
# both the launcher and the status scanner can read the slots without importing
# each other.
LIST_DEFS = [
    ("pesanan", "📋 Pesanan"),
    ("cust1", "👤 Cust 1"),
    ("cust2", "👤 Cust 2"),
    ("cust3", "👤 Cust 3"),
    ("cust4", "👤 Cust 4"),
    ("cust5", "👤 Cust 5"),
]

DEFAULT_SETTINGS = {
    "downloads_folder": str(Path.home() / "Downloads"),
    "extracted_root": r"D:\GAMES INSTALL",
    "extracted_root_2": "",   # optional 2nd scan root, e.g. an external HDD
    "unrar_path": "",
    "customer_hdd_target": "",
    "fuzzy_threshold": 0.72,
    "order_lists": {},          # slug -> raw pasted order text, per customer
    "active_order_list": "pesanan",
    "customer_hdd_folders": {},  # slug -> last-picked HDD folder, for the cleanup "sudah dikirim?" check
    "release_suffixes": [
        "-steamrip.com", "-steamrip", "-rip-dodi", "-dodi", "-codex",
        "-plaza", "-fitgirl", "-elamigos", "-empress", "-skidrow",
        "-gog", "-repack",
    ],
}


def _settings_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "WDGames" / "settings.json"


def load_settings() -> dict:
    """Load settings from disk, filling in defaults for any missing keys."""
    path = _settings_path()
    merged = dict(DEFAULT_SETTINGS)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged.update(data)
        except Exception:
            pass
    return merged


def save_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
