# tests/_helpers/in_memory_session_manager.py
"""InMemorySessionManager — test-only SessionManager stand-in."""
from __future__ import annotations

from typing import Any

from peppermill.session.types import TurnSummary


class InMemorySessionManager:
    """Mock SessionManager for tests — stores history in dict, not on disk.

    Useful for testing FSM-level logic without disk I/O.
    """

    def __init__(self) -> None:
        """Initialize with empty sessions dict."""
        self.sessions: dict[str, list[dict[str, Any]]] = {}

    async def load(self, session_key: str) -> list[dict[str, Any]]:
        """Load turns for a session."""
        return self.sessions.get(session_key, [])

    async def save(self, session_key: str, turn: TurnSummary) -> None:
        """Save one turn to a session."""
        if session_key not in self.sessions:
            self.sessions[session_key] = []
        turn_dict = {
            "turn": turn.turn,
            "timestamp": turn.timestamp,
            "user_message": turn.user_message,
            "assistant_response": turn.assistant_response,
            "tools_used": turn.tools_used,
            "stop_reason": turn.stop_reason,
        }
        self.sessions[session_key].append(turn_dict)
