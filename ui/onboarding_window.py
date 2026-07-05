"""
ui/onboarding_window.py — FluidVoice Windows
First-run setup wizard: choose a model, set hotkey, done.
Equivalent of the onboarding flow in ContentView.swift.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Callable

import customtkinter as ctk  # type: ignore[import]

from settings import settings
from transcription import WHISPER_MODELS, transcription_service


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
DANGER   = "#ff4d6d"

FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_H2    = ("Segoe UI", 14, "bold")
FONT_BODY  = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)


# ---------------------------------------------------------------------------
# OnboardingWindow
# ---------------------------------------------------------------------------

class OnboardingWindow(ctk.CTkToplevel):
    """3-step onboarding: Welcome → Model → Hotkey → Done."""

    def __init__(self, parent: tk.Misc, on_complete: Callable[[], None]) -> None:
        super().__init__(parent)
        self.title("Welcome to FluidVoice")
        self.geometry("600x560")
        self.resizable(False, True)
        self.configure(fg_color=BG)

        # Force window to front on Windows (CTkToplevel can appear behind other windows)
        self.attributes("-topmost", True)
        self.deiconify()
        self.lift()
        self.focus_force()
        # After a short delay, allow other windows to go on top again
        self.after(1000, lambda: self.attributes("-topmost", False))

        self.grab_set()  # Modal

        self._on_complete = on_complete
        self._step = 0

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # IMPORTANT: nav_frame must be packed BEFORE content.
        # tkinter pack() assigns space in the order widgets are packed.
        # If content (expand=True) packs first it consumes all available space
        # and the nav bar gets squashed to zero height.
        self._nav_frame = ctk.CTkFrame(self, fg_color=CARD_BG, height=70, corner_radius=0)
        self._nav_frame.pack(side="bottom", fill="x")
        self._nav_frame.pack_propagate(False)

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=40, pady=(24, 8))

        self._build_nav()
        self._show_step(0)

    # ------------------------------------------------------------------
    # Navigation bar
    # ------------------------------------------------------------------

    def _build_nav(self) -> None:
        # IMPORTANT: In tkinter pack(), side="right" widgets MUST be packed
        # BEFORE the center widget with expand=True. Pack processes left-to-right,
        # so right-anchored items must "claim" their space first.
        self._back_btn = ctk.CTkButton(
            self._nav_frame, text="← Back",
            font=FONT_BODY, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1,
            height=36, width=100, corner_radius=8,
            command=self._go_back,
        )
        self._back_btn.pack(side="left", padx=20, pady=17)

        # Pack Next BEFORE the center label so it claims right-side space first
        self._next_btn = ctk.CTkButton(
            self._nav_frame, text="Next →",
            font=FONT_BODY, fg_color=ACCENT, hover_color="#7d75ff",
            height=40, width=130, corner_radius=8,
            command=self._go_next,
        )
        self._next_btn.pack(side="right", padx=20, pady=15)

        self._step_label = ctk.CTkLabel(
            self._nav_frame, text="Step 1 of 3",
            font=FONT_SMALL, text_color=TEXT_SEC,
        )
        self._step_label.pack(side="left", expand=True)

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _show_step(self, step: int) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        self._step = step
        self._step_label.configure(text=f"Step {step + 1} of 3")
        self._back_btn.configure(state="normal" if step > 0 else "disabled")
        self._next_btn.configure(text="Finish ✓" if step == 2 else "Next →")

        [self._step_welcome, self._step_model, self._step_hotkey][step]()

    def _go_next(self) -> None:
        if self._step < 2:
            self._show_step(self._step + 1)
        else:
            self._finish()

    def _go_back(self) -> None:
        if self._step > 0:
            self._show_step(self._step - 1)

    # ------------------------------------------------------------------
    # Step 0: Welcome
    # ------------------------------------------------------------------

    def _step_welcome(self) -> None:
        ctk.CTkLabel(
            self._content, text="👋  Welcome to FluidVoice",
            font=FONT_TITLE, text_color=TEXT_PRI,
        ).pack(pady=(20, 8))

        ctk.CTkLabel(
            self._content,
            text=(
                "Voice-to-text dictation for Windows, powered by OpenAI Whisper.\n"
                "Hold a hotkey anywhere on your PC to start dictating — your words\n"
                "appear instantly in whatever app you're using."
            ),
            font=FONT_BODY, text_color=TEXT_SEC, justify="center",
        ).pack(pady=(0, 24))

        features = [
            ("🎙", "On-device transcription",  "No internet required. Whisper runs locally."),
            ("⌨",  "Works in any app",          "Text is injected directly into your focused window."),
            ("⚡",  "Global hotkey",             "One key combo triggers voice capture from anywhere."),
            ("✨",  "AI Enhancement",            "Optional post-processing via OpenAI or Groq."),
        ]
        for icon, title, desc in features:
            row = ctk.CTkFrame(self._content, fg_color=CARD_BG, corner_radius=10)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=icon, font=("Segoe UI", 20), width=40).pack(side="left", padx=12, pady=10)
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="both", expand=True, pady=8)
            ctk.CTkLabel(col, text=title, font=("Segoe UI", 12, "bold"), text_color=TEXT_PRI, anchor="w").pack(anchor="w")
            ctk.CTkLabel(col, text=desc, font=FONT_SMALL, text_color=TEXT_SEC, anchor="w").pack(anchor="w")

    # ------------------------------------------------------------------
    # Step 1: Model selection
    # ------------------------------------------------------------------

    def _step_model(self) -> None:
        ctk.CTkLabel(
            self._content, text="Choose Your Voice Model",
            font=FONT_H2, text_color=TEXT_PRI,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            self._content,
            text="Select a model then click Download. It downloads once and runs fully offline.",
            font=FONT_SMALL, text_color=TEXT_SEC,
        ).pack(anchor="w", pady=(0, 10))

        self._model_var = ctk.StringVar(value=settings.model_name)

        scroll = ctk.CTkScrollableFrame(self._content, fg_color=CARD_BG, corner_radius=12, height=180)
        scroll.pack(fill="x")

        for key, info in WHISPER_MODELS.items():
            card = ctk.CTkFrame(scroll, fg_color="transparent", corner_radius=8)
            card.pack(fill="x", pady=2, padx=8)

            ctk.CTkRadioButton(
                card, text="", variable=self._model_var, value=key,
                command=self._on_model_radio_change,
            ).pack(side="left", padx=8, pady=8)

            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.pack(side="left", fill="both", expand=True, pady=6)
            ctk.CTkLabel(info_col, text=info["label"], font=("Segoe UI", 11, "bold"), text_color=TEXT_PRI, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info_col, text=info["description"], font=FONT_SMALL, text_color=TEXT_SEC, anchor="w").pack(anchor="w")

            meta = ctk.CTkFrame(card, fg_color="transparent")
            meta.pack(side="right", padx=12, pady=6)
            ctk.CTkLabel(meta, text=f"~{info['size_mb']} MB", font=FONT_SMALL, text_color=TEXT_SEC).pack()
            ctk.CTkLabel(meta, text=info["speed"], font=FONT_SMALL, text_color=TEXT_SEC).pack()

        # Download section
        dl_card = ctk.CTkFrame(self._content, fg_color=CARD_BG, corner_radius=10)
        dl_card.pack(fill="x", pady=(10, 0))

        dl_row = ctk.CTkFrame(dl_card, fg_color="transparent")
        dl_row.pack(fill="x", padx=16, pady=(12, 6))

        self._download_btn = ctk.CTkButton(
            dl_row, text="⬇  Download Selected Model",
            font=("Segoe UI", 12, "bold"), fg_color=ACCENT, hover_color="#7d75ff",
            height=40, corner_radius=10, command=self._start_download,
        )
        self._download_btn.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self._dl_size_label = ctk.CTkLabel(
            dl_row, text=f"~{WHISPER_MODELS[settings.model_name]['size_mb']} MB",
            font=FONT_SMALL, text_color=TEXT_SEC,
        )
        self._dl_size_label.pack(side="left")

        self._progress_bar = ctk.CTkProgressBar(dl_card, height=6, corner_radius=4)
        self._progress_bar.set(0)
        self._progress_bar.pack(fill="x", padx=16, pady=(2, 4))

        self._dl_status = ctk.CTkLabel(
            dl_card, text="Select a model above, then click Download.",
            font=FONT_SMALL, text_color=TEXT_SEC,
        )
        self._dl_status.pack(anchor="w", padx=16, pady=(0, 10))

        # Lock Next until model is downloaded
        self._next_btn.configure(state="disabled", text="Download First →")

    def _on_model_radio_change(self) -> None:
        key = self._model_var.get()
        settings.model_name = key
        mb = WHISPER_MODELS.get(key, {}).get("size_mb", "?")
        if hasattr(self, "_dl_size_label"):
            self._dl_size_label.configure(text=f"~{mb} MB")
        if hasattr(self, "_dl_status"):
            self._dl_status.configure(
                text=f"Ready to download {WHISPER_MODELS[key]['label']}. Click Download.",
                text_color=TEXT_SEC,
            )
        if hasattr(self, "_next_btn"):
            self._next_btn.configure(state="disabled", text="Download First →")

    def _start_download(self) -> None:
        from transcription import transcription_service
        model_name = self._model_var.get()
        settings.model_name = model_name

        self._download_btn.configure(state="disabled", text="Downloading…")
        self._next_btn.configure(state="disabled", text="Downloading…")
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()
        self._dl_status.configure(
            text=f"Downloading {WHISPER_MODELS[model_name]['label']}… (may take a few minutes)",
            text_color=TEXT_SEC,
        )

        def _on_done(success: bool, message: str) -> None:
            self.after(0, lambda: self._download_finished(success, message))

        def _on_progress(msg: str) -> None:
            self.after(0, lambda: self._dl_status.configure(text=msg))

        transcription_service.load_model_async(
            model_name=model_name, on_done=_on_done, on_progress=_on_progress,
        )

    def _download_finished(self, success: bool, message: str) -> None:
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate")
        if success:
            self._progress_bar.set(1)
            self._dl_status.configure(text="✅ Model ready! Click Next to continue.", text_color=SUCCESS)
            self._download_btn.configure(state="normal", text="✅ Downloaded")
            self._next_btn.configure(state="normal", text="Next →")
        else:
            self._progress_bar.set(0)
            self._dl_status.configure(text=f"❌ Failed: {message}", text_color=DANGER)
            self._download_btn.configure(state="normal", text="⬇  Retry Download")
            self._next_btn.configure(state="disabled", text="Download First →")

    # ------------------------------------------------------------------
    # Step 2: Hotkey
    # ------------------------------------------------------------------

    def _step_hotkey(self) -> None:
        ctk.CTkLabel(
            self._content, text="Set Your Hotkey",
            font=FONT_H2, text_color=TEXT_PRI,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            self._content,
            text="Press any key combination. This hotkey will trigger voice recording from anywhere.",
            font=FONT_SMALL, text_color=TEXT_SEC, wraplength=500,
        ).pack(anchor="w", pady=(0, 24))

        self._hotkey_label = ctk.CTkLabel(
            self._content, text=settings.hotkey,
            font=("Consolas", 20, "bold"), text_color=ACCENT,
            fg_color=CARD_BG, corner_radius=12, height=60, width=360,
        )
        self._hotkey_label.pack(pady=(0, 16))

        self._capture_btn = ctk.CTkButton(
            self._content, text="Click here, then press your shortcut",
            font=FONT_BODY, fg_color=ACCENT, hover_color="#7d75ff",
            height=40, width=320, corner_radius=8,
            command=self._capture_hotkey,
        )
        self._capture_btn.pack(pady=(0, 12))

        ctk.CTkLabel(
            self._content,
            text="💡  Recommended: Ctrl + Alt + Space or Ctrl + Shift + R",
            font=FONT_SMALL, text_color=TEXT_SEC,
        ).pack()

    def _capture_hotkey(self) -> None:
        self._capture_btn.configure(text="Listening…", state="disabled")
        self._hotkey_label.configure(text="…")

        def _worker():
            from hotkey_manager import HotkeyManager
            combo = HotkeyManager.capture_hotkey(timeout=10.0)
            self.after(0, lambda: self._apply_hotkey(combo))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_hotkey(self, combo: str | None) -> None:
        self._capture_btn.configure(text="Click here, then press your shortcut", state="normal")
        if combo:
            settings.hotkey = combo
            self._hotkey_label.configure(text=combo)

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------

    def _finish(self) -> None:
        settings.onboarding_complete = True
        self.destroy()
        self._on_complete()
