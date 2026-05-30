"""Tests for bus message dataclasses."""
from peppermill.bus.events import InboundMessage, OutboundMessage


def test_inbound_session_key_defaults_to_channel_and_chat_id():
    msg = InboundMessage(
        channel="cli", sender_id="user", chat_id="local", content="hi"
    )
    assert msg.session_key == "cli:local"

def test_inbound_session_key_uses_override_when_present():
    msg = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="local",
        content="hi",
        session_key_override="custom-key",
    )
    assert msg.session_key == "custom-key"

def test_inbound_default_factories_produce_distinct_collections():
    a = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="x")
    b = InboundMessage(channel="cli", sender_id="u", chat_id="c", content="y")
    a.media.append("img.png")
    a.metadata["k"] = "v"
    # If default factories were shared (e.g. `media: list = []`), b would
    # see a's mutations. This test guards against that classic footgun.
    assert b.media == []
    assert b.metadata == {}

def test_outbound_construction_and_defaults():
    out = OutboundMessage(channel="cli", chat_id="local", content="hello")
    assert out.channel == "cli"
    assert out.chat_id == "local"
    assert out.content == "hello"
    assert out.metadata == {}
