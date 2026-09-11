"""Cleanup helper: which games in the install folder are still wanted by a
customer and which are safe to delete permanently.

"Wanted" = matches a line in any saved customer order list. Anything the live
folder scan turns up that no list asks for is safe to delete. Covers both
extracted game folders/disc images and not-yet-extracted archives sitting in
Downloads. No history log - folder contents and the order lists are the only
truth (same rule as game_folder_scan.py).

A game already copied to the ONE customer who ordered it no longer needs to
block deletion - so classify() can optionally live-scan one customer's HDD
folder and, for titles actually found there, drop that customer from the
"still wanted" list. If a *different* customer also ordered it and hasn't
been verified delivered, the game still shows as blocked - that's the "jangan
dihapus, masih dipesan cust lain" warning.
"""
import os
import shutil
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk

import game_folder_scan as folder_scan
import game_settings
from game_status_scanner import _create_btn, parse_order_list

from game_settings import (
    APP_BG,
    PANEL_BG,
    PANEL_ALT,
    TEXT_BG,
    ACCENT,
    ACCENT_PINK,
    OK,
    TEXT_FG,
    MUTED_FG,
    BORDER_COLOR,
)


@dataclass
class CleanupEntry:
    label: str
    path: str
    extracted: bool                       # True = extracted folder/disc, False = archive
    wanted_by: list[str] = field(default_factory=list)
    delivered_to: list[str] = field(default_factory=list)  # customers confirmed to already have it on their HDD

    @property
    def deletable(self) -> bool:
        return not self.wanted_by


def classify(
    scan_roots: list[str],
    downloads_folder: str,
    order_lists: dict[str, str],
    release_suffixes: list[str] | None = None,
    threshold: float = 0.72,
    verify_customer: str | None = None,
    verify_folder: str = "",
) -> list[CleanupEntry]:
    """One CleanupEntry per real folder/file in the scan roots + Downloads,
    tagged with which customer slots (if any) still want it.

    verify_customer/verify_folder: optionally live-scan one customer's HDD
    folder. A title from that customer's order list found there counts as
    already delivered - it no longer blocks deletion on its own, though
    another customer still wanting it (unverified) does.
    """
    extracted_index = folder_scan.scan_extracted_folders(scan_roots)
    downloads_index = folder_scan.scan_downloads_folder(downloads_folder, release_suffixes)
    hdd_index = folder_scan.scan_extracted_folder(verify_folder) if verify_folder else {}

    entries: dict[str, CleanupEntry] = {}
    for _norm, (label, path) in extracted_index.items():
        entries[path] = CleanupEntry(label, path, True)
    for _norm, (label, path) in downloads_index.items():
        entries.setdefault(path, CleanupEntry(label, path, False))

    for key, disp in game_settings.LIST_DEFS:
        short = disp.split(" ", 1)[-1] if " " in disp else disp
        for title in parse_order_list(order_lists.get(key, "") or ""):
            match = folder_scan.match_title(title, extracted_index, downloads_index, threshold)
            entry = entries.get(match.matched_path or "")
            if entry is None:
                continue
            delivered = (
                key == verify_customer
                and hdd_index
                and folder_scan.match_title(title, hdd_index, {}, threshold).status == folder_scan.STATUS_EXTRACTED
            )
            if delivered:
                if short not in entry.delivered_to:
                    entry.delivered_to.append(short)
            elif short not in entry.wanted_by:
                entry.wanted_by.append(short)

    return sorted(entries.values(), key=lambda e: (not e.deletable, e.label.lower()))


def delete_entry(path: str) -> None:
    """Permanent delete - no Recycle Bin. Folder or single file."""
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


