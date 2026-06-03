"""Tests for AgentRunner — pure LLM-conversation engine.

The runner is responsible for: take initial messages + tools, loop over
provider.chat() and tool execution, return an AgentRunResult. No bus,
no channels, no FSM. Tested in isolation with ScriptedProvider.
"""
from peppermill.agent.runner import AgentRunner, AgentRunSpec
from peppermill.providers.base import LLMResponse
from tests._helpers.scripted_provider import ScriptedProvider


def _spec(provider, tools=None, max_iterations=20):
    """Build an AgentRunSpec with sensible defaults for tests."""
    tools = tools or {}
    return AgentRunSpec(
        initial_messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        tool_schemas=[t.schema() for t in tools.values()],
        provider=provider,
        max_iterations=max_iterations,
    )


# ---------------------------------------------------------------------------
# Text-only path (Task 2)
# ---------------------------------------------------------------------------


async def test_run_returns_text_response_when_no_tool_calls():
    provider = ScriptedProvider([LLMResponse(content="hello", finish_reason="stop")])
    runner = AgentRunner()
    result = await runner.run(_spec(provider))
    assert result.final_content == "hello"
    assert result.tools_used == []
    assert result.stop_reason == "completed"


async def test_run_result_messages_include_initial_user_message():
    provider = ScriptedProvider([LLMResponse(content="hi back", finish_reason="stop")])
    runner = AgentRunner()
    result = await runner.run(_spec(provider))
    # Initial user message is preserved; assistant text reply isn't added to
    # messages for text-only responses (matches v0.2 behaviour).
    assert result.messages[0] == {"role": "user", "content": "hi"}
    assert len(result.messages) == 1


async def test_run_returns_none_content_when_provider_returns_no_text():
    provider = ScriptedProvider([LLMResponse(content=None, finish_reason="stop")])
    runner = AgentRunner()
    result = await runner.run(_spec(provider))
    assert result.final_content is None
    assert result.stop_reason == "completed"
