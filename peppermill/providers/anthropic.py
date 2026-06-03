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
        body = self._build_request(messages, tools)
        response = await self._client.post(
            "/v1/messages",
            json=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        return self._parse_response(response.json())

    # -- request building ----------------------------------------------------

    def _build_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [self._translate_message(m) for m in messages],
        }
        if tools:
            body["tools"] = [self._to_anthropic_tool(t) for t in tools]
        return body

    def _translate_message(self, m: dict[str, Any]) -> dict[str, Any]:
        role = m["role"]
        if role == "user":
            return {"role": "user", "content": m["content"]}
        if role == "assistant":
            if "tool_calls" in m:
                blocks = [
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"],
                    }
                    for tc in m["tool_calls"]
                ]
                return {"role": "assistant", "content": blocks}
            return {"role": "assistant", "content": m["content"]}
        if role == "tool":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }
                ],
            }
        raise ValueError(f"unknown role: {role}")

    @staticmethod
    def _to_anthropic_tool(schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": schema["name"],
            "description": schema["description"],
            "input_schema": schema["parameters"],
        }

    # -- response parsing ----------------------------------------------------
    # (full _parse_response arrives in Task 9; minimal stub for Task 8 tests)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> LLMResponse:
        # Minimal Task 8 stub — full implementation in Task 9.
        return LLMResponse(content="hi", finish_reason="stop")
