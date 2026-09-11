import os
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
import pyperclip

from game_scraper_multi_site import open_game_search_tabs, normalize_name
import game_folder_scan as folder_scan
import game_settings
import game_extraction
import game_copy
import game_ps2_serials
import game_status_scanner
import game_cleanup


VERSION = "2.6"

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

STATUS_COLORS = {
    "extracted": OK,
    "downloaded": WARN,
    "fuzzy": "#fb923c",
    "none": MUTED_FG,
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


# Slot definitions live in game_settings so the scanner panel can read them too.
LIST_DEFS = game_settings.LIST_DEFS


def normalize_parsed_title(title: str) -> str:
    """Parse and normalize game title from list.

    A ' PS3' suffix is kept on PS3 titles so the romsfun scraper can pick
    the playstation-3 category; normalize_name() strips it back out for
    folder matching. PS2 titles stay untagged (the scraper's default)."""
    is_ps3 = "(PS3)" in title
    title = re.sub(r"^\d+\.\s+", "", title)
    title = re.sub(r"\s*\(PS[23]\)\s*", "", title)
    for dash in ("-", "–", "—"):
        title = title.replace(dash, " ")
    for apostrophe in ("'", "’"):
        title = title.replace(apostrophe, "")
    title = re.sub(r"\s+", " ", title)
    title = title.strip()
    return f"{title} PS3" if is_ps3 and title else title


def norm_keys_in_text(text: str) -> set[str]:
    """Normalized match-keys for every numbered game line in a raw order list."""
    keys: set[str] = set()
    for line in (text or "").split("\n"):
        line = line.strip()
        if not re.match(r"^\d+\.", line):
            continue
        key = normalize_name(normalize_parsed_title(line))
        if key:
            keys.add(key)
    return keys


def build_also_map(
    active_key: str, list_defs: list[tuple[str, str]], order_lists: dict[str, str]
) -> dict[str, list[str]]:
    """normalized-title -> short names of the OTHER order lists that also want it.

    This is the cross-customer check: a game already on another customer's list
    only needs copying, not a fresh download."""
    result: dict[str, list[str]] = {}
    for key, label in list_defs:
        if key == active_key:
            continue
        short = label.split(" ", 1)[-1] if " " in label else label
        for norm_key in norm_keys_in_text(order_lists.get(key, "")):
            result.setdefault(norm_key, []).append(short)
    return result


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

        self._active_list: str = self._settings.get("active_order_list", "pesanan")
        self._also_map: dict[str, list[str]] = {}  # normalized title -> other lists wanting it
        self._list_tab_buttons: dict[str, tk.Button] = {}

        self._configure_theme()
        self._build_ui()
        self._load_active_list()
        self.bind_all("<Control-Return>", lambda event: self._start_all())

        # Warm the PS2 serial index off the main thread: the first fetch is a
        # ~2 MB download, and a scan started before it lands simply misses the
        # serial-named ISOs until this re-runs it.
        game_ps2_serials.ensure_index_async(
            log_fn=lambda msg: self.after(0, lambda: self._log(msg)),
            on_ready=lambda: self.after(0, self._refresh_after_background_change),
        )

    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Vertical.TScrollbar",
            gripcount=0, background=BORDER_COLOR, troughcolor=TEXT_BG,
            bordercolor=TEXT_BG, darkcolor=TEXT_BG, lightcolor=TEXT_BG,
            arrowsize=0, borderwidth=0,
        )
        style.map("Vertical.TScrollbar", background=[("active", ACCENT)])

        style.configure(
            "Treeview",
            background=TEXT_BG, fieldbackground=TEXT_BG, foreground=TEXT_FG,
            borderwidth=0, rowheight=36, font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_ALT, foreground=MUTED_FG, relief="flat",
            font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(8, 8),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Treeview.Heading", background=[("active", PANEL_BG)])

        # Tighter rows for the small resolved-links table at the bottom.
        style.configure("Compact.Treeview", background=TEXT_BG, fieldbackground=TEXT_BG,
                        foreground=TEXT_FG, borderwidth=0, rowheight=24, font=("Segoe UI", 9))
        style.configure("Compact.Treeview.Heading", background=PANEL_ALT, foreground=MUTED_FG,
                        relief="flat", font=("Segoe UI", 8, "bold"), borderwidth=0, padding=(6, 5))
        style.map("Compact.Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

    def _create_btn(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        style_type: str = "normal",
        **pack_kwargs
    ) -> tk.Button:
        """Flat button in one of a few semantic variants. tkinter has no
        rounded corners, so weight/padding/color carry the hierarchy."""
        palette = {
            "accent": (ACCENT, "#ffffff", ACCENT_HOVER),
            "accent_pink": (ACCENT_PINK, "#ffffff", "#f43f75"),
            "ok": (OK, "#04120c", "#6ee7b7"),
            "ghost": (APP_BG, MUTED_FG, PANEL_ALT),
            "normal": (PANEL_ALT, TEXT_FG, "#22304f"),
        }
        bg, fg, active_bg = palette.get(style_type, palette["normal"])

        btn = tk.Button(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=active_bg, activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
            padx=14, pady=8, cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_COLOR if style_type in ("ghost", "normal") else bg,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=active_bg, fg="#ffffff"))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=fg))
        if pack_kwargs:
            btn.pack(**pack_kwargs)
        return btn

    def _card(
        self, parent: tk.Widget, title: str, accent: str = ACCENT, **pack_kwargs
    ) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
        """Titled panel with a colored top rule. Returns (outer, header, body)
        so callers can drop extra controls into the header row."""
        outer = tk.Frame(parent, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        if pack_kwargs:
            outer.pack(**pack_kwargs)
        tk.Frame(outer, bg=accent, height=3).pack(fill="x")
        header = tk.Frame(outer, bg=PANEL_BG)
        header.pack(fill="x", padx=14, pady=(11, 8))
        tk.Label(
            header, text=title, font=("Segoe UI", 11, "bold"), fg="#ffffff", bg=PANEL_BG,
        ).pack(side="left")
        body = tk.Frame(outer, bg=PANEL_BG)
        body.pack(fill="both", expand=True)
        return outer, header, body

    # ------------------------------------------------------------------
    # App shell: left nav rail + header + swappable pages + status bar
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.configure(bg=APP_BG)

        shell = tk.Frame(self, bg=APP_BG)
        shell.pack(fill="both", expand=True)

        self._build_sidebar(shell)

        content = tk.Frame(shell, bg=APP_BG)
        content.pack(side="left", fill="both", expand=True)

        self._build_header(content)
        self._build_status_bar(content)

        # Packed last so it soaks up the space left between header and status bar.
        self._page_host = tk.Frame(content, bg=APP_BG)
        self._page_host.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self._downloader_tab = tk.Frame(self._page_host, bg=APP_BG)
        self._build_downloader_tab(self._downloader_tab)

        self._scanner_tab = tk.Frame(self._page_host, bg=APP_BG)
        self._scanner_panel = game_status_scanner.GameStatusScannerPanel(
            self._scanner_tab,
            default_folder=self._settings.get("extracted_root", ""),
            default_folder_2=self._settings.get("extracted_root_2", ""),
        )
        self._scanner_panel.pack(fill="both", expand=True)

        self._cleanup_tab = tk.Frame(self._page_host, bg=APP_BG)
        self._cleanup_panel = game_cleanup.GameCleanupPanel(self._cleanup_tab)
        self._cleanup_panel.pack(fill="both", expand=True)

        self._switch_tab("downloader")
        self._update_folder_badges()

    def _build_sidebar(self, parent: tk.Widget) -> None:
        rail = tk.Frame(parent, bg=SIDEBAR_BG, width=232)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        brand = tk.Frame(rail, bg=SIDEBAR_BG)
        brand.pack(fill="x", padx=18, pady=(22, 16))
        tk.Label(brand, text="\U0001F3AE", font=("Segoe UI Emoji", 20), fg=ACCENT, bg=SIDEBAR_BG).pack(side="left")
        wordmark = tk.Frame(brand, bg=SIDEBAR_BG)
        wordmark.pack(side="left", padx=(10, 0))
        tk.Label(
            wordmark, text="WD GAMES", font=("Segoe UI", 14, "bold"), fg="#ffffff", bg=SIDEBAR_BG,
        ).pack(anchor="w")
        tk.Label(
            wordmark, text=f"v{VERSION}  •  game ops", font=("Segoe UI", 8), fg=MUTED_FG, bg=SIDEBAR_BG,
        ).pack(anchor="w")

        tk.Frame(rail, bg=BORDER_COLOR, height=1).pack(fill="x", padx=18)

        tk.Label(
            rail, text="MENU", font=("Segoe UI", 8, "bold"), fg=MUTED_FG, bg=SIDEBAR_BG,
        ).pack(anchor="w", padx=20, pady=(16, 6))

        self._tab_buttons: dict[str, tk.Button] = {}
        for key, label in (
            ("downloader", "\U0001F4E5    Downloader"),
            ("scanner", "\U0001F50D    Cek Status Game"),
            ("cleanup", "\U0001F5D1    Bersih-bersih"),
        ):
            btn = tk.Button(
                rail, text=label, command=lambda k=key: self._switch_tab(k),
                anchor="w", font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                padx=14, pady=11, cursor="hand2", highlightthickness=0,
                activeforeground="#ffffff",
            )
            btn.pack(fill="x", padx=12, pady=2)
            btn.bind("<Enter>", lambda _e, b=btn, k=key: (
                None if self._current_tab == k else b.config(bg=PANEL_ALT, fg=TEXT_FG)
            ))
            btn.bind("<Leave>", lambda _e, b=btn, k=key: (
                None if self._current_tab == k else b.config(bg=SIDEBAR_BG, fg=MUTED_FG)
            ))
            self._tab_buttons[key] = btn

        tk.Label(
            rail, text="FOLDER SCAN", font=("Segoe UI", 8, "bold"), fg=MUTED_FG, bg=SIDEBAR_BG,
        ).pack(anchor="w", padx=20, pady=(22, 6))
        self._folder_badge_host = tk.Frame(rail, bg=SIDEBAR_BG)
        self._folder_badge_host.pack(fill="x", padx=12)

        footer = tk.Frame(rail, bg=SIDEBAR_BG)
        footer.pack(side="bottom", fill="x", padx=12, pady=14)
        # Tools that act on folders/lists as a whole live here - the downloader
        # toolbar is already full of per-row actions.
        self._create_btn(
            footer, "🎮   Rename Game PS2", self._open_ps2_rename_dialog, "normal", fill="x",
        )
        self._create_btn(
            footer, "💽   Cek HDD Customer", self._check_customer_hdd, "normal",
            fill="x", pady=(6, 0),
        )
        self._create_btn(
            footer, "⚙   Settings", self._open_settings_dialog, "normal", fill="x", pady=(6, 0),
        )
        self._create_btn(
            footer, "\U0001F50D   Scan Ulang Folder", self._rescan_button_clicked, "ghost", fill="x", pady=(6, 0),
        )

    def _scan_roots(self) -> list[tuple[str, str]]:
        """(short label, path) for every configured extracted-game root that
        actually exists. Both the local games folder and the external HDD are
        scanned, in this order - local wins on a duplicate title."""
        roots: list[tuple[str, str]] = []
        for label, key in (("Lokal", "extracted_root"), ("HDD", "extracted_root_2")):
            path = (self._settings.get(key) or "").strip()
            if path and os.path.isdir(path):
                roots.append((label, path))
        return roots

    def _source_label(self, matched_path: str | None) -> str:
        """Which scan root a matched folder came from, for the Lokasi column."""
        if not matched_path:
            return "-"
        for label, path in self._scan_roots():
            if os.path.normcase(matched_path).startswith(os.path.normcase(path)):
                return label
        return "-"

    def _update_folder_badges(self) -> None:
        """Repaint the sidebar's two scan-folder chips (green dot = folder is
        there right now, so an unplugged HDD is visible at a glance)."""
        for child in self._folder_badge_host.winfo_children():
            child.destroy()

        for title, key in (("Folder Lokal", "extracted_root"), ("HDD Eksternal", "extracted_root_2")):
            path = (self._settings.get(key) or "").strip()
            online = bool(path) and os.path.isdir(path)
            card = tk.Frame(self._folder_badge_host, bg=PANEL_BG, highlightthickness=1,
                            highlightbackground=BORDER_COLOR, cursor="hand2")
            card.pack(fill="x", pady=(0, 6))
            row = tk.Frame(card, bg=PANEL_BG)
            row.pack(fill="x", padx=10, pady=(8, 0))
            tk.Label(
                row, text="●", font=("Segoe UI", 9),
                fg=OK if online else (WARN if path else MUTED_FG), bg=PANEL_BG,
            ).pack(side="left")
            tk.Label(
                row, text=title, font=("Segoe UI", 9, "bold"), fg=TEXT_FG, bg=PANEL_BG,
            ).pack(side="left", padx=(6, 0))
            tk.Label(
                card, text=path or "(belum diatur - klik untuk set)",
                font=("Consolas", 8), fg=MUTED_FG if online else WARN, bg=PANEL_BG,
                anchor="w", wraplength=185, justify="left",
            ).pack(fill="x", padx=10, pady=(1, 8))
            for widget in (card, *card.winfo_children()):
                widget.bind("<Button-1>", lambda _e: self._open_settings_dialog())

    def _build_header(self, parent: tk.Widget) -> None:
        header = tk.Frame(parent, bg=APP_BG)
        header.pack(fill="x", padx=20, pady=(18, 12))

        titles = tk.Frame(header, bg=APP_BG)
        titles.pack(side="left")
        self._page_title = tk.Label(
            titles, text="", font=("Segoe UI", 17, "bold"), fg="#ffffff", bg=APP_BG,
        )
        self._page_title.pack(anchor="w")
        self._page_subtitle = tk.Label(
            titles, text="", font=("Segoe UI", 9), fg=MUTED_FG, bg=APP_BG,
        )
        self._page_subtitle.pack(anchor="w", pady=(2, 0))

    def _build_status_bar(self, parent: tk.Widget) -> None:
        bar = tk.Frame(parent, bg=SIDEBAR_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        bar.pack(side="bottom", fill="x")
        self._statusbar_label = tk.Label(
            bar, text="Siap.", font=("Segoe UI", 9), fg=MUTED_FG, bg=SIDEBAR_BG, anchor="w",
        )
        self._statusbar_label.pack(side="left", padx=14, pady=6)

    def _set_status(self, text: str) -> None:
        if getattr(self, "_statusbar_label", None):
            self._statusbar_label.config(text=text)

    def _switch_tab(self, key: str) -> None:
        self._current_tab = key
        for tab_key, btn in self._tab_buttons.items():
            active = tab_key == key
            btn.config(
                bg=ACCENT if active else SIDEBAR_BG,
                fg="#ffffff" if active else MUTED_FG,
            )

        tabs = {
            "downloader": (
                self._downloader_tab, "Downloader",
                "Paste daftar pesanan • cek status di 2 folder • resolve link • ekstrak & copy",
            ),
            "scanner": (
                self._scanner_tab, "Cek Status Game",
                "Scan folder mana pun untuk lihat game yang sudah ada / belum ada",
            ),
            "cleanup": (
                self._cleanup_tab, "Bersih-bersih Folder",
                "Game yang tidak dipesan customer mana pun = boleh dihapus permanen dari sini",
            ),
        }
        for tab_key, (frame, title, subtitle) in tabs.items():
            if tab_key == key:
                frame.pack(fill="both", expand=True)
                self._page_title.config(text=title)
                self._page_subtitle.config(text=subtitle)
            else:
                frame.pack_forget()

    # ------------------------------------------------------------------
    # Downloader page
    # ------------------------------------------------------------------

    def _build_downloader_tab(self, body: tk.Frame) -> None:
        left_panel, left_header, left_body = self._card(
            body, "Daftar Game Pesanan", ACCENT,
            side="left", fill="both", expand=False, padx=(0, 14),
        )
        left_panel.configure(width=430)
        left_panel.pack_propagate(False)

        self._list_count_label = tk.Label(
            left_header, text="", font=("Segoe UI", 9), fg=MUTED_FG, bg=PANEL_BG,
        )
        self._list_count_label.pack(side="right")

        # Order-list slots, 3 per row so all 6 fit the panel width.
        tabs_wrap = tk.Frame(left_body, bg=PANEL_BG)
        tabs_wrap.pack(fill="x", padx=14, pady=(0, 10))
        for column in range(3):
            tabs_wrap.columnconfigure(column, weight=1)
        for i, (key, label) in enumerate(LIST_DEFS):
            btn = tk.Button(
                tabs_wrap, text=label, command=lambda k=key: self._switch_list(k),
                font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                padx=6, pady=7, cursor="hand2", highlightthickness=0,
            )
            btn.grid(row=i // 3, column=i % 3, sticky="we", padx=2, pady=2)
            self._list_tab_buttons[key] = btn
        self._paint_list_tabs()

        actions = tk.Frame(left_body, bg=PANEL_BG)
        actions.pack(fill="x", padx=14)
        self._create_btn(actions, "\U0001F4CB  Parse Text", self._parse_text, "accent", side="left", fill="x", expand=True)
        self._create_btn(actions, "\U0001F4E5  Paste", self._paste_clipboard, side="left", padx=(6, 0))
        self._create_btn(actions, "\U0001F3B2", self._load_sample, "ghost", side="left", padx=(6, 0))
        self._create_btn(actions, "\U0001F9F9", self._clear_inputs, "ghost", side="left", padx=(6, 0))

        text_frame = tk.Frame(left_body, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        text_scroll.pack(side="right", fill="y")
        self.input_text = tk.Text(
            text_frame, wrap="word", yscrollcommand=text_scroll.set,
            bg=TEXT_BG, fg=TEXT_FG, insertbackground=ACCENT_HOVER, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
            font=("Consolas", 11), padx=12, pady=12, spacing1=2, spacing3=2,
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=self.input_text.yview)

        # ---- right column -------------------------------------------------
        right = tk.Frame(body, bg=APP_BG)
        right.pack(side="right", fill="both", expand=True)

        self._build_stat_cards(right)

        # Bottom-up packing so the game table keeps whatever room is left.
        primary = tk.Frame(right, bg=APP_BG)
        primary.pack(side="bottom", fill="x", pady=(10, 0))
        self._create_btn(primary, "▶  Start Selected", self._start_selected, "accent",
                         side="left", fill="x", expand=True)
        self._create_btn(primary, "⚡  Run All", self._start_all, "accent_pink",
                         side="left", fill="x", expand=True, padx=(8, 0))
        self._create_btn(primary, "\U0001F4E6  Ekstrak Semua", self._extract_all_clicked, "normal",
                         side="left", fill="x", expand=True, padx=(8, 0))
        self._create_btn(primary, "\U0001F4BE  Copy ke HDD", self._copy_to_hdd_clicked, "ok",
                         side="left", fill="x", expand=True, padx=(8, 0))

        utility = tk.Frame(right, bg=APP_BG)
        utility.pack(side="bottom", fill="x", pady=(8, 0))
        self._create_btn(utility, "\U0001F310 Steamrip", self._open_all_steamrip_downloads, "ghost", side="left")
        self._create_btn(utility, "\U0001F310 Romsfun", self._open_all_romsfun_downloads, "ghost", side="left", padx=(6, 0))
        self._create_btn(utility, "✕ Tutup Steamrip", self._close_steamrip_windows, "ghost", side="left", padx=(6, 0))
        self._create_btn(utility, "\U0001F4CE Copy Game", self._copy_game_to_clipboard, "ghost", side="right")
        self._create_btn(utility, "\U0001F4CB Copy Link", self._copy_selected_result, "ghost", side="right", padx=(0, 6))
        self._create_btn(utility, "\U0001F310 Open Link", self._open_selected_result, "ghost", side="right", padx=(0, 6))

        # Links and log share one bottom row - stacked they ate the whole
        # column and left the game table with no rows at all. Grid (not pack)
        # so the split stays 50/50 regardless of each child's requested size.
        bottom_row = tk.Frame(right, bg=APP_BG, height=200)
        bottom_row.pack(side="bottom", fill="x", pady=(10, 0))
        bottom_row.pack_propagate(False)
        bottom_row.rowconfigure(0, weight=1)
        bottom_row.columnconfigure(0, weight=1, uniform="half")
        bottom_row.columnconfigure(1, weight=1, uniform="half")

        log_card, log_header, log_body = self._card(bottom_row, "Status Log", ACCENT_PINK)
        log_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        log_frame = tk.Frame(log_body, bg=PANEL_BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical")
        log_scroll.pack(side="right", fill="y")
        self.status_text = tk.Text(
            log_frame, height=6, width=40, wrap="word", yscrollcommand=log_scroll.set,
            bg=TEXT_BG, fg=TEXT_FG, insertbackground=ACCENT_HOVER, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
            font=("Consolas", 9), padx=10, pady=8,
        )
        self.status_text.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.status_text.yview)

        result_card, result_header, result_body = self._card(bottom_row, "Resolved Host Links", WARN)
        result_card.grid(row=0, column=0, sticky="nsew")
        tk.Label(
            result_header, text="dobel-klik untuk buka link", font=("Segoe UI", 8),
            fg=MUTED_FG, bg=PANEL_BG,
        ).pack(side="right")
        result_table = tk.Frame(result_body, bg=PANEL_BG)
        result_table.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        result_scroll = ttk.Scrollbar(result_table, orient="vertical")
        result_scroll.pack(side="right", fill="y")
        self.result_tree = ttk.Treeview(
            result_table, columns=("game", "site", "host", "link"),
            show="headings", height=4, yscrollcommand=result_scroll.set,
            style="Compact.Treeview",
        )
        for col, text, width, anchor in (
            ("game", "Game", 200, "w"), ("site", "Site", 70, "center"),
            ("host", "Host", 90, "center"), ("link", "Link", 260, "w"),
        ):
            self.result_tree.heading(col, text=text)
            self.result_tree.column(col, width=width, anchor=anchor)
        self.result_tree.pack(side="left", fill="both", expand=True)
        result_scroll.config(command=self.result_tree.yview)
        self.result_tree.bind("<Double-1>", lambda event: self._open_selected_result())

        # ---- main game table (takes the remaining height) -------------------
        table_card, table_header, table_body = self._card(
            right, "Status Game", ACCENT, side="top", fill="both", expand=True, pady=(12, 0),
        )
        self.counter_label = tk.Label(
            table_header, text="Selected: 0/0", font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=PANEL_BG,
        )
        self.counter_label.pack(side="right")
        tk.Label(
            table_header, text="klik kanan: konfirmasi / tolak / tandai manual",
            font=("Segoe UI", 8), fg=MUTED_FG, bg=PANEL_BG,
        ).pack(side="right", padx=(0, 12))

        filter_row = tk.Frame(table_body, bg=PANEL_BG)
        filter_row.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(
            filter_row, text="\U0001F50E", font=("Segoe UI Emoji", 10), fg=MUTED_FG, bg=PANEL_BG,
        ).pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *args: self._apply_filter())
        filter_entry = tk.Entry(
            filter_row, textvariable=self.filter_var,
            bg=TEXT_BG, fg=TEXT_FG, insertbackground=ACCENT_HOVER, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
            font=("Segoe UI", 10),
        )
        filter_entry.pack(side="left", fill="x", expand=True, padx=(8, 10), ipady=5)
        self._create_btn(filter_row, "Select All", self._select_all, "ghost", side="left")
        self._create_btn(filter_row, "Deselect", self._deselect_all, "ghost", side="left", padx=(6, 0))

        table_frame = tk.Frame(table_body, bg=TEXT_BG)
        table_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        game_scroll = ttk.Scrollbar(table_frame, orient="vertical")
        game_scroll.pack(side="right", fill="y")
        self.game_tree = ttk.Treeview(
            table_frame, columns=("site", "title", "status", "info", "where", "also"),
            show="headings", selectmode="extended", yscrollcommand=game_scroll.set,
        )
        for col, text, width, anchor in (
            ("site", "Site", 80, "center"), ("title", "Judul Game", 250, "w"),
            ("status", "Status", 160, "w"), ("info", "Folder/File Cocok", 200, "w"),
            ("where", "Lokasi", 75, "center"), ("also", "Juga Dipesan", 130, "w"),
        ):
            self.game_tree.heading(col, text=text)
            self.game_tree.column(col, width=width, anchor=anchor)
        self.game_tree.pack(side="left", fill="both", expand=True)
        game_scroll.config(command=self.game_tree.yview)

        # Status color x zebra striping: a row carrying two tags resolves
        # conflicting options unpredictably in ttk, so combine them up front.
        for tag, color in STATUS_COLORS.items():
            self.game_tree.tag_configure(f"{tag}_even", foreground=color, background=TEXT_BG)
            self.game_tree.tag_configure(f"{tag}_odd", foreground=color, background=STRIPE_BG)

        self.game_tree.bind("<<TreeviewSelect>>", lambda event: self._update_counter())
        self.game_tree.bind("<Button-3>", self._show_game_context_menu)

    def _build_stat_cards(self, parent: tk.Widget) -> None:
        """Live counters across the top of the downloader page."""
        row = tk.Frame(parent, bg=APP_BG)
        row.pack(side="top", fill="x")
        self._stat_labels: dict[str, tk.Label] = {}
        specs = [
            ("total", "TOTAL GAME", ACCENT),
            ("extracted", "SUDAH DIEKSTRAK", OK),
            ("downloaded", "SUDAH DIDOWNLOAD", WARN),
            ("fuzzy", "PERLU DICEK", "#fb923c"),
            ("none", "BELUM ADA", DANGER),
        ]
        for i, (key, title, color) in enumerate(specs):
            card = tk.Frame(row, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
            card.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 8, 0))
            tk.Frame(card, bg=color, height=3).pack(fill="x")
            value = tk.Label(card, text="0", font=("Segoe UI", 22, "bold"), fg=color, bg=PANEL_BG)
            value.pack(anchor="w", padx=14, pady=(6, 0))
            tk.Label(
                card, text=title, font=("Segoe UI", 8, "bold"), fg=MUTED_FG, bg=PANEL_BG,
            ).pack(anchor="w", padx=14, pady=(0, 10))
            self._stat_labels[key] = value

    def _update_stat_cards(self) -> None:
        counts = {"extracted": 0, "downloaded": 0, "fuzzy": 0, "none": 0}
        for name, _site in self._filtered_games:
            _status, _info, tag = self._status_display(name)
            counts[tag] = counts.get(tag, 0) + 1
        counts["total"] = len(self._filtered_games)
        for key, label in self._stat_labels.items():
            label.config(text=str(counts.get(key, 0)))
        if getattr(self, "_list_count_label", None):
            self._list_count_label.config(text=f"{counts['total']} judul")

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
        return normalize_parsed_title(title)

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

            is_romsfun = "(PS2)" in line or "(PS3)" in line
            title = self._normalize_parsed_title(line)
            if title:
                site_type = "romsfun" if is_romsfun else "steamrip"
                games.append((title, site_type))

        return games

    # ------------------------------------------------------------------
    # Folder-scan status checking (no database - live filesystem check)
    # ------------------------------------------------------------------

    def _rescan_and_match(self) -> None:
        """Re-scan the extracted (D:) and downloads (C:) folders and recompute
        status for every currently parsed game. Pure live filesystem check -
        no database, nothing persisted across runs."""
        roots = self._scan_roots()
        extracted_index = folder_scan.scan_extracted_folders([path for _label, path in roots])
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
        where = ", ".join(f"{label} ({path})" for label, path in roots) or "tidak ada folder valid"
        self._log(f"ℹ Scan {len(roots)} folder: {where}")
        self._log(
            f"ℹ Hasil: {extracted_count} sudah diekstrak, "
            f"{downloaded_count} sudah didownload (belum diekstrak), "
            f"{not_found_count} belum ada."
        )
        self._set_status(
            f"Scan {len(roots)} folder • {extracted_count} siap • "
            f"{downloaded_count} perlu ekstrak • {not_found_count} belum ada"
        )
        self._update_folder_badges()

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
            self, tearoff=0, bg=PANEL_ALT, fg=TEXT_FG,
            activebackground=ACCENT, activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 9),
        )

        if match and match.status != folder_scan.STATUS_NOT_FOUND and not match.is_exact and decision != "rejected":
            menu.add_command(label="✓ Konfirmasi Match", command=lambda n=name: self._confirm_match(n))
            menu.add_command(label="✗ Tolak Match", command=lambda n=name: self._reject_match(n))
            menu.add_separator()

        menu.add_command(label="📁 Tandai Manual...", command=lambda n=name: self._manual_match(n))

        if match and match.status == folder_scan.STATUS_EXTRACTED and match.matched_path:
            menu.add_command(label="📎 Copy Game (paste ke HDD)", command=self._copy_game_to_clipboard)

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

    def _selected_extracted_sources(self) -> list[tuple[str, str]]:
        """(name, folder) for every selected row already extracted on disk.
        Shared by both copy paths - clipboard and robocopy - so they always
        agree on what "selected game" means."""
        sources: list[tuple[str, str]] = []
        for iid in self.game_tree.selection():
            name, _site = self._tree_item_map.get(iid, (None, None))
            if name is None:
                continue
            match = self._match_map.get(name)
            if match and match.status == folder_scan.STATUS_EXTRACTED and match.matched_path:
                sources.append((name, match.matched_path))
        return sources

    def _copy_game_to_clipboard(self) -> None:
        """Put the selected game folder(s) on the Windows clipboard so the user
        can paste them into the customer HDD in Explorer themselves."""
        sources = self._selected_extracted_sources()
        if not sources:
            messagebox.showinfo(
                "Copy Game",
                "Pilih dulu baris game yang statusnya sudah ter-ekstrak di tabel.",
            )
            return
        try:
            game_copy.copy_paths_to_clipboard([path for _name, path in sources])
        except Exception as exc:
            messagebox.showerror("Copy Game", f"Gagal copy ke clipboard: {exc}")
            return
        names = ", ".join(name for name, _p in sources)
        self._log(f"📋 {len(sources)} folder game di-copy ke clipboard: {names}")
        self._log("   Buka folder HDD di Explorer lalu tekan Ctrl+V untuk paste.")

    def _copy_to_hdd_clicked(self) -> None:
        """Copy extracted game folder(s) to a customer HDD via robocopy.
        Uses the currently selected rows (if any) whose status is already
        'extracted'; otherwise falls back to letting the user pick one
        source folder directly."""
        sources = self._selected_extracted_sources()

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

    # ------------------------------------------------------------------
    # PS2: serial-named discs -> real titles
    # ------------------------------------------------------------------

    def _check_customer_hdd(self) -> None:
        """Open the scanner against the customer's own drive, preloaded with
        the active order list - the 'is Cust 4's HDD complete yet?' check."""
        self._save_active_list_text()
        text = self.input_text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("Daftar Kosong", "Isi dulu daftar pesanan customer di tab Downloader.")
            return
        self._scanner_panel.load_order_text(text)
        self._switch_tab("scanner")
        self._log(
            f"💽 Daftar '{dict(LIST_DEFS)[self._active_list]}' dimuat ke Cek Status Game. "
            "Pilih folder/HDD customer lalu Scan."
        )

    def _open_ps2_rename_dialog(self) -> None:
        """Propose 'SCUS-97481 (1.01).iso' -> 'God of War II.iso' for every
        serial-named disc in the scan roots, and let the user take them all or
        pick rows by hand."""
        roots = [path for _label, path in self._scan_roots()]
        if not roots:
            messagebox.showwarning("Folder Belum Diatur", "Atur folder game dulu di Settings.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Rename Game PS2")
        dialog.configure(bg=PANEL_BG)
        dialog.geometry("980x560")
        dialog.transient(self)

        head = tk.Frame(dialog, bg=PANEL_BG)
        head.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(
            head, text="Rename Game PS2 ke Judul Asli", font=("Segoe UI", 14, "bold"),
            fg="#ffffff", bg=PANEL_BG,
        ).pack(side="left")
        status = tk.Label(
            head, text="Menyiapkan database serial...", font=("Segoe UI", 9), fg=MUTED_FG, bg=PANEL_BG,
        )
        status.pack(side="right")

        tk.Label(
            dialog,
            text="Pilih baris untuk rename sebagian (Ctrl/Shift buat pilih banyak), "
                 "atau langsung Rename Semua. Nama lama tidak ditimpa kalau bentrok.",
            font=("Segoe UI", 9), fg=MUTED_FG, bg=PANEL_BG, anchor="w", justify="left",
        ).pack(fill="x", padx=16, pady=(0, 10))

        table = tk.Frame(dialog, bg=TEXT_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        table.pack(fill="both", expand=True, padx=16)
        scroll = ttk.Scrollbar(table, orient="vertical")
        scroll.pack(side="right", fill="y")
        tree = ttk.Treeview(
            table, columns=("current", "serial", "title", "new"),
            show="headings", selectmode="extended", yscrollcommand=scroll.set,
        )
        for col, text, width, anchor in (
            ("current", "Nama Sekarang", 260, "w"), ("serial", "Serial", 110, "center"),
            ("title", "Judul Asli", 250, "w"), ("new", "Nama Baru", 280, "w"),
        ):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor=anchor)
        tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=tree.yview)

        plans: dict[str, game_ps2_serials.RenamePlan] = {}

        def render(found: list[game_ps2_serials.RenamePlan]) -> None:
            tree.delete(*tree.get_children())
            plans.clear()
            for plan in found:
                iid = tree.insert(
                    "", "end", values=(plan.current_name, plan.serial, plan.title, plan.new_name),
                )
                plans[iid] = plan
            status.config(
                text=f"{len(found)} disc bisa di-rename" if found else "Tidak ada file bernama serial PS2",
                fg=OK if found else MUTED_FG,
            )

        def reload_plans() -> None:
            status.config(text="Memindai...", fg=MUTED_FG)

            def worker() -> None:
                game_ps2_serials.ensure_index(
                    log_fn=lambda msg: self.after(0, lambda m=msg: self._log(m))
                )
                found = game_ps2_serials.plan_renames(roots)
                if dialog.winfo_exists():
                    self.after(0, lambda: render(found))

            threading.Thread(target=worker, daemon=True).start()

        def run_renames(chosen: list[game_ps2_serials.RenamePlan]) -> None:
            if not chosen:
                messagebox.showinfo("Rename PS2", "Pilih dulu baris yang mau di-rename.", parent=dialog)
                return
            if not messagebox.askyesno(
                "Rename PS2",
                f"Rename {len(chosen)} file/folder ke judul aslinya?\n\n"
                "Ini mengubah nama di disk (Playnite akan membacanya sebagai judul game).",
                parent=dialog,
            ):
                return
            done = 0
            for plan in chosen:
                try:
                    game_ps2_serials.apply_rename(plan)
                    self._log(f"✓ Rename: {plan.current_name}  ->  {plan.new_name}")
                    done += 1
                except Exception as exc:
                    self._log(f"✗ Gagal rename {plan.current_name}: {exc}")
            self._log(f"🎮 {done}/{len(chosen)} game PS2 di-rename.")
            reload_plans()
            self._refresh_after_background_change()

        buttons = tk.Frame(dialog, bg=PANEL_BG)
        buttons.pack(fill="x", padx=16, pady=14)
        self._create_btn(
            buttons, "✓  Rename Terpilih",
            lambda: run_renames([plans[i] for i in tree.selection() if i in plans]),
            "accent", side="left",
        )
        self._create_btn(
            buttons, "⚡  Rename Semua",
            lambda: run_renames(list(plans.values())), "accent_pink", side="left", padx=(8, 0),
        )
        self._create_btn(buttons, "🔄  Scan Ulang", reload_plans, "ghost", side="left", padx=(8, 0))
        self._create_btn(buttons, "Tutup", dialog.destroy, "normal", side="right")

        reload_plans()

    def _open_settings_dialog(self) -> None:
        """Small preferences dialog: folder paths + fuzzy threshold. Not a
        game database - just the 2-3 paths the scan/extract/copy features need."""
        dialog = tk.Toplevel(self)
        dialog.title("Settings")
        dialog.configure(bg=PANEL_BG)
        dialog.geometry("660x460")
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
        add_path_field(2, "Folder Game Utama / Tujuan Ekstrak (mis. D:\\GAMES INSTALL)", "extracted_root")
        add_path_field(4, "Folder Game Kedua - HDD Eksternal (ikut di-scan, opsional)", "extracted_root_2")
        add_path_field(6, "UnRAR.exe (opsional - kosongkan untuk auto-deteksi)", "unrar_path", is_file=True)

        tk.Label(
            dialog, text="Fuzzy Match Threshold (0.0 - 1.0, makin tinggi makin ketat)",
            font=("Segoe UI", 9, "bold"), fg=TEXT_FG, bg=PANEL_BG,
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 0))
        threshold_var = tk.StringVar(value=str(self._settings.get("fuzzy_threshold", 0.72)))
        tk.Entry(
            dialog, textvariable=threshold_var, width=10, bg=TEXT_BG, fg=TEXT_FG,
            insertbackground="#ffffff", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
        ).grid(row=9, column=0, sticky="w", padx=12)

        def save_and_close() -> None:
            for key in ("downloads_folder", "extracted_root", "extracted_root_2", "unrar_path"):
                self._settings[key] = fields[key].get().strip()
            try:
                self._settings["fuzzy_threshold"] = max(0.0, min(1.0, float(threshold_var.get())))
            except ValueError:
                pass
            game_settings.save_settings(self._settings)
            self._scanner_panel._target_folder.set(self._settings.get("extracted_root", ""))
            self._scanner_panel._target_folder_2.set(self._settings.get("extracted_root_2", ""))
            self._update_folder_badges()
            self._log("✓ Settings disimpan.")
            if self._parsed_games:
                self._rescan_and_match()
                self._apply_filter()
            dialog.destroy()

        btn_row = tk.Frame(dialog, bg=PANEL_BG)
        btn_row.grid(row=10, column=0, columnspan=2, pady=20)
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

        for row_index, (name, site) in enumerate(self._filtered_games):
            status_text, info_text, tag = self._status_display(name)
            also_text = ", ".join(self._also_map.get(normalize_name(name), []))
            match = self._match_map.get(name)
            where = "-"
            if info_text != "-" and match is not None:
                where = self._source_label(match.matched_path)
            stripe = "odd" if row_index % 2 else "even"
            iid = self.game_tree.insert(
                "", "end",
                values=(site.upper(), name, status_text, info_text, where, also_text),
                tags=(f"{tag}_{stripe}",),
            )
            self._tree_item_map[iid] = (name, site)

        self._update_counter()
        self._update_stat_cards()

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

        result = next((r for r in self._resolved_rows if r.get("selected_host_link") == link), None)
        self._open_link(result)
        self._log(f"Opened: {link}")

    def _open_link(self, result: dict | None) -> None:
        """Open one resolved result's link in the browser. For a confident
        Steamrip title match this is the real game page (opened directly, no
        automation needed since it's steamrip.com's own domain); for an
        unconfident match it's the search results page instead, so the user
        picks the right title/version themselves; Romsfun opens its resolved
        download page the same way."""
        if not result:
            return
        url = result.get("selected_host_link")
        if url and url != "-":
            webbrowser.open_new_tab(url)

    def _gather_resolved_results(self, site_type: str) -> list[dict]:
        """Resolved result rows for one site type ('steamrip' or 'romsfun')."""
        return [
            r for r in self._resolved_rows
            if r.get("site_type") == site_type and r.get("selected_host_link") and r.get("selected_host_link") != "-"
        ]

    def _open_all_steamrip_downloads(self) -> None:
        """Open all resolved Steamrip game page links in browser"""
        steamrip_results = self._gather_resolved_results("steamrip")

        if not steamrip_results:
            messagebox.showinfo("No Links", "No Steamrip download links found")
            return

        for result in steamrip_results:
            self._open_link(result)

        self._log(f"Opened {len(steamrip_results)} Steamrip download links")

    def _open_all_romsfun_downloads(self) -> None:
        """Open all Romsfun download page links in browser"""
        romsfun_results = self._gather_resolved_results("romsfun")

        if not romsfun_results:
            messagebox.showinfo("No Links", "No Romsfun download links found")
            return

        for result in romsfun_results:
            self._open_link(result)

        self._log(f"Opened {len(romsfun_results)} Romsfun download links")

    def _auto_open_all_resolved_downloads(self) -> None:
        """Open every resolved Steamrip AND Romsfun (PS2) result together in
        the browser, right after a scraping run finishes - so PS2 titles open
        automatically just like Steamrip ones do, instead of needing the two
        toolbar buttons clicked separately by hand."""
        steamrip_results = self._gather_resolved_results("steamrip")
        romsfun_results = self._gather_resolved_results("romsfun")

        if not steamrip_results and not romsfun_results:
            self._log("ℹ No resolved download links to open yet.")
            return

        for result in steamrip_results + romsfun_results:
            self._open_link(result)

        self._log(
            f"🌐 Auto-opened {len(steamrip_results)} Steamrip + {len(romsfun_results)} Romsfun link(s)."
        )

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

    # ------------------------------------------------------------------
    # Order-list tabs (default order + 5 customer slots)
    # ------------------------------------------------------------------

    def _paint_list_tabs(self) -> None:
        for key, btn in self._list_tab_buttons.items():
            active = key == self._active_list
            btn.config(
                bg=ACCENT if active else PANEL_ALT,
                fg="#ffffff" if active else MUTED_FG,
            )

    def _save_active_list_text(self) -> None:
        """Persist the textbox into the active slot so switching never loses it."""
        lists = self._settings.setdefault("order_lists", {})
        lists[self._active_list] = self.input_text.get("1.0", "end-1c")
        self._settings["active_order_list"] = self._active_list
        game_settings.save_settings(self._settings)

    def _rebuild_also_map(self) -> None:
        self._also_map = build_also_map(
            self._active_list, LIST_DEFS, self._settings.get("order_lists", {})
        )

    def _load_active_list(self) -> None:
        """Load the active slot's saved text into the textbox and parse it.

        An empty slot stays empty on purpose - it must never be auto-filled
        from the clipboard, or every customer tab silently inherits whatever
        was last copied. Use the Paste button to fill one deliberately."""
        text = self._settings.get("order_lists", {}).get(self._active_list, "")
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", text)
        self._paint_list_tabs()
        if text.strip():
            self._parse_text()
        else:
            self._rebuild_also_map()
            self._apply_filter()

    def _switch_list(self, key: str) -> None:
        if key == self._active_list:
            return
        self._save_active_list_text()
        self._active_list = key
        self._parsed_games = []
        self._match_map = {}
        self._match_decisions = {}
        self._clear_results()
        self._load_active_list()
        self._log(f"↔ Pindah ke daftar: {dict(LIST_DEFS)[key]}")

    def _parse_text(self) -> None:
        """Parse input text and populate game list"""
        self._parsed_games = self._parse_game_text()
        self._match_decisions = {}
        self._save_active_list_text()
        self._rebuild_also_map()
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

    def _load_sample(self) -> None:
        """Load sample text"""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", SAMPLE_TEXT)
        self._parse_text()

    def _clear_inputs(self) -> None:
        """Empty the active slot - on disk too, so a list cleared here stays
        cleared instead of coming back on the next switch/restart."""
        self.input_text.delete("1.0", "end")
        self._save_active_list_text()
        self._parsed_games = []
        self._match_map = {}
        self._match_decisions = {}
        self.filter_var.set("")
        self._apply_filter()
        self._clear_results()
        self.status_text.delete("1.0", "end")
        self._update_counter()
        self._log(f"🧹 Daftar '{dict(LIST_DEFS)[self._active_list]}' dikosongkan.")

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
            self._auto_open_all_resolved_downloads()
        except Exception as e:
            self._log(f"✗ Error: {str(e)}")


if __name__ == "__main__":
    app = GameLauncherMultiSite()
    app.mainloop()
