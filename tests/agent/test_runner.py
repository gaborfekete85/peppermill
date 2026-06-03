"""Tests for AgentRunner — pure LLM-conversation engine.

The runner is responsible for: take initial messages + tools, loop over
provider.chat() and tool execution, return an AgentRunResult. No bus,
no channels, no FSM. Tested in isolation with ScriptedProvider.
"""
from peppermill.agent.runner import AgentRunner, AgentRunSpec
from peppermill.agent.tools.add import AddTool
from peppermill.providers.base import LLMResponse, ToolCallRequest
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


# ---------------------------------------------------------------------------
# Tool execution (Task 3)
# ---------------------------------------------------------------------------


async def test_run_executes_tool_call_and_feeds_result_back():
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="1", name="add", arguments={"a": 2, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="The answer is 5.", finish_reason="stop"),
    ]
    runner = AgentRunner()
    result = await runner.run(_spec(ScriptedProvider(script), tools={"add": AddTool()}))

    assert result.final_content == "The answer is 5."
    assert result.tools_used == ["add"]
    assert result.stop_reason == "completed"


async def test_run_handles_multiple_tool_calls_in_one_response():
    script = [
        LLMResponse(
            tool_calls=[
                ToolCallRequest(id="1", name="add", arguments={"a": 1, "b": 1}),
                ToolCallRequest(id="2", name="add", arguments={"a": 5, "b": 5}),
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", finish_reason="stop"),
    ]
    runner = AgentRunner()
    result = await runner.run(_spec(ScriptedProvider(script), tools={"add": AddTool()}))

    assert result.tools_used == ["add", "add"]
    assert result.final_content == "done"


async def test_run_appends_assistant_tool_calls_then_tool_results_to_messages():
    """The messages list should mirror the on-the-wire shape after execution."""
    script = [
        LLMResponse(
            tool_calls=[ToolCallRequest(id="c1", name="add", arguments={"a": 2, "b": 3})],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="5", finish_reason="stop"),
    ]
    runner = AgentRunner()
    result = await runner.run(_spec(ScriptedProvider(script), tools={"add": AddTool()}))

    # messages: [user, assistant(tool_calls), tool(result)]
    assert len(result.messages) == 3
    assert result.messages[0]["role"] == "user"
    assert result.messages[1]["role"] == "assistant"
    assert result.messages[1]["tool_calls"][0]["name"] == "add"
    assert result.messages[2]["role"] == "tool"
    assert result.messages[2]["tool_call_id"] == "c1"
    assert result.messages[2]["content"] == "5"
