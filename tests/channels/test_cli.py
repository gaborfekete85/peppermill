"""Tests for CLIChannel.

The reader half (stdin) is integration-tested manually in Task 12 because
faking stdin reliably across platforms is more friction than it's worth at
v0.1. The writer half (consumes outbound, prints) is easy to test by
patching print.
"""
import asyncio

from peppermill.bus.events import InboundMessage, OutboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.channels.cli import CLIChannel


async def test_writer_consumes_outbound_and_prints(capfd):
    bus = MessageBus()
    channel = CLIChannel(bus=bus)
    writer = asyncio.create_task(channel._write_stdout())

    await bus.publish_outbound(
        OutboundMessage(channel="cli", chat_id="local", content="hello world")
    )
    # Give the writer a tick to consume + print.
    await asyncio.sleep(0.05)

    writer.cancel()
    try:
        await writer
    except asyncio.CancelledError:
        pass

    captured = capfd.readouterr()
    assert "hello world" in captured.out


async def test_publish_inbound_helper_pushes_to_bus():
    """CLIChannel exposes _publish_inbound for use by the stdin reader.

    Keeps the bus-publish detail centralised so the stdin reader test
    doesn't need its own duplicate.
    """
    bus = MessageBus()
    channel = CLIChannel(bus=bus)
    await channel._publish_inbound("hi there")

    msg: InboundMessage = await bus.consume_inbound()
    assert msg.content == "hi there"
    assert msg.channel == "cli"
    assert msg.sender_id == "user"
    assert msg.chat_id == "local"
