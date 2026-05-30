"""Tests for FakeProvider — a scripted provider for end-to-end testing without an LLM."""
import pytest

from peppermill.providers.fake import FakeProvider, LLMResponse, ToolCallRequest


def test_llm_response_has_tool_calls_is_false_when_empty():
    r = LLMResponse(content="hi", finish_reason="stop")
    assert r.has_tool_calls is False


def test_llm_response_has_tool_calls_is_true_when_nonempty():
    r = LLMResponse(
        tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 1, "b": 2})],
        finish_reason="tool_calls",
    )
    assert r.has_tool_calls is True


async def test_fake_provider_returns_scripted_responses_in_order():
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 2, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="5", finish_reason="stop"),
    ]
    provider = FakeProvider(script)

    r1 = await provider.chat(messages=[])
    assert r1.has_tool_calls
    assert r1.tool_calls[0].name == "add"
    assert r1.tool_calls[0].arguments == {"a": 2, "b": 3}
    assert r1.finish_reason == "tool_calls"

    r2 = await provider.chat(messages=[])
    assert not r2.has_tool_calls
    assert r2.content == "5"
    assert r2.finish_reason == "stop"


async def test_fake_provider_raises_when_script_exhausted():
    provider = FakeProvider([LLMResponse(content="x", finish_reason="stop")])
    await provider.chat(messages=[])
    with pytest.raises(RuntimeError, match="script exhausted"):
        await provider.chat(messages=[])


async def test_fake_provider_does_not_mutate_caller_script():
    """Construction takes a copy so the caller's list isn't drained."""
    original = [LLMResponse(content="x", finish_reason="stop")]
    provider = FakeProvider(original)
    await provider.chat(messages=[])
    assert len(original) == 1  # untouched
