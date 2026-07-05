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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "FluidVoice"
APP_VERSION = "1.0.0"
ICON_PATH = Path(__file__).parent / "assets" / "icon.png"


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

        # Proactively detect hardware on launch
        from transcription import get_hardware, resolve_device_and_compute
        hw = get_hardware()
        print(f"[{APP_NAME}] CPU Detected: {hw['cpu_brand']} (AVX2: {hw['avx2']}, AVX-512: {hw['avx512']})")
        
        gpu_found = []
        if hw["cuda"]: gpu_found.append("NVIDIA CUDA")
        if hw["rocm"]: gpu_found.append("AMD ROCm")
        if hw["vulkan"]: gpu_found.append("Vulkan")
        if hw["openvino"]: gpu_found.append("Intel OpenVINO")
        
        if gpu_found:
            print(f"[{APP_NAME}] GPU Detected: {', '.join(gpu_found)}")
        else:
            print(f"[{APP_NAME}] GPU Detected: None (falling back to optimized CPU)")

        # Resolve active device and compute types for visual confirmation in terminal
        dev, compute = resolve_device_and_compute(settings.model_device, settings.model_compute_type)
        print(f"[{APP_NAME}] Configured Backend: device={dev}, compute_type={compute}")

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

        print(f"[{APP_NAME}] Running. Hotkey: {settings.hotkey}")
        print(f"[{APP_NAME}] Look for FluidVoice in your system tray (bottom-right taskbar)")
        self._root.mainloop()

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

    def _on_hotkey_start(self) -> None:
        with self._pipeline_lock:
            if self._is_recording:
                return
            self._is_recording = True
            self._record_start_time = time.time()

        print("[FluidVoice] Recording started")
        audio_service.start_recording()
        if settings.overlay_enabled and self._overlay:
            self._overlay.show_recording()

        # Start background progressive/streaming transcription worker
        threading.Thread(target=self._streaming_transcription_worker, daemon=True).start()

    def _streaming_transcription_worker(self) -> None:
        """Background thread that transcribes intermediate audio progressively during recording."""
        time.sleep(1.0)  # Wait for initial buffer

        last_text = ""
        while True:
            with self._pipeline_lock:
                if not self._is_recording:
                    break

            # Fetch current intermediate audio recorded so far
            audio = audio_service.get_current_buffer()
            if audio is not None and len(audio) >= 16000 * 0.8:
                try:
                    text = transcription_service.transcribe(audio, fast_mode=True)
                    # If we got a valid progressive update, update the overlay text
                    if text and text != last_text:
                        last_text = text
                        if settings.overlay_enabled and self._overlay:
                            self._overlay.update_text(text)
                except Exception:
                    pass

            time.sleep(0.4)  # Update every 400ms

    def _on_hotkey_stop(self) -> None:
        with self._pipeline_lock:
            if not self._is_recording:
                return
            self._is_recording = False

        duration = time.time() - self._record_start_time
        print(f"[FluidVoice] Recording stopped ({duration:.1f}s)")

        # Run final transcription in a worker thread
        threading.Thread(
            target=self._run_pipeline,
            args=(duration,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Pipeline: stop → transcribe → enhance → inject → log
    # ------------------------------------------------------------------

    def _run_pipeline(self, duration: float) -> None:
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

        print(f"[FluidVoice] Transcribed: {text!r}")

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

        # 6. Inject text into focused window
        text_injection_service.inject(final_text)

        # 7. Save to history
        history_store.add(
            text=text,
            enhanced_text=enhanced,
            duration_sec=duration,
            model=settings.model_name,
        )

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
