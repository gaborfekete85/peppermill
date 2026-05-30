"""CLIChannel — reads lines from stdin, writes outbound to stdout.

v0.1 keeps this concrete (no BaseChannel ABC) — the ABC arrives in v0.11
when we add a second channel. The shape (start/stop/send-ish) is preserved
so retrofitting later is cheap.

Pattern note: sys.stdin.readline is blocking, so we run it in a thread
pool executor via loop.run_in_executor(None, ...). This is the canonical
way to use blocking I/O from an asyncio program without freezing the loop.
"""
from __future__ import annotations

import asyncio
import sys

from peppermill.bus.events import InboundMessage, OutboundMessage
from peppermill.bus.queue import MessageBus


class CLIChannel:
    CHANNEL_NAME = "cli"
    CHAT_ID = "local"
    SENDER_ID = "user"

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._reader_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._reader_task = asyncio.create_task(self._read_stdin())
        self._writer_task = asyncio.create_task(self._write_stdout())

    async def _read_stdin(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:  # EOF (Ctrl-D)
                return
            content = line.rstrip("\n").rstrip("\r")
            if not content:
                continue
            await self._publish_inbound(content)

    async def _publish_inbound(self, content: str) -> None:
        await self._bus.publish_inbound(
            InboundMessage(
                channel=self.CHANNEL_NAME,
                sender_id=self.SENDER_ID,
                chat_id=self.CHAT_ID,
                content=content,
            )
        )

    async def _write_stdout(self) -> None:
        while True:
            msg: OutboundMessage = await self._bus.consume_outbound()
            print(f"\n{msg.content}\n", flush=True)
