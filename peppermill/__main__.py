"""`python -m peppermill` entry point.

Wires bus + CLI channel + agent loop + scripted fake provider + add tool
into a runnable program. v0.1 always plans `add(2, 3)` regardless of
input — proves the full pipeline end-to-end without an LLM.
"""
from __future__ import annotations

import asyncio
import logging

from peppermill.agent.loop import AgentLoop
from peppermill.agent.tools.add import AddTool
from peppermill.bus.queue import MessageBus
from peppermill.channels.cli import CLIChannel
from peppermill.providers.fake import FakeProvider, LLMResponse, ToolCallRequest


def _default_script() -> list[LLMResponse]:
    """The canned 'always plan add(2,3) and answer 5' script."""
    return [
        LLMResponse(
            tool_calls=[
                ToolCallRequest(id="call_1", name="add", arguments={"a": 2, "b": 3})
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="The answer is 5.", finish_reason="stop"),
    ]


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    bus = MessageBus()
    tools = {"add": AddTool()}
    provider = FakeProvider(_default_script())
    agent = AgentLoop(bus=bus, provider=provider, tools=tools)

    channel = CLIChannel(bus=bus)
    await channel.start()

    print("PepperMill v0.1 — type a message and press Enter. Ctrl-D to exit.", flush=True)
    await agent.run_forever()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
