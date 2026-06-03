"""LLMProvider ABC + shared LLM response types.

The ABC enforces that every provider implements `chat`. Future versions
will add `chat_stream` (v0.7) and discovery helpers (v0.12).

LLMResponse and ToolCallRequest are plain dataclasses — they're values
that travel between providers and the agent loop and don't need behaviour.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """One tool invocation the LLM has requested."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """One response from an LLM provider.

    Either ``content`` is set (text reply) or ``tool_calls`` is non-empty
    (the LLM wants to invoke tools). Both can be set when the LLM emits
    a preamble text before the tool calls.
    """

    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """The contract every LLM provider must satisfy.

    Subclasses must implement ``chat``. Instantiating either this ABC
    or a subclass that hasn't implemented every ``@abstractmethod``
    raises ``TypeError`` — this is what makes ABCs different from
    Protocols: nominal "is-a" enforcement at construction time.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send a single turn to the LLM and return the response."""
        ...
