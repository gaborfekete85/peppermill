"""Tests for AgentLoop.run_once — the minimal v0.1 LLM call + tool loop."""
import pytest

from peppermill.agent.loop import AgentLoop
from peppermill.agent.tools.add import AddTool
from peppermill.bus.events import InboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.fake import FakeProvider, LLMResponse, ToolCallRequest


@pytest.fixture
def bus():
    return MessageBus()


async def test_run_once_executes_tool_and_publishes_outbound(bus):
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 5, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="The answer is 8.", finish_reason="stop"),
    ]
    loop = AgentLoop(bus=bus, provider=FakeProvider(script), tools={"add": AddTool()})
    inbound = InboundMessage(
        channel="cli", sender_id="u", chat_id="c", content="what is 5+3?"
    )

    await loop.run_once(inbound)

    out = await bus.consume_outbound()
    assert out.content == "The answer is 8."
    assert out.channel == "cli"
    assert out.chat_id == "c"


async def test_run_once_with_direct_text_response_publishes_immediately(bus):
    loop = AgentLoop(
        bus=bus,
        provider=FakeProvider([LLMResponse(content="hello", finish_reason="stop")]),
        tools={},
    )
    inbound = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="hi")

    await loop.run_once(inbound)

    out = await bus.consume_outbound()
    assert out.content == "hello"


async def test_run_once_handles_unknown_tool_as_error_message(bus):
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="missing", arguments={})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="recovered", finish_reason="stop"),
    ]
    loop = AgentLoop(bus=bus, provider=FakeProvider(script), tools={})
    inbound = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x")

    await loop.run_once(inbound)
    out = await bus.consume_outbound()
    assert out.content == "recovered"


async def test_run_once_handles_multiple_tool_calls_in_single_response(bus):
    script = [
        LLMResponse(
            tool_calls=[
                ToolCallRequest(id="1", name="add", arguments={"a": 1, "b": 1}),
                ToolCallRequest(id="2", name="add", arguments={"a": 5, "b": 5}),
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ]
    loop = AgentLoop(bus=bus, provider=FakeProvider(script), tools={"add": AddTool()})
    inbound = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x")

    await loop.run_once(inbound)
    out = await bus.consume_outbound()
    assert out.content == "done"
