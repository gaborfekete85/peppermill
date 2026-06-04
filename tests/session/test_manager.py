"""Tests for SessionManager."""
import json
import tempfile
from pathlib import Path

import pytest

from peppermill.session.manager import SessionManager
from peppermill.session.types import TurnSummary


@pytest.fixture
def tmp_sessions_dir():
    """Temporary directory for test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def session_manager(tmp_sessions_dir):
    """SessionManager instance with tmp dir."""
    return SessionManager(base_path=tmp_sessions_dir)


async def test_manager_load_returns_empty_list_if_missing(session_manager):
    result = await session_manager.load("cli:main")
    assert result == []


async def test_manager_load_and_save_roundtrip(session_manager):
    turn1 = TurnSummary(
        turn=1,
        timestamp="2026-06-04T10:30:00Z",
        user_message="hello",
        assistant_response="hi there",
        tools_used=[],
        stop_reason="completed",
    )

    await session_manager.save("cli:main", turn1)
    loaded = await session_manager.load("cli:main")

    assert len(loaded) == 1
    assert loaded[0]["turn"] == 1
    assert loaded[0]["user_message"] == "hello"


async def test_manager_multiple_sessions_isolated(session_manager):
    turn_a = TurnSummary(
        turn=1,
        timestamp="2026-06-04T10:30:00Z",
        user_message="from A",
        assistant_response="response A",
        tools_used=[],
        stop_reason="completed",
    )
    turn_b = TurnSummary(
        turn=1,
        timestamp="2026-06-04T10:30:00Z",
        user_message="from B",
        assistant_response="response B",
        tools_used=[],
        stop_reason="completed",
    )

    await session_manager.save("cli:a", turn_a)
    await session_manager.save("cli:b", turn_b)

    loaded_a = await session_manager.load("cli:a")
    loaded_b = await session_manager.load("cli:b")

    assert loaded_a[0]["user_message"] == "from A"
    assert loaded_b[0]["user_message"] == "from B"
