"""SessionManager — high-level session history API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from peppermill.session import history
from peppermill.session.types import TurnSummary


class SessionManager:
    """Manages session history across conversations.

    Wraps history.py with a clean async API.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize SessionManager.

        Args:
            base_path: Root directory for all sessions.
                Defaults to ~/.peppermill/sessions/
        """
        self._base_path = base_path

    async def load(self, session_key: str) -> list[dict[str, Any]]:
        """Load all turns for a session.

        Args:
            session_key: e.g., "cli:main"

        Returns:
            List of turn dicts, or [] if session doesn't exist.
        """
        return await history.load_history(session_key, base_path=self._base_path)

    async def save(self, session_key: str, turn: TurnSummary) -> None:
        """Save one turn to a session's history.

        Args:
            session_key: e.g., "cli:main"
            turn: TurnSummary to append
        """
        turn_dict = {
            "turn": turn.turn,
            "timestamp": turn.timestamp,
            "user_message": turn.user_message,
            "assistant_response": turn.assistant_response,
            "tools_used": turn.tools_used,
            "stop_reason": turn.stop_reason,
        }
        await history.append_turn(session_key, turn_dict, base_path=self._base_path)
