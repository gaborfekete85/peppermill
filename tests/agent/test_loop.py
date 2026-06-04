"""Tests for AgentLoop FSM-level behaviour.

The runner is mocked out (ScriptedRunner) so these tests target only
what the loop does: drive the FSM, build the run spec, publish the
outbound. Tool execution coverage lives in tests/agent/test_runner.py.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from peppermill.agent.loop import AgentLoop, TurnState
from peppermill.agent.runner import AgentRunResult
from peppermill.agent.tools.add import AddTool
from peppermill.bus.events import InboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.base import LLMResponse
from peppermill.session.types import TurnSummary
from tests._helpers.in_memory_session_manager import InMemorySessionManager
from tests._helpers.scripted_provider import ScriptedProvider
from tests._helpers.scripted_runner import ScriptedRunner


@pytest.fixture
def bus():
    return MessageBus()


def _loop_with_runner(bus, runner, tools=None, session_manager=None):
    """Build an AgentLoop and inject a ScriptedRunner so the real runner is bypassed."""
    loop = AgentLoop(
        bus=bus,
        provider=ScriptedProvider([LLMResponse(content="never called")]),
        tools=tools or {},
        session_manager=session_manager or InMemorySessionManager(),
    )
    loop._runner = runner
    return loop


def _loop_with_session_manager(bus, runner, session_manager, tools=None):
    """Build an AgentLoop with ScriptedRunner and SessionManager."""
    loop = AgentLoop(
        bus=bus,
        provider=ScriptedProvider([LLMResponse(content="never called")]),
        tools=tools or {},
        session_manager=session_manager,
    )
    loop._runner = runner
    return loop


# ---------------------------------------------------------------------------
# TurnState enum
# ---------------------------------------------------------------------------


def test_turnstate_has_v04_states():
    """Pedagogical guard: the FSM includes RESTORE and SAVE in v0.4.

    Additional states (COMMAND, COMPACT) arrive in later
    versions; this test fails loudly if someone adds them prematurely.
    """
    assert {s.name for s in TurnState} == {"RESTORE", "BUILD", "RUN", "SAVE", "RESPOND", "DONE"}


# ---------------------------------------------------------------------------
# BUILD state — seeds messages + tool schemas
# ---------------------------------------------------------------------------


async def test_build_state_seeds_user_message_from_inbound(bus):
    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_runner(bus, runner, tools={"add": AddTool()})

    await loop.run_once(
        InboundMessage(channel="cli", sender_id="u", chat_id="c", content="What is 2+3?")
    )

    assert runner.last_spec is not None
    assert runner.last_spec.initial_messages == [
        {"role": "user", "content": "What is 2+3?"}
    ]


async def test_build_state_includes_tool_schemas_in_spec(bus):
    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_runner(bus, runner, tools={"add": AddTool()})

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x"))

    schemas = runner.last_spec.tool_schemas
    assert any(s.get("name") == "add" for s in schemas)


async def test_build_state_with_no_tools_passes_empty_schemas(bus):
    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_runner(bus, runner, tools={})

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x"))

    assert runner.last_spec.tool_schemas == []


async def test_run_state_forwards_max_iterations_to_spec(bus):
    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = AgentLoop(
        bus=bus,
        provider=ScriptedProvider([LLMResponse(content="x")]),
        tools={},
        max_iterations=7,
        session_manager=InMemorySessionManager(),
    )
    loop._runner = runner

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x"))
    assert runner.last_spec.max_iterations == 7


# ---------------------------------------------------------------------------
# RESPOND state — publishes outbound from runner result
# ---------------------------------------------------------------------------


async def test_respond_state_publishes_outbound_with_runner_final_content(bus):
    runner = ScriptedRunner([
        AgentRunResult(
            final_content="hello back",
            messages=[],
            tools_used=[],
            stop_reason="completed",
        ),
    ])
    loop = _loop_with_runner(bus, runner)

    await loop.run_once(
        InboundMessage(channel="cli", sender_id="u", chat_id="c", content="hi")
    )

    out = await bus.consume_outbound()
    assert out.content == "hello back"
    assert out.channel == "cli"
    assert out.chat_id == "c"


async def test_respond_state_publishes_empty_string_when_runner_returns_none(bus):
    """Matches v0.2 behaviour: OutboundMessage.content is always a string."""
    runner = ScriptedRunner([
        AgentRunResult(
            final_content=None,
            messages=[],
            tools_used=[],
            stop_reason="max_iterations",
        ),
    ])
    loop = _loop_with_runner(bus, runner)

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x"))
    out = await bus.consume_outbound()
    assert out.content == ""


# ---------------------------------------------------------------------------
# run_forever — drains inbound and processes each msg
# ---------------------------------------------------------------------------


async def test_run_forever_processes_inbound_messages_sequentially(bus):
    runner = ScriptedRunner([
        AgentRunResult(final_content="reply 1", messages=[], tools_used=[], stop_reason="completed"),
        AgentRunResult(final_content="reply 2", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_runner(bus, runner)

    task = asyncio.create_task(loop.run_forever())
    try:
        await bus.publish_inbound(
            InboundMessage(channel="cli", sender_id="u", chat_id="c", content="m1")
        )
        await bus.publish_inbound(
            InboundMessage(channel="cli", sender_id="u", chat_id="c", content="m2")
        )

        out1 = await asyncio.wait_for(bus.consume_outbound(), timeout=2.0)
        out2 = await asyncio.wait_for(bus.consume_outbound(), timeout=2.0)
        assert out1.content == "reply 1"
        assert out2.content == "reply 2"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# RESTORE state — load history from session manager
# ---------------------------------------------------------------------------


async def test_restore_state_loads_history_into_context(bus):
    """RESTORE should load past turns from session manager."""
    session_manager = InMemorySessionManager()
    # Pre-populate with one past turn
    await session_manager.save(
        "cli:main",
        TurnSummary(
            turn=1,
            timestamp="2026-06-04T10:30:00Z",
            user_message="What is 2+3?",
            assistant_response="The answer is 5.",
            tools_used=["add"],
            stop_reason="completed",
        ),
    )

    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_session_manager(bus, runner, session_manager)

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="main", content="What is 3+4?"))

    # Check that runner received messages with past context
    assert runner.last_spec is not None
    assert len(runner.last_spec.initial_messages) >= 3  # past user, past assistant, new user


async def test_restore_state_converts_history_to_messages(bus):
    """History records should be converted to user/assistant messages."""
    session_manager = InMemorySessionManager()
    await session_manager.save(
        "cli:main",
        TurnSummary(
            turn=1,
            timestamp="2026-06-04T10:30:00Z",
            user_message="first question",
            assistant_response="first answer",
            tools_used=[],
            stop_reason="completed",
        ),
    )

    runner = ScriptedRunner([
        AgentRunResult(final_content="ok", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_session_manager(bus, runner, session_manager)

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="main", content="second question"))

    # Messages passed to runner should include past context
    assert len(runner.last_spec.initial_messages) >= 3  # past user, past assistant, new user
    assert runner.last_spec.initial_messages[0]["content"] == "first question"
    assert runner.last_spec.initial_messages[1]["content"] == "first answer"
    assert runner.last_spec.initial_messages[2]["content"] == "second question"


async def test_save_state_persists_turn_to_session_manager(bus):
    """SAVE should append a TurnSummary to the session."""
    session_manager = InMemorySessionManager()

    runner = ScriptedRunner([
        AgentRunResult(
            final_content="hello there",
            messages=[],
            tools_used=["add"],
            stop_reason="completed",
        ),
    ])
    loop = _loop_with_session_manager(bus, runner, session_manager)

    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="main", content="hi there"))

    # Session should now have one turn
    loaded = await session_manager.load("cli:main")
    assert len(loaded) == 1
    assert loaded[0]["turn"] == 1
    assert loaded[0]["user_message"] == "hi there"
    assert loaded[0]["assistant_response"] == "hello there"
    assert loaded[0]["tools_used"] == ["add"]


async def test_full_two_turn_conversation_with_session_persistence(bus):
    """Full turn with history loading and saving."""
    session_manager = InMemorySessionManager()

    # First turn
    runner1 = ScriptedRunner([
        AgentRunResult(final_content="answer 1", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop = _loop_with_session_manager(bus, runner1, session_manager)
    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="main", content="question 1"))

    # Second turn: session should have history
    runner2 = ScriptedRunner([
        AgentRunResult(final_content="answer 2", messages=[], tools_used=[], stop_reason="completed"),
    ])
    loop._runner = runner2
    await loop.run_once(InboundMessage(channel="cli", sender_id="u", chat_id="main", content="question 2"))

    # Check final state
    final = await session_manager.load("cli:main")
    assert len(final) == 2
    assert final[0]["user_message"] == "question 1"
    assert final[1]["user_message"] == "question 2"

    # Second turn's spec should have had past context
    assert len(runner2.last_spec.initial_messages) >= 3
    assert runner2.last_spec.initial_messages[0]["content"] == "question 1"
