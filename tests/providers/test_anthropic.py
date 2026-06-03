"""Hermetic tests for AnthropicProvider using httpx.MockTransport — no network."""

from typing import Any

import httpx
import pytest

from peppermill.providers.anthropic import AnthropicProvider

# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


def test_constructor_requires_api_key(monkeypatch):
    """No api_key arg and no env var → fail loudly at construction."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()


def test_constructor_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    provider = AnthropicProvider()
    assert provider.api_key == "env-key"


def test_constructor_explicit_api_key_overrides_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    provider = AnthropicProvider(api_key="explicit-key")
    assert provider.api_key == "explicit-key"


def test_constructor_defaults_to_haiku_4_5_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    provider = AnthropicProvider()
    assert provider.model == "claude-haiku-4-5-20251001"


def test_constructor_accepts_model_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    provider = AnthropicProvider(model="claude-sonnet-4-6")
    assert provider.model == "claude-sonnet-4-6"


def test_constructor_with_injected_client_does_not_create_its_own():
    """When a client is supplied, the provider stores it as-is."""
    sentinel_client = httpx.AsyncClient()
    provider = AnthropicProvider(api_key="x", client=sentinel_client)
    assert provider._client is sentinel_client


# ---------------------------------------------------------------------------
# Request-building tests
# ---------------------------------------------------------------------------


def _capture_request_client(captured: dict[str, Any], response_payload: dict[str, Any] | None = None) -> httpx.AsyncClient:
    """Build an AsyncClient with a MockTransport that records the outbound request."""
    payload = response_payload or {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}],
        "stop_reason": "end_turn",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode()
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )


async def test_chat_posts_to_messages_endpoint_with_required_headers():
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(api_key="test-key", client=_capture_request_client(captured))

    await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["content-type"] == "application/json"


async def test_chat_body_includes_model_and_max_tokens():
    import json
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(
        api_key="k", model="my-model", max_tokens=999, client=_capture_request_client(captured)
    )

    await provider.chat(messages=[{"role": "user", "content": "hi"}])
    body = json.loads(captured["body"])

    assert body["model"] == "my-model"
    assert body["max_tokens"] == 999


async def test_chat_translates_simple_user_message_unchanged():
    import json
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(api_key="k", client=_capture_request_client(captured))

    await provider.chat(messages=[{"role": "user", "content": "hello"}])
    body = json.loads(captured["body"])

    assert body["messages"] == [{"role": "user", "content": "hello"}]


async def test_chat_translates_assistant_tool_calls_to_tool_use_blocks():
    import json
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(api_key="k", client=_capture_request_client(captured))

    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "c1", "name": "add", "arguments": {"a": 1, "b": 2}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "3"},
    ]
    await provider.chat(messages=messages)
    body = json.loads(captured["body"])

    assert body["messages"][0] == {"role": "user", "content": "hi"}
    assert body["messages"][1] == {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "c1", "name": "add", "input": {"a": 1, "b": 2}}
        ],
    }
    assert body["messages"][2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": "3"}
        ],
    }


async def test_chat_translates_tool_schemas_renaming_parameters_to_input_schema():
    import json
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(api_key="k", client=_capture_request_client(captured))

    tools = [
        {
            "name": "add",
            "description": "Sum two ints.",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        }
    ]
    await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=tools)
    body = json.loads(captured["body"])

    assert body["tools"] == [
        {
            "name": "add",
            "description": "Sum two ints.",
            "input_schema": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        }
    ]


async def test_chat_omits_tools_field_when_no_tools():
    import json
    captured: dict[str, Any] = {}
    provider = AnthropicProvider(api_key="k", client=_capture_request_client(captured))

    await provider.chat(messages=[{"role": "user", "content": "hi"}])
    body = json.loads(captured["body"])

    assert "tools" not in body

