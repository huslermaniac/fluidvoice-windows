"""
audio_capture.py — FluidVoice Windows
Microphone capture using sounddevice with simple energy-based VAD.
Equivalent of AVFoundation + CoreAudio audio pipeline on macOS.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from settings import settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16_000           # Whisper expects 16 kHz
CHANNELS = 1
DTYPE = "float32"
BLOCK_DURATION_MS = 30         # Size of each audio block in ms
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION_MS / 1000)

# VAD thresholds
SILENCE_THRESHOLD = 0.01       # RMS below this → silence
SILENCE_TIMEOUT_SEC = 1.5      # Auto-stop after this much silence (push-to-talk off)


# ---------------------------------------------------------------------------
# AudioCaptureService
# ---------------------------------------------------------------------------

class AudioCaptureService:
    """
    Records from the microphone while active.

    Usage (hold-to-record mode):
        service.start_recording()
        ... user holds key ...
        audio = service.stop_recording()   # returns numpy float32 array at 16 kHz

    Usage (push-to-talk / toggle mode):
        service.start_recording()
        ... VAD detects silence for > SILENCE_TIMEOUT_SEC ...
        service.on_auto_stop_callback fires
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._silence_timer: threading.Timer | None = None

        # Callbacks
        self.on_auto_stop_callback: Callable[[], None] | None = None
        self.on_level_callback: Callable[[float], None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._frames = []

        device = settings.input_device
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            device=device,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return the collected audio as a 1-D float32 array."""
        self._cancel_silence_timer()
        with self._lock:
            if not self._recording:
                return np.array([], dtype=np.float32)
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            frames = list(self._frames)
            self._frames = []

        if not frames:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(frames, axis=0).flatten()
        return audio

    def get_current_buffer(self) -> np.ndarray:
        """Return all audio frames recorded so far as a 1-D float32 array, without stopping."""
        with self._lock:
            if not self._recording or not self._frames:
                return np.array([], dtype=np.float32)
            frames = list(self._frames)
        return np.concatenate(frames, axis=0).flatten()

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------

    @staticmethod
    def list_input_devices() -> list[dict]:
        """Return a list of available input devices."""
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                devices.append({
                    "index": i,
                    "name": dev["name"],
                    "channels": dev["max_input_channels"],
                    "default_samplerate": dev["default_samplerate"],
                })
        return devices

    @staticmethod
    def get_default_input_device() -> dict | None:
        try:
            idx = sd.default.device[0]
            dev = sd.query_devices(idx)
            return {"index": idx, "name": dev["name"]}
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        with self._lock:
            if not self._recording:
                return
            chunk = indata.copy()
            self._frames.append(chunk)

        rms = float(np.sqrt(np.mean(chunk ** 2)))

        # Fire level callback for UI meter
        if self.on_level_callback:
            self.on_level_callback(rms)

        # VAD: reset silence timer on sound, trigger auto-stop on sustained silence
        if not settings.hold_to_record:
            if rms > SILENCE_THRESHOLD:
                self._cancel_silence_timer()
            else:
                self._start_silence_timer()

    def _start_silence_timer(self) -> None:
        if self._silence_timer is None or not self._silence_timer.is_alive():
            self._silence_timer = threading.Timer(
                SILENCE_TIMEOUT_SEC, self._on_silence_detected
            )
            self._silence_timer.daemon = True
            self._silence_timer.start()

    def _cancel_silence_timer(self) -> None:
        if self._silence_timer is not None:
            self._silence_timer.cancel()
            self._silence_timer = None

    def _on_silence_detected(self) -> None:
        if self._recording and self.on_auto_stop_callback:
            self.on_auto_stop_callback()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

audio_service = AudioCaptureService()
