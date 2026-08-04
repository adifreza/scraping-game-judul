import os
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
import pyperclip

from game_scraper_multi_site import open_game_search_tabs
import game_folder_scan as folder_scan
import game_settings
import game_extraction
import game_copy
import game_status_scanner


APP_BG = "#090d16"      # Deep Midnight Black
PANEL_BG = "#151c2c"    # Card/Panel Slate Blue/Gray
TEXT_BG = "#0c101b"     # Input/Listbox/Table Deep Navy Black
ACCENT = "#6366f1"      # Primary Indigo Accent
ACCENT_PINK = "#db2777" # Pink Accent for start/highlight
TEXT_FG = "#f1f5f9"     # Clean White/Slate 100
MUTED_FG = "#94a3b8"    # Muted Gray/Slate 400
BORDER_COLOR = "#334155" # Subtle border color

STATUS_COLORS = {
    "extracted": "#6ee7b7",
    "downloaded": "#fcd34d",
    "fuzzy": "#fb923c",
    "none": TEXT_FG,
}

SAMPLE_TEXT = """Daftar Game Pesanan

1. WRC 10 FIA World Rally Championship
2. Forza Horizon 4
3. Forza Horizon 3
4. Forza Horizon 2 (XBOX 360 Classics)
5. Battlefield 6 (Campaign | v1.1.2.0)
6. Super Mario Odyssey
7. Zombie Army 4: Dead War
8. Super Smash Bros. Ultimate
9. Ready or Not
10. Bodycam
11. Grand Theft Auto V Enhanced
12. Cyberpunk 2077
13. PC Building Simulator 2
14. Farming Simulator 25
15. FIFA 23 Ultimate Edition
16. Assetto Corsa
17. Riders Republic
18. Minecraft
19. Call of Duty: Modern Warfare 2

Total Size: 937.6 GB"""


