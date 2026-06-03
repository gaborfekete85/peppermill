"""AgentRunner — pure LLM-conversation engine.

Given an AgentRunSpec (initial messages, tools, tool schemas, provider,
iteration limit), the runner loops over ``provider.chat()`` and tool
execution until either a final text reply arrives or ``max_iterations``
is reached. Returns an AgentRunResult.

The runner has zero knowledge of the bus, channels, sessions, or the
FSM in AgentLoop. That separation is the whole point of v0.3.

What the runner does NOT do (deferred):
- Streaming (v0.7).
- Mid-turn message injection (v0.10).
- Crash-recovery checkpoints (v0.9).
- Context governance / orphan-tool cleanup / history snipping (v0.8).
- Retries on empty responses or length-truncations (later).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from peppermill.providers.base import LLMProvider

log = logging.getLogger(__name__)


class _ToolLike(Protocol):
    """Structural type for any tool the runner can execute.

    Same shape as v0.1/v0.2's AddTool. v0.5 promotes this to a proper
    Tool ABC.
    """

    name: str

    def schema(self) -> dict[str, Any]: ...
    async def execute(self, **kwargs: Any) -> Any: ...


@dataclass
class AgentRunSpec:
    """Input to AgentRunner.run()."""

    initial_messages: list[dict[str, Any]]
    tools: dict[str, _ToolLike]
    tool_schemas: list[dict[str, Any]]
    provider: LLMProvider
    max_iterations: int = 20


@dataclass
class AgentRunResult:
    """Output of AgentRunner.run()."""

    final_content: str | None
    messages: list[dict[str, Any]]
    tools_used: list[str] = field(default_factory=list)
    stop_reason: str = "completed"


class AgentRunner:
    """Runs a single LLM turn (possibly with multiple tool-call iterations).

    Stateless across turns; the same instance can be reused.
    """

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        messages: list[dict[str, Any]] = list(spec.initial_messages)
        tools_used: list[str] = []
        tool_schemas = spec.tool_schemas or None

        for _iteration in range(spec.max_iterations):
            response = await spec.provider.chat(messages, tools=tool_schemas)

            if response.has_tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in response.tool_calls
                        ],
                    }
                )
                for tc in response.tool_calls:
                    tools_used.append(tc.name)
                    tool = spec.tools.get(tc.name)
                    if tool is None:
                        result: Any = f"error: unknown tool '{tc.name}'"
                        log.warning("unknown tool requested: %s", tc.name)
                    else:
                        try:
                            result = await tool.execute(**tc.arguments)
                        except Exception as exc:
                            log.exception("tool %s raised", tc.name)
                            result = f"error: {exc}"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result),
                        }
                    )
                continue  # back to the provider

            return AgentRunResult(
                final_content=response.content,
                messages=messages,
                tools_used=tools_used,
                stop_reason="completed",
            )

        # Loop exhausted without a final text response.
        return AgentRunResult(
            final_content=None,
            messages=messages,
            tools_used=tools_used,
            stop_reason="max_iterations",
        )
