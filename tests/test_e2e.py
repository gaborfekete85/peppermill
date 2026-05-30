"""End-to-end test: inbound message through the bus, through the loop,
through tool execution, out as an OutboundMessage."""
import asyncio

import pytest

from peppermill.agent.loop import AgentLoop
from peppermill.agent.tools.add import AddTool
from peppermill.bus.events import InboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.fake import FakeProvider, LLMResponse, ToolCallRequest


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
        provider=FakeProvider(script),
        tools={"add": AddTool()},
    )

    # Drive the loop in the background; cancel it after we get the reply.
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
