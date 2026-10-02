"""Small IDM command-line integration for resolved direct download URLs."""
import os
import subprocess
from pathlib import Path


def find_idman() -> str | None:
    """Find Internet Download Manager's command-line executable."""
    candidates = [
        os.getenv("IDMAN_PATH", ""),
        os.path.join(os.getenv("PROGRAMFILES", ""), "Internet Download Manager", "IDMan.exe"),
        os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Internet Download Manager", "IDMan.exe"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Internet Download Manager", "IDMan.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def add_to_queue(url: str, idman_path: str | None = None) -> None:
    """Add one URL to IDM's queue without starting the download."""
    executable = idman_path or find_idman()
    if not executable:
        raise FileNotFoundError("IDMan.exe tidak ditemukan")

    subprocess.run(
        [executable, "/d", url, "/n", "/a"],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )