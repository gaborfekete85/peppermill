"""FakeProvider — a scripted LLM stand-in for v0.1.

The real LLMProvider ABC arrives in v0.2. For now, FakeProvider plays a
caller-supplied list of LLMResponses in order, ignoring its input. This
lets us exercise the agent loop, tool execution, and bus end-to-end with
zero network calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """One tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """A response from the LLM provider.

    Either ``content`` is set (text reply) or ``tool_calls`` is non-empty
    (the LLM wants to invoke tools). v0.1 trusts the script not to mix
    them; later versions add validation.
    """

    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class FakeProvider:
    """Plays back a fixed list of LLMResponses, one per ``chat()`` call."""

    def __init__(self, script: list[LLMResponse]) -> None:
        # Copy so caller's list isn't consumed via the index advance.
        self._script: list[LLMResponse] = list(script)
        self._idx: int = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if self._idx >= len(self._script):
            raise RuntimeError("FakeProvider script exhausted")
        resp = self._script[self._idx]
        self._idx += 1
        return resp
