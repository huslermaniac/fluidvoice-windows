"""
settings.py — FluidVoice Windows
JSON-backed settings store. Drop-in equivalent of SettingsStore.swift.
"""

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

import sys

# Dynamic path resolution to support PyInstaller bundling and local project directory
if getattr(sys, "frozen", False):
    APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "FluidVoice"
    MODELS_DIR = Path(sys._MEIPASS) / "models"
else:
    PROJECT_DIR = Path(__file__).parent.absolute()
    APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "FluidVoice"
    
    # Use local folder if present (helps with packaging / offline bundling)
    LOCAL_MODELS_DIR = PROJECT_DIR / "models"
    if LOCAL_MODELS_DIR.exists():
        MODELS_DIR = LOCAL_MODELS_DIR
    else:
        MODELS_DIR = APP_DIR / "models"

SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"

APP_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    # Hotkey
    "hotkey": "ctrl+alt+space",
    "hold_to_record": True,

    # Transcription model
    "model_name": "base",          # tiny | base | small | distil-small.en | medium | distil-large-v3 | large-v3
    "model_device": "auto",        # auto | cpu | cuda | rocm | vulkan | openvino
    "model_compute_type": "auto",  # auto | int8 | float16 | float32
    "language": None,              # None = auto-detect

    # Text injection
    "injection_mode": "paste",     # paste | type

    # AI enhancement
    "ai_enhancement_enabled": False,
    "ai_provider": "openai",       # openai | groq | custom
    "ai_api_key": "",
    "ai_base_url": "",             # for custom providers
    "ai_model": "gpt-4o-mini",
    "ai_prompt": (
        "You are a transcription post-processor. Fix punctuation, capitalization, "
        "and minor errors in the following dictated text. Return ONLY the corrected "
        "text, no commentary."
    ),

    # UI / appearance
    "overlay_enabled": True,
    "overlay_position": "bottom",  # bottom | top | cursor
    "theme": "dark",               # dark | light | system

    # Audio
    "input_device": None,          # None = system default

    # Onboarding
    "onboarding_complete": False,

    # History
    "history_enabled": True,
    "history_max_entries": 500,

    # Misc
    "show_in_taskbar": True,
    "start_with_windows": False,
}


# ---------------------------------------------------------------------------
# SettingsStore
# ---------------------------------------------------------------------------