class GameCleanupPanel(tk.Frame):
    """Embeddable panel: scan the install folder, mark keep/delete against every
    saved order list, delete the safe ones permanently from here."""

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, bg=APP_BG)
        self._entries: list[CleanupEntry] = []
        self._row_map: dict[str, CleanupEntry] = {}
        self._customers = [(k, d) for k, d in game_settings.LIST_DEFS if k.startswith("cust")]
        self._label_to_key = {d: k for k, d in self._customers}
        self._verify_customer = tk.StringVar(value=self._customers[0][1])
        self._verify_folder = tk.StringVar(value="")
        self._build_ui()
        self._load_verify_folder_for_customer()

    def _build_ui(self) -> None:
        top = tk.Frame(self, bg=APP_BG)
        top.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(
            top,
            text="Hanya scan folder game LOKAL (bukan HDD eksternal). Game yang tidak ada di "
            "daftar pesanan customer mana pun = BOLEH DIHAPUS. Isi dulu semua slot pesanan "
            "di tab Downloader, lalu scan di sini. Mau hapus game yang SUDAH dikirim ke HDD "
            "customer? Pilih customer + folder HDD-nya di bawah dulu - game yang sudah pasti "
            "ada di HDD itu ikut boleh dihapus, KECUALI masih dipesan customer lain juga.",
            font=("Segoe UI", 9), fg=MUTED_FG, bg=APP_BG, anchor="w", justify="left", wraplength=1100,
        ).pack(fill="x")

        verify_row = tk.Frame(self, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        verify_row.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(
            verify_row, text="✅ Sudah dikirim ke HDD:", font=("Segoe UI", 9, "bold"),
            fg=TEXT_FG, bg=PANEL_BG,
        ).pack(side="left", padx=(12, 6), pady=8)
        customer_box = ttk.Combobox(
            verify_row, textvariable=self._verify_customer, state="readonly", width=12,
            values=[d for _k, d in self._customers],
        )
        customer_box.pack(side="left", pady=8)
        customer_box.bind("<<ComboboxSelected>>", lambda _e: self._load_verify_folder_for_customer())
        tk.Label(
            verify_row, textvariable=self._verify_folder, font=("Consolas", 9),
            fg=MUTED_FG, bg=PANEL_BG, anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(10, 8), pady=8)
        _create_btn(verify_row, text="Pilih Folder HDD...", command=self._choose_verify_folder, side="right", padx=(0, 12), pady=6)

        bar = tk.Frame(self, bg=APP_BG)
        bar.pack(fill="x", padx=20, pady=(0, 10))
        _create_btn(bar, text="🔍  SCAN SEKARANG", command=self._scan, style_type="accent", side="left")
        _create_btn(bar, text="Pilih Semua yang Boleh Dihapus", command=self._select_deletable, side="left", padx=(8, 0))
        _create_btn(bar, text="🗑  Hapus Permanen (Terpilih)", command=self._delete_selected, style_type="accent_pink", side="right")
        self._summary = tk.Label(bar, text="Belum discan", font=("Segoe UI", 10, "bold"), fg=MUTED_FG, bg=APP_BG)
        self._summary.pack(side="right", padx=(0, 14))

        table_frame = tk.Frame(self, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_COLOR)
        table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Cleanup.Treeview", background=TEXT_BG, fieldbackground=TEXT_BG, foreground=TEXT_FG,
                        borderwidth=0, rowheight=30, font=("Segoe UI", 10))
        style.configure("Cleanup.Treeview.Heading", background=PANEL_ALT, foreground="#f8fafc",
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Cleanup.Treeview", background=[("selected", "#4f46e5")], foreground=[("selected", "#ffffff")])

        scroll = ttk.Scrollbar(table_frame, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            table_frame, columns=("no", "game", "kind", "decision", "path"),
            show="headings", selectmode="extended", yscrollcommand=scroll.set, style="Cleanup.Treeview",
        )
        for col, text, width, anchor in (
            ("no", "No", 44, "center"),
            ("game", "Nama Folder / File", 340, "w"),
            ("kind", "Status Ekstrak", 150, "w"),
            ("decision", "Keputusan", 320, "w"),
            ("path", "Lokasi", 360, "w"),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.tree.yview)
        self.tree.tag_configure("delete", foreground="#6ee7b7")
        self.tree.tag_configure("keep", foreground="#f87171")

    def _verify_customer_key(self) -> str:
        return self._label_to_key.get(self._verify_customer.get(), self._customers[0][0])

    def _load_verify_folder_for_customer(self) -> None:
        s = game_settings.load_settings()
        saved = (s.get("customer_hdd_folders", {}) or {}).get(self._verify_customer_key(), "")
        self._verify_folder.set(saved)

    def _choose_verify_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Pilih folder HDD customer yang sudah dikirim")
        if not chosen:
            return
        self._verify_folder.set(chosen)
        s = game_settings.load_settings()
        folders = dict(s.get("customer_hdd_folders", {}) or {})
        folders[self._verify_customer_key()] = chosen
        s["customer_hdd_folders"] = folders
        game_settings.save_settings(s)

    def _scan(self) -> None:
        s = game_settings.load_settings()
        # Local install folder only - never the external HDD (extracted_root_2).
        # Deleting off someone's plugged-in drive here would be too easy a mistake.
        local = s.get("extracted_root", "")
        roots = [local] if local and os.path.isdir(local) else []
        downloads = s.get("downloads_folder", "")
        if not roots and not (downloads and os.path.isdir(downloads)):
            messagebox.showwarning("Folder Belum Diatur", "Atur folder game / Downloads dulu di Settings.")
            return

        verify_folder = self._verify_folder.get().strip()
        if verify_folder and not os.path.isdir(verify_folder):
            messagebox.showwarning("Folder HDD Tidak Ditemukan", f"Folder tidak ada:\n{verify_folder}")
            return
        verify_customer = self._verify_customer_key() if verify_folder else None

        self._summary.config(text="Sedang scan...", fg=ACCENT)

        def worker() -> None:
            entries = classify(
                roots, downloads, s.get("order_lists", {}) or {},
                s.get("release_suffixes"), s.get("fuzzy_threshold", 0.72),
                verify_customer=verify_customer, verify_folder=verify_folder,
            )
            self.after(0, lambda: self._render(entries))

        threading.Thread(target=worker, daemon=True).start()

    def _render(self, entries: list[CleanupEntry]) -> None:
        self._entries = entries
        self._row_map.clear()
        self.tree.delete(*self.tree.get_children())

        deletable = 0
        for i, e in enumerate(entries, 1):
            if e.deletable:
                decision, tag = "🟢 BOLEH DIHAPUS", "delete"
                if e.delivered_to:
                    decision += " - sudah dikirim ke " + ", ".join(e.delivered_to)
                deletable += 1
            else:
                decision, tag = "🔴 JANGAN - dipesan " + ", ".join(e.wanted_by), "keep"
                if e.delivered_to:
                    decision += " (sudah dikirim ke " + ", ".join(e.delivered_to) + ")"
            kind = "✅ Sudah diekstrak" if e.extracted else "📦 Belum (arsip)"
            iid = self.tree.insert("", "end", values=(i, e.label, kind, decision, e.path), tags=(tag,))
            self._row_map[iid] = e

        self._summary.config(
            text=f"🟢 {deletable} boleh dihapus   🔴 {len(entries) - deletable} dipakai   (total {len(entries)})",
            fg=TEXT_FG,
        )

    def _select_deletable(self) -> None:
        self.tree.selection_set([iid for iid, e in self._row_map.items() if e.deletable])

    def _delete_selected(self) -> None:
        chosen = [self._row_map[i] for i in self.tree.selection() if i in self._row_map]
        if not chosen:
            messagebox.showinfo("Hapus", "Pilih dulu baris yang mau dihapus.")
            return

        preview = "\n".join(f"• {e.label}" for e in chosen[:15])
        if len(chosen) > 15:
            preview += f"\n… +{len(chosen) - 15} lagi"
        msg = (
            f"Hapus PERMANEN {len(chosen)} item?\n(langsung terhapus, TIDAK masuk Recycle Bin)\n\n{preview}"
        )
        kept = [e for e in chosen if not e.deletable]
        if kept:
            msg += f"\n\n⚠  {len(kept)} di antaranya MASIH DIPESAN customer!"
        if not messagebox.askyesno("Hapus Permanen", msg):
            return

        done = 0
        for e in chosen:
            try:
                delete_entry(e.path)
                done += 1
            except OSError as exc:
                messagebox.showerror("Gagal Hapus", f"{e.label}:\n{exc}")
        messagebox.showinfo("Selesai", f"{done}/{len(chosen)} item dihapus.")
        self._scan()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Bersih-bersih Folder Game")
    root.geometry("1280x720")
    root.configure(bg=APP_BG)
    GameCleanupPanel(root).pack(fill="both", expand=True)
    root.mainloop()
