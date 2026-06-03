"""ScriptedProvider — test-only LLMProvider that returns canned responses.

Lives in tests/_helpers/ rather than peppermill/providers/ because it
exists purely to make tests hermetic, not as production code. It still
subclasses LLMProvider so the ABC contract is enforced.
"""
from __future__ import annotations

from typing import Any

from peppermill.providers.base import LLMProvider, LLMResponse


class ScriptedProvider(LLMProvider):
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
            raise RuntimeError("ScriptedProvider script exhausted")
        resp = self._script[self._idx]
        self._idx += 1
        return resp
