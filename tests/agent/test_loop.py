"""Tests for AgentLoop FSM-level behaviour.

The runner is mocked out (ScriptedRunner) so these tests target only
what the loop does: drive the FSM, build the run spec, publish the
outbound. Tool execution coverage lives in tests/agent/test_runner.py.
"""
import asyncio

import pytest

from peppermill.agent.loop import AgentLoop, TurnState
from peppermill.agent.runner import AgentRunResult
from peppermill.agent.tools.add import AddTool
from peppermill.bus.events import InboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.base import LLMResponse
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
