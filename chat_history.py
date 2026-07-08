"""
chat_history.py — FluidVoice Windows
Manages and persists Command Mode conversation sessions to a local JSON file.
Equivalent of ChatHistoryStore.swift on macOS.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from settings import APP_DIR

CHAT_HISTORY_FILE = APP_DIR / "chat_history.json"


@dataclass
class ChatMessage:
    id: str
    role: str                 # "user" | "assistant" | "tool"
    content: str
    timestamp: float          # Unix timestamp
    step_type: str = "normal" # "normal" | "thinking" | "checking" | "executing" | "verifying" | "success" | "failure"
    tool_call: Optional[dict[str, Any]] = None # {"id": "", "command": "", "workingDirectory": "", "purpose": ""}

    @classmethod
    def from_dict(cls, d: dict) -> ChatMessage:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            role=d.get("role", "user"),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", time.time()),
            step_type=d.get("step_type", "normal"),
            tool_call=d.get("tool_call")
        )


@dataclass
class ChatSession:
    id: str
    title: str = "New Chat"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[ChatMessage] = field(default_factory=list)

    def update_title_from_first_message(self) -> None:
        """Update the title of the chat from the first user message."""
        user_msgs = [m for m in self.messages if m.role == "user"]
        if user_msgs:
            first_user_text = user_msgs[0].content.strip()
            if len(first_user_text) > 40:
                self.title = first_user_text[:37] + "..."
            else:
                self.title = first_user_text if first_user_text else "New Chat"
        else:
            self.title = "New Chat"

    @classmethod
    def from_dict(cls, d: dict) -> ChatSession:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            title=d.get("title", "New Chat"),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])]
        )


class ChatHistoryStore:
    def __init__(self) -> None:
        self.sessions: list[ChatSession] = []
        self.current_chat_id: Optional[str] = None
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        if CHAT_HISTORY_FILE.exists():
            try:
                with CHAT_HISTORY_FILE.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                sessions_raw = raw.get("sessions", [])
                self.sessions = [ChatSession.from_dict(s) for s in sessions_raw]
                self.current_chat_id = raw.get("current_chat_id")
            except Exception as e:
                print(f"[ChatHistoryStore] Load failed: {e}")
                self.sessions = []
                self.current_chat_id = None
        
        # Ensure there is always a session available
        if not self.sessions:
            self.create_new_chat()
        elif not self.current_chat_id or not any(s.id == self.current_chat_id for s in self.sessions):
            self.current_chat_id = self.sessions[0].id

        self._loaded = True

    def save(self) -> None:
        try:
            payload = {
                "current_chat_id": self.current_chat_id,
                "sessions": [asdict(s) for s in self.sessions]
            }
            with CHAT_HISTORY_FILE.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ChatHistoryStore] Save failed: {e}")

    @property
    def current_session(self) -> Optional[ChatSession]:
        self._ensure_loaded()
        return next((s for s in self.sessions if s.id == self.current_chat_id), None)

    def create_new_chat(self) -> ChatSession:
        new_session = ChatSession(id=str(uuid.uuid4()))
        self.sessions.insert(0, new_session)
        self.current_chat_id = new_session.id
        self.save()
        return new_session

    def delete_current_chat(self) -> None:
        if not self.current_chat_id:
            return
        
        self.sessions = [s for s in self.sessions if s.id != self.current_chat_id]
        if self.sessions:
            self.current_chat_id = self.sessions[0].id
        else:
            self.create_new_chat()
        self.save()

    def update_current_chat(self, messages: list[ChatMessage]) -> None:
        session = self.current_session
        if session:
            session.messages = messages
            session.updated_at = time.time()
            session.update_title_from_first_message()
            self.save()

    def switch_to_chat(self, chat_id: str) -> bool:
        if any(s.id == chat_id for s in self.sessions):
            self.current_chat_id = chat_id
            self.save()
            return True
        return False

    def get_recent_chats(self, excluding_current: bool = False) -> list[ChatSession]:
        self._ensure_loaded()
        sorted_sessions = sorted(self.sessions, key=lambda s: s.updated_at, reverse=True)
        if excluding_current and self.current_chat_id:
            return [s for s in sorted_sessions if s.id != self.current_chat_id]
        return sorted_sessions

    def clear(self) -> None:
        self.sessions = []
        self.create_new_chat()


chat_history_store = ChatHistoryStore()
