"""Tests for the test-only ScriptedProvider helper.

ScriptedProvider lives under tests/ because it exists purely to make
AgentLoop tests hermetic — never used by production code. It still
subclasses LLMProvider so the ABC contract is enforced.
"""
import pytest

from peppermill.providers.base import LLMResponse, ToolCallRequest
from tests._helpers.scripted_provider import ScriptedProvider


async def test_scripted_provider_returns_responses_in_order():
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 2, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="5", finish_reason="stop"),
    ]
    p = ScriptedProvider(script)

    r1 = await p.chat(messages=[])
    assert r1.has_tool_calls
    assert r1.tool_calls[0].name == "add"

    r2 = await p.chat(messages=[])
    assert r2.content == "5"


async def test_scripted_provider_raises_when_exhausted():
    p = ScriptedProvider([LLMResponse(content="x", finish_reason="stop")])
    await p.chat(messages=[])
    with pytest.raises(RuntimeError, match="exhausted"):
        await p.chat(messages=[])


async def test_scripted_provider_does_not_mutate_caller_script():
    original = [LLMResponse(content="x")]
    p = ScriptedProvider(original)
    await p.chat(messages=[])
    assert len(original) == 1
