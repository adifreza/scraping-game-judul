"""Copy an extracted game folder to a customer HDD via robocopy.

robocopy is used (over plain shutil.copytree) because these are huge game
folders (orders can total 900GB+) on a removable USB HDD - /Z gives
restartable copies if the drive is unplugged mid-transfer, and retry limits
must be overridden or a single locked file can hang forever.
"""
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable

LogFn = Callable[[str], None]

# robocopy exit codes are a bitmask: 0-7 = success (possibly with skipped/
# extra files), 8+ = at least one real failure. This is the OPPOSITE of the
# usual "0 = success" CLI convention.
ROBOCOPY_FAILURE_THRESHOLD = 8


@dataclass
class CopyResult:
    success: bool
    return_code: int | None
    error: str | None = None


def build_robocopy_args(src_dir: str, dest_dir: str, log_path: str) -> list[str]:
    return [
        "robocopy", src_dir, dest_dir,
        "/E",       # include subfolders (incl. empty ones)
        "/Z",       # restartable mode - resume large-file copies after an interruption
        "/MT:8",    # multi-threaded copy, modest thread count (USB HDD is usually the bottleneck)
        "/R:3",     # retry a locked/busy file 3 times (default is ~1,000,000 - would hang the app)
        "/W:5",     # wait 5s between retries
        "/NP",      # no per-file percentage spam
        "/NDL",     # no directory-listing lines (less noise, keep per-file lines)
        "/TEE",     # also print to stdout so it can be streamed live
        f"/LOG+:{log_path}",
    ]


def run_copy(
    src_dir: str,
    dest_dir: str,
    log_path: str,
    log_fn: LogFn | None = None,
    on_done: Callable[[CopyResult], None] | None = None,
) -> subprocess.Popen:
    """Start robocopy in a background thread, streaming stdout line-by-line
    to log_fn. Returns the Popen handle immediately (non-blocking); on_done
    is called once the process finishes."""
    args = build_robocopy_args(src_dir, dest_dir, log_path)
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def _pump() -> None:
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    line = line.strip()
                    if line and log_fn:
                        log_fn(line)
            proc.wait()
        except Exception as exc:
            if log_fn:
                log_fn(f"✗ Copy error: {exc}")
            if on_done:
                on_done(CopyResult(False, None, error=str(exc)))
            return

        success = proc.returncode < ROBOCOPY_FAILURE_THRESHOLD
        result = CopyResult(success, proc.returncode)
        if on_done:
            on_done(result)

    threading.Thread(target=_pump, daemon=True).start()
    return proc


def default_log_path(order_label: str) -> str:
    base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    log_dir = os.path.join(base, "WDGames", "logs")
    os.makedirs(log_dir, exist_ok=True)
    safe_label = re.sub(r'[<>:"/\\|?*]', "_", order_label).strip() or "copy"
    return os.path.join(log_dir, f"copy_{safe_label}.log")


def copy_paths_to_clipboard(paths: list[str]) -> None:
    """Put folders/files on the Windows clipboard as a file-drop list, so the
    user can Ctrl+V them straight into Explorer on the customer HDD.

    PowerShell's Set-Clipboard is used because tkinter's clipboard only holds
    text - a file-drop list (CF_HDROP) needs the Win32/OLE clipboard, and
    Set-Clipboard flushes it so it survives the helper process exiting.
    """
    if not paths:
        raise ValueError("no paths to copy")
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in paths)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"Set-Clipboard -LiteralPath {quoted}"],
        check=True, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
