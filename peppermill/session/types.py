# peppermill/session/types.py
"""Session types — TurnSummary for history storage."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TurnSummary:
    """One turn in a session's conversation history.

    Stored as JSON in history.jsonl, one per line.
    """

    turn: int  # 1-indexed turn number
    timestamp: str  # ISO 8601, e.g., "2026-06-04T10:30:00Z"
    user_message: str  # The raw user input
    assistant_response: str  # Final assistant text (empty string if None)
    tools_used: list[str]  # Tool names invoked (e.g., ["add"])
    stop_reason: str  # "completed" | "max_iterations"
