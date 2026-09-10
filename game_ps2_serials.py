"""PS2 disc serial -> real game title, plus the rename that follows from it.

Extracted PS2 games land on disk named after the disc serial - "SCUS-97481
(1.01).iso" - which Playnite (and every human) reads as noise. PCSX2 ships a
serial index covering ~12.8k discs, so that file is the lookup table: fetch
once, cache, and from then on "SCUS-97481" resolves to "God of War II" both
for renaming the file and for matching it against an order list.

The fetch is ~2.4 MB and can take 20s+, so callers must use
ensure_index_async() at startup: title_for() never blocks and simply returns
None until the index is ready.
"""
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

GAME_INDEX_URL = "https://raw.githubusercontent.com/PCSX2/pcsx2/master/bin/resources/GameIndex.yaml"
_CACHE_VERSION = 1
_CACHE_MAX_AGE_SECONDS = 90 * 24 * 60 * 60

# Serials are 4 letters + 5 digits, written either as the disc label
# ("SLUS-21215") or as the boot filename ("SLUS_212.15"). Both normalize to
# the dashed form. A wrong hit is harmless: nothing is proposed unless the
# serial is actually in the index.
SERIAL_RE = re.compile(r"\b([A-Za-z]{4})[-_ ]?(\d{3})[.\-_ ]?(\d{2})\b")

_YAML_SERIAL_RE = re.compile(r'^([A-Z]{4}-\d{5}):\s*$')
_YAML_NAME_RE = re.compile(r'^\s+name:\s*"?(.*?)"?\s*$')

# Windows-illegal characters, and the separator each becomes in a filename.
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*]')

_index: dict[str, str] | None = None
_load_lock = threading.Lock()


def _cache_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "WDGames" / "ps2_serials.json"


def extract_serial(name: str) -> str | None:
    """'SCUS-97481 (1.01).iso' -> 'SCUS-97481'. None when there is no serial."""
    match = SERIAL_RE.search(name)
    if not match:
        return None
    return f"{match.group(1).upper()}-{match.group(2)}{match.group(3)}"


def parse_game_index(yaml_text: str) -> dict[str, str]:
    """serial -> name, straight off PCSX2's GameIndex.yaml.

    Parsed line-by-line rather than with a YAML library: the file is 2.4 MB of
    a strictly regular shape (a serial key, then an indented name), so a real
    parser would only add a dependency and seconds of parse time.
    """
    index: dict[str, str] = {}
    serial: str | None = None
    for line in yaml_text.splitlines():
        key = _YAML_SERIAL_RE.match(line)
        if key:
            serial = key.group(1)
            continue
        if serial:
            name = _YAML_NAME_RE.match(line)
            if name:
                title = name.group(1).strip()
                if title:
                    index[serial] = title
                serial = None
    return index


def _load_cache() -> dict[str, str] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != _CACHE_VERSION:
            return None
        if time.time() - data.get("built_at", 0) > _CACHE_MAX_AGE_SECONDS:
            return None
        index = data.get("index")
        return index if isinstance(index, dict) and index else None
    except Exception:
        return None


def _save_cache(index: dict[str, str]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": _CACHE_VERSION, "built_at": time.time(), "index": index}),
        encoding="utf-8",
    )


def ensure_index(log_fn=None) -> dict[str, str]:
    """Cache -> memory, downloading the index once if there is no fresh copy.
    Blocks; call it from a worker thread."""
    global _index
    with _load_lock:
        if _index:
            return _index
        cached = _load_cache()
        if cached:
            _index = cached
            return _index
        if log_fn:
            log_fn("⏳ Mengunduh database serial PS2 (sekali saja, ±2 MB)...")
        try:
            request = Request(GAME_INDEX_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=90) as response:
                text = response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            if log_fn:
                log_fn(f"✗ Gagal mengunduh database serial PS2: {exc}")
            return {}
        index = parse_game_index(text)
        if index:
            _save_cache(index)
            _index = index
            if log_fn:
                log_fn(f"✓ Database serial PS2 siap: {len(index)} judul.")
        return index or {}


def ensure_index_async(log_fn=None, on_ready=None) -> None:
    """Warm the index in the background so the first scan never blocks the UI."""
    def worker() -> None:
        index = ensure_index(log_fn)
        if index and on_ready:
            on_ready()

    threading.Thread(target=worker, daemon=True).start()


def title_for(serial: str | None) -> str | None:
    """Never blocks - returns None while the index is still loading."""
    if not serial:
        return None
    return (_index or {}).get(serial.upper())


