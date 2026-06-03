"""Hermetic tests for AnthropicProvider using httpx.MockTransport — no network."""

from typing import Any

import httpx
import pytest

from peppermill.providers.anthropic import AnthropicProvider
from peppermill.providers.base import ToolCallRequest

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


# ---------------------------------------------------------------------------
# Response-parsing tests
# ---------------------------------------------------------------------------


def _client_returning(payload: dict[str, Any], status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )


async def test_chat_parses_text_only_response():
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "hello"}],
        "stop_reason": "end_turn",
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert r.content == "hello"
    assert r.tool_calls == []
    assert r.finish_reason == "stop"


async def test_chat_concatenates_multiple_text_blocks():
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ],
        "stop_reason": "end_turn",
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[])

    assert r.content == "hello world"


async def test_chat_parses_tool_use_blocks():
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "add", "input": {"a": 2, "b": 3}}
        ],
        "stop_reason": "tool_use",
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[])

    assert r.content is None
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0] == ToolCallRequest(
        id="tu_1", name="add", arguments={"a": 2, "b": 3}
    )
    assert r.finish_reason == "tool_calls"


async def test_chat_parses_mixed_text_and_tool_use():
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [
            {"type": "text", "text": "Let me calculate."},
            {"type": "tool_use", "id": "tu_1", "name": "add", "input": {"a": 1, "b": 1}},
        ],
        "stop_reason": "tool_use",
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[])

    assert r.content == "Let me calculate."
    assert r.has_tool_calls
    assert r.finish_reason == "tool_calls"


async def test_chat_returns_none_content_when_no_text_blocks():
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "add", "input": {}}
        ],
        "stop_reason": "tool_use",
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[])

    assert r.content is None


@pytest.mark.parametrize(
    "raw_stop_reason,expected_finish",
    [
        ("end_turn", "stop"),
        ("tool_use", "tool_calls"),
        ("max_tokens", "length"),
        ("stop_sequence", "stop_sequence"),  # unknown → passes through
    ],
)
async def test_chat_maps_stop_reasons(raw_stop_reason: str, expected_finish: str):
    payload = {
        "id": "m", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": "x"}],
        "stop_reason": raw_stop_reason,
    }
    provider = AnthropicProvider(api_key="k", client=_client_returning(payload))

    r = await provider.chat(messages=[])

    assert r.finish_reason == expected_finish


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------


async def test_chat_raises_http_status_error_on_401():
    provider = AnthropicProvider(
        api_key="bad-key",
        client=_client_returning({"error": "unauthorized"}, status=401),
    )
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.chat(messages=[{"role": "user", "content": "hi"}])
    assert exc_info.value.response.status_code == 401


async def test_chat_raises_http_status_error_on_500():
    provider = AnthropicProvider(
        api_key="k",
        client=_client_returning({"error": "server"}, status=500),
    )
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.chat(messages=[])
    assert exc_info.value.response.status_code == 500


async def test_chat_does_not_swallow_connect_errors():
    """A transport that raises ConnectError should bubble up unchanged."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    provider = AnthropicProvider(api_key="k", client=client)

    with pytest.raises(httpx.ConnectError, match="simulated"):
        await provider.chat(messages=[])



