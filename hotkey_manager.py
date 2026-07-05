"""
hotkey_manager.py — FluidVoice Windows
Global hotkey registration and management.
Equivalent of GlobalHotkeyManager.swift (CGEvent tap / Carbon on macOS).

Supports:
  - Hold-to-record: key down → start, key up → stop
  - Toggle: first press → start, second press → stop
"""

from __future__ import annotations

import threading
from typing import Callable

import keyboard  # type: ignore[import]

from settings import settings


# ---------------------------------------------------------------------------
# HotkeyManager
# ---------------------------------------------------------------------------

class HotkeyManager:
    """
    Listens for a global hotkey and fires start/stop callbacks.

    Usage:
        manager = HotkeyManager()
        manager.on_start = lambda: print("Record start")
        manager.on_stop  = lambda: print("Record stop")
        manager.start()
        ...
        manager.stop()
    """

    def __init__(self) -> None:
        self.on_start: Callable[[], None] | None = None
        self.on_stop: Callable[[], None] | None = None

        self._active = False
        self._toggle_state = False    # For toggle mode: True = recording
        self._current_hotkey = ""
        self._hook_id = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin listening for the configured hotkey."""
        self._active = True
        self._register_hotkey(settings.hotkey)

    def stop(self) -> None:
        """Stop listening."""
        self._active = False
        self._unregister_hotkey()

    def reload_hotkey(self) -> None:
        """Re-register after the hotkey setting changes."""
        if self._active:
            self._unregister_hotkey()
            self._register_hotkey(settings.hotkey)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register_hotkey(self, hotkey_str: str) -> None:
        self._unregister_hotkey()
        self._current_hotkey = hotkey_str

        try:
            if settings.hold_to_record:
                # Hold-to-record: separate down/up hooks
                keyboard.add_hotkey(hotkey_str, self._on_key_down, suppress=False)
                keyboard.on_release_key(
                    hotkey_str.split("+")[-1],  # watch release of the last key
                    self._on_key_up,
                    suppress=False,
                )
            else:
                # Toggle mode
                keyboard.add_hotkey(hotkey_str, self._on_toggle, suppress=False)

            print(f"[HotkeyManager] Registered hotkey: {hotkey_str}")
        except Exception as e:
            print(f"[HotkeyManager] Failed to register hotkey '{hotkey_str}': {e}")

    def _unregister_hotkey(self) -> None:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

    def _on_key_down(self) -> None:
        with self._lock:
            if not self._active:
                return
        if self.on_start:
            # Run in thread to avoid blocking keyboard listener
            threading.Thread(target=self.on_start, daemon=True).start()

    def _on_key_up(self, event) -> None:  # noqa: ANN001
        with self._lock:
            if not self._active:
                return
        if self.on_stop:
            threading.Thread(target=self.on_stop, daemon=True).start()

    def _on_toggle(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._toggle_state = not self._toggle_state
            starting = self._toggle_state

        if starting:
            if self.on_start:
                threading.Thread(target=self.on_start, daemon=True).start()
        else:
            if self.on_stop:
                threading.Thread(target=self.on_stop, daemon=True).start()

    # ------------------------------------------------------------------
    # Hotkey recording (for the settings UI "click to set" flow)
    # ------------------------------------------------------------------

    @staticmethod
    def capture_hotkey(timeout: float = 10.0) -> str | None:
        """
        Block until the user presses a key combination and return it as a string.
        Returns None if timed out.
        """
        result: list[str] = []
        event = threading.Event()

        def _handler(e: keyboard.KeyboardEvent) -> None:
            if e.event_type == keyboard.KEY_DOWN:
                mods = []
                if keyboard.is_pressed("ctrl"):
                    mods.append("ctrl")
                if keyboard.is_pressed("alt"):
                    mods.append("alt")
                if keyboard.is_pressed("shift"):
                    mods.append("shift")
                if keyboard.is_pressed("windows"):
                    mods.append("windows")
                key = e.name
                if key not in ("ctrl", "alt", "shift", "left windows", "right windows"):
                    combo = "+".join(mods + [key])
                    result.append(combo)
                    event.set()

        hook = keyboard.hook(_handler)
        event.wait(timeout=timeout)
        keyboard.unhook(hook)
        return result[0] if result else None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

hotkey_manager = HotkeyManager()
