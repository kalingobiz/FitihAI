"""In-memory conversation sessions with expiry.

Nothing here is persisted: when a session expires or the process restarts, the
conversation is gone. This is deliberate (privacy by design).
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from .i18n import normalize_language


@dataclass
class Session:
    id: str
    language: str
    history: list[dict] = field(default_factory=list)
    last_seen: float = field(default_factory=time.monotonic)


class SessionStore:
    def __init__(self, ttl_minutes: int = 30, max_turns: int = 6):
        self.ttl = ttl_minutes * 60
        self.max_turns = max_turns
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.ttl
        for sid in [sid for sid, s in self._sessions.items() if s.last_seen < cutoff]:
            del self._sessions[sid]

    def get(self, session_id: str | None, language: str | None = None) -> Session:
        with self._lock:
            self._expire()
            session = self._sessions.get(session_id or "")
            if session is None:
                session = Session(id=session_id or secrets.token_urlsafe(16), language=normalize_language(language))
                self._sessions[session.id] = session
            elif language:
                session.language = normalize_language(language)
            session.last_seen = time.monotonic()
            return session

    def append(self, session: Session, user: str, assistant: str) -> None:
        with self._lock:
            session.history.extend([
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ])
            session.history[:] = session.history[-2 * self.max_turns :]

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