class GameLauncherMultiSite(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WD Games")
        self.geometry("1500x860")
        self.minsize(1200, 680)
        self.state("zoomed")

        self._worker_thread: threading.Thread | None = None
        self._pause_event: threading.Event | None = None
        self._parsed_games: list[tuple[str, str]] = []  # (game_name, site_type)
        self._filtered_games: list[tuple[str, str]] = []
        self._resolved_rows: list[dict[str, str | None]] = []

        self._settings = game_settings.load_settings()
        self._match_map: dict[str, folder_scan.MatchResult] = {}
        self._match_decisions: dict[str, str] = {}  # name -> "confirmed" | "rejected"
        self._copy_queue: list[tuple[str, str]] = []
        self._copy_dest_root: str = ""
        self._tree_item_map: dict[str, tuple[str, str]] = {}  # treeview iid -> (name, site)

        self._configure_theme()
        self._build_ui()
        self._load_initial_text()
        self.bind_all("<Control-Return>", lambda event: self._start_all())

    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Scrollbar Styling
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background="#334155",
            troughcolor=TEXT_BG,
            bordercolor=TEXT_BG,
            darkcolor=TEXT_BG,
            lightcolor=TEXT_BG,
            arrowsize=0,
            borderwidth=0,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#475569")],
        )

        # Treeview Styling
        style.configure(
            "Treeview",
            background=TEXT_BG,
            fieldbackground=TEXT_BG,
            foreground=TEXT_FG,
            borderwidth=0,
            rowheight=34,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#1e293b",
            foreground="#f8fafc",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#4f46e5")],
            foreground=[("selected", "#ffffff")],
        )

    def _create_btn(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        style_type: str = "normal",
        **pack_kwargs
    ) -> tk.Button:
        if style_type == "accent":
            bg = ACCENT
            fg = "#ffffff"
            active_bg = "#4f46e5"
        elif style_type == "accent_pink":
            bg = ACCENT_PINK
            fg = "#ffffff"
            active_bg = "#be185d"
        else:
            bg = "#1e293b"
            fg = "#f1f5f9"
            active_bg = "#334155"

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
        )

        # Hover colors
        btn.bind("<Enter>", lambda e: btn.config(bg=active_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))

        if pack_kwargs:
            btn.pack(**pack_kwargs)
        return btn

    # ------------------------------------------------------------------
    # Top-level layout: header, tab bar, two swappable tab frames
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.configure(bg=APP_BG)

        self._build_top_bar()

        # Two swappable full-size tab frames, sharing the same parent/region.
        self._downloader_tab = tk.Frame(self, bg=APP_BG)
        self._build_downloader_tab(self._downloader_tab)

        self._scanner_tab = tk.Frame(self, bg=APP_BG)
        self._scanner_panel = game_status_scanner.GameStatusScannerPanel(
            self._scanner_tab, default_folder=self._settings.get("extracted_root", "")
        )
        self._scanner_panel.pack(fill="both", expand=True)

        self._switch_tab("downloader")

    def _build_top_bar(self) -> None:
        """Compact single-row header: wordmark + tabs together, so the tab
        content below keeps as much vertical room as possible."""
        top_bar = tk.Frame(self, bg=APP_BG)
        top_bar.pack(fill="x", padx=24, pady=(12, 0))

        brand = tk.Frame(top_bar, bg=APP_BG)
        brand.pack(side="left")
        tk.Label(
            brand, text="🎮 WD GAMES", font=("Segoe UI", 16, "bold"), fg=ACCENT, bg=APP_BG,
        ).pack(side="left")
        tk.Label(
            brand, text="  scraping • status • extract • copy",
            font=("Segoe UI", 8), fg=MUTED_FG, bg=APP_BG,
        ).pack(side="left")

        tab_bar = tk.Frame(top_bar, bg=APP_BG)
        tab_bar.pack(side="right")

        self._tab_buttons: dict[str, tk.Button] = {}
        tabs = [
            ("downloader", "📥  Downloader"),
            ("scanner", "🔍  Cek Status Game"),
        ]
        for key, label in tabs:
            btn = tk.Button(
                tab_bar, text=label, command=lambda k=key: self._switch_tab(k),
                font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                padx=18, pady=8, cursor="hand2",
            )
            btn.pack(side="left", padx=(4, 0))

            def on_enter(_e, b=btn, k=key):
                if self._current_tab != k:
                    b.config(bg="#1e293b")

            def on_leave(_e, b=btn, k=key):
                if self._current_tab != k:
                    b.config(bg=PANEL_BG)

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            self._tab_buttons[key] = btn

        underline = tk.Frame(self, bg=BORDER_COLOR, height=1)
        underline.pack(fill="x", padx=24, pady=(10, 10))

    def _switch_tab(self, key: str) -> None:
        self._current_tab = key
        for tab_key, btn in self._tab_buttons.items():
            active = tab_key == key
            btn.config(
                bg=ACCENT if active else PANEL_BG,
                fg="#ffffff" if active else MUTED_FG,
            )

        if key == "downloader":
            self._scanner_tab.pack_forget()
            self._downloader_tab.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        else:
            self._downloader_tab.pack_forget()
            self._scanner_tab.pack(fill="both", expand=True, padx=24, pady=(0, 12))

    # ------------------------------------------------------------------
    # Downloader tab
    # ------------------------------------------------------------------

    def _build_downloader_tab(self, body: tk.Frame) -> None:
        # Left Panel - Input
        left_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        left_panel.pack(side="left", fill="both", expand=False, padx=(0, 12))
        left_panel.configure(width=460)
        left_panel.pack_propagate(False)

        left_header = tk.Frame(left_panel, bg=PANEL_BG)
        left_header.pack(fill="x", padx=16, pady=(16, 8))

        left_title_bar = tk.Frame(left_header, bg=PANEL_BG)
        left_title_bar.pack(anchor="w")
        accent_strip_left = tk.Frame(left_title_bar, bg=ACCENT, width=4, height=18)
        accent_strip_left.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            left_title_bar,
            text="Paste Daftar Game",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=PANEL_BG,
        ).pack(side="left")

        button_row = tk.Frame(left_header, bg=PANEL_BG)
        button_row.pack(fill="x", pady=(12, 0))

        self._create_btn(button_row, text="📋 Parse Text", command=self._parse_text, style_type="accent", side="left")
        self._create_btn(button_row, text="📥 Paste", command=self._paste_clipboard, side="left", padx=(8, 0))
        self._create_btn(button_row, text="🔄 Auto Load", command=self._load_initial_text, side="left", padx=(8, 0))

        button_row2 = tk.Frame(left_header, bg=PANEL_BG)
        button_row2.pack(fill="x", pady=(8, 0))
        self._create_btn(button_row2, text="🎲 Sample", command=self._load_sample, side="left")
        self._create_btn(button_row2, text="🔍 Scan Ulang", command=self._rescan_button_clicked, side="left", padx=(8, 0))
        self._create_btn(button_row2, text="🧹 Clear", command=self._clear_inputs, side="right")

        text_frame = tk.Frame(left_panel, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        text_scroll.pack(side="right", fill="y")

        self.input_text = tk.Text(
            text_frame,
            wrap="word",
            yscrollcommand=text_scroll.set,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            font=("Consolas", 11),
            padx=10,
            pady=10,
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=self.input_text.yview)

        # Right Panel - Game Table & Controls
        right_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        right_panel.pack(side="right", fill="both", expand=True)

        right_header = tk.Frame(right_panel, bg=PANEL_BG)
        right_header.pack(side="top", fill="x", padx=16, pady=(16, 8))

        right_title_bar = tk.Frame(right_header, bg=PANEL_BG)
        right_title_bar.pack(anchor="w")
        accent_strip_right = tk.Frame(right_title_bar, bg=ACCENT, width=4, height=18)
        accent_strip_right.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            right_title_bar,
            text="Daftar Game & Status Download",
            font=("Segoe UI", 13, "bold"),
            fg="#ffffff",
            bg=PANEL_BG,
        ).pack(side="left")

        tk.Label(
            right_header, text="Klik kanan pada baris game untuk Konfirmasi/Tolak match atau Tandai Manual",
            font=("Segoe UI", 8), fg=MUTED_FG, bg=PANEL_BG,
        ).pack(anchor="w", pady=(2, 0))

        # Pack bottom elements first (from bottom to top) so they never get squeezed out.
        # Kept to just 2 compact toolbar rows so the game table above keeps the most room
        # even on smaller/laptop screens.

        # Row 1 (bottom-most): secondary/utility actions, small icon-style buttons
        utility_frame = tk.Frame(right_panel, bg=PANEL_BG)
        utility_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
        self._create_btn(utility_frame, text="⚙ Settings", command=self._open_settings_dialog, side="right")
        self._create_btn(utility_frame, text="✕ Tutup Steamrip", command=self._close_steamrip_windows, side="right", padx=(0, 6))
        self._create_btn(utility_frame, text="📋 Copy Link", command=self._copy_selected_result, side="right", padx=(0, 6))
        self._create_btn(utility_frame, text="🌐 Open Link", command=self._open_selected_result, side="right", padx=(0, 6))
        self._create_btn(utility_frame, text="🌐 Romsfun", command=self._open_all_romsfun_downloads, side="left")
        self._create_btn(utility_frame, text="🌐 Steamrip", command=self._open_all_steamrip_downloads, side="left", padx=(6, 0))

        # Row 2: the actions that matter most - download, extract, copy
        primary_frame = tk.Frame(right_panel, bg=PANEL_BG)
        primary_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 6))
        self._create_btn(
            primary_frame, text="▶ Start Selected", command=self._start_selected,
            style_type="accent", side="left", fill="x", expand=True,
        )
        self._create_btn(
            primary_frame, text="⚡ Run All", command=self._start_all,
            style_type="accent_pink", side="left", fill="x", expand=True, padx=(6, 0),
        )
        self._create_btn(
            primary_frame, text="📦 Ekstrak Semua", command=self._extract_all_clicked,
            style_type="accent_pink", side="left", fill="x", expand=True, padx=(6, 0),
        )
        self._create_btn(
            primary_frame, text="💾 Copy to HDD", command=self._copy_to_hdd_clicked,
            style_type="accent_pink", side="left", fill="x", expand=True, padx=(6, 0),
        )

        divider = tk.Frame(right_panel, bg=BORDER_COLOR, height=1)
        divider.pack(side="bottom", fill="x", padx=16, pady=(0, 6))

        # Status log
        status_frame = tk.Frame(right_panel, bg=PANEL_BG)
        status_frame.pack(side="bottom", fill="both", expand=False, padx=16, pady=(0, 6))

        status_title_bar = tk.Frame(status_frame, bg=PANEL_BG)
        status_title_bar.pack(anchor="w", pady=(0, 4))
        accent_strip_status = tk.Frame(status_title_bar, bg=ACCENT, width=4, height=16)
        accent_strip_status.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            status_title_bar, text="Status Log", font=("Segoe UI", 10, "bold"), fg=TEXT_FG, bg=PANEL_BG,
        ).pack(side="left")

        status_text_frame = tk.Frame(status_frame, bg=PANEL_BG)
        status_text_frame.pack(fill="both", expand=True)
        status_scroll = ttk.Scrollbar(status_text_frame, orient="vertical")
        status_scroll.pack(side="right", fill="y")

        self.status_text = tk.Text(
            status_text_frame,
            height=4,
            wrap="word",
            yscrollcommand=status_scroll.set,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            font=("Consolas", 10),
            padx=8,
            pady=8,
        )
        self.status_text.pack(side="left", fill="both", expand=True)
        status_scroll.config(command=self.status_text.yview)

        # Resolved host links table
        result_frame = tk.Frame(right_panel, bg=PANEL_BG)
        result_frame.pack(side="bottom", fill="both", expand=False, padx=16, pady=(0, 6))

        table_title_bar = tk.Frame(result_frame, bg=PANEL_BG)
        table_title_bar.pack(anchor="w", pady=(0, 4))
        accent_strip_table = tk.Frame(table_title_bar, bg=ACCENT_PINK, width=4, height=16)
        accent_strip_table.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            table_title_bar, text="Resolved Host Links", font=("Segoe UI", 10, "bold"), fg=TEXT_FG, bg=PANEL_BG,
        ).pack(side="left")

        result_table_frame = tk.Frame(result_frame, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        result_table_frame.pack(fill="both", expand=True)

        result_scroll = ttk.Scrollbar(result_table_frame, orient="vertical")
        result_scroll.pack(side="right", fill="y")

        self.result_tree = ttk.Treeview(
            result_table_frame,
            columns=("game", "site", "host", "link"),
            show="headings",
            height=2,
            yscrollcommand=result_scroll.set,
        )
        self.result_tree.heading("game", text="Game")
        self.result_tree.heading("site", text="Site")
        self.result_tree.heading("host", text="Host")
        self.result_tree.heading("link", text="Link")
        self.result_tree.column("game", width=220, anchor="w")
        self.result_tree.column("site", width=80, anchor="center")
        self.result_tree.column("host", width=120, anchor="center")
        self.result_tree.column("link", width=380, anchor="w")
        self.result_tree.pack(side="left", fill="both", expand=True)
        result_scroll.config(command=self.result_tree.yview)
        self.result_tree.bind("<<TreeviewSelect>>", lambda event: None)
        self.result_tree.bind("<Double-1>", lambda event: self._open_selected_result())

        # Filter + selection controls, single compact row (top)
        filter_frame = tk.Frame(right_panel, bg=PANEL_BG)
        filter_frame.pack(side="top", fill="x", padx=16, pady=(0, 6))

        tk.Label(
            filter_frame, text="Filter:", font=("Segoe UI", 10), fg=TEXT_FG, bg=PANEL_BG,
        ).pack(side="left")

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *args: self._apply_filter())
        filter_entry = tk.Entry(
            filter_frame,
            textvariable=self.filter_var,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            font=("Segoe UI", 10),
        )
        filter_entry.pack(side="left", fill="x", expand=True, padx=(8, 10))

        self._create_btn(filter_frame, text="Select All", command=self._select_all, side="left")
        self._create_btn(filter_frame, text="Deselect All", command=self._deselect_all, side="left", padx=(6, 0))

        self.counter_label = tk.Label(
            filter_frame, text="Selected: 0/0", font=("Segoe UI", 9, "bold"), fg=ACCENT_PINK, bg=PANEL_BG,
        )
        self.counter_label.pack(side="right", padx=(8, 0))

        # Game table - the main upgrade: a real, readable, sortable-by-eye table
        # instead of tiny badges crammed into a custom row widget. This gets
        # whatever vertical space is left after the compact rows above/below it.
        table_frame = tk.Frame(
            right_panel, bg=TEXT_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0,
        )
        table_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 8))

        game_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        game_scroll.pack(side="right", fill="y")

        self.game_tree = ttk.Treeview(
            table_frame,
            columns=("site", "title", "status", "info"),
            show="headings",
            selectmode="extended",
            yscrollcommand=game_scroll.set,
        )
        self.game_tree.heading("site", text="Site")
        self.game_tree.heading("title", text="Judul Game")
        self.game_tree.heading("status", text="Status")
        self.game_tree.heading("info", text="Info Folder/File Cocok")
        self.game_tree.column("site", width=90, anchor="center")
        self.game_tree.column("title", width=340, anchor="w")
        self.game_tree.column("status", width=190, anchor="w")
        self.game_tree.column("info", width=280, anchor="w")
        self.game_tree.pack(side="left", fill="both", expand=True)
        game_scroll.config(command=self.game_tree.yview)

        for tag, color in STATUS_COLORS.items():
            self.game_tree.tag_configure(tag, foreground=color)

        self.game_tree.bind("<<TreeviewSelect>>", lambda event: self._update_counter())
        self.game_tree.bind("<Button-3>", self._show_game_context_menu)

    # ------------------------------------------------------------------
    # Existing behavior (scraping / parsing / results), largely unchanged
    # ------------------------------------------------------------------

    def _close_steamrip_windows(self) -> None:
        """Close all Brave windows that contain Steamrip tabs"""
        try:
            import subprocess
            cmd = (
                'powershell -Command "'
                'Get-Process brave -ErrorAction SilentlyContinue | '
                'Where-Object { $_.MainWindowTitle -like \'*steamrip*\' } | '
                'ForEach-Object { $_.CloseMainWindow() }'
                '"'
            )
            subprocess.run(cmd, shell=True)
            self._log("ℹ Sent close command to Steamrip Brave windows.")
        except Exception as e:
            self._log(f"✗ Failed to close Steamrip windows: {str(e)}")

    def _normalize_parsed_title(self, title: str) -> str:
        """Parse and normalize game title from list"""
        title = re.sub(r"^\d+\.\s+", "", title)
        title = re.sub(r"\s*\(PS2\)\s*", "", title)
        for dash in ("-", "–", "—"):
            title = title.replace(dash, " ")
        for apostrophe in ("'", "'"):
            title = title.replace(apostrophe, "")
        title = re.sub(r"\s+", " ", title)
        return title.strip()

    def _parse_game_text(self) -> list[tuple[str, str]]:
        """Parse game text and determine site type based on tags"""
        text = self.input_text.get("1.0", "end-1c")
        if not text.strip():
            return []

        games: list[tuple[str, str]] = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or not re.match(r"^\d+\.", line):
                continue

            is_ps2 = "(PS2)" in line
            title = self._normalize_parsed_title(line)
            if title:
                site_type = "romsfun" if is_ps2 else "steamrip"
                games.append((title, site_type))

        return games

    # ------------------------------------------------------------------
    # Folder-scan status checking (no database - live filesystem check)
    # ------------------------------------------------------------------

    def _rescan_and_match(self) -> None:
        """Re-scan the extracted (D:) and downloads (C:) folders and recompute
        status for every currently parsed game. Pure live filesystem check -
        no database, nothing persisted across runs."""
        extracted_index = folder_scan.scan_extracted_folder(self._settings.get("extracted_root", ""))
        downloads_index = folder_scan.scan_downloads_folder(
            self._settings.get("downloads_folder", ""),
            self._settings.get("release_suffixes"),
        )
        threshold = self._settings.get("fuzzy_threshold", 0.72)

        self._match_map = {
            name: folder_scan.match_title(name, extracted_index, downloads_index, threshold)
            for name, _site in self._parsed_games
        }

        extracted_count = sum(1 for m in self._match_map.values() if m.status == folder_scan.STATUS_EXTRACTED)
        downloaded_count = sum(1 for m in self._match_map.values() if m.status == folder_scan.STATUS_DOWNLOADED)
        not_found_count = len(self._match_map) - extracted_count - downloaded_count
        self._log(
            f"ℹ Scan folder: {extracted_count} sudah diekstrak, "
            f"{downloaded_count} sudah didownload (belum diekstrak), "
            f"{not_found_count} belum ada."
        )

    def _rescan_button_clicked(self) -> None:
        """Manual 'Scan Ulang' trigger - re-check folders without re-parsing text."""
        if not self._parsed_games:
            messagebox.showinfo("Belum Ada Daftar", "Parse daftar game dulu sebelum scan.")
            return
        self._rescan_and_match()
        self._apply_filter()

    def _confirm_match(self, name: str) -> None:
        """User confirms a fuzzy match really is the same game."""
        self._match_decisions[name] = "confirmed"
        self._apply_filter()

    def _reject_match(self, name: str) -> None:
        """User rejects a fuzzy match - treat this title as a fresh download."""
        self._match_decisions[name] = "rejected"
        self._apply_filter()

    def _reset_decision(self, name: str) -> None:
        """Clear a previous confirm/reject decision for one title."""
        self._match_decisions.pop(name, None)
        self._apply_filter()

    def _manual_match(self, name: str) -> None:
        """Manually link a title to a folder when auto-matching can't find it
        (e.g. a folder renamed far from the original title, like 'GTA4' for
        'Grand Theft Auto IV')."""
        initial_dir = self._settings.get("extracted_root") or "D:\\"
        chosen = filedialog.askdirectory(
            title=f"Pilih folder untuk: {name}",
            initialdir=initial_dir if os.path.isdir(initial_dir) else "D:\\",
        )
        if not chosen:
            return
        label = os.path.basename(chosen.rstrip("/\\")) or chosen
        self._match_map[name] = folder_scan.MatchResult(
            status=folder_scan.STATUS_EXTRACTED,
            matched_path=chosen,
            matched_label=label,
            confidence=1.0,
            is_exact=True,
        )
        self._match_decisions[name] = "confirmed"
        self._log(f"✓ Ditandai manual: '{name}' -> {chosen}")
        self._apply_filter()

    def _show_game_context_menu(self, event: tk.Event) -> None:
        """Right-click menu on the game table: Confirm/Reject a fuzzy match,
        or manually link a title to a folder."""
        iid = self.game_tree.identify_row(event.y)
        if not iid:
            return
        self.game_tree.selection_set(iid)
        name, _site = self._tree_item_map.get(iid, (None, None))
        if name is None:
            return

        match = self._match_map.get(name)
        decision = self._match_decisions.get(name)

        menu = tk.Menu(
            self, tearoff=0, bg="#1e293b", fg=TEXT_FG,
            activebackground=ACCENT, activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 9),
        )

        if match and match.status != folder_scan.STATUS_NOT_FOUND and not match.is_exact and decision != "rejected":
            menu.add_command(label="✓ Konfirmasi Match", command=lambda n=name: self._confirm_match(n))
            menu.add_command(label="✗ Tolak Match", command=lambda n=name: self._reject_match(n))
            menu.add_separator()

        menu.add_command(label="📁 Tandai Manual...", command=lambda n=name: self._manual_match(n))

        if decision is not None:
            menu.add_command(label="↺ Reset Keputusan", command=lambda n=name: self._reset_decision(n))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _refresh_after_background_change(self) -> None:
        """Re-scan folders and repaint the table after extraction/copy finished,
        without popping the 'no list parsed' warning the manual button uses."""
        if self._parsed_games:
            self._rescan_and_match()
            self._apply_filter()

    # ------------------------------------------------------------------
    # Extraction / copy automation
    # ------------------------------------------------------------------

    def _extract_all_clicked(self) -> None:
        """Batch-extract every archive currently in the downloads folder."""
        unrar_path = self._settings.get("unrar_path") or game_extraction.find_unrar_exe()
        if not unrar_path:
            messagebox.showerror(
                "UnRAR Tidak Ditemukan",
                "UnRAR.exe tidak ditemukan otomatis. Install WinRAR, atau atur path-nya manual di Settings.",
            )
            return

        downloads_folder = self._settings.get("downloads_folder", "")
        extracted_root = self._settings.get("extracted_root", "")
        if not messagebox.askyesno(
            "Ekstrak Semua",
            f"Ekstrak semua file arsip di:\n{downloads_folder}\n\n"
            f"ke folder:\n{extracted_root}\n\n"
            "File rar sumber akan DIHAPUS otomatis setelah berhasil diekstrak.\n"
            "Lanjutkan?",
        ):
            return

        name_hints = folder_scan.build_name_hints(self._match_map, self._settings.get("release_suffixes"))

        def worker() -> None:
            def log_line(msg: str) -> None:
                self.after(0, lambda: self._log(msg))

            game_extraction.extract_all_downloads(
                downloads_folder=downloads_folder,
                extracted_root=extracted_root,
                unrar_path=unrar_path,
                release_suffixes=self._settings.get("release_suffixes"),
                delete_source_on_success=True,
                name_hints=name_hints,
                log_fn=log_line,
            )
            self.after(0, self._refresh_after_background_change)

        threading.Thread(target=worker, daemon=True).start()

    def _copy_to_hdd_clicked(self) -> None:
        """Copy extracted game folder(s) to a customer HDD via robocopy.
        Uses the currently selected rows (if any) whose status is already
        'extracted'; otherwise falls back to letting the user pick one
        source folder directly."""
        sources: list[tuple[str, str]] = []
        for iid in self.game_tree.selection():
            name, _site = self._tree_item_map.get(iid, (None, None))
            if name is None:
                continue
            match = self._match_map.get(name)
            if match and match.status == folder_scan.STATUS_EXTRACTED and match.matched_path:
                sources.append((name, match.matched_path))

        if not sources:
            initial = self._settings.get("extracted_root") or "D:\\"
            chosen = filedialog.askdirectory(
                title="Pilih folder game hasil ekstrak yang mau di-copy",
                initialdir=initial if os.path.isdir(initial) else "D:\\",
            )
            if not chosen:
                return
            sources.append((os.path.basename(chosen.rstrip("/\\")) or chosen, chosen))

        dest_root = filedialog.askdirectory(
            title="Pilih folder tujuan di HDD customer",
            initialdir=self._settings.get("customer_hdd_target") or "",
        )
        if not dest_root:
            return

        self._settings["customer_hdd_target"] = dest_root
        game_settings.save_settings(self._settings)

        self._copy_queue = sources
        self._copy_dest_root = dest_root
        self._log(f"▶ Mulai copy {len(sources)} folder ke {dest_root}")
        self._run_next_copy()

    def _run_next_copy(self) -> None:
        """Pop and run the next queued copy job; chains itself via on_done
        so multiple selected games copy one after another."""
        if not self._copy_queue:
            self._log("✓ Semua copy selesai.")
            return

        label, src = self._copy_queue.pop(0)
        dest_dir = os.path.join(self._copy_dest_root, os.path.basename(src.rstrip("/\\")))
        log_path = game_copy.default_log_path(label)
        self._log(f"⏳ Copy: {label} -> {dest_dir}")

        def log_line(line: str, item_label: str = label) -> None:
            self.after(0, lambda: self._log(f"[{item_label}] {line}"))

        def on_done(result: game_copy.CopyResult, item_label: str = label) -> None:
            def finish() -> None:
                if result.success:
                    self._log(f"✓ Copy sukses: {item_label}")
                else:
                    self._log(f"✗ Copy gagal: {item_label} (code={result.return_code} {result.error or ''})")
                self._run_next_copy()
            self.after(0, finish)

        game_copy.run_copy(src, dest_dir, log_path, log_fn=log_line, on_done=on_done)

    def _open_settings_dialog(self) -> None:
        """Small preferences dialog: folder paths + fuzzy threshold. Not a
        game database - just the 2-3 paths the scan/extract/copy features need."""
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.configure(bg=PANEL_BG)
        dialog.geometry("600x340")
        dialog.transient(self)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)

        fields: dict[str, tk.StringVar] = {}

        def add_path_field(row: int, label_text: str, key: str, is_file: bool = False) -> None:
            tk.Label(
                dialog, text=label_text, font=("Segoe UI", 9, "bold"),
                fg=TEXT_FG, bg=PANEL_BG,
            ).grid(row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 0))

            var = tk.StringVar(value=self._settings.get(key, "") or "")
            entry = tk.Entry(
                dialog, textvariable=var, bg=TEXT_BG, fg=TEXT_FG,
                insertbackground="#ffffff", relief="flat", bd=0,
                highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
            )
            entry.grid(row=row + 1, column=0, sticky="we", padx=(12, 6))

            def browse() -> None:
                if is_file:
                    path = filedialog.askopenfilename(title=label_text)
                else:
                    initial = var.get() or "D:\\"
                    path = filedialog.askdirectory(
                        title=label_text, initialdir=initial if os.path.isdir(initial) else "D:\\"
                    )
                if path:
                    var.set(path)

            self._create_btn(dialog, text="Browse...", command=browse).grid(row=row + 1, column=1, padx=(0, 12))
            fields[key] = var

        add_path_field(0, "Folder Downloads (tempat file .rar hasil download)", "downloads_folder")
        add_path_field(2, "Folder Tujuan Ekstrak (root folder game di D:)", "extracted_root")
        add_path_field(4, "UnRAR.exe (opsional - kosongkan untuk auto-deteksi)", "unrar_path", is_file=True)

        tk.Label(
            dialog, text="Fuzzy Match Threshold (0.0 - 1.0, makin tinggi makin ketat)",
            font=("Segoe UI", 9, "bold"), fg=TEXT_FG, bg=PANEL_BG,
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 0))
        threshold_var = tk.StringVar(value=str(self._settings.get("fuzzy_threshold", 0.72)))
        tk.Entry(
            dialog, textvariable=threshold_var, width=10, bg=TEXT_BG, fg=TEXT_FG,
            insertbackground="#ffffff", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
        ).grid(row=7, column=0, sticky="w", padx=12)

        def save_and_close() -> None:
            self._settings["downloads_folder"] = fields["downloads_folder"].get().strip()
            self._settings["extracted_root"] = fields["extracted_root"].get().strip()
            self._settings["unrar_path"] = fields["unrar_path"].get().strip()
            try:
                self._settings["fuzzy_threshold"] = max(0.0, min(1.0, float(threshold_var.get())))
            except ValueError:
                pass
            game_settings.save_settings(self._settings)
            self._scanner_panel._target_folder.set(self._settings.get("extracted_root", ""))
            self._log("✓ Settings disimpan.")
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg=PANEL_BG)
        btn_row.grid(row=8, column=0, columnspan=2, pady=20)
        self._create_btn(btn_row, text="Simpan", command=save_and_close, style_type="accent", side="left")
        self._create_btn(btn_row, text="Batal", command=dialog.destroy, side="left", padx=(8, 0))

    # ------------------------------------------------------------------
    # Game table population
    # ------------------------------------------------------------------

    def _status_display(self, name: str) -> tuple[str, str, str]:
        """Return (status_text, info_text, tag) for one game title, based on
        the live folder-scan match result and any user confirm/reject decision."""
        match = self._match_map.get(name)
        decision = self._match_decisions.get(name)

        if match is None or match.status == folder_scan.STATUS_NOT_FOUND or decision == "rejected":
            return "—", "-", "none"

        if match.is_exact or decision == "confirmed":
            if match.status == folder_scan.STATUS_EXTRACTED:
                return "✅ SUDAH DIEKSTRAK", match.matched_label or "-", "extracted"
            return "📦 SUDAH DIDOWNLOAD", match.matched_label or "-", "downloaded"

        pct = int(round(match.confidence * 100))
        return f"🟡 MIRIP {pct}%", match.matched_label or "-", "fuzzy"

    def _apply_filter(self) -> None:
        """Repopulate the game table based on the current filter text and match status."""
        filter_text = self.filter_var.get().lower()

        for item in self.game_tree.get_children():
            self.game_tree.delete(item)
        self._tree_item_map = {}

        self._filtered_games = [
            (name, site) for name, site in self._parsed_games
            if filter_text in name.lower()
        ]

        for name, site in self._filtered_games:
            status_text, info_text, tag = self._status_display(name)
            iid = self.game_tree.insert(
                "", "end", values=(site.upper(), name, status_text, info_text), tags=(tag,)
            )
            self._tree_item_map[iid] = (name, site)

        self._update_counter()

    def _update_counter(self) -> None:
        """Update selection counter"""
        selected = len(self.game_tree.selection())
        total = len(self.game_tree.get_children())
        self.counter_label.config(text=f"Selected: {selected}/{total}")

    def _clear_results(self) -> None:
        """Clear resolved host links table"""
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._resolved_rows = []

    def _append_result_row(self, result: dict[str, str | None]) -> None:
        """Add one resolved game row to the table"""
        self._resolved_rows.append(result)
        game_name = result.get("game_name") or ""
        site_type = (result.get("site_type") or "").upper()
        host_name = result.get("selected_host_name") or "-"
        host_link = result.get("selected_host_link") or "-"
        self.result_tree.insert("", "end", values=(game_name, site_type, host_name, host_link))

    def _copy_selected_result(self) -> None:
        """Copy the selected host link to clipboard"""
        selection = self.result_tree.selection()
        if not selection:
            return

        values = self.result_tree.item(selection[0], "values")
        if len(values) < 4:
            return

        link = values[3]
        if not link or link == "-":
            return

        self.clipboard_clear()
        self.clipboard_append(link)
        self._log(f"Copied link: {link}")

    def _open_selected_result(self) -> None:
        """Open the selected host link in the default browser"""
        selection = self.result_tree.selection()
        if not selection:
            return

        values = self.result_tree.item(selection[0], "values")
        if len(values) < 4:
            return

        link = values[3]
        if not link or link == "-":
            return

        webbrowser.open_new_tab(link)
        self._log(f"Opened link: {link}")

    def _open_all_steamrip_downloads(self) -> None:
        """Open all Steamrip BZZHR/GOFILE links in browser"""
        steamrip_links = [
            result.get("selected_host_link")
            for result in self._resolved_rows
            if result.get("site_type") == "steamrip" and result.get("selected_host_link")
        ]

        if not steamrip_links:
            messagebox.showinfo("No Links", "No Steamrip download links found")
            return

        for link in steamrip_links:
            if link and link != "-":
                webbrowser.open_new_tab(link)

        self._log(f"Opened {len(steamrip_links)} Steamrip download links")

    def _open_all_romsfun_downloads(self) -> None:
        """Open all Romsfun download page links in browser"""
        romsfun_links = [
            result.get("selected_host_link")
            for result in self._resolved_rows
            if result.get("site_type") == "romsfun" and result.get("selected_host_link")
        ]

        if not romsfun_links:
            messagebox.showinfo("No Links", "No Romsfun download links found")
            return

        for link in romsfun_links:
            if link and link != "-":
                webbrowser.open_new_tab(link)

        self._log(f"Opened {len(romsfun_links)} Romsfun download links")

    def _select_all(self) -> None:
        """Select all games in the table"""
        self.game_tree.selection_set(self.game_tree.get_children())

    def _deselect_all(self) -> None:
        """Deselect all games"""
        self.game_tree.selection_remove(self.game_tree.get_children())

    def _log(self, message: str) -> None:
        """Add message to status log"""
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.update()

    def _show_pause_dialog(self, message: str) -> None:
        """Show pause dialog during download"""
        messagebox.showinfo(
            "Manual Action Required",
            f"{message}\n\nClick OK when ready to continue.",
        )

    def _parse_text(self) -> None:
        """Parse input text and populate game list"""
        self._parsed_games = self._parse_game_text()
        self._match_decisions = {}
        self._log(f"Parsed {len(self._parsed_games)} games")
        self._rescan_and_match()
        self.filter_var.set("")
        self._apply_filter()
        self._clear_results()

    def _paste_clipboard(self) -> None:
        """Paste from clipboard"""
        try:
            text = pyperclip.paste()
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", text)
            self._parse_text()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to paste: {str(e)}")

    def _load_initial_text(self) -> None:
        """Load initial text (clipboard or sample)"""
        try:
            text = pyperclip.paste()
            if text.strip():
                self.input_text.delete("1.0", "end")
                self.input_text.insert("1.0", text)
        except Exception:
            pass

    def _load_sample(self) -> None:
        """Load sample text"""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", SAMPLE_TEXT)
        self._parse_text()

    def _clear_inputs(self) -> None:
        """Clear all inputs and lists"""
        self.input_text.delete("1.0", "end")
        self._parsed_games = []
        self._match_map = {}
        self._match_decisions = {}
        self.filter_var.set("")
        self._apply_filter()
        self._clear_results()
        self.status_text.delete("1.0", "end")
        self._update_counter()

    def _start_selected(self) -> None:
        """Start downloads for selected games"""
        selected_iids = self.game_tree.selection()
        if not selected_iids:
            messagebox.showwarning("No Selection", "Please select games to download")
            return

        selected_games = [self._tree_item_map[iid] for iid in selected_iids if iid in self._tree_item_map]
        self._start_downloads(selected_games)

    def _start_all(self) -> None:
        """Start downloads for all filtered games"""
        if not self._filtered_games:
            messagebox.showwarning("No Games", "No games to download")
            return

        self._start_downloads(self._filtered_games)

    def _start_downloads(self, games: list[tuple[str, str]]) -> None:
        """Start download thread"""
        if self._worker_thread and self._worker_thread.is_alive():
            messagebox.showwarning("Already Running", "Download already in progress")
            return

        self.status_text.delete("1.0", "end")
        self._pause_event = threading.Event()
        self._pause_event.set()

        self._worker_thread = threading.Thread(
            target=self._download_worker,
            args=(games,),
            daemon=True,
        )
        self._worker_thread.start()

    def _download_worker(self, games: list[tuple[str, str]]) -> None:
        """Background worker for downloads"""
        try:
            open_game_search_tabs(
                games,
                log_fn=self._log,
                pause_fn=self._show_pause_dialog,
                result_fn=self._append_result_row,
                open_in_browser=False,
            )
            self._log("✓ All links resolved in-app!")
        except Exception as e:
            self._log(f"✗ Error: {str(e)}")


if __name__ == "__main__":
    app = GameLauncherMultiSite()
    app.mainloop()
