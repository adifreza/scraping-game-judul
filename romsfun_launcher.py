import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from open_romsfun_tabs import open_game_search_tabs


APP_BG = "#111827"
PANEL_BG = "#0f172a"
TEXT_BG = "#020617"
ACCENT = "#ec4899"
TEXT_FG = "#e5e7eb"
MUTED_FG = "#cbd5e1"

SAMPLE_TEXT = """Daftar Game Pesanan

1. Ghost Rider (PS2)
2. FIFA Street 2 (PS2)
3. Guitar Hero II (PS2)
4. Need for Speed - Most Wanted (and Black Edition) (PS2)
5. PES 6 Absolute Patch 2006 (PS2)
6. PES 2013: Pro Evolution Soccer (PS2)
7. Grand Theft Auto San Andreas Remastered (PS2)
8. Grand Theft Auto San Andreas Upin & Ipin (PS2)
9. GTA San Andreas Opera Van Java (PS2)
10. Burnout 3 - Takedown (PS2)
11. WRC - World Rally Championship (PS2)
12. Call of Duty 3 (PS2)
13. Captain Tsubasa (PS2)
14. Conflict: Desert Storm II - Back to Baghdad (PS2)
15. Conflict: Global Terror (PS2)
16. Freedom Fighters (PS2)
17. FIFA 14: Legacy Edition (PS2)
18. Grand Theft Auto: Vice City (PS2)
19. Gran Turismo 4 Spec II (PS2)
20. NBA Street V3 (PS2)
21. MotoGP 3 (PS2)
22. MotoGP 4 (PS2)
23. Motocross Mania 3 (PS2)
24. Tenchu: Wrath of Heaven (PS2)
25. Shadow of the Colossus (PS2)
26. Tony Hawk's Underground (PS2)
27. Okami (PS2)
28. Marvel - Ultimate Alliance 2 (PS2)
29. Twisted Metal - Black (PS2)
30. Crash Nitro Kart (PS2)
31. Devil May Cry 3: Dante's Awakening (PS2)
32. eFootball 2026 (PS2)
33. SBK-09 Superbike World Championship (PS2)
34. Yakuza 2 (PS2)
35. Need for Speed - Hot Pursuit 2 (PS2)
36. Super Bomba Patch 2026 (PS2)
37. Jet Li: Rise to Honor (PS2)
38. Red Dead Revolver (PS2)
39. Grand Theft Auto V Legacy (PS2)
40. Spider-Man 3 (PS2)
41. Dynasty Warriors 6 (PS2)
42. The Lord of the Rings: The Return of the King (PS2)
43. Disney-Pixar Cars (PS2)
44. Auto Modellista (PS2)
45. Sonic Unleashed (PS2)
46. Ben 10 - Alien Force - Vilgax Attacks (PS2)
47. Jak 3 (PS2)
48. Formula One 06 (PS2)

Total Size: 114.5 GB"""


class RomsFunLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RomsFun Launcher")
        self.geometry("1220x760")
        self.minsize(1120, 680)

        self._worker_thread: threading.Thread | None = None
        self._pause_event: threading.Event | None = None
        self._parsed_games: list[str] = []
        self._filtered_games: list[str] = []

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
            text="RomsFun PS2 Launcher",
            font=("Segoe UI", 24, "bold"),
            fg="#f9fafb",
            bg=APP_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Paste teks daftar game. Program hanya mengambil judul yang memiliki tag PS2, lalu jalankan antrian dari hasil itu.",
            font=("Segoe UI", 10),
            fg=MUTED_FG,
            bg=APP_BG,
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self, bg=APP_BG)
        body.pack(fill="both", expand=True, padx=20, pady=10)

        left_panel = tk.Frame(body, bg=PANEL_BG, bd=1, relief="solid")
        left_panel.pack(side="left", fill="both", expand=False)
        left_panel.configure(width=520)
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
            text="Tempel teks dari foto atau daftar yang kamu copy. Hanya baris yang ada tulisan PS2 yang akan diproses.",
            font=("Segoe UI", 9),
            fg=MUTED_FG,
            bg=PANEL_BG,
            wraplength=480,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        button_row = tk.Frame(left_header, bg=PANEL_BG)
        button_row.pack(fill="x", pady=(10, 0))

        ttk.Button(button_row, text="Parse Text", style="Accent.TButton", command=self._parse_text).pack(side="left")
        ttk.Button(button_row, text="Paste Clipboard", command=self._paste_clipboard).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Auto Load Clipboard", command=self._load_initial_text).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Load Sample", command=self._load_sample).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Clear", command=self._clear_inputs).pack(side="right")

        text_frame = tk.Frame(left_panel, bg=PANEL_BG)
        text_frame.pack(fill="both", expand=False, padx=14)

        text_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        text_scroll.pack(side="right", fill="y")

        self.input_text = tk.Text(
            text_frame,
            height=18,
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

        parse_summary = tk.Frame(left_panel, bg=PANEL_BG)
        parse_summary.pack(fill="x", padx=14, pady=(10, 0))

        self.parse_var = tk.StringVar(value="Parsed 0 game title(s)")
        self.preview_var = tk.StringVar(value="Preview: 0 PS2 title(s) ready")
        self.selected_var = tk.StringVar(value="Selected: 0")
        tk.Label(
            parse_summary,
            textvariable=self.parse_var,
            font=("Segoe UI", 10, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")
        tk.Label(
            parse_summary,
            textvariable=self.preview_var,
            font=("Segoe UI", 9),
            fg=MUTED_FG,
            bg=PANEL_BG,
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            parse_summary,
            textvariable=self.selected_var,
            font=("Segoe UI", 9),
            fg=MUTED_FG,
            bg=PANEL_BG,
        ).pack(anchor="w", pady=(4, 0))

        list_header = tk.Frame(left_panel, bg=PANEL_BG)
        list_header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            list_header,
            text="Parsed Titles",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")

        search_row = tk.Frame(list_header, bg=PANEL_BG)
        search_row.pack(fill="x", pady=(8, 0))

        tk.Label(
            search_row,
            text="Filter",
            font=("Segoe UI", 9, "bold"),
            fg=MUTED_FG,
            bg=PANEL_BG,
        ).pack(side="left")

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *args: self._apply_filter())
        filter_entry = ttk.Entry(search_row, textvariable=self.filter_var)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        filter_entry.insert(0, "")

        list_button_row = tk.Frame(list_header, bg=PANEL_BG)
        list_button_row.pack(fill="x", pady=(8, 0))

        ttk.Button(list_button_row, text="Select All", command=self._select_all).pack(side="left")
        ttk.Button(list_button_row, text="Select None", command=self._select_none).pack(side="left", padx=(8, 0))
        ttk.Button(list_button_row, text="Quick Start Clipboard", style="Accent.TButton", command=self._quick_start_from_clipboard).pack(side="right")
        ttk.Button(list_button_row, text="Run Selected", command=self._start_selected).pack(side="right", padx=(0, 8))

        list_frame = tk.Frame(left_panel, bg=PANEL_BG)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        list_scroll.pack(side="right", fill="y")

        self.game_listbox = tk.Listbox(
            list_frame,
            selectmode="extended",
            yscrollcommand=list_scroll.set,
            bg="#111827",
            fg=TEXT_FG,
            selectbackground=ACCENT,
            selectforeground="#ffffff",
            highlightthickness=0,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.game_listbox.pack(side="left", fill="both", expand=True)
        list_scroll.config(command=self.game_listbox.yview)
        self.game_listbox.bind("<<ListboxSelect>>", lambda event: self._update_selected_count())

        right_panel = tk.Frame(body, bg=APP_BG)
        right_panel.pack(side="right", fill="both", expand=True, padx=(16, 0))

        control_card = tk.Frame(right_panel, bg=PANEL_BG, bd=1, relief="solid")
        control_card.pack(fill="x")

        control_top = tk.Frame(control_card, bg=PANEL_BG)
        control_top.pack(fill="x", padx=14, pady=14)

        tk.Label(
            control_top,
            text="Run Control",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            control_top,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            fg=MUTED_FG,
            bg=PANEL_BG,
        ).pack(anchor="w", pady=(4, 0))

        action_row = tk.Frame(control_card, bg=PANEL_BG)
        action_row.pack(fill="x", padx=14, pady=(0, 14))

        self.run_all_button = ttk.Button(action_row, text="Run All PS2", style="Accent.TButton", command=self._start_all)
        self.run_all_button.pack(side="left")

        self.pause_button = ttk.Button(
            action_row,
            text="Continue Download Step",
            command=self._resume_from_pause,
            state="disabled",
        )
        self.pause_button.pack(side="left", padx=(8, 0))

        self.clear_button = ttk.Button(action_row, text="Clear Log", command=self._clear_log)
        self.clear_button.pack(side="right")

        log_card = tk.Frame(right_panel, bg=PANEL_BG, bd=1, relief="solid")
        log_card.pack(fill="both", expand=True, pady=(16, 0))

        log_header = tk.Frame(log_card, bg=PANEL_BG)
        log_header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            log_header,
            text="Activity Log",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg=PANEL_BG,
        ).pack(anchor="w")

        log_frame = tk.Frame(log_card, bg=PANEL_BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical")
        log_scroll.pack(side="right", fill="y")

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            height=18,
            yscrollcommand=log_scroll.set,
            bg=TEXT_BG,
            fg="#e2e8f0",
            insertbackground="#f8fafc",
            relief="flat",
            font=("Consolas", 10),
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.config(command=self.log_text.yview)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _normalize_parsed_title(self, title: str) -> str:
        cleaned = title.strip()
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
        cleaned = re.sub(r"\s*\(PS2\)\s*$", "", cleaned, flags=re.IGNORECASE)
        for dash in ("-", "–", "—"):
            cleaned = cleaned.replace(dash, " ")
        for apostrophe in ("'", "’"):
            cleaned = cleaned.replace(apostrophe, "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" -:|\t")

    def _finalize_candidate(self, candidate_parts: list[str]) -> str | None:
        combined = " ".join(candidate_parts).strip()
        if not combined:
            return None
        if not re.search(r"\bPS2\b", combined, flags=re.IGNORECASE):
            return None
        return self._normalize_parsed_title(combined)

    def _parse_game_text(self, raw_text: str) -> list[str]:
        parsed: list[str] = []
        current_item: list[str] = []

        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if re.match(r"(?i)^total\s+size\b", line):
                continue
            if re.match(r"(?i)^daftar\s+game\s+pesanan\b", line):
                continue

            numbered = re.match(r"^\s*\d+\.\s*(.+)$", line)
            if numbered:
                if current_item:
                    finalized = self._finalize_candidate(current_item)
                    if finalized:
                        parsed.append(finalized)
                    current_item = []
                current_item.append(numbered.group(1).strip())
            else:
                if current_item:
                    current_item.append(line)

        if current_item:
            finalized = self._finalize_candidate(current_item)
            if finalized:
                parsed.append(finalized)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in parsed:
            if not item:
                continue
            key = item.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        return deduped

    def _update_preview(self, parsed_games: list[str]) -> None:
        self.preview_var.set(f"Preview: {len(parsed_games)} PS2 title(s) ready")
        self.selected_var.set(f"Selected: {len(self._get_selected_games())}")

    def _refresh_parsed_list(self, parsed_games: list[str]) -> None:
        self._parsed_games = parsed_games
        self.parse_var.set(f"Parsed {len(parsed_games)} game title(s)")
        self._update_preview(parsed_games)
        self._apply_filter(select_all=True)

    def _apply_filter(self, select_all: bool = False) -> None:
        query = self.filter_var.get().strip().lower() if hasattr(self, "filter_var") else ""
        if query:
            self._filtered_games = [game for game in self._parsed_games if query in game.lower()]
        else:
            self._filtered_games = list(self._parsed_games)

        current_selection = set(self._get_selected_games())
        self.game_listbox.delete(0, tk.END)
        for game in self._filtered_games:
            self.game_listbox.insert(tk.END, game)

        if select_all and self._filtered_games:
            self.game_listbox.select_set(0, tk.END)
        else:
            for index, game in enumerate(self._filtered_games):
                if game in current_selection:
                    self.game_listbox.select_set(index)

        self.selected_var.set(f"Selected: {len(self._get_selected_games())}")

    def _update_selected_count(self) -> None:
        self.selected_var.set(f"Selected: {len(self._get_selected_games())}")

    def _load_initial_text(self) -> None:
        clipboard_text = ""
        try:
            clipboard_text = self.clipboard_get()
        except tk.TclError:
            clipboard_text = ""

        if clipboard_text and re.search(r"\bPS2\b", clipboard_text, flags=re.IGNORECASE):
            self.input_text.delete("1.0", tk.END)
            self.input_text.insert("1.0", clipboard_text)
            self._parse_text()
            self._append_log("Loaded PS2 text from clipboard.")
        else:
            self._load_sample()
            self._append_log("Clipboard empty or not PS2 text. Loaded sample list.")

    def _quick_start_from_clipboard(self) -> None:
        self._load_initial_text()
        self._start_all()

    def _load_sample(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", SAMPLE_TEXT)
        self._parse_text()

    def _paste_clipboard(self) -> None:
        try:
            clipboard_text = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("RomsFun Launcher", "Clipboard is empty or unavailable.")
            return

        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", clipboard_text)
        self._parse_text()

    def _clear_inputs(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.game_listbox.delete(0, tk.END)
        self._parsed_games = []
        self._filtered_games = []
        self.filter_var.set("")
        self.parse_var.set("Parsed 0 game title(s)")
        self.preview_var.set("Preview: 0 PS2 title(s) ready")
        self.selected_var.set("Selected: 0")

    def _parse_text(self) -> None:
        raw_text = self.input_text.get("1.0", tk.END)
        parsed_games = self._parse_game_text(raw_text)
        self._refresh_parsed_list(parsed_games)
        self._append_log(f"Parsed {len(parsed_games)} title(s) from pasted text.")

    def _append_log(self, message: str) -> None:
        def write() -> None:
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)

        self.after(0, write)

    def _set_status(self, message: str) -> None:
        self.after(0, lambda: self.status_var.set(message))

    def _select_all(self) -> None:
        self.game_listbox.select_set(0, tk.END)
        self._update_selected_count()

    def _select_none(self) -> None:
        self.game_listbox.selection_clear(0, tk.END)
        self._update_selected_count()

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _get_selected_games(self) -> list[str]:
        indices = list(self.game_listbox.curselection())
        return [self.game_listbox.get(index) for index in indices]

    def _start_all(self) -> None:
        self._parse_text()
        self._select_all()
        self._start_selected()

    def _start_selected(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            messagebox.showinfo("RomsFun Launcher", "A run is already in progress.")
            return

        selected_games = self._get_selected_games()
        if not selected_games:
            messagebox.showwarning("RomsFun Launcher", "Paste and parse game text first, then select at least one game.")
            return

        self._pause_event = threading.Event()
        self._set_controls_running(True)
        self._append_log(f"Starting run for {len(selected_games)} parsed game(s)...")
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            args=(selected_games,),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_worker(self, selected_games: list[str]) -> None:
        def log(message: str) -> None:
            self._append_log(message)

        def pause_prompt(game: str) -> None:
            self._append_log(f"Pause requested for download step: {game}")
            self._set_status(f"Waiting for manual click: {game}")
            self.after(0, self._show_pause_dialog, game)
            assert self._pause_event is not None
            self._pause_event.wait()
            self._pause_event.clear()
            self._set_status("Running")

        try:
            self._set_status("Running")
            open_game_search_tabs(selected_games, log_fn=log, pause_fn=pause_prompt)
            self._append_log("Run completed.")
            self._set_status("Done")
        except Exception as error:
            self._append_log(f"Error: {error}")
            self._set_status("Error")
        finally:
            self.after(0, lambda: self._set_controls_running(False))

    def _show_pause_dialog(self, game: str) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Manual Download Step")
        dialog.configure(bg=APP_BG)
        dialog.geometry("560x240")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Manual download step",
            font=("Segoe UI", 14, "bold"),
            fg="#f8fafc",
            bg=APP_BG,
        ).pack(anchor="w", padx=18, pady=(18, 8))

        tk.Label(
            dialog,
            text=(
                f"Game: {game}\n\n"
                "1. Saat halaman download final terbuka, klik 'Download Now' di Brave.\n"
                "2. Pastikan IDM menangkap file.\n"
                "3. Setelah mulai atau popup muncul, klik Continue."
            ),
            justify="left",
            wraplength=520,
            font=("Segoe UI", 10),
            fg=MUTED_FG,
            bg=APP_BG,
        ).pack(anchor="w", padx=18)

        button_row = tk.Frame(dialog, bg=APP_BG)
        button_row.pack(fill="x", padx=18, pady=18)

        def continue_run() -> None:
            if self._pause_event is not None:
                self._pause_event.set()
            dialog.destroy()

        ttk.Button(button_row, text="Continue", command=continue_run).pack(side="right")

    def _resume_from_pause(self) -> None:
        if self._pause_event is not None:
            self._pause_event.set()

    def _set_controls_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.after(0, lambda: self.run_all_button.configure(state=state))
        self.after(0, lambda: self.clear_button.configure(state=state))
        self.after(0, lambda: self.pause_button.configure(state="normal" if running else "disabled"))

    def _on_close(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            if not messagebox.askyesno("RomsFun Launcher", "A run is still active. Close anyway?"):
                return
        self.destroy()


if __name__ == "__main__":
    app = RomsFunLauncher()
    app.mainloop()
