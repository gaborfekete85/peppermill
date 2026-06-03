"""ScriptedRunner — test-only stand-in for AgentRunner.

Lets AgentLoop tests exercise the FSM without going through the real
runner, provider, and tool execution. Captures the last spec it was
called with so tests can assert on what the loop passed in (initial
messages, tool schemas, etc.).
"""
from __future__ import annotations

from peppermill.agent.runner import AgentRunResult, AgentRunSpec


class ScriptedRunner:
    """Plays back a fixed list of AgentRunResults, one per ``run()`` call.

    Stores the most recent spec on ``self.last_spec`` for assertions.
    """

    def __init__(self, results: list[AgentRunResult]) -> None:
        self._results = list(results)
        self._idx = 0
        self.last_spec: AgentRunSpec | None = None

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        self.last_spec = spec
        if self._idx >= len(self._results):
            raise RuntimeError("ScriptedRunner exhausted")
        result = self._results[self._idx]
        self._idx += 1
        return result
