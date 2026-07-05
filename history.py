"""
history.py — FluidVoice Windows
Local transcription history stored as a JSON file.
Equivalent of the audio history + stats system on macOS.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from settings import settings, HISTORY_FILE


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    id: str
    timestamp: float          # Unix timestamp
    text: str                 # Final transcribed text
    enhanced_text: str        # AI-enhanced version (empty if not used)
    model: str                # Whisper model name used
    duration_sec: float       # Recording duration in seconds
    word_count: int           # Word count of final text

    @property
    def timestamp_display(self) -> str:
        import datetime
        dt = datetime.datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%b %d, %Y  %I:%M %p")

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(**d)


# ---------------------------------------------------------------------------
# HistoryStore
# ---------------------------------------------------------------------------

class HistoryStore:
    def __init__(self) -> None:
        self._entries: list[HistoryEntry] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if HISTORY_FILE.exists():
            try:
                with HISTORY_FILE.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._entries = [HistoryEntry.from_dict(d) for d in raw]
            except Exception:
                self._entries = []
        self._loaded = True

    def _save(self) -> None:
        try:
            with HISTORY_FILE.open("w", encoding="utf-8") as f:
                json.dump([asdict(e) for e in self._entries], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[HistoryStore] Save failed: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        text: str,
        duration_sec: float,
        model: str,
        enhanced_text: str = "",
    ) -> HistoryEntry:
        self._ensure_loaded()
        if not settings.history_enabled:
            return HistoryEntry(
                id="", timestamp=time.time(), text=text,
                enhanced_text=enhanced_text, model=model,
                duration_sec=duration_sec, word_count=len(text.split()),
            )

        import uuid
        entry = HistoryEntry(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            text=text,
            enhanced_text=enhanced_text,
            model=model,
            duration_sec=round(duration_sec, 2),
            word_count=len(text.split()),
        )
        self._entries.insert(0, entry)

        # Trim to max entries
        max_entries = settings.history_max_entries
        if len(self._entries) > max_entries:
            self._entries = self._entries[:max_entries]

        self._save()
        return entry

    def get_all(self) -> list[HistoryEntry]:
        self._ensure_loaded()
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._save()

    def today_stats(self) -> dict:
        """Return today's usage stats."""
        self._ensure_loaded()
        import datetime
        today = datetime.date.today()
        today_entries = [
            e for e in self._entries
            if datetime.date.fromtimestamp(e.timestamp) == today
        ]
        return {
            "count": len(today_entries),
            "words": sum(e.word_count for e in today_entries),
            "duration_sec": sum(e.duration_sec for e in today_entries),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

history_store = HistoryStore()
