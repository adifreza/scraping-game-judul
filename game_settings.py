"""Small local preferences file: folder paths used for status scanning.

This is NOT a game history database - it only remembers 2-3 folder paths so
the user doesn't have to re-pick them every time. Source of truth for "is
this game already downloaded" is always the live folder scan (see
game_folder_scan.py), never a stored log.
"""
import json
import os
from pathlib import Path

DEFAULT_SETTINGS = {
    "downloads_folder": str(Path.home() / "Downloads"),
    "extracted_root": r"D:\GAMES INSTALL",
    "unrar_path": "",
    "customer_hdd_target": "",
    "fuzzy_threshold": 0.72,
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
