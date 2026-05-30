"""Message dataclasses exchanged on the bus.

InboundMessage flows: channel → bus → agent.
OutboundMessage flows: agent → bus → channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InboundMessage:
    """A message from a chat platform delivered to the agent."""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        """Logical session this message belongs to.

        Defaults to ``f"{channel}:{chat_id}"`` so each chat in each platform
        gets its own session, but channels can override it (e.g. to split
        a single chat into multiple threads).
        """
        return self.session_key_override or f"{self.channel}:{self.chat_id}"

@dataclass
class OutboundMessage:
    """A message the agent wants to send back through a channel."""

    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
