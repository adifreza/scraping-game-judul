"""Filesystem-based game status checking - no database.

Ground truth for "has this game already been downloaded/extracted" is
whatever currently sits in the extracted-games folder (D:) and the
downloads folder (C:), because games routinely get deleted after use. A
persisted history log would drift out of sync with reality the moment a
folder is deleted, so every check here re-reads the folders live.
"""
import os
from dataclasses import dataclass
from difflib import SequenceMatcher

from game_scraper_multi_site import normalize_name
import game_ps2_serials

ARCHIVE_EXTENSIONS = (".rar", ".zip", ".7z")

# A finished PS2 game is a single disc image sitting next to the PC game
# folders, not a folder of its own - so the extracted-root scan has to index
# these files too or every PS2 title reads as "belum ada".
DISC_EXTENSIONS = (".iso", ".chd", ".bin", ".cue", ".mdf", ".nrg", ".img")

STATUS_EXTRACTED = "extracted"
STATUS_DOWNLOADED = "downloaded"
STATUS_NOT_FOUND = "not_found"

DEFAULT_RELEASE_SUFFIXES = [
    "-steamrip.com", "-steamrip", "-rip-dodi", "-dodi", "-codex",
    "-plaza", "-fitgirl", "-elamigos", "-empress", "-skidrow",
    "-gog", "-repack",
]

# (normalized_name -> (original_label, full_path))
FolderIndex = dict[str, tuple[str, str]]


@dataclass
class MatchResult:
    status: str = STATUS_NOT_FOUND
    matched_path: str | None = None
    matched_label: str | None = None
    confidence: float = 0.0
    is_exact: bool = False


def clean_archive_filename(filename: str, release_suffixes: list[str] | None = None) -> str:
    """Strip extension + known release-tag suffix, turn dots/underscores into spaces."""
    suffixes = release_suffixes if release_suffixes is not None else DEFAULT_RELEASE_SUFFIXES
    name = filename
    for ext in ARCHIVE_EXTENSIONS:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    lowered = name.lower()
    for suffix in suffixes:
        if lowered.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.replace(".", " ").replace("_", " ")
    return name.strip()


def scan_extracted_folder(root: str) -> FolderIndex:
    """Index the extracted-games root: immediate subfolders (PC games) plus
    disc images (PS2 games).

    A disc image still named after its serial - "SCUS-97481 (1.01).iso" - is
    additionally indexed under its real title, so it matches an order line
    reading "God of War II" even before anyone renames the file.
    """
    index: FolderIndex = {}
    if not root or not os.path.isdir(root):
        return index
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.is_dir():
                    name = entry.name
                elif entry.name.lower().endswith(DISC_EXTENSIONS):
                    name = os.path.splitext(entry.name)[0]
                else:
                    continue

                norm = normalize_name(name)
                if norm:
                    index.setdefault(norm, (entry.name, entry.path))

                real_title = game_ps2_serials.title_for_name(name)
                if real_title:
                    title_norm = normalize_name(real_title)
                    if title_norm:
                        index.setdefault(title_norm, (entry.name, entry.path))
    except OSError:
        pass
    return index


def scan_downloads_folder(root: str, release_suffixes: list[str] | None = None) -> FolderIndex:
    """Index archive files in the downloads folder (e.g. C:\\Users\\...\\Downloads)."""
    index: FolderIndex = {}
    if not root or not os.path.isdir(root):
        return index
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                if not entry.name.lower().endswith(ARCHIVE_EXTENSIONS):
                    continue
                cleaned = clean_archive_filename(entry.name, release_suffixes)
                norm = normalize_name(cleaned)
                if norm:
                    index[norm] = (entry.name, entry.path)
    except OSError:
        pass
    return index


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio, boosted when one title is a whole-word prefix of
    the other - covers the common 'Max Payne 3' vs 'Max Payne 3 - Complete
    Edition' case, where a plain ratio unfairly drops due to length
    difference even though it's clearly the same game."""
    ratio = SequenceMatcher(None, a, b).ratio()
    if a and b:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if longer == shorter or longer.startswith(shorter + " "):
            ratio = max(ratio, 0.90)
    return ratio


def _best_fuzzy(
    normalized_title: str, index: FolderIndex, threshold: float
) -> tuple[tuple[str, str] | None, float]:
    best_ratio = 0.0
    best_entry: tuple[str, str] | None = None
    for candidate_norm, entry in index.items():
        ratio = _similarity(normalized_title, candidate_norm)
        if ratio > best_ratio:
            best_ratio = ratio
            best_entry = entry
    if best_entry is not None and best_ratio >= threshold:
        return best_entry, best_ratio
    return None, best_ratio


def match_title(
    title: str,
    extracted_index: FolderIndex,
    downloads_index: FolderIndex,
    threshold: float = 0.72,
) -> MatchResult:
    """Match one order-list title against the two live folder indexes.

    Extracted folder takes priority over the downloads (not-yet-extracted)
    folder when both would match. Fuzzy matches are always returned with
    is_exact=False so the caller can require user confirmation - never
    silently treated as a duplicate.
    """
    normalized = normalize_name(title)
    if not normalized:
        return MatchResult()

    if normalized in extracted_index:
        label, path = extracted_index[normalized]
        return MatchResult(STATUS_EXTRACTED, path, label, 1.0, True)
    if normalized in downloads_index:
        label, path = downloads_index[normalized]
        return MatchResult(STATUS_DOWNLOADED, path, label, 1.0, True)

    entry, ratio = _best_fuzzy(normalized, extracted_index, threshold)
    if entry:
        label, path = entry
        return MatchResult(STATUS_EXTRACTED, path, label, ratio, False)

    entry, ratio = _best_fuzzy(normalized, downloads_index, threshold)
    if entry:
        label, path = entry
        return MatchResult(STATUS_DOWNLOADED, path, label, ratio, False)

    return MatchResult()


def build_name_hints(
    matches: dict[str, MatchResult], release_suffixes: list[str] | None = None
) -> dict[str, str]:
    """Map normalized-cleaned-archive-name -> order-list title, for games that
    are matched to an un-extracted downloaded archive. Lets extraction name
    the destination folder after the order title instead of the raw
    scene-release filename."""
    hints: dict[str, str] = {}
    for order_title, match in matches.items():
        if match.status == STATUS_DOWNLOADED and match.matched_path:
            cleaned = clean_archive_filename(os.path.basename(match.matched_path), release_suffixes)
            norm = normalize_name(cleaned)
            if norm:
                hints[norm] = order_title
    return hints


def scan_extracted_folders(roots: list[str]) -> FolderIndex:
    """Merge the indexes of several extracted-game roots (e.g. the local
    games folder plus an external HDD). Earlier roots win on a name
    clash, so the local copy is preferred over the same game on the HDD."""
    merged: FolderIndex = {}
    for root in roots:
        for norm, entry in scan_extracted_folder(root).items():
            merged.setdefault(norm, entry)
    return merged
