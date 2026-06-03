"""AnthropicProvider — real LLM provider using Anthropic's Messages API.

v0.2 scope: non-streaming, no retries, no extended thinking. Just send
a list of messages and tools, get back content + tool_calls.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from peppermill.providers.base import LLMProvider, LLMResponse

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


class AnthropicProvider(LLMProvider):
    """Calls Anthropic's POST /v1/messages endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
        timeout: float = 60.0,
        base_url: str = "https://api.anthropic.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
            self._owns_client = True

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        # Implemented in Tasks 8–10. For Task 7, just satisfy the ABC.
        raise NotImplementedError("chat() arrives in Task 8")