def title_for_name(name: str) -> str | None:
    """Real title for a serial-named file/folder, or None."""
    return title_for(extract_serial(name))


def safe_filename(title: str) -> str:
    """Windows-safe version of a game title, keeping it readable for Playnite."""
    cleaned = _ILLEGAL_RE.sub(" - ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


@dataclass
class RenamePlan:
    path: str
    current_name: str
    serial: str
    title: str
    new_name: str

    @property
    def new_path(self) -> str:
        return os.path.join(os.path.dirname(self.path), self.new_name)


def _version_tag(name: str) -> str:
    """The '(1.01)' disc-version suffix, used only to break a name collision."""
    match = re.search(r"\((\d+\.\d+)\)", name)
    return f" ({match.group(1)})" if match else ""


def plan_rename(path: str) -> RenamePlan | None:
    """Proposal for one entry, or None when it has no known serial or is
    already named after its title."""
    name = os.path.basename(path.rstrip("/\\"))
    serial = extract_serial(name)
    title = title_for(serial)
    if not serial or not title:
        return None

    stem, ext = os.path.splitext(name)
    if os.path.isdir(path):
        ext = ""
    base = safe_filename(title)
    new_name = f"{base}{ext}"

    if new_name.lower() == name.lower():
        return None

    # Two discs of the same game (or a re-release) would collide; keep the
    # disc version, then a counter, so nothing is ever silently overwritten.
    directory = os.path.dirname(path)
    if os.path.exists(os.path.join(directory, new_name)):
        new_name = f"{base}{_version_tag(name)}{ext}"
        counter = 2
        while os.path.exists(os.path.join(directory, new_name)):
            new_name = f"{base} ({counter}){ext}"
            counter += 1

    return RenamePlan(path, name, serial, title, new_name)


def plan_renames(roots: list[str]) -> list[RenamePlan]:
    """Every serial-named file/folder across the given roots that can be
    renamed to a real title."""
    plans: list[RenamePlan] = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in entries:
            plan = plan_rename(entry.path)
            if plan:
                plans.append(plan)
    return plans


def apply_rename(plan: RenamePlan) -> str:
    """Rename one entry, returning the new path. Refuses to overwrite."""
    target = plan.new_path
    if os.path.exists(target):
        raise FileExistsError(target)
    os.rename(plan.path, target)
    return target


if __name__ == "__main__":
    import tempfile

    sample = (
        'SLUS-21215:\n'
        '  name: "The Warriors"\n'
        '  name-sort: "Warriors, The"\n'
        '  region: "NTSC-U"\n'
        'SCUS-97481:\n'
        '  name: "God of War II"\n'
        '  region: "NTSC-U"\n'
        'SLUS-20946:\n'
        '  name: "Grand Theft Auto - San Andreas"\n'
    )
    parsed = parse_game_index(sample)
    assert parsed == {
        "SLUS-21215": "The Warriors",
        "SCUS-97481": "God of War II",
        "SLUS-20946": "Grand Theft Auto - San Andreas",
    }, parsed

    assert extract_serial("SCUS-97481 (1.01).iso") == "SCUS-97481"
    assert extract_serial("SLUS_212.15") == "SLUS-21215"
    assert extract_serial("God of War III.iso") is None
    assert safe_filename('Ratchet & Clank: Up Your Arsenal') == "Ratchet & Clank - Up Your Arsenal"

    _index = parsed
    with tempfile.TemporaryDirectory() as root:
        iso = os.path.join(root, "SCUS-97481 (1.01).iso")
        open(iso, "w").close()
        os.mkdir(os.path.join(root, "SLUS-21215"))
        open(os.path.join(root, "Untouched Game.iso"), "w").close()

        plans = {p.current_name: p for p in plan_renames([root])}
        assert set(plans) == {"SCUS-97481 (1.01).iso", "SLUS-21215"}, plans
        assert plans["SCUS-97481 (1.01).iso"].new_name == "God of War II.iso"
        assert plans["SLUS-21215"].new_name == "The Warriors"  # a folder keeps no extension

        apply_rename(plans["SCUS-97481 (1.01).iso"])
        assert os.path.isfile(os.path.join(root, "God of War II.iso"))
        assert not plan_renames([root])[0].current_name.startswith("SCUS")

        # A second disc of the same title must not overwrite the first.
        open(os.path.join(root, "SCUS-97481 (2.00).iso"), "w").close()
        collide = plan_rename(os.path.join(root, "SCUS-97481 (2.00).iso"))
        assert collide is not None and collide.new_name == "God of War II (2.00).iso", collide

    print("game_ps2_serials self-check OK")
