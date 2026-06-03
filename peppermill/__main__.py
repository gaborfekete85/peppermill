"""`python -m peppermill` entry point.

v0.2: wires the real AnthropicProvider. Requires ANTHROPIC_API_KEY.
Type messages on stdin; Claude Haiku 4.5 decides whether to call the
`add` tool; response prints to stdout. Ctrl-D to exit.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from peppermill.agent.loop import AgentLoop
from peppermill.agent.tools.add import AddTool
from peppermill.bus.queue import MessageBus
from peppermill.channels.cli import CLIChannel
from peppermill.providers.anthropic import AnthropicProvider


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it before running peppermill, e.g.:\n"
            "  export ANTHROPIC_API_KEY=sk-...",
            file=sys.stderr,
        )
        raise SystemExit(1)

    bus = MessageBus()
    tools = {"add": AddTool()}
    provider = AnthropicProvider()
    agent = AgentLoop(bus=bus, provider=provider, tools=tools)

    channel = CLIChannel(bus=bus)
    await channel.start()

    print("PepperMill v0.2 — type a message and press Enter. Ctrl-D to exit.", flush=True)
    await agent.run_forever()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