class SettingsStore:
    """Thread-safe JSON-backed settings store. Singleton via module-level instance."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if SETTINGS_FILE.exists():
            try:
                with SETTINGS_FILE.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge saved values over defaults so new keys always exist
                self._data = {**DEFAULTS, **saved}
                # Sanitize device values (vulkan/openvino fall back to auto)
                if self._data.get("model_device") in ("vulkan", "openvino"):
                    self._data["model_device"] = "auto"
            except Exception:
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)

    def save(self) -> None:
        try:
            with SETTINGS_FILE.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsStore] Failed to save settings: {e}")

    # ------------------------------------------------------------------
    # Generic get / set
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    # ------------------------------------------------------------------
    # Typed convenience properties
    # ------------------------------------------------------------------

    @property
    def hotkey(self) -> str:
        return self._data.get("hotkey", DEFAULTS["hotkey"])

    @hotkey.setter
    def hotkey(self, value: str) -> None:
        self.set("hotkey", value)

    @property
    def hold_to_record(self) -> bool:
        return bool(self._data.get("hold_to_record", DEFAULTS["hold_to_record"]))

    @hold_to_record.setter
    def hold_to_record(self, value: bool) -> None:
        self.set("hold_to_record", value)

    @property
    def model_name(self) -> str:
        return self._data.get("model_name", DEFAULTS["model_name"])

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.set("model_name", value)

    @property
    def model_device(self) -> str:
        return self._data.get("model_device", DEFAULTS["model_device"])

    @model_device.setter
    def model_device(self, value: str) -> None:
        self.set("model_device", value)

    @property
    def model_compute_type(self) -> str:
        return self._data.get("model_compute_type", DEFAULTS["model_compute_type"])

    @model_compute_type.setter
    def model_compute_type(self, value: str) -> None:
        self.set("model_compute_type", value)

    @property
    def language(self) -> str | None:
        v = self._data.get("language", DEFAULTS["language"])
        return v if v else None

    @language.setter
    def language(self, value: str | None) -> None:
        self.set("language", value)

    @property
    def injection_mode(self) -> str:
        return self._data.get("injection_mode", DEFAULTS["injection_mode"])

    @injection_mode.setter
    def injection_mode(self, value: str) -> None:
        self.set("injection_mode", value)

    @property
    def ai_enhancement_enabled(self) -> bool:
        return bool(self._data.get("ai_enhancement_enabled", DEFAULTS["ai_enhancement_enabled"]))

    @ai_enhancement_enabled.setter
    def ai_enhancement_enabled(self, value: bool) -> None:
        self.set("ai_enhancement_enabled", value)

    @property
    def ai_provider(self) -> str:
        return self._data.get("ai_provider", DEFAULTS["ai_provider"])

    @ai_provider.setter
    def ai_provider(self, value: str) -> None:
        self.set("ai_provider", value)

    @property
    def ai_api_key(self) -> str:
        return self._data.get("ai_api_key", "")

    @ai_api_key.setter
    def ai_api_key(self, value: str) -> None:
        self.set("ai_api_key", value)

    @property
    def ai_base_url(self) -> str:
        return self._data.get("ai_base_url", "")

    @ai_base_url.setter
    def ai_base_url(self, value: str) -> None:
        self.set("ai_base_url", value)

    @property
    def ai_model(self) -> str:
        return self._data.get("ai_model", DEFAULTS["ai_model"])

    @ai_model.setter
    def ai_model(self, value: str) -> None:
        self.set("ai_model", value)

    @property
    def ai_prompt(self) -> str:
        return self._data.get("ai_prompt", DEFAULTS["ai_prompt"])

    @ai_prompt.setter
    def ai_prompt(self, value: str) -> None:
        self.set("ai_prompt", value)

    @property
    def overlay_enabled(self) -> bool:
        return bool(self._data.get("overlay_enabled", DEFAULTS["overlay_enabled"]))

    @overlay_enabled.setter
    def overlay_enabled(self, value: bool) -> None:
        self.set("overlay_enabled", value)

    @property
    def overlay_position(self) -> str:
        return self._data.get("overlay_position", DEFAULTS["overlay_position"])

    @overlay_position.setter
    def overlay_position(self, value: str) -> None:
        self.set("overlay_position", value)

    @property
    def theme(self) -> str:
        return self._data.get("theme", DEFAULTS["theme"])

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)

    @property
    def input_device(self) -> int | None:
        v = self._data.get("input_device", None)
        return int(v) if v is not None else None

    @input_device.setter
    def input_device(self, value: int | None) -> None:
        self.set("input_device", value)

    @property
    def onboarding_complete(self) -> bool:
        return bool(self._data.get("onboarding_complete", False))

    @onboarding_complete.setter
    def onboarding_complete(self, value: bool) -> None:
        self.set("onboarding_complete", value)

    @property
    def history_enabled(self) -> bool:
        return bool(self._data.get("history_enabled", DEFAULTS["history_enabled"]))

    @history_enabled.setter
    def history_enabled(self, value: bool) -> None:
        self.set("history_enabled", value)

    @property
    def history_max_entries(self) -> int:
        return int(self._data.get("history_max_entries", DEFAULTS["history_max_entries"]))

    @property
    def start_with_windows(self) -> bool:
        return bool(self._data.get("start_with_windows", False))

    @start_with_windows.setter
    def start_with_windows(self, value: bool) -> None:
        self.set("start_with_windows", value)
        _apply_startup_registry(value)


# ---------------------------------------------------------------------------
# Windows startup registry helper
# ---------------------------------------------------------------------------

def _apply_startup_registry(enable: bool) -> None:
    """Add or remove FluidVoice from the Windows startup registry key."""
    try:
        import sys
        import winreg  # type: ignore[import]
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe = sys.executable
                winreg.SetValueEx(key, "FluidVoice", 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(key, "FluidVoice")
                except FileNotFoundError:
                    pass
    except Exception as e:
        print(f"[SettingsStore] Registry startup error: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

settings = SettingsStore()
