"""Low-level session history I/O.

Handles loading and appending to history.jsonl files.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_BASE_PATH = Path.home() / ".peppermill" / "sessions"


async def load_history(
    session_key: str, base_path: Path | None = None
) -> list[dict[str, Any]]:
    """Load all turns from a session's history.jsonl.

    Args:
        session_key: e.g., "cli:main"
        base_path: Root sessions directory. Defaults to ~/.peppermill/sessions/

    Returns:
        List of turn dicts (parsed JSON lines).
        Silently skips malformed lines (logs warning).
        Returns [] if file doesn't exist.
    """
    if base_path is None:
        base_path = DEFAULT_BASE_PATH

    history_file = base_path / session_key / "history.jsonl"

    if not history_file.exists():
        return []

    turns = []
    for line_num, line in enumerate(history_file.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            turns.append(json.loads(line))
        except json.JSONDecodeError as exc:
            log.warning(
                "Skipping malformed JSON in session %s line %d: %s",
                session_key,
                line_num,
                exc,
            )
    return turns


async def append_turn(
    session_key: str, turn_dict: dict[str, Any], base_path: Path | None = None
) -> None:
    """Append one turn to a session's history.jsonl.

    Creates the session directory if it doesn't exist.

    Args:
        session_key: e.g., "cli:main"
        turn_dict: TurnSummary as dict
        base_path: Root sessions directory. Defaults to ~/.peppermill/sessions/

    Raises:
        OSError: If directory creation fails.
    """
    if base_path is None:
        base_path = DEFAULT_BASE_PATH

    session_dir = await ensure_session_dir(session_key, base_path=base_path)
    history_file = session_dir / "history.jsonl"

    # Simple append: write JSON + newline
    json_line = json.dumps(turn_dict)
    with open(history_file, "a") as f:
        f.write(json_line + "\n")


async def ensure_session_dir(session_key: str, base_path: Path | None = None) -> Path:
    """Create a session directory if it doesn't exist.

    Args:
        session_key: e.g., "cli:main"
        base_path: Root sessions directory. Defaults to ~/.peppermill/sessions/

    Returns:
        Path to the session directory.

    Raises:
        OSError: If creation fails (permissions, disk full, etc.).
    """
    if base_path is None:
        base_path = DEFAULT_BASE_PATH

    session_dir = base_path / session_key
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir
