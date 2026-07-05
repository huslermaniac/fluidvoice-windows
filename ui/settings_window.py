"""
ui/settings_window.py — FluidVoice Windows
Full settings UI built with CustomTkinter (dark mode).
Equivalent of the Settings panel in ContentView.swift.
"""

from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk  # type: ignore[import]
import sounddevice as sd     # type: ignore[import]

from settings import settings
from transcription import WHISPER_MODELS
from audio_capture import AudioCaptureService


# ---------------------------------------------------------------------------
# Colour / style tokens
# ---------------------------------------------------------------------------

BG_DARK      = "#0f0f13"
CARD_BG      = "#1a1a22"
CARD_BG2     = "#1f1f2a"
BORDER       = "#2d2d3e"
ACCENT       = "#6c63ff"
ACCENT_HOVER = "#7d75ff"
TEXT_PRI     = "#f0f0f5"
TEXT_SEC     = "#8888aa"
SUCCESS      = "#4ade80"
DANGER       = "#ff4d6d"
FONT_H1      = ("Segoe UI", 18, "bold")
FONT_H2      = ("Segoe UI", 13, "bold")
FONT_BODY    = ("Segoe UI", 12)
FONT_SMALL   = ("Segoe UI", 10)


# ---------------------------------------------------------------------------
# SettingsWindow
# ---------------------------------------------------------------------------

