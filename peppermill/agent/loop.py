"""AgentLoop — v0.1's minimal LLM + tool-execution loop.

For each inbound message:
  1. Seed the messages list with the user's content.
  2. Call provider.chat().
  3. If the response has tool calls: execute each, append results, loop.
  4. If the response has text: publish as outbound, stop.

No state machine, no sessions, no streaming, no context governance.
v0.3 promotes this to a proper TurnState FSM and extracts AgentRunner.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from peppermill.bus.events import InboundMessage, OutboundMessage
from peppermill.bus.queue import MessageBus

log = logging.getLogger(__name__)


class _ProviderLike(Protocol):
    """The minimal provider contract v0.1 needs.

    Avoids importing FakeProvider at the type level so v0.2 can plug in
    a real provider without changing this file.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any: ...


class _ToolLike(Protocol):
    """The minimal tool contract v0.1 needs."""

    name: str

    def schema(self) -> dict[str, Any]: ...
    async def execute(self, **kwargs: Any) -> Any: ...


class AgentLoop:
    def __init__(
        self,
        bus: MessageBus,
        provider: _ProviderLike,
        tools: dict[str, _ToolLike],
    ) -> None:
        self._bus = bus
        self._provider = provider
        self._tools = tools

    async def run_once(self, msg: InboundMessage) -> None:
        """Process one inbound message: call provider, execute tools, publish reply."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": msg.content}]
        tool_schemas: list[dict[str, Any]] = [t.schema() for t in self._tools.values()]

        while True:
            response = await self._provider.chat(messages, tools=tool_schemas)

            if response.has_tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                            for tc in response.tool_calls
                        ],
                    }
                )
                for tc in response.tool_calls:
                    tool = self._tools.get(tc.name)
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
                continue  # loop back to call the provider again

            await self._bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=response.content or "",
                )
            )
            return

    async def run_forever(self) -> None:
        """Drain inbound forever, processing each message sequentially."""
        while True:
            msg = await self._bus.consume_inbound()
            try:
                await self.run_once(msg)
            except Exception:
                log.exception("error processing message session=%s", msg.session_key)
