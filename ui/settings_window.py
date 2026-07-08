"""
ui/settings_window.py — FluidVoice Windows
Unified settings and functionality dashboard built with CustomTkinter.
Includes pages for:
  1. Hotkey captures
  2. Whisper model downloads
  3. Audio input devices
  4. AI Enhancements
  5. Command Mode (PowerShell Terminal Agent loop + Chat Console)
  6. Edit Mode (Selected text rewrite prompts)
  7. File Transcription (Audio/video files batch transcribing)
  8. Dictation stats / word counts
  9. Custom dictionary triggering replacements
  10. Local transcription history log
  11. General preferences
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Any, Callable, Optional
import customtkinter as ctk

from settings import settings, DEFAULTS
from transcription import WHISPER_MODELS, transcription_service
from audio_capture import AudioCaptureService
from chat_history import chat_history_store, ChatMessage
from history import history_store
from llm_client import LLMClient
from terminal_service import TerminalService

# Style / Colors
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
FONT_MONO    = ("Consolas", 11)


class SettingsWindow(ctk.CTkToplevel):
    """The unified control center for settings and functionalities."""

    def __init__(self, parent: tk.Misc, on_hotkey_changed: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.title("FluidVoice Dashboard")
        self.geometry("880x680")
        self.minsize(780, 580)
        self.configure(fg_color=BG_DARK)
        self.resizable(True, True)

        self._on_hotkey_changed = on_hotkey_changed
        self._hotkey_capture_thread: Optional[threading.Thread] = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build()
        self.lift()
        self.focus_force()

    def _build(self) -> None:
        # Navigation sidebar + content panel
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=0, pady=0)

        self._nav = self._build_nav(container)
        self._nav.pack(side="left", fill="y", padx=0, pady=0)

        self._content_frame = ctk.CTkFrame(container, fg_color=BG_DARK)
        self._content_frame.pack(side="left", fill="both", expand=True)

        # Tab configuration
        self._pages: dict[str, ctk.CTkScrollableFrame] = {}
        tabs = [
            ("Hotkey",            self._page_hotkey),
            ("Model",             self._page_model),
            ("Audio",             self._page_audio),
            ("AI",                self._page_ai),
            ("Command Mode",      self._page_command_mode),
            ("Edit Mode",         self._page_edit_mode),
            ("File Transcribe",   self._page_file_transcribe),
            ("Stats",             self._page_stats),
            ("Custom Dict",       self._page_custom_dict),
            ("History",           self._page_history),
            ("General",           self._page_general),
        ]

        for name, build_fn in tabs:
            # Scrollable frame for tabs to avoid cut-off content
            frame = ctk.CTkScrollableFrame(self._content_frame, fg_color="transparent")
            build_fn(frame)
            self._pages[name] = frame

        self._show_page("Hotkey")

    def _build_nav(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        nav = ctk.CTkFrame(parent, fg_color=CARD_BG, width=190, corner_radius=0)
        nav.pack_propagate(False)

        header = ctk.CTkLabel(
            nav, text="⚜  FluidVoice", font=("Segoe UI", 15, "bold"),
            text_color=ACCENT
        )
        header.pack(pady=(24, 16), padx=16, anchor="w")

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        items = [
            ("Hotkey",            "⌨"),
            ("Model",             "🎙"),
            ("Audio",             "🔊"),
            ("AI",                "✨"),
            ("Command Mode",      "🤖"),
            ("Edit Mode",         "📝"),
            ("File Transcribe",   "📁"),
            ("Stats",             "📊"),
            ("Custom Dict",       "📖"),
            ("History",           "📜"),
            ("General",           "⚙"),
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
                height=34,
                corner_radius=8,
                command=lambda l=label: self._show_page(l),
            )
            btn.pack(fill="x", padx=8, pady=1)
            self._nav_buttons[label] = btn

        return nav

    def _show_page(self, name: str) -> None:
        for n, frame in self._pages.items():
            frame.pack_forget()
        self._pages[name].pack(fill="both", expand=True, padx=20, pady=20)

        for n, btn in self._nav_buttons.items():
            if n == name:
                btn.configure(fg_color=ACCENT, text_color=TEXT_PRI)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC)

    # ------------------------------------------------------------------
    # Page: Hotkey
    # ------------------------------------------------------------------
    def _page_hotkey(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Global Dictation Hotkey")
        _subtitle(frame, "The hotkey that activates voice recording from anywhere on your PC.")

        card = _card(frame)
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
            from hotkey_manager import hotkey_manager
            combo = hotkey_manager.capture_hotkey(timeout=10.0)
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
        settings.hotkey = DEFAULTS["hotkey"]
        self._hotkey_label.configure(text=DEFAULTS["hotkey"])
        if self._on_hotkey_changed:
            self._on_hotkey_changed()

    def _on_mode_change(self) -> None:
        settings.hold_to_record = self._hold_var.get()
        if self._on_hotkey_changed:
            self._on_hotkey_changed()

    # ------------------------------------------------------------------
    # Page: Model
    # ------------------------------------------------------------------
    def _page_model(self, frame: ctk.CTkScrollableFrame) -> None:
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

        self._on_model_change()

        _separator(frame)
        _section_title(frame, "Compute Device & Hardware Acceleration")
        _subtitle(frame, "Select the hardware backend. Auto detects the fastest setup for your system.")

        dev_card = _card(frame)
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

        grid = ctk.CTkFrame(dev_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=12)

        options = [
            ("Auto Detect (Recommended)", "auto"),
            ("CPU Only", "cpu"),
            ("NVIDIA GPU (CUDA)", "cuda"),
            ("AMD GPU (ROCm / HIP)", "rocm"),
        ]

        for i, (label, val) in enumerate(options):
            r = i // 2
            c = i % 2
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
            
        diag_lbl = ctk.CTkLabel(
            dev_card, text=diag_text,
            font=FONT_SMALL, text_color=TEXT_SEC, justify="left",
            anchor="w",
        )
        diag_lbl.pack(fill="x", padx=16, pady=(4, 12))

    def _on_model_change(self) -> None:
        key = self._model_var.get()
        settings.model_name = key
        
        from transcription import MODELS_DIR
        model_dir = MODELS_DIR / f"models--systran--faster-whisper-{key}"
        if not model_dir.exists():
            model_dir = MODELS_DIR / f"faster-whisper-{key}"
        
        has_model = False
        if model_dir.exists() and list(model_dir.glob("**/*.bin")):
            has_model = True

        if has_model:
            self._dl_status.configure(text="✅ Ready (Downloaded)", text_color=SUCCESS)
            self._download_btn.configure(state="normal", text="✅ Ready")
        else:
            self._dl_status.configure(text="⬇ Not downloaded. Click Download to get this model.", text_color=TEXT_SEC)
            self._download_btn.configure(state="normal", text="⬇  Download Model")

    def _start_download(self) -> None:
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
    def _page_audio(self, frame: ctk.CTkScrollableFrame) -> None:
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
    def _page_ai(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "AI Enhancement")
        _subtitle(frame, "Optionally post-process transcriptions with an LLM for formatting.")

        card = _card(frame)
        self._ai_enabled_var = ctk.BooleanVar(value=settings.ai_enhancement_enabled)
        ctk.CTkSwitch(
            card, text="Enable AI Enhancement",
            variable=self._ai_enabled_var,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("ai_enhancement_enabled", self._ai_enabled_var.get()),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(card, text="Provider", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._provider_combo = ctk.CTkComboBox(
            card, values=["openai", "groq", "custom"],
            font=FONT_BODY, width=300, height=36,
            command=lambda v: settings.__setattr__("ai_provider", v),
        )
        self._provider_combo.set(settings.ai_provider)
        self._provider_combo.pack(anchor="w", padx=16, pady=(4, 12))

        ctk.CTkLabel(card, text="API Key", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._api_key_entry = ctk.CTkEntry(
            card, placeholder_text="sk-…", show="•", width=400, height=36, font=FONT_BODY,
        )
        self._api_key_entry.insert(0, settings.ai_api_key)
        self._api_key_entry.pack(anchor="w", padx=16, pady=(4, 8))
        self._api_key_entry.bind("<FocusOut>", lambda _: settings.__setattr__("ai_api_key", self._api_key_entry.get()))

        ctk.CTkLabel(card, text="Model", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._ai_model_entry = ctk.CTkEntry(
            card, placeholder_text="gpt-4o-mini", width=300, height=36, font=FONT_BODY,
        )
        self._ai_model_entry.insert(0, settings.ai_model)
        self._ai_model_entry.pack(anchor="w", padx=16, pady=(4, 16))
        self._ai_model_entry.bind("<FocusOut>", lambda _: settings.__setattr__("ai_model", self._ai_model_entry.get()))

    # ------------------------------------------------------------------
    # Page: Command Mode
    # ------------------------------------------------------------------
    def _page_command_mode(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Command Mode")
        _subtitle(frame, "Control your Windows system using natural voice commands (PowerShell execution).")

        card = _card(frame)
        self._cmd_enabled_var = ctk.BooleanVar(value=settings.command_mode_enabled)
        ctk.CTkSwitch(
            card, text="Enable Command Mode", variable=self._cmd_enabled_var,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_cmd_enabled_toggle,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Command Mode Hotkey
        ctk.CTkLabel(card, text="Command Mode Hotkey", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._cmd_hotkey_lbl = ctk.CTkLabel(
            card, text=settings.command_mode_hotkey, font=("Consolas", 14, "bold"),
            text_color=ACCENT, fg_color=CARD_BG2, corner_radius=6, height=32, width=160,
        )
        self._cmd_hotkey_lbl.pack(anchor="w", padx=16, pady=4)
        
        self._cmd_capture_btn = ctk.CTkButton(
            card, text="Record Shortcut", font=FONT_SMALL, height=28, width=120,
            command=self._record_cmd_hotkey,
        )
        self._cmd_capture_btn.pack(anchor="w", padx=16, pady=(4, 12))

        # Confirm destructive commands
        self._cmd_confirm_var = ctk.BooleanVar(value=settings.command_mode_confirm)
        ctk.CTkSwitch(
            card, text="Confirm before running destructive commands (rm, del, mv, kill)",
            variable=self._cmd_confirm_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("command_mode_confirm", self._cmd_confirm_var.get()),
        ).pack(anchor="w", padx=16, pady=(4, 12))

        # Sync AI provider
        self._cmd_sync_var = ctk.BooleanVar(value=settings.command_mode_sync)
        ctk.CTkSwitch(
            card, text="Sync model & provider with global AI Enhancement",
            variable=self._cmd_sync_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_cmd_sync_toggle,
        ).pack(anchor="w", padx=16, pady=(4, 16))

        # Chat interface
        _separator(frame)
        _section_title(frame, "Interactive Command Console")
        _subtitle(frame, "Test voice/text execution agent directly in this console:")

        self._chat_card = _card(frame)
        
        self._chat_box = ctk.CTkTextbox(
            self._chat_card, height=180, font=FONT_MONO, fg_color=CARD_BG2,
            border_width=1, border_color=BORDER, text_color=TEXT_PRI
        )
        self._chat_box.pack(fill="x", padx=12, pady=12)
        self._chat_box.configure(state="disabled")

        input_row = ctk.CTkFrame(self._chat_card, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(0, 12))

        self._console_entry = ctk.CTkEntry(
            input_row, placeholder_text="Enter command to run (e.g. open notepad, list desktop files)...",
            height=34, font=FONT_BODY, fg_color=CARD_BG2
        )
        self._console_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._console_entry.bind("<Return>", lambda _: self._send_console_command())

        self._console_send_btn = ctk.CTkButton(
            input_row, text="Send 🚀", font=FONT_BODY, width=90, height=34,
            command=self._send_console_command
        )
        self._console_send_btn.pack(side="right")

        self._refresh_chat_console()

    def _on_cmd_enabled_toggle(self) -> None:
        settings.command_mode_enabled = self._cmd_enabled_var.get()
        if self._on_hotkey_changed:
            self._on_hotkey_changed()

    def _on_cmd_sync_toggle(self) -> None:
        settings.command_mode_sync = self._cmd_sync_var.get()

    def _record_cmd_hotkey(self) -> None:
        self._cmd_capture_btn.configure(text="Press keys...", state="disabled")
        self._cmd_hotkey_lbl.configure(text="…")

        def _do_capture():
            from hotkey_manager import hotkey_manager
            combo = hotkey_manager.capture_hotkey(timeout=10.0)
            self.after(0, lambda: self._apply_cmd_hotkey(combo))

        threading.Thread(target=_do_capture, daemon=True).start()

    def _apply_cmd_hotkey(self, combo: str | None) -> None:
        self._cmd_capture_btn.configure(text="Record Shortcut", state="normal")
        if combo:
            settings.command_mode_hotkey = combo
            self._cmd_hotkey_lbl.configure(text=combo)
            if self._on_hotkey_changed:
                self._on_hotkey_changed()

    def _refresh_chat_console(self) -> None:
        self._chat_box.configure(state="normal")
        self._chat_box.delete("1.0", tk.END)
        session = chat_history_store.current_session
        if session:
            for msg in session.messages:
                role_prefix = "User: " if msg.role == "user" else "Agent: "
                self._chat_box.insert(tk.END, f"{role_prefix}{msg.content}\n")
                if msg.tool_call:
                    self._chat_box.insert(tk.END, f"  [Command]: {msg.tool_call.get('command')}\n")
                self._chat_box.insert(tk.END, "-"*50 + "\n")
        self._chat_box.see(tk.END)
        self._chat_box.configure(state="disabled")

    def _send_console_command(self) -> None:
        cmd_text = self._console_entry.get().strip()
        if not cmd_text:
            return
        
        self._console_entry.delete(0, tk.END)
        session = chat_history_store.current_session
        if not session:
            return

        # Add user message
        new_msg = ChatMessage(id=str(uuid.uuid4()), role="user", content=cmd_text, timestamp=time.time())
        session.messages.append(new_msg)
        chat_history_store.update_current_chat(session.messages)
        self._refresh_chat_console()

        # Run terminal agent in background thread
        def _run_agent():
            try:
                self._chat_box.configure(state="normal")
                self.after(0, lambda: self._chat_box.insert(tk.END, "Agent: Thinking...\n"))
                
                # Setup provider/model
                provider = settings.ai_provider if settings.command_mode_sync else settings.command_mode_provider
                model = settings.ai_model if settings.command_mode_sync else settings.command_mode_model
                api_key = settings.ai_api_key

                system_prompt = (
                    "You are a thoughtful Windows Terminal PowerShell agent. "
                    "Execute user requests reliably and safely. Use execute_terminal_command tool."
                )

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": cmd_text}
                ]

                term_service = TerminalService()

                resp = LLMClient.call(
                    messages=messages,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    tools=[term_service.tool_definition]
                )

                # Process result
                agent_content = resp.content
                tool_data = None
                if resp.tool_calls:
                    tc = resp.tool_calls[0]
                    command = tc.get_string("command") or ""
                    purpose = tc.get_string("purpose") or ""
                    
                    tool_data = {
                        "id": tc.id,
                        "command": command,
                        "workingDirectory": tc.get_string("workingDirectory"),
                        "purpose": purpose
                    }

                    # Execute command
                    exec_result = term_service.execute(command)
                    agent_content = f"{purpose}\nResult success={exec_result['success']}\nOutput: {exec_result['output'][:300]}"

                agent_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    role="assistant",
                    content=agent_content,
                    timestamp=time.time(),
                    tool_call=tool_data
                )
                session.messages.append(agent_msg)
                chat_history_store.update_current_chat(session.messages)
                self.after(0, self._refresh_chat_console)
            except Exception as e:
                self.after(0, lambda: self._chat_box.insert(tk.END, f"Agent: Error: {e}\n"))
        
        threading.Thread(target=_run_agent, daemon=True).start()

    # ------------------------------------------------------------------
    # Page: Edit Mode
    # ------------------------------------------------------------------
    def _page_edit_mode(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Edit Mode (Rewrite)")
        _subtitle(frame, "Instantly rewrite selected text on screen using voice instructions.")

        card = _card(frame)
        self._rw_enabled_var = ctk.BooleanVar(value=settings.rewrite_mode_enabled)
        ctk.CTkSwitch(
            card, text="Enable Edit/Rewrite Mode", variable=self._rw_enabled_var,
            font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_rw_enabled_toggle,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(card, text="Edit Mode Hotkey", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=16)
        self._rw_hotkey_lbl = ctk.CTkLabel(
            card, text=settings.rewrite_mode_hotkey, font=("Consolas", 14, "bold"),
            text_color=ACCENT, fg_color=CARD_BG2, corner_radius=6, height=32, width=160,
        )
        self._rw_hotkey_lbl.pack(anchor="w", padx=16, pady=4)
        
        self._rw_capture_btn = ctk.CTkButton(
            card, text="Record Shortcut", font=FONT_SMALL, height=28, width=120,
            command=self._record_rw_hotkey,
        )
        self._rw_capture_btn.pack(anchor="w", padx=16, pady=(4, 12))

        # Sync AI provider
        self._rw_sync_var = ctk.BooleanVar(value=settings.rewrite_mode_sync)
        ctk.CTkSwitch(
            card, text="Sync model & provider with global AI Enhancement",
            variable=self._rw_sync_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=self._on_rw_sync_toggle,
        ).pack(anchor="w", padx=16, pady=(4, 16))

    def _on_rw_enabled_toggle(self) -> None:
        settings.rewrite_mode_enabled = self._rw_enabled_var.get()
        if self._on_hotkey_changed:
            self._on_hotkey_changed()

    def _on_rw_sync_toggle(self) -> None:
        settings.rewrite_mode_sync = self._rw_sync_var.get()

    def _record_rw_hotkey(self) -> None:
        self._rw_capture_btn.configure(text="Press keys...", state="disabled")
        self._rw_hotkey_lbl.configure(text="…")

        def _do_capture():
            from hotkey_manager import hotkey_manager
            combo = hotkey_manager.capture_hotkey(timeout=10.0)
            self.after(0, lambda: self._apply_rw_hotkey(combo))

        threading.Thread(target=_do_capture, daemon=True).start()

    def _apply_rw_hotkey(self, combo: str | None) -> None:
        self._rw_capture_btn.configure(text="Record Shortcut", state="normal")
        if combo:
            settings.rewrite_mode_hotkey = combo
            self._rw_hotkey_lbl.configure(text=combo)
            if self._on_hotkey_changed:
                self._on_hotkey_changed()

    # ------------------------------------------------------------------
    # Page: File Transcription (Meeting Tools)
    # ------------------------------------------------------------------
    def _page_file_transcribe(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "File Transcription")
        _subtitle(frame, "Transcribe complete audio/video files locally onto your machine.")

        card = _card(frame)
        self._selected_file_path = ""

        # Select file row
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)

        self._file_entry = ctk.CTkEntry(
            row, placeholder_text="Select audio or video file...", font=FONT_BODY, height=36, fg_color=CARD_BG2
        )
        self._file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            row, text="Browse 📁", font=FONT_BODY, width=90, height=36,
            command=self._browse_file
        ).pack(side="right")

        # Progress elements
        self._ft_status = ctk.CTkLabel(card, text="Idle", font=FONT_SMALL, text_color=TEXT_SEC)
        self._ft_status.pack(anchor="w", padx=16, pady=(0, 4))

        self._ft_progress = ctk.CTkProgressBar(card, height=6, corner_radius=4)
        self._ft_progress.set(0.0)
        self._ft_progress.pack(fill="x", padx=16, pady=(0, 16))

        self._ft_btn = ctk.CTkButton(
            card, text="🚀 Transcribe File", font=FONT_H2, height=38, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._start_file_transcription
        )
        self._ft_btn.pack(fill="x", padx=16, pady=(0, 16))

        # Result box
        _separator(frame)
        _section_title(frame, "Transcription Result")
        
        result_card = _card(frame)
        self._ft_textbox = ctk.CTkTextbox(
            result_card, height=180, font=FONT_BODY, fg_color=CARD_BG2,
            border_width=1, border_color=BORDER, text_color=TEXT_PRI
        )
        self._ft_textbox.pack(fill="x", padx=12, pady=12)

        ctk.CTkButton(
            result_card, text="Copy text to clipboard 📋", font=FONT_SMALL, height=28, width=180,
            command=self._copy_ft_text
        ).pack(anchor="e", padx=12, pady=(0, 12))

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Audio/Video Files", "*.wav *.mp3 *.m4a *.mp4 *.avi *.mov *.mkv *.ogg")]
        )
        if path:
            self._selected_file_path = path
            self._file_entry.delete(0, tk.END)
            self._file_entry.insert(0, path)

    def _start_file_transcription(self) -> None:
        path = self._file_entry.get().strip()
        if not path or not os.path.exists(path):
            self._ft_status.configure(text="❌ Invalid file path.", text_color=DANGER)
            return

        self._ft_btn.configure(state="disabled", text="Transcribing…")
        self._ft_status.configure(text="Transcribing file...", text_color=TEXT_PRI)
        self._ft_progress.set(0.0)
        self._ft_textbox.delete("1.0", tk.END)

        def _work():
            try:
                def _prog(p):
                    self.after(0, lambda: self._ft_progress.set(p))
                    self.after(0, lambda: self._ft_status.configure(text=f"Transcribing... {int(p*100)}%"))

                text = transcription_service.transcribe_file(path, on_progress=_prog)
                
                self.after(0, lambda: self._ft_status.configure(text="✅ Complete!", text_color=SUCCESS))
                self.after(0, lambda: self._ft_progress.set(1.0))
                self.after(0, lambda: self._ft_textbox.insert(tk.END, text))
            except Exception as e:
                self.after(0, lambda: self._ft_status.configure(text=f"❌ Error: {e}", text_color=DANGER))
            finally:
                self.after(0, lambda: self._ft_btn.configure(state="normal", text="🚀 Transcribe File"))

        threading.Thread(target=_work, daemon=True).start()

    def _copy_ft_text(self) -> None:
        import pyperclip
        try:
            pyperclip.copy(self._ft_textbox.get("1.0", tk.END).strip())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Page: Stats
    # ------------------------------------------------------------------
    def _page_stats(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Usage Stats")
        _subtitle(frame, "Dictation usage metrics tracked locally.")

        stats = history_store.today_stats()
        card = _card(frame)

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=16)

        for col, (label, val) in enumerate([
            ("Dictations Today", str(stats["count"])),
            ("Words Spoken", str(stats["words"])),
            ("Time Recorded", f"{int(stats['duration_sec'] // 60)}m {int(stats['duration_sec'] % 60)}s"),
        ]):
            box = ctk.CTkFrame(grid, fg_color=CARD_BG2, corner_radius=8, width=160, height=80)
            box.pack(side="left", padx=10, fill="y", expand=True)
            box.pack_propagate(False)

            ctk.CTkLabel(box, text=val, font=("Segoe UI", 20, "bold"), text_color=ACCENT).pack(pady=(12, 0))
            ctk.CTkLabel(box, text=label, font=FONT_SMALL, text_color=TEXT_SEC).pack()

    # ------------------------------------------------------------------
    # Page: Custom Dictionary
    # ------------------------------------------------------------------
    def _page_custom_dict(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Custom Dictionary")
        _subtitle(frame, "Add specific technical terms or trigger word replacements (e.g. 'kubernetes' -> 'Kubernetes').")

        # Add form
        card = _card(frame)
        ctk.CTkLabel(card, text="Add New Post-Replacement trigger", font=FONT_H2).pack(anchor="w", padx=16, pady=(12, 4))
        
        self._dict_triggers = ctk.CTkEntry(
            card, placeholder_text="Trigger word/phrase (e.g., ai, deepmind)...", font=FONT_BODY, height=34, fg_color=CARD_BG2
        )
        self._dict_triggers.pack(fill="x", padx=16, pady=4)

        self._dict_replacement = ctk.CTkEntry(
            card, placeholder_text="Replacement output (e.g. AI, DeepMind)...", font=FONT_BODY, height=34, fg_color=CARD_BG2
        )
        self._dict_replacement.pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            card, text="➕ Add Replacement Entry", font=FONT_BODY, height=34, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._add_dict_entry
        ).pack(fill="x", padx=16, pady=(8, 16))

        # Search bar
        search_row = ctk.CTkFrame(frame, fg_color="transparent")
        search_row.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(search_row, text="Configured Replacements", font=FONT_H2).pack(side="left")

        self._dict_list_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self._dict_list_frame.pack(fill="x", pady=4)

        self._render_dict_entries()

    def _render_dict_entries(self) -> None:
        for w in self._dict_list_frame.winfo_children():
            w.destroy()

        entries = settings.custom_dictionary_entries
        if not entries:
            ctk.CTkLabel(self._dict_list_frame, text="No custom dictionary triggers configured yet.", font=FONT_BODY, text_color=TEXT_SEC).pack(pady=20)
            return

        for idx, entry in enumerate(entries):
            card = ctk.CTkFrame(self._dict_list_frame, fg_color=CARD_BG, corner_radius=8, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=3)

            triggers_str = ", ".join(entry.get("triggers", []))
            replacement = entry.get("replacement", "")

            # Grid columns
            lbl = ctk.CTkLabel(card, text=f"Triggers: {triggers_str}  ➡️  {replacement}", font=FONT_BODY, text_color=TEXT_PRI)
            lbl.pack(side="left", padx=16, pady=10)

            # Delete button
            del_btn = ctk.CTkButton(
                card, text="Delete 🗑", font=FONT_SMALL, width=80, height=24, fg_color="transparent",
                hover_color=DANGER, border_color=BORDER, border_width=1,
                command=lambda index=idx: self._delete_dict_entry(index)
            )
            del_btn.pack(side="right", padx=16)

    def _add_dict_entry(self) -> None:
        triggers_txt = self._dict_triggers.get().strip()
        replacement_txt = self._dict_replacement.get().strip()
        if not triggers_txt or not replacement_txt:
            return

        triggers = [t.strip() for t in triggers_txt.split(",") if t.strip()]
        
        # Add to settings
        entries = list(settings.custom_dictionary_entries)
        entries.append({
            "id": str(uuid.uuid4()),
            "triggers": triggers,
            "replacement": replacement_txt
        })
        settings.custom_dictionary_entries = entries

        # Reset form
        self._dict_triggers.delete(0, tk.END)
        self._dict_replacement.delete(0, tk.END)
        self._render_dict_entries()

    def _delete_dict_entry(self, index: int) -> None:
        entries = list(settings.custom_dictionary_entries)
        if 0 <= index < len(entries):
            entries.pop(index)
            settings.custom_dictionary_entries = entries
            self._render_dict_entries()

    # ------------------------------------------------------------------
    # Page: History
    # ------------------------------------------------------------------
    def _page_history(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "Transcription History")
        _subtitle(frame, "Review and copy past voice dictations.")

        card = _card(frame)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)

        ctk.CTkButton(
            row, text="Clear All", font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1, height=28, width=80,
            command=self._clear_history,
        ).pack(side="right")

        ctk.CTkButton(
            row, text="Refresh list ↻", font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
            border_color=BORDER, border_width=1, height=28, width=100,
            command=self._render_history_entries,
        ).pack(side="right", padx=(0, 8))

        self._history_list_container = ctk.CTkFrame(frame, fg_color="transparent")
        self._history_list_container.pack(fill="x", pady=4)
        self._render_history_entries()

    def _render_history_entries(self) -> None:
        for w in self._history_list_container.winfo_children():
            w.destroy()

        entries = history_store.get_all()
        if not entries:
            ctk.CTkLabel(
                self._history_list_container,
                text="No transcriptions yet.\nPress your hotkey anywhere to start dictating.",
                font=FONT_BODY, text_color=TEXT_SEC, justify="center",
            ).pack(expand=True, pady=40)
            return

        for entry in entries:
            card = ctk.CTkFrame(self._history_list_container, fg_color=CARD_BG, corner_radius=10, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(top, text=entry.timestamp_display, font=FONT_SMALL, text_color=TEXT_SEC).pack(side="left")
            ctk.CTkLabel(top, text=f"  {entry.model}  ", font=FONT_SMALL, text_color=ACCENT,
                         fg_color="#1e1e30", corner_radius=4).pack(side="right")

            display = entry.enhanced_text if entry.enhanced_text else entry.text
            ctk.CTkLabel(
                card, text=display, font=FONT_BODY, text_color=TEXT_PRI, anchor="w",
                wraplength=480, justify="left",
            ).pack(anchor="w", padx=12, pady=(4, 4))

            bot = ctk.CTkFrame(card, fg_color="transparent")
            bot.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkLabel(bot, text=f"{entry.word_count} words  ·  {entry.duration_sec:.1f}s",
                         font=FONT_SMALL, text_color=TEXT_SEC).pack(side="left")
            
            ctk.CTkButton(
                bot, text="Copy", font=FONT_SMALL, fg_color="transparent", hover_color=BORDER,
                border_color=BORDER, border_width=1, height=24, width=60,
                command=lambda t=display: self._copy_history_text(t),
            ).pack(side="right")

    def _copy_history_text(self, text: str) -> None:
        import pyperclip
        try:
            pyperclip.copy(text)
        except Exception:
            pass

    def _clear_history(self) -> None:
        history_store.clear()
        self._render_history_entries()

    # ------------------------------------------------------------------
    # Page: General
    # ------------------------------------------------------------------
    def _page_general(self, frame: ctk.CTkScrollableFrame) -> None:
        _section_title(frame, "General Settings")

        card = _card(frame)
        self._overlay_var = ctk.BooleanVar(value=settings.overlay_enabled)
        ctk.CTkSwitch(
            card, text="Show transcription overlay",
            variable=self._overlay_var, font=FONT_BODY, text_color=TEXT_PRI,
            command=lambda: settings.__setattr__("overlay_enabled", self._overlay_var.get()),
        ).pack(anchor="w", padx=16, pady=(16, 8))

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
def _section_title(parent: ctk.CTkScrollableFrame, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=text, font=FONT_H2, text_color=TEXT_PRI, anchor="w")
    lbl.pack(anchor="w", pady=(0, 4))
    return lbl


def _subtitle(parent: ctk.CTkScrollableFrame, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(parent, text=text, font=FONT_SMALL, text_color=TEXT_SEC, anchor="w", wraplength=520)
    lbl.pack(anchor="w", pady=(0, 12))
    return lbl


def _card(parent: ctk.CTkScrollableFrame) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12, border_width=1, border_color=BORDER)
    card.pack(fill="x", pady=(0, 12))
    return card


def _separator(parent: ctk.CTkScrollableFrame) -> None:
    ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x", pady=12)
