import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import pyperclip

from game_scraper_multi_site import open_game_search_tabs


APP_BG = "#111827"
PANEL_BG = "#0f172a"
TEXT_BG = "#020617"
ACCENT = "#ec4899"
TEXT_FG = "#e5e7eb"
MUTED_FG = "#cbd5e1"

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

        style.configure(
            "TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(12, 8),
            background="#1f2937",
            foreground="#f9fafb",
            borderwidth=0,
        )
        style.map(
            "TButton",
            background=[("active", "#374151"), ("disabled", "#111827")],
            foreground=[("disabled", "#6b7280")],
        )

        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(12, 8),
            background=ACCENT,
            foreground="#ffffff",
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#f43f5e"), ("disabled", "#7f1d1d")],
            foreground=[("disabled", "#fecdd3")],
        )

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
        left_panel = tk.Frame(body, bg=PANEL_BG, bd=1, relief="solid")
        left_panel.pack(side="left", fill="both", expand=False)
        left_panel.configure(width=550)
        left_panel.pack_propagate(False)

        left_header = tk.Frame(left_panel, bg=PANEL_BG)
        left_header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            left_header,
            text="Paste Game Text",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")

        tk.Label(
            left_header,
            text="Game dengan (PS2) → romsfun | Tanpa tag → steamrip",
            font=("Segoe UI", 9),
            fg=MUTED_FG,
            bg=PANEL_BG,
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        button_row = tk.Frame(left_header, bg=PANEL_BG)
        button_row.pack(fill="x", pady=(10, 0))

        ttk.Button(button_row, text="Parse Text", style="Accent.TButton", command=self._parse_text).pack(side="left")
        ttk.Button(button_row, text="Paste Clipboard", command=self._paste_clipboard).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Auto Load", command=self._load_initial_text).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Load Sample", command=self._load_sample).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Clear", command=self._clear_inputs).pack(side="right")

        text_frame = tk.Frame(left_panel, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=False, padx=14)

        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        text_scroll.pack(side="right", fill="y")

        self.input_text = tk.Text(
            text_frame,
            height=20,
            wrap="word",
            yscrollcommand=text_scroll.set,
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground="#f8fafc",
            relief="flat",
            font=("Consolas", 10),
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        text_scroll.config(command=self.input_text.yview)

        # Right Panel - Game List & Controls
        right_panel = tk.Frame(body, bg=PANEL_BG, bd=1, relief="solid")
        right_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))

        right_header = tk.Frame(right_panel, bg=PANEL_BG)
        right_header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            right_header,
            text="Parsed Games",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")

        # Filter section
        filter_frame = tk.Frame(right_panel, bg=PANEL_BG)
        filter_frame.pack(fill="x", padx=14, pady=(0, 8))

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
            insertbackground="#f8fafc",
            relief="flat",
            font=("Segoe UI", 10),
        )
        filter_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # Selection counter
        self.counter_label = tk.Label(
            filter_frame,
            text="Selected: 0/0",
            font=("Segoe UI", 9),
            fg=ACCENT,
            bg=PANEL_BG,
        )
        self.counter_label.pack(side="right", padx=(8, 0))

        # Game list with scrollbar
        list_frame = tk.Frame(right_panel, bg=PANEL_BG)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

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
            highlightthickness=0,
        )
        self.game_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.game_listbox.yview)
        self.game_listbox.bind("<<ListboxSelect>>", lambda event: self._update_counter())

        # Control section
        control_frame = tk.Frame(right_panel, bg=PANEL_BG)
        control_frame.pack(fill="x", padx=14, pady=(0, 14))

        ttk.Button(control_frame, text="Select All", command=self._select_all).pack(side="left")
        ttk.Button(control_frame, text="Deselect All", command=self._deselect_all).pack(side="left", padx=(8, 0))

        # Status section
        status_frame = tk.Frame(right_panel, bg=PANEL_BG)
        status_frame.pack(fill="x", padx=14, pady=(0, 14))

        tk.Label(
            status_frame,
            text="Status:",
            font=("Segoe UI", 9),
            fg=TEXT_FG,
            bg=PANEL_BG,
        ).pack(anchor="w")

        self.status_text = tk.Text(
            status_frame,
            height=6,
            wrap="word",
            bg=TEXT_BG,
            fg=TEXT_FG,
            relief="flat",
            font=("Consolas", 9),
        )
        self.status_text.pack(fill="both", expand=True, pady=(4, 0))

        # Action buttons
        button_frame = tk.Frame(right_panel, bg=PANEL_BG)
        button_frame.pack(fill="x", padx=14, pady=(0, 14))

        ttk.Button(
            button_frame,
            text="Start Selected",
            style="Accent.TButton",
            command=self._start_selected,
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            button_frame,
            text="Run All",
            style="Accent.TButton",
            command=self._start_all,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

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
            )
            self._log("✓ All downloads completed!")
        except Exception as e:
            self._log(f"✗ Error: {str(e)}")


if __name__ == "__main__":
    app = GameLauncherMultiSite()
    app.mainloop()
