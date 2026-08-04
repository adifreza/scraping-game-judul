"""Batch RAR/ZIP extraction using WinRAR's UnRAR.exe CLI.

Scans the downloads folder for archive files, extracts each into the
extracted-games root, and (only on confirmed success) deletes the source
archive to save space on C:. Never touches a file that failed to extract.
"""
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from game_scraper_multi_site import normalize_name
from game_folder_scan import ARCHIVE_EXTENSIONS, clean_archive_filename

UNRAR_CANDIDATES = [
    r"C:\Program Files\WinRAR\UnRAR.exe",
    r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
]

# Skip files still being written to (e.g. IDM mid-download) - require the
# file to have been untouched for at least this many seconds.
MIN_FILE_AGE_SECONDS = 30

ILLEGAL_FOLDER_CHARS = '<>:"/\\|?*'


@dataclass
class ExtractResult:
    archive_path: str
    dest_dir: str | None
    success: bool
    deleted_source: bool = False
    error: str | None = None


def find_unrar_exe() -> str | None:
    for candidate in UNRAR_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("UnRAR.exe") or shutil.which("unrar")
    return found


def sanitize_folder_name(name: str) -> str:
    cleaned = "".join(c for c in name if c not in ILLEGAL_FOLDER_CHARS)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "Unnamed"


def _is_ready_to_extract(path: str) -> bool:
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return False
    return age > MIN_FILE_AGE_SECONDS


def extract_archive(unrar_path: str, archive_path: str, dest_dir: str) -> ExtractResult:
    """Run UnRAR against one archive. Only reports success if UnRAR's exit
    code indicates success/warning AND the destination folder actually has
    content - guards against silently "succeeding" on a no-op."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_arg = dest_dir if dest_dir.endswith(os.sep) else dest_dir + os.sep

    try:
        proc = subprocess.run(
            [unrar_path, "x", "-o+", "-idq", archive_path, dest_arg],
            capture_output=True, text=True,
        )
    except Exception as exc:
        return ExtractResult(archive_path, dest_dir, False, error=str(exc))

    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    has_content = os.path.isdir(dest_dir) and any(os.scandir(dest_dir))

    if proc.returncode == 11 or "password" in output.lower():
        return ExtractResult(
            archive_path, dest_dir, False,
            error="Archive dilindungi password - ekstrak manual diperlukan.",
        )

    # UnRAR: 0 = success, 1 = warning (still usable). Anything else is a real failure.
    if proc.returncode not in (0, 1) or not has_content:
        lines = [line for line in output.strip().splitlines() if line.strip()]
        error = lines[-1] if lines else f"UnRAR exit code {proc.returncode}"
        return ExtractResult(archive_path, dest_dir, False, error=error)

    return ExtractResult(archive_path, dest_dir, True)


def extract_all_downloads(
    downloads_folder: str,
    extracted_root: str,
    unrar_path: str,
    release_suffixes: list[str] | None = None,
    delete_source_on_success: bool = True,
    name_hints: dict[str, str] | None = None,
    log_fn=None,
) -> list[ExtractResult]:
    """Extract every archive currently sitting in downloads_folder into
    extracted_root, one folder per archive. name_hints maps a normalized
    cleaned-filename to a nicer display name (e.g. the matching order-item
    title) so the destination folder reads like the order list, not the
    scene-release filename."""
    def log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    results: list[ExtractResult] = []

    if not unrar_path or not os.path.isfile(unrar_path):
        log("✗ UnRAR.exe tidak ditemukan. Atur path-nya di Settings.")
        return results
    if not downloads_folder or not os.path.isdir(downloads_folder):
        log(f"✗ Folder Downloads tidak ditemukan: {downloads_folder}")
        return results
    if not extracted_root:
        log("✗ Folder tujuan ekstrak (D:) belum diatur di Settings.")
        return results
    os.makedirs(extracted_root, exist_ok=True)

    with os.scandir(downloads_folder) as entries:
        archive_files = [
            e.path for e in entries
            if e.is_file() and e.name.lower().endswith(ARCHIVE_EXTENSIONS)
        ]

    if not archive_files:
        log("ℹ Tidak ada file arsip di folder Downloads.")
        return results

    for archive_path in archive_files:
        filename = os.path.basename(archive_path)

        if not _is_ready_to_extract(archive_path):
            log(f"⏭ Lewati (masih baru/mungkin sedang ditulis): {filename}")
            continue

        cleaned = clean_archive_filename(filename, release_suffixes)
        norm = normalize_name(cleaned)
        dest_name = (name_hints or {}).get(norm, cleaned)
        dest_name = sanitize_folder_name(dest_name)
        dest_dir = os.path.join(extracted_root, dest_name)

        log(f"⏳ Mengekstrak: {filename} -> {dest_dir}")
        result = extract_archive(unrar_path, archive_path, dest_dir)

        if result.success:
            log(f"✓ Sukses ekstrak: {filename}")
            if delete_source_on_success:
                try:
                    os.remove(archive_path)
                    result.deleted_source = True
                    log(f"🗑 File rar sumber dihapus: {filename}")
                except OSError as exc:
                    log(f"⚠ Gagal hapus {filename}: {exc}")
        else:
            log(f"✗ Gagal ekstrak {filename}: {result.error}")

        results.append(result)

    return results
