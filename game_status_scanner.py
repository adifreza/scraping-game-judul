"""Game status scanner: paste a game order list, pick any folder, see which
titles already exist in that folder vs which are missing.

Exposed as a reusable tk.Frame (GameStatusScannerPanel) so it can be
embedded as a tab inside game_launcher_multi_site.py, plus a thin tk.Tk
wrapper (GameStatusScanner) so it can still run standalone. Reuses the same
live-folder-scan matching logic (no database, folder contents are always
the source of truth).
"""
import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pyperclip

import game_folder_scan as folder_scan
import game_settings

from game_settings import (
    APP_BG,
    SIDEBAR_BG,
    PANEL_BG,
    PANEL_ALT,
    TEXT_BG,
    STRIPE_BG,
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PINK,
    OK,
    WARN,
    DANGER,
    TEXT_FG,
    MUTED_FG,
    BORDER_COLOR,
)

SAMPLE_TEXT = """Daftar Game Pesanan

1. 007 First Light
2. Mafia: The Old Country
3. Black Myth: Wukong
4. Indiana Jones and the Great Circle
5. Lost Soul Aside
6. WUCHANG: Fallen Feathers
7. Max Payne 3
8. Grand Theft Auto IV
9. DRAGON BALL: Sparking! ZERO
10. Solo Leveling: ARISE OVERDRIVE
11. Rise of the Ronin
12. Trails in the Sky 1st Chapter
13. MY HERO ACADEMIA: All's Justice
14. The Legend of Zelda: Breath of the Wild
15. The Legend of Zelda: Tears of the Kingdom
16. Tales of Arise
17. Assassin's Creed Liberation HD

Total Size: 918.9 GB"""


def parse_order_list(text: str) -> list[str]:
    """Same cleanup rules as game_launcher_multi_site._normalize_parsed_title,
    kept as a small standalone copy so this module has no GUI-class dependency."""
    titles: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not re.match(r"^\d+\.", line):
            continue
        title = re.sub(r"^\d+\.\s*", "", line)
        title = re.sub(r"\s*\(PS2\)\s*", "", title)
        for dash in ("-", "\u2013", "\u2014"):
            title = title.replace(dash, " ")
        for apostrophe in ("'", "\u2019"):
            title = title.replace(apostrophe, "")
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            titles.append(title)
    return titles


def _create_btn(parent, text, command, style_type="normal", **pack_kwargs) -> tk.Button:
    if style_type == "accent":
        bg, fg, active_bg = ACCENT, "#ffffff", ACCENT_HOVER
    elif style_type == "accent_pink":
        bg, fg, active_bg = ACCENT_PINK, "#ffffff", "#f43f75"
    else:
        bg, fg, active_bg = PANEL_ALT, TEXT_FG, "#22304f"

    btn = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=active_bg, activeforeground="#ffffff",
        font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
        padx=16, pady=9, cursor="hand2",
    )
    btn.bind("<Enter>", lambda e: btn.config(bg=active_bg))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    if pack_kwargs:
        btn.pack(**pack_kwargs)
    return btn


