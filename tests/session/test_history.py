"""Tests for history.py — low-level I/O."""
import json
import tempfile
from pathlib import Path

import pytest

from peppermill.session.history import (
    append_turn,
    ensure_session_dir,
    load_history,
)


@pytest.fixture
def tmp_sessions_dir():
    """Temporary directory for test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


async def test_load_history_returns_empty_list_if_file_missing(tmp_sessions_dir):
    result = await load_history("cli:main", base_path=tmp_sessions_dir)
    assert result == []


async def test_load_history_parses_valid_jsonl(tmp_sessions_dir):
    # Create history file manually
    session_dir = tmp_sessions_dir / "cli:main"
    session_dir.mkdir()
    history_file = session_dir / "history.jsonl"
    history_file.write_text(
        '{"turn": 1, "timestamp": "2026-06-04T10:30:00Z", "user_message": "hi", '
        '"assistant_response": "hello", "tools_used": [], "stop_reason": "completed"}\n'
        '{"turn": 2, "timestamp": "2026-06-04T10:30:15Z", "user_message": "hi again", '
        '"assistant_response": "hi back", "tools_used": [], "stop_reason": "completed"}\n'
    )

    result = await load_history("cli:main", base_path=tmp_sessions_dir)

    assert len(result) == 2
    assert result[0]["turn"] == 1
    assert result[1]["turn"] == 2


async def test_load_history_skips_malformed_json_lines(tmp_sessions_dir):
    # Create history file with one bad line in the middle
    session_dir = tmp_sessions_dir / "cli:main"
    session_dir.mkdir()
    history_file = session_dir / "history.jsonl"
    history_file.write_text(
        '{"turn": 1, "timestamp": "2026-06-04T10:30:00Z", "user_message": "hi", '
        '"assistant_response": "hello", "tools_used": [], "stop_reason": "completed"}\n'
        "this is not json\n"
        '{"turn": 2, "timestamp": "2026-06-04T10:30:15Z", "user_message": "hi again", '
        '"assistant_response": "hi back", "tools_used": [], "stop_reason": "completed"}\n'
    )

    result = await load_history("cli:main", base_path=tmp_sessions_dir)

    # Should skip the bad line and return turns 1 and 2
    assert len(result) == 2
    assert result[0]["turn"] == 1
    assert result[1]["turn"] == 2


async def test_append_turn_creates_session_dir(tmp_sessions_dir):
    turn_dict = {
        "turn": 1,
        "timestamp": "2026-06-04T10:30:00Z",
        "user_message": "test",
        "assistant_response": "response",
        "tools_used": [],
        "stop_reason": "completed",
    }

    await append_turn("cli:main", turn_dict, base_path=tmp_sessions_dir)

    session_dir = tmp_sessions_dir / "cli:main"
    assert session_dir.exists()


async def test_append_turn_appends_json_line_to_file(tmp_sessions_dir):
    turn1 = {
        "turn": 1,
        "timestamp": "2026-06-04T10:30:00Z",
        "user_message": "first",
        "assistant_response": "response1",
        "tools_used": [],
        "stop_reason": "completed",
    }
    turn2 = {
        "turn": 2,
        "timestamp": "2026-06-04T10:30:15Z",
        "user_message": "second",
        "assistant_response": "response2",
        "tools_used": ["add"],
        "stop_reason": "completed",
    }

    await append_turn("cli:main", turn1, base_path=tmp_sessions_dir)
    await append_turn("cli:main", turn2, base_path=tmp_sessions_dir)

    history_file = tmp_sessions_dir / "cli:main" / "history.jsonl"
    lines = history_file.read_text().strip().split("\n")

    assert len(lines) == 2
    assert json.loads(lines[0])["turn"] == 1
    assert json.loads(lines[1])["turn"] == 2


async def test_ensure_session_dir_creates_nested_path(tmp_sessions_dir):
    result = await ensure_session_dir("telegram:12345", base_path=tmp_sessions_dir)

    assert result.exists()
    assert result == tmp_sessions_dir / "telegram:12345"
