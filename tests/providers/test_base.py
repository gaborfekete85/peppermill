"""Tests for the LLMProvider ABC.

Pedagogical: shows what abc.abstractmethod actually enforces.
Constructing an ABC subclass that doesn't implement every @abstractmethod
fails at instantiation, not at first method call.
"""
import pytest

from peppermill.providers.base import LLMProvider, LLMResponse, ToolCallRequest


def test_cannot_instantiate_abstract_provider_directly():
    with pytest.raises(TypeError, match="abstract"):
        LLMProvider()  # type: ignore[abstract]


def test_subclass_without_chat_cannot_be_instantiated():
    class IncompleteProvider(LLMProvider):
        pass

    with pytest.raises(TypeError, match="abstract"):
        IncompleteProvider()  # type: ignore[abstract]


async def test_complete_subclass_instantiates_and_chat_works():
    class MinimalProvider(LLMProvider):
        async def chat(self, messages, tools=None):
            return LLMResponse(content="ok")

    provider = MinimalProvider()
    result = await provider.chat(messages=[])
    assert result.content == "ok"


def test_llm_response_has_tool_calls_property_false_when_empty():
    r = LLMResponse(content="x")
    assert r.has_tool_calls is False


def test_llm_response_has_tool_calls_property_true_when_nonempty():
    r = LLMResponse(
        tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 1, "b": 2})],
        finish_reason="tool_calls",
    )
    assert r.has_tool_calls is True


def test_tool_call_request_construction():
    tc = ToolCallRequest(id="x", name="add", arguments={"a": 1})
    assert tc.id == "x"
    assert tc.name == "add"
    assert tc.arguments == {"a": 1}
