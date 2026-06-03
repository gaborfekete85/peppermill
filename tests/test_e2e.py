"""End-to-end test: inbound through bus → loop → ScriptedProvider →
tool → ScriptedProvider → out as OutboundMessage. Hermetic — no network."""
import asyncio

import pytest

from peppermill.agent.loop import AgentLoop
from peppermill.agent.tools.add import AddTool
from peppermill.bus.events import InboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.base import LLMResponse, ToolCallRequest
from tests._helpers.scripted_provider import ScriptedProvider


async def test_full_pipeline_inbound_to_outbound():
    bus = MessageBus()
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 2, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="The answer is 5.", finish_reason="stop"),
    ]
    agent = AgentLoop(
        bus=bus,
        provider=ScriptedProvider(script),
        tools={"add": AddTool()},
    )

    runner = asyncio.create_task(agent.run_forever())
    try:
        await bus.publish_inbound(
            InboundMessage(
                channel="cli",
                sender_id="u",
                chat_id="c",
                content="what is 2+3?",
            )
        )
        out = await asyncio.wait_for(bus.consume_outbound(), timeout=2.0)
        assert out.content == "The answer is 5."
        assert out.channel == "cli"
        assert out.chat_id == "c"
    finally:
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await runner
