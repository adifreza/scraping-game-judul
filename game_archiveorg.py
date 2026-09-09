"""Exact-title lookup against the two archive.org Redump PS2 NTSC-U items.
Fetching the file list needs no login; the eventual download does - so this
module only ever hands back a direct archive.org URL, opened as a real Brave
tab the same way Romsfun/Steamrip links are today, so the IDM extension
captures it inside whatever archive.org session the user is already logged
into in that browser. No credential storage, no headless auth flow here."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from game_scraper_multi_site import fetch_html, normalize_name

ARCHIVE_ITEMS = ["RedumpSonyPS2NTSCU", "RedumpSonyPS2NTSCUPart2"]
_CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_CACHE_VERSION = 2  # bump whenever _normalized_key changes, so stale keys rebuild
_EXCLUDE_WORDS = ("demo", "beta", "proto")


def _cache_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "WDGames" / "archiveorg_ps2_index.json"


# Redump files the article at the end: "Warriors, The", "Chronicles of Narnia,
# The - Prince Caspian". 82 of the ~1900 PS2 titles are named this way, so the
# article has to move back to the front or none of them ever match a normal
# "The Warriors" style title from the order list.
_ARTICLE_SUFFIX_RE = re.compile(r"^(.*?), +(The|A|An)(?=[^A-Za-z]|$)", re.IGNORECASE)


def _unswap_article(title: str) -> str:
    return _ARTICLE_SUFFIX_RE.sub(lambda m: f"{m.group(2)} {m.group(1)}", title, count=1)


def _normalized_key(filename: str) -> str:
    stem = filename[:-3] if filename.lower().endswith(".7z") else filename
    stem = re.sub(r"\([^)]*\)", " ", stem)  # drop (USA)/(v2.00)/(En,Fr,Es) tags
    return normalize_name(_unswap_article(stem))


def _fetch_item_files(item_id: str) -> list[str]:
    xml_text = fetch_html(f"https://archive.org/download/{item_id}/{item_id}_files.xml")
    if not xml_text:
        return []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    names = []
    for file_el in root.findall("file"):
        name = file_el.get("name") or ""
        if file_el.get("source") != "original" or not name.lower().endswith(".7z"):
            continue
        if any(w in name.lower() for w in _EXCLUDE_WORDS):
            continue
        names.append(name)
    return names


def _build_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for item_id in ARCHIVE_ITEMS:
        for filename in _fetch_item_files(item_id):
            key = _normalized_key(filename)
            if not key or key in index:
                continue  # ponytail: first-seen wins on collision (stable XML order);
                          # switch to largest <size> if the wrong variant gets picked in practice
            index[key] = [item_id, filename]
    return index


def _load_cached_index() -> dict | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != _CACHE_VERSION:
            return None
        if time.time() - data.get("built_at", 0) > _CACHE_MAX_AGE_SECONDS:
            return None
        return data.get("index")
    except Exception:
        return None


def _save_cache(index: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": _CACHE_VERSION, "built_at": time.time(), "index": index}),
        encoding="utf-8",
    )


_index_cache: dict | None = None


def _get_index() -> dict:
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    cached = _load_cached_index()
    if cached is not None:
        _index_cache = cached
        return _index_cache
    built = _build_index()
    if built:
        _save_cache(built)
    _index_cache = built  # empty on fetch failure - don't refetch every title this run
    return _index_cache


def find_exact_match(game_name: str) -> tuple[str, str] | None:
    hit = _get_index().get(normalize_name(_unswap_article(game_name)))
    return (hit[0], hit[1]) if hit else None


def download_url(item_id: str, filename: str) -> str:
    return f"https://archive.org/download/{item_id}/{quote(filename)}"


if __name__ == "__main__":
    assert _normalized_key("007 - Agent Under Fire (USA).7z") == normalize_name("007 Agent Under Fire")
    # article-suffix titles must match how a customer actually writes them
    assert _normalized_key("Warriors, The (USA) (En,Fr,De,Es,It).7z") == normalize_name("The Warriors")
    assert (_normalized_key("Chronicles of Narnia, The - Prince Caspian (USA).7z")
            == normalize_name("The Chronicles of Narnia - Prince Caspian"))
    # a comma that is not an article suffix must be left alone
    assert _unswap_article("Warhammer 40,000 - Fire Warrior") == "Warhammer 40,000 - Fire Warrior"
    idx: dict[str, str] = {}
    for fn in ["Foo (USA) (v1.00).7z", "Foo (USA) (v2.00).7z"]:
        k = _normalized_key(fn)
        if k not in idx:
            idx[k] = fn
    assert idx[_normalized_key("Foo (USA).7z")] == "Foo (USA) (v1.00).7z"
    print("game_archiveorg self-check OK")
