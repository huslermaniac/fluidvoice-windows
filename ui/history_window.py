"""
ui/history_window.py — FluidVoice Windows
Transcription history viewer with stats header.
Equivalent of the History & Stats view in ContentView.swift.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk  # type: ignore[import]
import pyperclip              # type: ignore[import]

from history import history_store


# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

BG       = "#0f0f13"
CARD_BG  = "#1a1a22"
BORDER   = "#2d2d3e"
ACCENT   = "#6c63ff"
TEXT_PRI = "#f0f0f5"
TEXT_SEC = "#8888aa"
SUCCESS  = "#4ade80"

FONT_H1    = ("Segoe UI", 18, "bold")
FONT_H2    = ("Segoe UI", 13, "bold")
FONT_BODY  = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO  = ("Consolas", 11)


# ---------------------------------------------------------------------------
# HistoryWindow
# ---------------------------------------------------------------------------

class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("FluidVoice — History & Stats")
        self.geometry("760x580")
        self.minsize(600, 400)
        self.configure(fg_color=BG)
        self.lift()
        self.focus_force()

        self._build()

    def _build(self) -> None:
        # Stats header
        stats = history_store.today_stats()
        header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=80)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(expand=True)

        for label, value in [
            ("Dictations Today", str(stats["count"])),
            ("Words Spoken", str(stats["words"])),
            ("Time Recorded", f"{int(stats['duration_sec'] // 60)}m {int(stats['duration_sec'] % 60)}s"),
        ]:
            col = ctk.CTkFrame(inner, fg_color="transparent")
            col.pack(side="left", padx=32, pady=16)
            ctk.CTkLabel(col, text=value, font=("Segoe UI", 22, "bold"), text_color=ACCENT).pack()
            ctk.CTkLabel(col, text=label, font=FONT_SMALL, text_color=TEXT_SEC).pack()

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(12, 0))

        ctk.CTkLabel(toolbar, text="Transcription History", font=FONT_H2, text_color=TEXT_PRI).pack(side="left")

        ctk.CTkButton(
            toolbar, text="Clear All",
            font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1, height=30, width=80,
            command=self._clear_history,
        ).pack(side="right")

        ctk.CTkButton(
            toolbar, text="↻ Refresh",
            font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1, height=30, width=80,
            command=self._refresh,
        ).pack(side="right", padx=(0, 8))

        # Scroll list
        self._list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self._list_frame.pack(fill="both", expand=True, padx=20, pady=12)

        self._render_entries()

    def _render_entries(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

        entries = history_store.get_all()
        if not entries:
            ctk.CTkLabel(
                self._list_frame,
                text="No transcriptions yet.\nPress your hotkey anywhere to start dictating.",
                font=FONT_BODY, text_color=TEXT_SEC, justify="center",
            ).pack(expand=True, pady=60)
            return

        for entry in entries:
            card = ctk.CTkFrame(self._list_frame, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4)

            # Top row: timestamp + model badge
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(top, text=entry.timestamp_display, font=FONT_SMALL, text_color=TEXT_SEC).pack(side="left")
            ctk.CTkLabel(top, text=f"  {entry.model}  ", font=FONT_SMALL, text_color=ACCENT,
                         fg_color="#1e1e30", corner_radius=4).pack(side="right")

            # Main text
            display = entry.enhanced_text if entry.enhanced_text else entry.text
            ctk.CTkLabel(
                card, text=display,
                font=FONT_BODY, text_color=TEXT_PRI, anchor="w",
                wraplength=640, justify="left",
            ).pack(anchor="w", padx=12, pady=(4, 4))

            # Bottom row: stats + copy button
            bot = ctk.CTkFrame(card, fg_color="transparent")
            bot.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkLabel(bot, text=f"{entry.word_count} words  ·  {entry.duration_sec:.1f}s",
                         font=FONT_SMALL, text_color=TEXT_SEC).pack(side="left")
            ctk.CTkButton(
                bot, text="Copy",
                font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
                border_color=BORDER, border_width=1, height=24, width=60,
                command=lambda t=display: self._copy(t),
            ).pack(side="right")

    def _copy(self, text: str) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass

    def _clear_history(self) -> None:
        history_store.clear()
        self._render_entries()

    def _refresh(self) -> None:
        self._render_entries()
