"""Tests for the MessageBus (two asyncio.Queue wrappers)."""
from peppermill.bus.events import InboundMessage, OutboundMessage
from peppermill.bus.queue import MessageBus


async def test_publish_and_consume_inbound_roundtrip():
    bus = MessageBus()
    msg = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="hi")
    await bus.publish_inbound(msg)
    received = await bus.consume_inbound()
    assert received is msg  # identity, not equality


async def test_publish_and_consume_outbound_roundtrip():
    bus = MessageBus()
    out = OutboundMessage(channel="cli", chat_id="c", content="hello")
    await bus.publish_outbound(out)
    received = await bus.consume_outbound()
    assert received is out


async def test_inbound_and_outbound_queues_are_independent():
    """Putting on one queue must not affect the other."""
    bus = MessageBus()
    inb = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="hi")
    out = OutboundMessage(channel="cli", chat_id="c", content="hello")
    await bus.publish_inbound(inb)
    await bus.publish_outbound(out)
    assert await bus.consume_inbound() is inb
    assert await bus.consume_outbound() is out


async def test_consume_inbound_preserves_fifo_order():
    bus = MessageBus()
    msgs = [
        InboundMessage(channel="cli", sender_id="u", chat_id="c", content=f"m{i}")
        for i in range(3)
    ]
    for m in msgs:
        await bus.publish_inbound(m)
    received = [await bus.consume_inbound() for _ in range(3)]
    assert [m.content for m in received] == ["m0", "m1", "m2"]
