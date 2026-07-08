"""
main.py — FluidVoice Windows
Entry point. Manages the system tray, hotkey, audio pipeline,
transcription, text injection, and overlay.

Architecture:
  - tkinter root runs on the main thread (hidden; drives overlay + timers)
  - pystray tray icon runs in its own thread
  - keyboard hotkey callbacks fire in a background thread
  - audio capture runs in sounddevice callback thread
  - faster-whisper transcription runs in a worker thread
"""

from __future__ import annotations

import sys
import warnings
warnings.filterwarnings("ignore") # Suppress annoying requests/urllib3 mismatch warnings

import threading
import time
import tkinter as tk
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the app directory is on PATH for sibling imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "ui"))

import customtkinter as ctk  # type: ignore[import]
from PIL import Image          # type: ignore[import]
import pystray                 # type: ignore[import]

from settings import settings
from audio_capture import audio_service
from transcription import transcription_service, enhance_with_ai
from text_injection import text_injection_service
from hotkey_manager import hotkey_manager
from overlay import OverlayWindow
from history import history_store
from llm_client import LLMClient
from terminal_service import TerminalService
from chat_history import chat_history_store, ChatMessage


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "FluidVoice"
APP_VERSION = "1.0.0"
ICON_PATH = Path(__file__).parent / "assets" / "icon.png"
TRAY_ICON_PATH = Path(__file__).parent / "assets" / "tray_icon.png"


# ---------------------------------------------------------------------------
# FluidVoiceApp
# ---------------------------------------------------------------------------

class FluidVoiceApp:
    """
    Top-level application controller.
    Equivalent of FluidApp + AppDelegate + AppServices on macOS.
    """

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._overlay: OverlayWindow | None = None
        self._tray: pystray.Icon | None = None

        self._is_recording = False
        self._record_start_time: float = 0.0
        self._settings_window = None
        self._history_window = None
        self._onboarding_window = None

        # Thread safety for the pipeline state
        self._pipeline_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the app. Blocks until the user quits."""
        print(f"[{APP_NAME}] Starting…")

        # Hidden tkinter root — drives overlay + after() scheduling
        self._root = tk.Tk()
        self._root.withdraw()                       # Never show the root window
        self._root.title(APP_NAME)
        self._root.protocol("WM_DELETE_WINDOW", self._root.withdraw)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Overlay
        self._overlay = OverlayWindow(self._root)

        # System tray (runs in its own daemon thread — start AFTER root exists)
        self._start_tray()

        # Hotkey
        self._setup_hotkey()

        # Show onboarding on first run (small delay so root loop is alive)
        if not settings.onboarding_complete:
            print(f"[{APP_NAME}] First run — showing onboarding")
            self._root.after(150, self._show_onboarding)
        else:
            # Pre-load model in background so first dictation is fast
            self._preload_model()

        # Hardware detection runs in background — avoids blocking startup with
        # slow torch/cpuinfo/CUDA imports (can take 3-8s on first run).
        threading.Thread(target=self._detect_hardware_async, daemon=True).start()

        print(f"[{APP_NAME}] Running. Hotkey: {settings.hotkey}")
        print(f"[{APP_NAME}] Look for FluidVoice in your system tray (bottom-right taskbar)")
        self._root.mainloop()

    def _detect_hardware_async(self) -> None:
        """Probe hardware in the background so it doesn't delay startup."""
        try:
            from transcription import get_hardware, resolve_device_and_compute
            hw = get_hardware()
            print(f"[{APP_NAME}] CPU Detected: {hw['cpu_brand']} (AVX2: {hw['avx2']}, AVX-512: {hw['avx512']})")

            gpu_found = []
            if hw["cuda"]:    gpu_found.append("NVIDIA CUDA")
            if hw["rocm"]:    gpu_found.append("AMD ROCm")
            if hw["vulkan"]:  gpu_found.append("Vulkan")
            if hw["openvino"]: gpu_found.append("Intel OpenVINO")

            if gpu_found:
                print(f"[{APP_NAME}] GPU Detected: {', '.join(gpu_found)}")
            else:
                print(f"[{APP_NAME}] GPU Detected: None (falling back to optimized CPU)")

            dev, compute = resolve_device_and_compute(settings.model_device, settings.model_compute_type)
            print(f"[{APP_NAME}] Configured Backend: device={dev}, compute_type={compute}")
        except Exception as e:
            print(f"[{APP_NAME}] Hardware detection error: {e}")

    # ------------------------------------------------------------------
    # System Tray
    # ------------------------------------------------------------------

    def _start_tray(self) -> None:
        icon_image = self._load_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem(f"{APP_NAME}  v{APP_VERSION}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Settings", self._tray_open_settings),
            pystray.MenuItem("View History", self._tray_open_history),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Hotkey: " + settings.hotkey, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit FluidVoice", self._tray_quit),
        )
        self._tray = pystray.Icon(APP_NAME, icon_image, APP_NAME, menu)
        t = threading.Thread(target=self._tray.run, daemon=True)
        t.start()

    def _load_tray_icon(self) -> Image.Image:
        if TRAY_ICON_PATH.exists():
            return Image.open(TRAY_ICON_PATH).resize((64, 64))
        if ICON_PATH.exists():
            return Image.open(ICON_PATH).resize((64, 64))
        # Generate a simple purple circle icon if no file exists
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill="#6c63ff")
        draw.ellipse([22, 18, 42, 46], fill="white")  # mic shape
        draw.rectangle([30, 44, 34, 54], fill="white")
        draw.arc([24, 34, 40, 56], 0, 180, fill="white", width=2)
        return img

    def _tray_open_settings(self, icon=None, item=None) -> None:
        self._root.after(0, self._show_settings)

    def _tray_open_history(self, icon=None, item=None) -> None:
        self._root.after(0, self._show_history)

    def _tray_quit(self, icon=None, item=None) -> None:
        self._root.after(0, self._quit)

    # ------------------------------------------------------------------
    # Hotkey setup
    # ------------------------------------------------------------------

    def _setup_hotkey(self) -> None:
        hotkey_manager.on_start = self._on_hotkey_start
        hotkey_manager.on_stop = self._on_hotkey_stop
        hotkey_manager.start()

    def _on_hotkey_start(self, mode: str = "dictate") -> None:
        with self._pipeline_lock:
            if self._is_recording:
                return
            self._is_recording = True
            self._recording_mode = mode
            self._record_start_time = time.time()

        print(f"[FluidVoice] Recording started (mode={mode})")
        audio_service.start_recording()
        if settings.overlay_enabled and self._overlay:
            self._overlay.show_recording(mode)

        # Start background progressive/streaming transcription worker
        threading.Thread(target=self._streaming_transcription_worker, daemon=True).start()

    def _streaming_transcription_worker(self) -> None:
        """
        Background thread: progressively transcribes audio during recording.

        Uses a sliding-window + settled-text accumulator so displayed text
        only ever grows — it never resets mid-sentence.

        Architecture:
          settled_text    — text confirmed from chunks we've already moved past
          settled_end     — sample index up to which text is settled
          LIVE_WINDOW     — how many samples to transcribe in each cycle (5 s)
          SETTLE_AFTER    — commit the live window to settled once we have this
                            many samples of NEW audio beyond it (4 s)
        """
        time.sleep(0.3)  # Reduced from 1.0 s — first preview appears faster

        SR = 16000
        LIVE_WINDOW  = SR * 5   # 5 s live window fed to Whisper each cycle
        SETTLE_AFTER = SR * 4   # settle window when 4 s of new audio exists beyond it

        settled_text: str = ""
        settled_end:  int = 0
        last_display: str = ""

        while True:
            with self._pipeline_lock:
                if not self._is_recording:
                    break

            audio = audio_service.get_current_buffer()
            if audio is None or len(audio) < SR * 0.5:
                time.sleep(0.25)
                continue

            total = len(audio)

            # ── Settle old window when enough new audio has accumulated ──────
            # Once we have SETTLE_AFTER samples of fresh audio beyond the current
            # live window, lock in that window as "settled" text so it's never
            # re-transcribed or dropped from the display.
            while total > settled_end + LIVE_WINDOW + SETTLE_AFTER:
                chunk = audio[settled_end: settled_end + LIVE_WINDOW]
                try:
                    chunk_text = transcription_service.transcribe(chunk, fast_mode=True)
                    if chunk_text:
                        settled_text = (settled_text + " " + chunk_text).strip()
                except Exception:
                    pass
                settled_end += LIVE_WINDOW  # advance window regardless of success

            # ── Transcribe current live window ───────────────────────────────
            live_chunk = audio[settled_end: settled_end + LIVE_WINDOW]
            if len(live_chunk) >= SR * 0.5:
                try:
                    live_text = transcription_service.transcribe(live_chunk, fast_mode=True)
                    full_text = (settled_text + " " + live_text).strip() if live_text else settled_text
                    if full_text and full_text != last_display:
                        last_display = full_text
                        if settings.overlay_enabled and self._overlay:
                            self._overlay.update_text(full_text)
                except Exception:
                    pass

            time.sleep(0.25)  # Poll every 250 ms (was 400 ms)

    def _on_hotkey_stop(self) -> None:
        with self._pipeline_lock:
            if not self._is_recording:
                return
            self._is_recording = False
            mode = self._recording_mode

        duration = time.time() - self._record_start_time
        print(f"[FluidVoice] Recording stopped ({duration:.1f}s)")

        # Run final transcription in a worker thread
        threading.Thread(
            target=self._run_pipeline,
            args=(duration, mode),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Pipeline: stop → transcribe → enhance/agent → inject → log
    # ------------------------------------------------------------------

    def _run_pipeline(self, duration: float, mode: str = "dictate") -> None:
        # 1. Collect audio
        audio = audio_service.stop_recording()

        if audio is None or len(audio) == 0:
            print("[FluidVoice] No audio captured — skipping")
            if self._overlay:
                self._overlay.hide()
            return

        # 2. Show "transcribing" indicator
        if settings.overlay_enabled and self._overlay:
            self._overlay.show_transcribing()

        # 3. Transcribe
        try:
            text = transcription_service.transcribe(audio)
        except Exception as e:
            print(f"[FluidVoice] Transcription error: {e}")
            if self._overlay:
                self._overlay.hide()
            return

        if not text:
            print("[FluidVoice] Empty transcription — skipping")
            if self._overlay:
                self._overlay.hide()
            return

        print(f"[FluidVoice] ({mode}) Transcribed: {text!r}")

        if mode == "dictate":
            # 4. AI Enhancement (optional)
            enhanced = ""
            if settings.ai_enhancement_enabled:
                enhanced = enhance_with_ai(text)
                final_text = enhanced if enhanced != text else text
                print(f"[FluidVoice] Enhanced: {final_text!r}")
            else:
                final_text = text

            # 5. Show result in overlay
            if settings.overlay_enabled and self._overlay:
                self._overlay.show_text(final_text)

            # 6. Inject text into focused window.
            # Brief delay after show_text: the overlay's deiconify+lift+topmost is
            # scheduled via root.after(0,...) on the main thread. On Windows this can
            # briefly steal focus, causing Ctrl+V to land on the overlay instead of
            # the user's app. Sleeping here lets the tkinter event loop settle first.
            time.sleep(0.15)
            print(f"[FluidVoice] Injecting {len(final_text)} chars via '{settings.injection_mode}' mode")
            text_injection_service.inject(final_text)
            print(f"[FluidVoice] Injection complete")

            # 7. Save to history
            history_store.add(
                text=text,
                enhanced_text=enhanced,
                duration_sec=duration,
                model=settings.model_name,
            )

        elif mode == "command":
            # Command Mode execution
            self._run_command_agent(text)

        elif mode == "rewrite":
            # Edit / Rewrite Mode execution
            self._run_rewrite_agent(text)

    def _run_command_agent(self, user_command: str) -> None:
        try:
            provider = settings.ai_provider if settings.command_mode_sync else settings.command_mode_provider
            model = settings.ai_model if settings.command_mode_sync else settings.command_mode_model
            api_key = settings.ai_api_key

            term_service = TerminalService()
            session = chat_history_store.current_session
            if not session:
                session = chat_history_store.create_new_chat()

            import uuid
            new_msg = ChatMessage(id=str(uuid.uuid4()), role="user", content=user_command, timestamp=time.time())
            session.messages.append(new_msg)
            chat_history_store.update_current_chat(session.messages)

            system_prompt = (
                "You are an autonomous, thoughtful Windows Terminal Agent. Execute user requests reliably and safely "
                "using the execute_terminal_command tool. You can open applications (using PowerShell Start-Process), "
                "manage files, check versions, etc. Explain your purpose clearly. Keep explanations short."
            )
            messages = [{"role": "system", "content": system_prompt}]
            for msg in session.messages:
                messages.append({"role": msg.role, "content": msg.content})

            if self._overlay:
                self._overlay.show_text("Analyzing command...")

            resp = LLMClient.call(
                messages=messages,
                provider=provider,
                model=model,
                api_key=api_key,
                tools=[term_service.tool_definition]
            )

            final_response = resp.content
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

                execute_allowed = True
                is_destructive = self._is_destructive_command(command)
                
                if settings.command_mode_confirm or is_destructive:
                    if self._overlay:
                        self._overlay.show_text("Confirmation needed on screen...")
                    
                    def _confirm():
                        from tkinter import messagebox
                        title = "Confirm Destruction" if is_destructive else "Confirm Action"
                        msg = f"The AI agent wants to execute the following command:\n\n{command}\n\nPurpose: {purpose}\n\nDo you want to run this command?"
                        # Must explicitly specify parent as root to avoid Tk inter-thread locking
                        return messagebox.askyesno(title, msg, parent=self._root)
                    
                    # Blocking call to main thread
                    execute_allowed = self._root.after(0, _confirm)

                if execute_allowed:
                    if self._overlay:
                        self._overlay.show_text(f"Executing: {purpose}...")
                    
                    exec_result = term_service.execute(command)
                    final_response = f"✓ Executed: {purpose}\nOutput: {exec_result['output'][:200]}"
                else:
                    final_response = "✗ Command cancelled by user."

            # Save response to history
            assistant_msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="assistant",
                content=final_response,
                timestamp=time.time(),
                tool_call=tool_data
            )
            session.messages.append(assistant_msg)
            chat_history_store.update_current_chat(session.messages)

            # Update settings GUI if open
            if self._settings_window and self._settings_window.winfo_exists():
                self._root.after(0, self._settings_window._refresh_chat_console)

            # Display final summary on overlay
            if self._overlay:
                self._overlay.show_text(final_response)

        except Exception as e:
            print(f"[CommandMode] Agent loop failed: {e}")
            if self._overlay:
                self._overlay.show_text(f"Error: {e}")

    def _is_destructive_command(self, cmd: str) -> bool:
        cmd_l = cmd.lower().strip()
        destructive_words = ["rm ", "del ", "rmdir ", "rd ", "format ", "mkfs ", "kill ", "stop-process ", "remove-item "]
        return any(w in cmd_l for w in destructive_words)

    def _run_rewrite_agent(self, instruction: str) -> None:
        try:
            # Small settle delay: the rewrite hotkey (e.g. ctrl+alt+e) may still have
            # modifiers physically held when this thread starts. get_selected_text()
            # adds its own delay, but an extra buffer here prevents race conditions
            # on fast machines where the thread spawns before key-up fully propagates.
            time.sleep(0.1)

            selected_text = text_injection_service.get_selected_text()

            provider = settings.ai_provider if settings.rewrite_mode_sync else settings.rewrite_mode_provider
            model = settings.ai_model if settings.rewrite_mode_sync else settings.rewrite_mode_model
            api_key = settings.ai_api_key

            if selected_text:
                system_prompt = (
                    "You are a text editing assistant. Rewrite the following selected text based on the user's instructions.\n"
                    "Return ONLY the final rewritten text. Do NOT include conversational filler, markdown formatting (like ```), "
                    "or introductory/concluding explanations."
                )
                user_content = f"Selected Text:\n\"\"\"{selected_text}\"\"\"\n\nInstructions: {instruction}"
            else:
                system_prompt = (
                    "You are a dictation assistant. Write or generate text based on the user's instructions.\n"
                    "Return ONLY the generated text. Do NOT include conversational filler, markdown, or explanations."
                )
                user_content = f"Instructions: {instruction}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]

            if self._overlay:
                self._overlay.show_text("Generating text...")

            resp = LLMClient.call(
                messages=messages,
                provider=provider,
                model=model,
                api_key=api_key
            )

            final_text = resp.content.strip()

            if final_text:
                if self._overlay:
                    self._overlay.show_text("Done!")
                text_injection_service.inject(final_text)
            else:
                if self._overlay:
                    self._overlay.show_text("Failed: Empty AI response")
        except Exception as e:
            print(f"[RewriteMode] Failed: {e}")
            if self._overlay:
                self._overlay.show_text(f"Error: {e}")

    # ------------------------------------------------------------------
    # Model pre-load
    # ------------------------------------------------------------------

    def _preload_model(self) -> None:
        def _load():
            try:
                transcription_service.ensure_model_loaded()
                print(f"[FluidVoice] Model '{settings.model_name}' pre-loaded")
            except Exception as e:
                print(f"[FluidVoice] Model pre-load failed: {e}")

        threading.Thread(target=_load, daemon=True).start()

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _show_settings(self) -> None:
        from ui.settings_window import SettingsWindow
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return
        self._settings_window = SettingsWindow(
            self._root,
            on_hotkey_changed=self._on_settings_hotkey_changed,
        )

    def _show_history(self) -> None:
        from ui.history_window import HistoryWindow
        if self._history_window is not None and self._history_window.winfo_exists():
            self._history_window.lift()
            self._history_window.focus_force()
            return
        self._history_window = HistoryWindow(self._root)

    def _show_onboarding(self) -> None:
        from ui.onboarding_window import OnboardingWindow

        def _on_complete():
            self._preload_model()
            self._setup_hotkey()

        self._onboarding_window = OnboardingWindow(self._root, on_complete=_on_complete)

    def _on_settings_hotkey_changed(self) -> None:
        hotkey_manager.reload_hotkey()
        print(f"[FluidVoice] Hotkey updated to: {settings.hotkey}")

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _quit(self) -> None:
        print(f"[{APP_NAME}] Shutting down…")
        hotkey_manager.stop()
        if self._tray:
            self._tray.stop()
        self._root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Windows: ensure the taskbar icon and DPI scaling work correctly
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = FluidVoiceApp()
    app.run()
