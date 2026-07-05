"""
text_injection.py — FluidVoice Windows
Inject transcribed text into the currently focused window.
Equivalent of TypingService.swift (AXUIElement-based text insertion on macOS).

Strategy:
  1. "paste" mode (default, most reliable): save clipboard → paste text → restore clipboard
  2. "type" mode: simulate key presses (slower but works in some edge-case apps)
"""

from __future__ import annotations

import time
import threading

import pyperclip  # type: ignore[import]
import pyautogui  # type: ignore[import]

from settings import settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIPBOARD_RESTORE_DELAY = 0.6   # seconds before restoring original clipboard


# ---------------------------------------------------------------------------
# TextInjectionService
# ---------------------------------------------------------------------------

class TextInjectionService:
    """Injects text into the focused window via clipboard paste or keyboard typing."""

    def __init__(self) -> None:
        self._clipboard_lock = threading.Lock()

    def _release_modifiers(self) -> None:
        """Ensure modifier keys are programmatically up so they don't interfere with typing or pasting."""
        for key in ["ctrl", "alt", "shift", "win"]:
            try:
                pyautogui.keyUp(key)
            except Exception:
                pass

    def inject(self, text: str) -> None:
        """Inject text using the configured mode."""
        if not text:
            return

        # Release modifiers first so hotkeys don't corrupt pasting/typing
        self._release_modifiers()

        mode = settings.injection_mode
        if mode == "paste":
            self._inject_via_paste(text)
        else:
            self._inject_via_typing(text)

    # ------------------------------------------------------------------
    # Paste mode (preferred)
    # ------------------------------------------------------------------

    def _inject_via_paste(self, text: str) -> None:
        """
        1. Save the current clipboard contents.
        2. Put our text on the clipboard.
        3. Simulate Ctrl+V.
        4. Restore the original clipboard after a short delay.
        """
        with self._clipboard_lock:
            # Save original clipboard
            try:
                original = pyperclip.paste()
            except Exception:
                original = ""

            try:
                pyperclip.copy(text)
                time.sleep(0.08)  # Brief pause for clipboard to propagate

                # Simulate Ctrl+V
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)

            except Exception as e:
                print(f"[TextInjection] Paste failed: {e}")
                # Fall back to typing
                self._inject_via_typing(text)
                return

        # Restore clipboard in background after delay
        def _restore():
            time.sleep(CLIPBOARD_RESTORE_DELAY)
            try:
                pyperclip.copy(original)
            except Exception:
                pass

        t = threading.Thread(target=_restore, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Type mode (fallback)
    # ------------------------------------------------------------------

    def _inject_via_typing(self, text: str) -> None:
        """Simulate typing the text character-by-character via pyautogui."""
        try:
            pyautogui.write(text, interval=0.01)
        except Exception as e:
            print(f"[TextInjection] Typing failed: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

text_injection_service = TextInjectionService()