class GameStatusScannerPanel(tk.Frame):
    """Embeddable panel - pack/grid this into any parent widget."""

    def __init__(
        self, master: tk.Widget, default_folder: str = "", default_folder_2: str = ""
    ) -> None:
        super().__init__(master, bg=APP_BG)
        self._target_folder = tk.StringVar(value=default_folder)
        self._target_folder_2 = tk.StringVar(value=default_folder_2)
        self._results: list[tuple[str, folder_scan.MatchResult]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        # Two folder pickers - the local games folder and an external HDD -
        # both scanned together in one pass.
        picker_wrap = tk.Frame(self, bg=APP_BG)
        picker_wrap.pack(fill="x", padx=20, pady=(16, 12))

        for title, var, chooser in (
            ("📁 Folder / HDD Cust", self._target_folder, self._choose_folder),
            ("💽 HDD Eksternal", self._target_folder_2, self._choose_folder_2),
        ):
            folder_row = tk.Frame(picker_wrap, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
            folder_row.pack(fill="x", pady=(0, 8))
            tk.Label(
                folder_row, text=f"{title}:", font=("Segoe UI", 10, "bold"),
                fg=TEXT_FG, bg=PANEL_BG, width=16, anchor="w",
            ).pack(side="left", padx=(14, 8), pady=10)
            tk.Label(
                folder_row, textvariable=var, font=("Consolas", 10),
                fg=MUTED_FG, bg=PANEL_BG, anchor="w",
            ).pack(side="left", fill="x", expand=True, pady=10)
            _create_btn(folder_row, text="Pilih...", command=chooser, side="right", padx=(0, 12), pady=6)

        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Left: input
        left_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, width=440)
        left_panel.pack(side="left", fill="both", expand=False, padx=(0, 12))
        left_panel.pack_propagate(False)

        left_header = tk.Frame(left_panel, bg=PANEL_BG)
        left_header.pack(fill="x", padx=16, pady=(16, 10))
        accent_bar = tk.Frame(left_header, bg=ACCENT, width=4, height=20)
        accent_bar.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            left_header, text="Daftar Game Pesanan", font=("Segoe UI", 13, "bold"),
            fg="#ffffff", bg=PANEL_BG,
        ).pack(side="left")

        # Pull a saved order list straight in, so "is Cust 4's HDD complete?"
        # is two clicks: their slot, then Scan against their drive.
        tk.Label(
            left_panel, text="AMBIL DARI DAFTAR PESANAN", font=("Segoe UI", 8, "bold"),
            fg=MUTED_FG, bg=PANEL_BG, anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        slot_row = tk.Frame(left_panel, bg=PANEL_BG)
        slot_row.pack(fill="x", padx=16, pady=(0, 10))
        for column in range(3):
            slot_row.columnconfigure(column, weight=1)
        for i, (key, label) in enumerate(game_settings.LIST_DEFS):
            btn = tk.Button(
                slot_row, text=label, command=lambda k=key: self._load_order_slot(k),
                bg=PANEL_ALT, fg=TEXT_FG, activebackground=ACCENT, activeforeground="#ffffff",
                font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                padx=6, pady=7, cursor="hand2", highlightthickness=0,
            )
            btn.grid(row=i // 3, column=i % 3, sticky="we", padx=2, pady=2)

        btn_row = tk.Frame(left_panel, bg=PANEL_BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 10))
        _create_btn(btn_row, text="Paste Clipboard", command=self._paste_clipboard, side="left")
        _create_btn(btn_row, text="Load Sample", command=self._load_sample, side="left", padx=(8, 0))
        _create_btn(btn_row, text="Clear", command=self._clear_input, side="right")

        # Packed bottom-first: the expanding text box below would otherwise
        # squeeze the scan button off the panel.
        _create_btn(
            left_panel, text="🔍  SCAN SEKARANG", command=self._scan_clicked, style_type="accent",
            side="bottom", fill="x", padx=16, pady=(0, 16),
        )

        text_frame = tk.Frame(left_panel, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        text_scroll.pack(side="right", fill="y")
        self.input_text = tk.Text(
            text_frame, wrap="word", yscrollcommand=text_scroll.set,
            bg=TEXT_BG, fg=TEXT_FG, insertbackground="#ffffff", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
            font=("Consolas", 11), padx=8, pady=8,
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=self.input_text.yview)

        # Right: results
        right_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        right_panel.pack(side="right", fill="both", expand=True)

        right_header = tk.Frame(right_panel, bg=PANEL_BG)
        right_header.pack(fill="x", padx=16, pady=(16, 10))
        accent_bar2 = tk.Frame(right_header, bg=ACCENT_PINK, width=4, height=20)
        accent_bar2.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            right_header, text="Hasil Scan", font=("Segoe UI", 13, "bold"),
            fg="#ffffff", bg=PANEL_BG,
        ).pack(side="left")
        self._summary_label = tk.Label(
            right_header, text="Belum ada hasil scan", font=("Segoe UI", 10, "bold"), fg=MUTED_FG, bg=PANEL_BG,
        )
        self._summary_label.pack(side="right")

        table_frame = tk.Frame(right_panel, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Scanner.Treeview", background=TEXT_BG, fieldbackground=TEXT_BG, foreground=TEXT_FG,
                         borderwidth=0, rowheight=32, font=("Segoe UI", 10))
        style.configure("Scanner.Treeview.Heading", background="#1e293b", foreground="#f8fafc",
                         relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Scanner.Treeview", background=[("selected", "#4f46e5")], foreground=[("selected", "#ffffff")])

        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        tree_scroll.pack(side="right", fill="y")

        self.result_tree = ttk.Treeview(
            table_frame, columns=("no", "title", "status", "match"),
            show="headings", yscrollcommand=tree_scroll.set, style="Scanner.Treeview",
        )
        self.result_tree.heading("no", text="No")
        self.result_tree.heading("title", text="Judul Pesanan")
        self.result_tree.heading("status", text="Status")
        self.result_tree.heading("match", text="Folder yang Cocok")
        self.result_tree.column("no", width=44, anchor="center")
        self.result_tree.column("title", width=300, anchor="w")
        self.result_tree.column("status", width=170, anchor="w")
        self.result_tree.column("match", width=300, anchor="w")
        self.result_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.config(command=self.result_tree.yview)

        self.result_tree.tag_configure("found", foreground="#6ee7b7")
        self.result_tree.tag_configure("fuzzy", foreground="#fcd34d")
        self.result_tree.tag_configure("missing", foreground="#f87171")

        action_row = tk.Frame(right_panel, bg=PANEL_BG)
        action_row.pack(fill="x", padx=16, pady=(0, 16))
        _create_btn(
            action_row, text="📋 Copy yang Belum Ada", command=self._copy_missing,
            style_type="accent_pink", side="left",
        )
        _create_btn(
            action_row, text="Copy Semua Hasil", command=self._copy_all,
            side="left", padx=(8, 0),
        )

    def _choose_folder(self) -> None:
        self._pick_into(self._target_folder, "Pilih folder / HDD customer yang mau di-scan")

    def _choose_folder_2(self) -> None:
        self._pick_into(self._target_folder_2, "Pilih folder HDD eksternal yang ikut di-scan")

    def _pick_into(self, var: tk.StringVar, title: str) -> None:
        initial = var.get() or "D:\\"
        chosen = filedialog.askdirectory(
            title=title, initialdir=initial if os.path.isdir(initial) else "D:\\",
        )
        if chosen:
            var.set(chosen)

    def load_order_text(self, text: str) -> None:
        """Drop an order list into the input (used by the launcher's
        'Cek HDD Cust' shortcut)."""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)
        self._clear_results()

    def _load_order_slot(self, key: str) -> None:
        """Load one saved customer slot. Settings are re-read from disk so the
        slot reflects edits made on the downloader tab in this same session."""
        text = (game_settings.load_settings().get("order_lists", {}) or {}).get(key, "")
        if not text.strip():
            messagebox.showinfo("Daftar Kosong", f"Slot '{dict(game_settings.LIST_DEFS)[key]}' masih kosong.")
            return
        self.load_order_text(text)

    def _paste_clipboard(self) -> None:
        try:
            text = pyperclip.paste()
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", text)
        except Exception as exc:
            messagebox.showerror("Error", f"Gagal paste clipboard: {exc}")

    def _load_sample(self) -> None:
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", SAMPLE_TEXT)

    def _clear_input(self) -> None:
        self.input_text.delete("1.0", "end")
        self._clear_results()

    def _clear_results(self) -> None:
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._results = []
        self._summary_label.config(text="Belum ada hasil scan", fg=MUTED_FG)

    def _scan_clicked(self) -> None:
        folders = [
            f for f in (self._target_folder.get().strip(), self._target_folder_2.get().strip())
            if f and os.path.isdir(f)
        ]
        if not folders:
            messagebox.showwarning("Folder Belum Dipilih", "Pilih minimal satu folder yang valid dulu sebelum scan.")
            return

        titles = parse_order_list(self.input_text.get("1.0", "end-1c"))
        if not titles:
            messagebox.showwarning("Daftar Kosong", "Paste daftar game dengan format '1. Judul Game' dulu.")
            return

        self._clear_results()
        self._summary_label.config(text="Sedang scan...", fg=ACCENT)

        def worker() -> None:
            index = folder_scan.scan_extracted_folders(folders)
            results = [(title, folder_scan.match_title(title, index, {}, threshold=0.72)) for title in titles]
            self.after(0, lambda: self._render_results(results))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _match_label(match: folder_scan.MatchResult) -> str:
        """Folder name plus its drive, so a hit on the external HDD is
        distinguishable from one in the local games folder."""
        label = match.matched_label or "-"
        drive = os.path.splitdrive(match.matched_path or "")[0]
        return f"{label}   [{drive}]" if drive else label

    def _render_results(self, results: list[tuple[str, folder_scan.MatchResult]]) -> None:
        self._results = results
        found = 0
        fuzzy = 0

        for i, (title, match) in enumerate(results, 1):
            if match.status == folder_scan.STATUS_NOT_FOUND:
                status_text, tag, match_label = "❌ TIDAK ADA", "missing", "-"
            elif match.is_exact:
                status_text, tag, match_label = "✅ ADA", "found", self._match_label(match)
                found += 1
            else:
                pct = int(round(match.confidence * 100))
                status_text, tag, match_label = f"🟡 MIRIP {pct}%", "fuzzy", self._match_label(match)
                fuzzy += 1

            self.result_tree.insert("", "end", values=(i, title, status_text, match_label), tags=(tag,))

        missing = len(results) - found - fuzzy
        self._summary_label.config(
            text=f"✅ {found} ADA   🟡 {fuzzy} MIRIP   ❌ {missing} TIDAK ADA   (dari {len(results)} game)",
            fg=TEXT_FG,
        )

    def _copy_missing(self) -> None:
        if not self._results:
            return
        missing_titles = [
            title for title, match in self._results
            if match.status == folder_scan.STATUS_NOT_FOUND
        ]
        if not missing_titles:
            messagebox.showinfo("Tidak Ada", "Semua game sudah ada di folder ini.")
            return
        lines = [f"{i}. {title}" for i, title in enumerate(missing_titles, 1)]
        pyperclip.copy("\n".join(lines))
        messagebox.showinfo("Tersalin", f"{len(missing_titles)} judul yang belum ada disalin ke clipboard.")

    def _copy_all(self) -> None:
        if not self._results:
            return
        lines = []
        for i, (title, match) in enumerate(self._results, 1):
            if match.status == folder_scan.STATUS_NOT_FOUND:
                status = "TIDAK ADA"
            elif match.is_exact:
                status = "ADA"
            else:
                status = f"MIRIP {int(round(match.confidence * 100))}%"
            lines.append(f"{i}. {title} -> {status}")
        pyperclip.copy("\n".join(lines))
        messagebox.showinfo("Tersalin", "Hasil scan disalin ke clipboard.")


class GameStatusScanner(tk.Tk):
    """Standalone window wrapper around GameStatusScannerPanel."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Cek Status Game - Scanning Folder")
        self.geometry("1200x720")
        self.minsize(960, 600)
        self.configure(bg=APP_BG)

        header = tk.Frame(self, bg=APP_BG)
        header.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(
            header, text="CEK STATUS GAME", font=("Segoe UI", 22, "bold"),
            fg=ACCENT, bg=APP_BG,
        ).pack(anchor="center")
        tk.Label(
            header, text="Scan folder mana pun untuk cek game yang sudah ada / belum ada",
            font=("Segoe UI", 9), fg=MUTED_FG, bg=APP_BG,
        ).pack(anchor="center", pady=(2, 0))

        panel = GameStatusScannerPanel(self)
        panel.pack(fill="both", expand=True)


if __name__ == "__main__":
    app = GameStatusScanner()
    app.mainloop()
