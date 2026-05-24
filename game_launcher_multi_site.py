import re
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable
import pyperclip

from game_scraper_multi_site import open_game_search_tabs


APP_BG = "#090d16"      # Deep Midnight Black
PANEL_BG = "#151c2c"    # Card/Panel Slate Blue/Gray
TEXT_BG = "#0c101b"     # Input/Listbox/Table Deep Navy Black
ACCENT = "#6366f1"      # Primary Indigo Accent
ACCENT_PINK = "#db2777" # Pink Accent for start/highlight
TEXT_FG = "#f1f5f9"     # Clean White/Slate 100
MUTED_FG = "#94a3b8"    # Muted Gray/Slate 400
BORDER_COLOR = "#334155" # Subtle border color

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
        self.title("Game Launcher - Multi Site")
        self.geometry("1400x780")
        self.minsize(1280, 700)

        self._worker_thread: threading.Thread | None = None
        self._pause_event: threading.Event | None = None
        self._parsed_games: list[tuple[str, str]] = []  # (game_name, site_type)
        self._filtered_games: list[tuple[str, str]] = []
        self._resolved_rows: list[dict[str, str | None]] = []

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
            rowheight=32,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#1e293b",
            foreground="#f8fafc",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
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
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
        )
        
        # Hover colors
        btn.bind("<Enter>", lambda e: btn.config(bg=active_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        
        if pack_kwargs:
            btn.pack(**pack_kwargs)
        return btn

    def _build_ui(self) -> None:
        self.configure(bg=APP_BG)

        header = tk.Frame(self, bg=APP_BG)
        header.pack(fill="x", padx=20, pady=(20, 10))

        tk.Label(
            header,
            text="Game Launcher - Multi Site",
            font=("Segoe UI", 24, "bold"),
            fg="#f9fafb",
            bg=APP_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Paste game list. Tag (PS2) → romsfun.com | No tag → steamrip.com",
            font=("Segoe UI", 10),
            fg=MUTED_FG,
            bg=APP_BG,
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=10)

        # Left Panel - Input
        left_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        left_panel.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left_panel.configure(width=500)
        left_panel.pack_propagate(False)

        left_header = tk.Frame(left_panel, bg=PANEL_BG)
        left_header.pack(fill="x", padx=14, pady=(14, 8))

        # Title bar with vertical accent bar
        left_title_bar = tk.Frame(left_header, bg=PANEL_BG)
        left_title_bar.pack(anchor="w")
        accent_strip_left = tk.Frame(left_title_bar, bg=ACCENT, width=4, height=18)
        accent_strip_left.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            left_title_bar,
            text="Paste Game Text",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=PANEL_BG,
        ).pack(side="left")

        tk.Label(
            left_header,
            text="Game dengan (PS2) → romsfun | Tanpa tag → steamrip",
            font=("Segoe UI", 9),
            fg=MUTED_FG,
            bg=PANEL_BG,
            wraplength=470,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        button_row = tk.Frame(left_header, bg=PANEL_BG)
        button_row.pack(fill="x", pady=(10, 0))

        self._create_btn(button_row, text="Parse Text", command=self._parse_text, style_type="accent", side="left")
        self._create_btn(button_row, text="Paste Clipboard", command=self._paste_clipboard, side="left", padx=(8, 0))
        self._create_btn(button_row, text="Auto Load", command=self._load_initial_text, side="left", padx=(8, 0))
        self._create_btn(button_row, text="Load Sample", command=self._load_sample, side="left", padx=(8, 0))
        self._create_btn(button_row, text="Clear", command=self._clear_inputs, side="right")

        text_frame = tk.Frame(left_panel, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

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
            font=("Consolas", 10),
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=self.input_text.yview)

        # Right Panel - Game List & Controls
        right_panel = tk.Frame(body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        right_panel.pack(side="right", fill="both", expand=True)

        right_header = tk.Frame(right_panel, bg=PANEL_BG)
        right_header.pack(side="top", fill="x", padx=14, pady=(14, 8))

        # Title bar with vertical accent bar
        right_title_bar = tk.Frame(right_header, bg=PANEL_BG)
        right_title_bar.pack(anchor="w")
        accent_strip_right = tk.Frame(right_title_bar, bg=ACCENT, width=4, height=18)
        accent_strip_right.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            right_title_bar,
            text="Parsed Games",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=PANEL_BG,
        ).pack(side="left")

        # Pack bottom elements first (from bottom to top) to ensure they are never pushed out
        
        # 1. Action buttons at the very bottom
        button_frame = tk.Frame(right_panel, bg=PANEL_BG)
        button_frame.pack(side="bottom", fill="x", padx=14, pady=(0, 14))

        self._create_btn(
            button_frame,
            text="Start Selected",
            command=self._start_selected,
            style_type="accent",
            side="left",
            fill="x",
            expand=True,
        )

        self._create_btn(
            button_frame,
            text="Run All",
            command=self._start_all,
            style_type="accent_pink",
            side="left",
            fill="x",
            expand=True,
            padx=(8, 0),
        )

        self._create_btn(
            button_frame,
            text="Open Link",
            command=self._open_selected_result,
            side="right",
        )

        self._create_btn(
            button_frame,
            text="Copy Link",
            command=self._copy_selected_result,
            side="right",
            padx=(0, 8),
        )

        self._create_btn(
            button_frame,
            text="Close Steamrip",
            command=self._close_steamrip_windows,
            side="right",
            padx=(0, 8),
        )

        # 2. Status section just above buttons
        status_frame = tk.Frame(right_panel, bg=PANEL_BG)
        status_frame.pack(side="bottom", fill="x", padx=14, pady=(0, 14))

        status_title_bar = tk.Frame(status_frame, bg=PANEL_BG)
        status_title_bar.pack(anchor="w", pady=(0, 4))
        accent_strip_status = tk.Frame(status_title_bar, bg=ACCENT, width=4, height=16)
        accent_strip_status.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            status_title_bar,
            text="Status Log",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_FG,
            bg=PANEL_BG,
        ).pack(side="left")

        self.status_text = tk.Text(
            status_frame,
            height=4,  # Reduced from 6 to 4 to save vertical space
            wrap="word",
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            font=("Consolas", 9),
        )
        self.status_text.pack(fill="both", expand=True)

        # 3. Resolved host links table just above status
        result_frame = tk.Frame(right_panel, bg=PANEL_BG)
        result_frame.pack(side="bottom", fill="both", expand=False, padx=14, pady=(0, 14))

        table_title_bar = tk.Frame(result_frame, bg=PANEL_BG)
        table_title_bar.pack(anchor="w", pady=(0, 4))
        accent_strip_table = tk.Frame(table_title_bar, bg=ACCENT_PINK, width=4, height=16)
        accent_strip_table.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            table_title_bar,
            text="Resolved Host Links",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_FG,
            bg=PANEL_BG,
        ).pack(side="left")

        result_table_frame = tk.Frame(result_frame, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR, bd=0)
        result_table_frame.pack(fill="both", expand=True)

        result_scroll = ttk.Scrollbar(result_table_frame, orient="vertical")
        result_scroll.pack(side="right", fill="y")

        self.result_tree = ttk.Treeview(
            result_table_frame,
            columns=("game", "site", "host", "link"),
            show="headings",
            height=4,  # Reduced from 6 to 4 to save vertical space
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
        self.result_tree.bind("<<TreeviewSelect>>", lambda event: self._update_counter())
        self.result_tree.bind("<Double-1>", lambda event: self._open_selected_result())

        # 4. Control section just above table
        control_frame = tk.Frame(right_panel, bg=PANEL_BG)
        control_frame.pack(side="bottom", fill="x", padx=14, pady=(0, 14))

        self._create_btn(control_frame, text="Select All", command=self._select_all, side="left")
        self._create_btn(control_frame, text="Deselect All", command=self._deselect_all, side="left", padx=(8, 0))

        # 5. Filter section (packed from top, below right_header)
        filter_frame = tk.Frame(right_panel, bg=PANEL_BG)
        filter_frame.pack(side="top", fill="x", padx=14, pady=(0, 8))

        tk.Label(
            filter_frame,
            text="Filter:",
            font=("Segoe UI", 9),
            fg=TEXT_FG,
            bg=PANEL_BG,
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
        filter_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.counter_label = tk.Label(
            filter_frame,
            text="Selected: 0/0",
            font=("Segoe UI", 9, "bold"),
            fg=ACCENT_PINK,
            bg=PANEL_BG,
        )
        self.counter_label.pack(side="right", padx=(8, 0))

        # 6. Remaining middle space is list_frame for the Listbox (packed from top with expand=True)
        list_frame = tk.Frame(right_panel, bg=PANEL_BG)
        list_frame.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 8))

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.game_listbox = tk.Listbox(
            list_frame,
            bg=TEXT_BG,
            fg=TEXT_FG,
            selectmode="multiple",
            yscrollcommand=scrollbar.set,
            relief="flat",
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT,
            selectbackground=ACCENT,
            selectforeground="#ffffff",
        )
        self.game_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.game_listbox.yview)
        self.game_listbox.bind("<<ListboxSelect>>", lambda event: self._update_counter())

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
        # Remove numbering (1. → "")
        title = re.sub(r"^\d+\.\s+", "", title)
        # Remove PS2 tag
        title = re.sub(r"\s*\(PS2\)\s*", "", title)
        # Sanitize dashes and apostrophes
        for dash in ("-", "–", "—"):
            title = title.replace(dash, " ")
        for apostrophe in ("'", "'"):
            title = title.replace(apostrophe, "")
        # Clean up
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

            # Check if this is a PS2 game
            is_ps2 = "(PS2)" in line
            
            # Normalize title
            title = self._normalize_parsed_title(line)
            if title:
                site_type = "romsfun" if is_ps2 else "steamrip"
                games.append((title, site_type))

        return games

    def _apply_filter(self) -> None:
        """Apply search filter to game list"""
        filter_text = self.filter_var.get().lower()
        self.game_listbox.delete(0, "end")

        self._filtered_games = [
            (name, site) for name, site in self._parsed_games
            if filter_text in name.lower()
        ]

        for name, site in self._filtered_games:
            display = f"[{site.upper()}] {name}"
            self.game_listbox.insert("end", display)

        self._update_counter()

    def _update_counter(self) -> None:
        """Update selection counter"""
        selected = len(self.game_listbox.curselection())
        total = self.game_listbox.size()
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

    def _select_all(self) -> None:
        """Select all games in filtered list"""
        self.game_listbox.select_set(0, "end")
        self._update_counter()

    def _deselect_all(self) -> None:
        """Deselect all games"""
        self.game_listbox.selection_clear(0, "end")
        self._update_counter()

    def _log(self, message: str) -> None:
        """Add message to status log"""
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.update()

    def _show_pause_dialog(self, message: str) -> None:
        """Show pause dialog during download"""
        result = messagebox.showinfo(
            "Manual Action Required",
            f"{message}\n\nClick OK when ready to continue.",
        )

    def _parse_text(self) -> None:
        """Parse input text and populate game list"""
        self._parsed_games = self._parse_game_text()
        self.filter_var.set("")
        self._apply_filter()
        self._clear_results()
        self._log(f"Parsed {len(self._parsed_games)} games")

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
        self.game_listbox.delete(0, "end")
        self._parsed_games = []
        self._filtered_games = []
        self._clear_results()
        self.filter_var.set("")
        self.status_text.delete("1.0", "end")
        self._update_counter()

    def _start_selected(self) -> None:
        """Start downloads for selected games"""
        selected_indices = self.game_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select games to download")
            return

        selected_games = [self._filtered_games[i] for i in selected_indices]
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
