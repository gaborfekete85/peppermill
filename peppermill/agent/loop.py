"""AgentLoop — per-turn orchestration via a small TurnState FSM.

v0.3 promotes v0.2's linear run_once into a state machine and extracts
the LLM-conversation engine into AgentRunner (peppermill/agent/runner.py).

The FSM is intentionally minimal — four states, all linear:

    BUILD → RUN → RESPOND → DONE

Each state handler is ``async def _state_X(self, ctx) -> TurnState`` and
returns the next state. ``run_once`` drives transitions with ``match/case``.

Future versions will add states without rewriting this one:
- RESTORE + SAVE  (v0.4 — sessions / persistence)
- COMMAND         (later — /slash command dispatch)
- COMPACT         (v0.8 — context governance / auto-compact)

When that happens we may switch from "handler returns next state" to a
transition-table dict (matching nanobot's shape), but for four linear
states direct returns are clearer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from peppermill.agent.runner import AgentRunner, AgentRunResult, AgentRunSpec, _ToolLike
from peppermill.bus.events import InboundMessage, OutboundMessage
from peppermill.bus.queue import MessageBus
from peppermill.providers.base import LLMProvider

log = logging.getLogger(__name__)


class TurnState(Enum):
    """Sentinel values for each phase of processing one inbound message."""

    BUILD = auto()
    RUN = auto()
    RESPOND = auto()
    DONE = auto()


@dataclass
class _TurnContext:
    """Mutable scratch space carried between state handlers.

    Each handler reads/writes only the fields it owns; this keeps
    handler signatures uniform ``(self, ctx) -> TurnState`` without
    relying on globals or method-instance state.
    """

    inbound: InboundMessage
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    result: AgentRunResult | None = None


class AgentLoop:
    """Per-inbound-message orchestrator.

    Owns: bus, provider, tools registry, max_iterations, the runner.
    Does NOT own: LLM-conversation logic (that's AgentRunner).
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        tools: dict[str, _ToolLike],
        max_iterations: int = 20,
    ) -> None:
        self._bus = bus
        self._provider = provider
        self._tools = tools
        self._max_iterations = max_iterations
        # AgentRunner is stateless across turns; one instance is fine.
        self._runner = AgentRunner()

    async def run_once(self, msg: InboundMessage) -> None:
        """Drive the FSM through one inbound message."""
        ctx = _TurnContext(inbound=msg)
        state = TurnState.BUILD
        while state is not TurnState.DONE:
            match state:
                case TurnState.BUILD:
                    state = await self._state_build(ctx)
                case TurnState.RUN:
                    state = await self._state_run(ctx)
                case TurnState.RESPOND:
                    state = await self._state_respond(ctx)
                case TurnState.DONE:
                    break  # while-condition exits next iteration anyway
                case _:
                    raise RuntimeError(f"unknown state: {state}")

    async def run_forever(self) -> None:
        """Drain inbound forever, processing each message sequentially."""
        while True:
            msg = await self._bus.consume_inbound()
            try:
                await self.run_once(msg)
            except Exception:
                log.exception("error processing message session=%s", msg.session_key)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _state_build(self, ctx: _TurnContext) -> TurnState:
        """Seed the initial messages list + tool schemas from the inbound."""
        ctx.messages = [{"role": "user", "content": ctx.inbound.content}]
        ctx.tool_schemas = [t.schema() for t in self._tools.values()]
        return TurnState.RUN

    async def _state_run(self, ctx: _TurnContext) -> TurnState:
        """Delegate the LLM turn to AgentRunner; store the result on ctx."""
        spec = AgentRunSpec(
            initial_messages=ctx.messages,
            tools=self._tools,
            tool_schemas=ctx.tool_schemas,
            provider=self._provider,
            max_iterations=self._max_iterations,
        )
        ctx.result = await self._runner.run(spec)
        return TurnState.RESPOND

    async def _state_respond(self, ctx: _TurnContext) -> TurnState:
        """Publish an OutboundMessage built from the runner result."""
        final_content = ctx.result.final_content if ctx.result is not None else None
        await self._bus.publish_outbound(
            OutboundMessage(
                channel=ctx.inbound.channel,
                chat_id=ctx.inbound.chat_id,
                content=final_content or "",
            )
        )
        return TurnState.DONE