class SettingsWindow(ctk.CTkToplevel):
    """The main settings window."""

    def __init__(self, parent: tk.Misc, on_hotkey_changed: callable = None) -> None:  # type: ignore
        super().__init__(parent)
        self.title("FluidVoice — Settings")
        self.geometry("720x600")
        self.minsize(640, 520)
        self.configure(fg_color=BG_DARK)
        self.resizable(True, True)

        self._on_hotkey_changed = on_hotkey_changed
        self._hotkey_capture_thread: threading.Thread | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build()
        self.lift()
        self.focus_force()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Navigation sidebar + content area
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=0, pady=0)

        self._nav = self._build_nav(container)
        self._nav.pack(side="left", fill="y", padx=0, pady=0)

        self._content_frame = ctk.CTkFrame(container, fg_color=BG_DARK)
        self._content_frame.pack(side="left", fill="both", expand=True)

        # Pages
        self._pages: dict[str, ctk.CTkFrame] = {}
        for name, build_fn in [
            ("Hotkey",  self._page_hotkey),
            ("Model",   self._page_model),
            ("Audio",   self._page_audio),
            ("AI",      self._page_ai),
            ("General", self._page_general),
        ]:
            frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            build_fn(frame)
            self._pages[name] = frame

        self._show_page("Hotkey")

    def _build_nav(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        nav = ctk.CTkFrame(parent, fg_color=CARD_BG, width=160, corner_radius=0)
        nav.pack_propagate(False)

        header = ctk.CTkLabel(
            nav, text="⚙  Settings", font=("Segoe UI", 13, "bold"),
            text_color=TEXT_PRI
        )
        header.pack(pady=(24, 16), padx=16, anchor="w")

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        items = [
            ("Hotkey",  "⌨"),
            ("Model",   "🎙"),
            ("Audio",   "🔊"),
            ("AI",      "✨"),
            ("General", "⚙"),
        ]
        for label, icon in items:
            btn = ctk.CTkButton(
                nav,
                text=f"  {icon}  {label}",
                font=FONT_BODY,
                anchor="w",
                fg_color="transparent",
                hover_color=ACCENT,
                text_color=TEXT_SEC,
                height=38,
                corner_radius=8,
                command=lambda l=label: self._show_page(l),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_buttons[label] = btn

        return nav

    def _show_page(self, name: str) -> None:
        for n, frame in self._pages.items():
            frame.pack_forget()
        self._pages[name].pack(fill="both", expand=True, padx=24, pady=24)

        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(fg_color=ACCENT, text_color=TEXT_PRI)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC)

    # ------------------------------------------------------------------
    # Page: Hotkey
    # ------------------------------------------------------------------

    def _page_hotkey(self, frame: ctk.CTkFrame) -> None:
        _section_title(frame, "Global Hotkey")
        _subtitle(frame, "The hotkey that activates voice recording from anywhere on your PC.")

        card = _card(frame)

        # Current hotkey display
        self._hotkey_label = ctk.CTkLabel(
            card, text=settings.hotkey, font=("Consolas", 16, "bold"),
            text_color=ACCENT, fg_color=CARD_BG2, corner_radius=8,
            height=44, width=240,
        )
        self._hotkey_label.pack(pady=(12, 8), padx=16)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        self._capture_btn = ctk.CTkButton(
            btn_row, text="Click to Record Hotkey",
            font=FONT_BODY, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            height=36, corner_radius=8,
            command=self._start_hotkey_capture,
        )
        self._capture_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Reset to Default",
            font=FONT_BODY, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1,
            height=36, corner_radius=8,
            command=self._reset_hotkey,
        ).pack(side="left")

        _separator(frame)
        _section_title(frame, "Recording Mode")

        mode_card = _card(frame)
        self._hold_var = ctk.BooleanVar(value=settings.hold_to_record)

        ctk.CTkRadioButton(
            mode_card, text="Hold to Record  (release = stop)",
            variable=self._hold_var, value=True,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_mode_change,
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkRadioButton(
            mode_card, text="Toggle  (press once = start, press again = stop)",
            variable=self._hold_var, value=False,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_mode_change,
        ).pack(anchor="w", padx=16, pady=(4, 12))

    def _start_hotkey_capture(self) -> None:
        self._capture_btn.configure(text="Listening… press your shortcut", state="disabled")
        self._hotkey_label.configure(text="…")

        def _do_capture():
            from hotkey_manager import HotkeyManager
            combo = HotkeyManager.capture_hotkey(timeout=10.0)
            self.after(0, lambda: self._apply_hotkey(combo))

        self._hotkey_capture_thread = threading.Thread(target=_do_capture, daemon=True)
        self._hotkey_capture_thread.start()

    def _apply_hotkey(self, combo: str | None) -> None:
        self._capture_btn.configure(text="Click to Record Hotkey", state="normal")
        if combo:
            settings.hotkey = combo
            self._hotkey_label.configure(text=combo)
            if self._on_hotkey_changed:
                self._on_hotkey_changed()

    def _reset_hotkey(self) -> None:
        from settings import DEFAULTS
        settings.hotkey = DEFAULTS["hotkey"]
        self._hotkey_label.configure(text=DEFAULTS["hotkey"])
        if self._on_hotkey_changed:
            self._on_hotkey_changed()

    def _on_mode_change(self) -> None:
        settings.hold_to_record = self._hold_var.get()

    # ------------------------------------------------------------------
    # Page: Model
    # ------------------------------------------------------------------

    def _page_model(self, frame: ctk.CTkFrame) -> None:
        _section_title(frame, "Whisper Model")
        _subtitle(frame, "Choose the transcription model. Larger = more accurate but slower.")

        card = _card(frame)

        self._model_var = ctk.StringVar(value=settings.model_name)

        for key, info in WHISPER_MODELS.items():
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)

            ctk.CTkRadioButton(
                row,
                text=f"{info['label']}  —  {info['description']}",
                variable=self._model_var,
                value=key,
                font=FONT_BODY,
                text_color=TEXT_PRI,
                command=self._on_model_change,
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=info["speed"],
                font=FONT_SMALL, text_color=TEXT_SEC,
            ).pack(side="right", padx=8)

        # Download / model status box
        self._dl_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=10)
        self._dl_card.pack(fill="x", pady=(10, 0))

        dl_row = ctk.CTkFrame(self._dl_card, fg_color="transparent")
        dl_row.pack(fill="x", padx=16, pady=(12, 6))

        self._download_btn = ctk.CTkButton(
            dl_row, text="⬇  Download Model",
            font=("Segoe UI", 12, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            height=38, width=200, command=self._start_download,
        )
        self._download_btn.pack(side="left", padx=(0, 12))

        self._dl_status = ctk.CTkLabel(
            dl_row, text="Select a model size to check status.",
            font=FONT_SMALL, text_color=TEXT_SEC,
        )
        self._dl_status.pack(side="left", fill="x", expand=True, anchor="w")

        self._progress_bar = ctk.CTkProgressBar(self._dl_card, height=6, corner_radius=4)
        self._progress_bar.set(0)
        self._progress_bar.pack(fill="x", padx=16, pady=(2, 10))

        # Check initial download status of selected model
        self._on_model_change()

        _separator(frame)
        _section_title(frame, "Compute Device & Hardware Acceleration")
        _subtitle(frame, "Select the hardware backend. Auto detects and configures the fastest setup for your system.")

        dev_card = _card(frame)
        
        # Get hardware diagnostic string to print inside settings
        from transcription import get_hardware, get_recommended_compute_for_cpu
        hw = get_hardware()
        avx_str = "AVX-512" if hw["avx512"] else ("AVX2" if hw["avx2"] else "no-AVX")
        cpu_info = f"CPU detected: {hw['cpu_brand']} ({avx_str})"
        
        gpu_list = []
        if hw["cuda"]: gpu_list.append("CUDA (NVIDIA)")
        if hw["rocm"]: gpu_list.append("ROCm (AMD)")
        if hw["vulkan"]: gpu_list.append("Vulkan")
        if hw["openvino"]: gpu_list.append("OpenVINO")
        gpu_info = f"GPU backends: {', '.join(gpu_list) if gpu_list else 'None detected'}"
        
        diag_text = f"⚙️  {cpu_info}  |  {gpu_info}\n💡  Recommended compute: {get_recommended_compute_for_cpu()}"

        self._device_var = ctk.StringVar(value=settings.model_device)

        # Let's create a cleaner grid of choices
        grid = ctk.CTkFrame(dev_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=12)

        options = [
            ("Auto Detect (Recommended)", "auto"),
            ("CPU Only", "cpu"),
            ("NVIDIA GPU (CUDA)", "cuda"),
            ("AMD GPU (ROCm / HIP)", "rocm"),
        ]

        # Render choices in 2 columns
        for i, (label, val) in enumerate(options):
            r = i // 2
            c = i % 2
            
            # Show a green dot or badge if the backend is physically detected as available
            detected = True
            if val == "cuda" and not hw["cuda"]: detected = False
            if val == "rocm" and not hw["rocm"]: detected = False
            
            suffix = " (Detected)" if (detected and val != "auto" and val != "cpu") else ""
            color = SUCCESS if (detected and val != "auto" and val != "cpu") else TEXT_PRI
            
            rb = ctk.CTkRadioButton(
                grid, text=f"{label}{suffix}",
                variable=self._device_var, value=val,
                font=FONT_BODY, text_color=color,
                command=lambda: settings.__setattr__("model_device", self._device_var.get()),
            )
            rb.grid(row=r, column=c, padx=12, pady=6, sticky="w")
            
        # Status / diagnostics card footer
        diag_lbl = ctk.CTkLabel(
            dev_card, text=diag_text,
            font=FONT_SMALL, text_color=TEXT_SEC, justify="left",
            anchor="w",
        )
        diag_lbl.pack(fill="x", padx=16, pady=(4, 12))

    def _on_model_change(self) -> None:
        key = self._model_var.get()
        settings.model_name = key
        
        # Check if model files already exist locally in MODELS_DIR
        from transcription import MODELS_DIR
        model_dir = MODELS_DIR / f"models--systran--faster-whisper-{key}"
        if not model_dir.exists():
            model_dir = MODELS_DIR / f"faster-whisper-{key}"
        
        has_model = False
        if model_dir.exists():
            bin_files = list(model_dir.glob("**/*.bin"))
            if bin_files:
                has_model = True

        if has_model:
            self._dl_status.configure(text="✅ Ready (Downloaded)", text_color=SUCCESS)
            self._download_btn.configure(state="normal", text="✅ Ready")
        else:
            self._dl_status.configure(text="⬇ Not downloaded. Click Download to get this model.", text_color=TEXT_SEC)
            self._download_btn.configure(state="normal", text="⬇  Download Model")

    def _start_download(self) -> None:
        from transcription import transcription_service
        model_name = self._model_var.get()
        settings.model_name = model_name
        
        self._download_btn.configure(state="disabled", text="Downloading…")
        self._progress_bar.configure(mode="indeterminate")
        self._progress_bar.start()
        self._dl_status.configure(text="Downloading model files... (may take a few minutes)")

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
            self._dl_status.configure(text="✅ Model downloaded successfully!", text_color=SUCCESS)
            self._download_btn.configure(state="normal", text="✅ Downloaded")
        else:
            self._progress_bar.set(0)
            self._dl_status.configure(text=f"❌ Failed: {message}", text_color=DANGER)
            self._download_btn.configure(state="normal", text="⬇  Retry Download")

    # ------------------------------------------------------------------
    # Page: Audio
    # ------------------------------------------------------------------

    def _page_audio(self, frame: ctk.CTkFrame) -> None:
        _section_title(frame, "Input Device")
        _subtitle(frame, "Choose which microphone FluidVoice uses for recording.")

        card = _card(frame)

        devices = AudioCaptureService.list_input_devices()
        device_names = ["System Default"] + [d["name"] for d in devices]
        current_idx = settings.input_device
        current_name = "System Default"
        if current_idx is not None:
            for d in devices:
                if d["index"] == current_idx:
                    current_name = d["name"]

        self._device_combo = ctk.CTkComboBox(
            card, values=device_names,
            font=FONT_BODY, dropdown_font=FONT_BODY,
            width=400, height=38,
            command=self._on_device_change,
        )
        self._device_combo.set(current_name)
        self._device_combo.pack(padx=16, pady=16)

    def _on_device_change(self, choice: str) -> None:
        if choice == "System Default":
            settings.input_device = None
        else:
            devices = AudioCaptureService.list_input_devices()
            for d in devices:
                if d["name"] == choice:
                    settings.input_device = d["index"]
                    break

    # ------------------------------------------------------------------
    # Page: AI Enhancement
    # ------------------------------------------------------------------

    def _page_ai(self, frame: ctk.CTkFrame) -> None:
        _section_title(frame, "AI Enhancement")
        _subtitle(frame, "Optionally post-process transcriptions with an LLM for better formatting.")

        card = _card(frame)

        # Toggle
        self._ai_enabled_var = ctk.BooleanVar(value=settings.ai_enhancement_enabled)
        ctk.CTkSwitch(
            card, text="Enable AI Enhancement",
            variable=self._ai_enabled_var,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("ai_enhancement_enabled", self._ai_enabled_var.get()),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Provider
        ctk.CTkLabel(card, text="Provider", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._provider_combo = ctk.CTkComboBox(
            card, values=["openai", "groq", "custom"],
            font=FONT_BODY, width=300, height=36,
            command=lambda v: settings.__setattr__("ai_provider", v),
        )
        self._provider_combo.set(settings.ai_provider)
        self._provider_combo.pack(anchor="w", padx=16, pady=(4, 12))

        # API Key
        ctk.CTkLabel(card, text="API Key", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._api_key_entry = ctk.CTkEntry(
            card, placeholder_text="sk-…",
            show="•", width=400, height=36, font=FONT_BODY,
        )
        self._api_key_entry.insert(0, settings.ai_api_key)
        self._api_key_entry.pack(anchor="w", padx=16, pady=(4, 8))
        self._api_key_entry.bind("<FocusOut>", lambda _: settings.__setattr__("ai_api_key", self._api_key_entry.get()))

        # Model
        ctk.CTkLabel(card, text="Model", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._ai_model_entry = ctk.CTkEntry(
            card, placeholder_text="gpt-4o-mini",
            width=300, height=36, font=FONT_BODY,
        )
        self._ai_model_entry.insert(0, settings.ai_model)
        self._ai_model_entry.pack(anchor="w", padx=16, pady=(4, 16))
        self._ai_model_entry.bind("<FocusOut>", lambda _: settings.__setattr__("ai_model", self._ai_model_entry.get()))

    # ------------------------------------------------------------------
    # Page: General
    # ------------------------------------------------------------------

    def _page_general(self, frame: ctk.CTkFrame) -> None:
        _section_title(frame, "General")

        card = _card(frame)

        # Overlay
        self._overlay_var = ctk.BooleanVar(value=settings.overlay_enabled)
        ctk.CTkSwitch(
            card, text="Show transcription overlay",
            variable=self._overlay_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("overlay_enabled", self._overlay_var.get()),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Text injection mode
        ctk.CTkLabel(card, text="Text Injection Mode", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16, pady=(8, 0))
        self._inject_var = ctk.StringVar(value=settings.injection_mode)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 12))
        for label, val in [("Clipboard Paste (recommended)", "paste"), ("Simulate Typing", "type")]:
            ctk.CTkRadioButton(
                row, text=label, variable=self._inject_var, value=val,
                font=FONT_BODY, text_color=TEXT_PRI,
                command=lambda: settings.__setattr__("injection_mode", self._inject_var.get()),
            ).pack(side="left", padx=(0, 20))

        _separator(frame)
        _section_title(frame, "Startup")
        card2 = _card(frame)

        self._startup_var = ctk.BooleanVar(value=settings.start_with_windows)
        ctk.CTkSwitch(
            card2, text="Launch FluidVoice when Windows starts",
            variable=self._startup_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("start_with_windows", self._startup_var.get()),
        ).pack(anchor="w", padx=16, pady=16)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section_title(parent: ctk.CTkFrame, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=text, font=FONT_H2, text_color=TEXT_PRI, anchor="w")
    lbl.pack(anchor="w", pady=(0, 4))
    return lbl

def _subtitle(parent: ctk.CTkFrame, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=text, font=FONT_SMALL, text_color=TEXT_SEC, anchor="w", wraplength=560)
    lbl.pack(anchor="w", pady=(0, 12))
    return lbl

def _card(parent: ctk.CTkFrame) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
    card.pack(fill="x", pady=(0, 12))
    return card

def _separator(parent: ctk.CTkFrame) -> None:
    ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x", pady=12)
