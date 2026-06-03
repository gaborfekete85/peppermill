# PepperMill — Architecture (as of v0.3)

> This document is the source of truth for "what does PepperMill look like
> right now?". Every version step updates it. Compare against
> [nanobot's architecture doc](../../nanobot/docs/architecture.md) to see
> what we have NOT built yet.

## Big picture

```
stdin ──► CLIChannel._read_stdin
              │
              ▼
       MessageBus.inbound (asyncio.Queue)
              │ consume_inbound
              ▼
       AgentLoop.run_forever
              │ run_once
              ▼
       ┌────── TurnState FSM (BUILD → RUN → RESPOND → DONE) ──────┐
       │                                                          │
       │  BUILD  ─► seed initial_messages + tool_schemas          │
       │  RUN    ─► build AgentRunSpec, await self._runner.run    │
       │              │                                           │
       │              ▼                                           │
       │       AgentRunner.run (peppermill/agent/runner.py)       │
       │              │                                           │
       │              ├─ for _ in range(max_iterations):          │
       │              │    LLMProvider.chat ─► AnthropicProvider  │
       │              │                          │                │
       │              │                          ▼                │
       │              │                 httpx POST /v1/messages   │
       │              │                  (api.anthropic.com)      │
       │              │                                           │
       │              ├─ if tool_calls: execute (AddTool), append │
       │              └─ if text:       return AgentRunResult     │
       │                                                          │
       │  RESPOND ─► publish OutboundMessage from runner result   │
       └──────────────────────────────────────────────────────────┘
              │
              ▼
       MessageBus.outbound (asyncio.Queue)
              │ consume_outbound
              ▼
       CLIChannel._write_stdout ──► stdout
```

## Components (v0.3)

| File | Responsibility |
|---|---|
| `peppermill/bus/events.py` | `InboundMessage`, `OutboundMessage` dataclasses. |
| `peppermill/bus/queue.py` | `MessageBus` — two asyncio.Queue wrappers. |
| `peppermill/channels/cli.py` | Reads stdin, publishes inbound; consumes outbound, prints. |
| `peppermill/agent/loop.py` | `AgentLoop` — per-turn orchestrator. Owns `TurnState` FSM. |
| `peppermill/agent/runner.py` | `AgentRunner` + `AgentRunSpec` + `AgentRunResult` — pure LLM-conversation engine. |
| `peppermill/agent/tools/add.py` | `AddTool` — sums two ints. |
| `peppermill/providers/base.py` | `LLMProvider` ABC + `LLMResponse`, `ToolCallRequest` dataclasses. |
| `peppermill/providers/anthropic.py` | `AnthropicProvider` — real LLM via Anthropic Messages API. |
| `peppermill/__main__.py` | Wires everything. Requires `ANTHROPIC_API_KEY`. |
| `tests/_helpers/scripted_provider.py` | Test-only `ScriptedProvider`. Used by runner tests + e2e. |
| `tests/_helpers/scripted_runner.py` | Test-only `ScriptedRunner`. Used by FSM-level loop tests. |

## The TurnState FSM (v0.3)

```python
class TurnState(Enum):
    BUILD   = auto()    # seed messages + tool_schemas from inbound
    RUN     = auto()    # delegate LLM loop to AgentRunner
    RESPOND = auto()    # publish OutboundMessage from runner result
    DONE    = auto()    # sentinel — exit FSM
```

`run_once` drives transitions with `match/case` on the current state.
Each `_state_X(ctx)` handler returns the next `TurnState` directly —
no transition-table dict yet (only useful when a state has N-way
branching, which arrives with COMMAND in a later version).

`_TurnContext` (mutable dataclass) is passed between handlers; each
handler reads/writes only the fields it owns.

## What changed from v0.2

- **New**: `peppermill/agent/runner.py` (`AgentRunSpec`, `AgentRunResult`, `AgentRunner`).
- **New**: `tests/agent/test_runner.py` (9 tests covering the runner in isolation).
- **New**: `tests/_helpers/scripted_runner.py` (test-only stand-in).
- **Rewritten**: `peppermill/agent/loop.py` — now a TurnState FSM driving handlers; LLM/tool work delegated to AgentRunner. Public constructor still takes `(bus, provider, tools)` plus new optional `max_iterations=20`. `__main__.py` keeps working unchanged.
- **Rewritten**: `tests/agent/test_loop.py` — FSM-level coverage using `ScriptedRunner`.
- **No changes**: `__main__.py`, providers, channels, bus, tools.

## What is NOT in v0.3 yet

(Each item is one or more future versions — see the [project spec](superpowers/specs/2026-05-29-peppermill-reimplementation-design.md).)

- `RESTORE` + `SAVE` FSM states; sessions, persistence (v0.4)
- Tool registry, more tools, workspace restriction (v0.5)
- ContextBuilder, Jinja2 templates (v0.6)
- Streaming (v0.7)
- `COMPACT` FSM state; context governance (v0.8)
- Crash-recovery checkpoints (v0.9)
- Concurrency primitives, mid-turn injections (v0.10)
- BaseChannel ABC, WebSocket channel (v0.11)
- Provider factory + OpenAI-compatible provider (v0.12)
- Config (Pydantic) (v0.13)
- Web tool + SSRF (v0.14)
- `COMMAND` FSM state (later — `/slash` command dispatch)
- Retries, structured error recovery (deferred)

## One turn in detail (v0.3)

1. User types `What is 2+3? Use add.` on stdin.
2. `CLIChannel._read_stdin` reads, publishes `InboundMessage` to `bus.inbound`.
3. `AgentLoop.run_forever` consumes it, calls `run_once`.
4. `run_once` constructs `_TurnContext(inbound=msg)`, sets `state = BUILD`.
5. **`BUILD`** — `_state_build` seeds `ctx.messages = [{"role": "user", "content": ...}]` and `ctx.tool_schemas = [t.schema() for t in tools.values()]`. Returns `RUN`.
6. **`RUN`** — `_state_run` builds an `AgentRunSpec` from `ctx`, awaits `self._runner.run(spec)`, stores the `AgentRunResult` on `ctx.result`. Returns `RESPOND`.
   - Inside the runner: `for _ in range(max_iterations)`, call `provider.chat(messages, tools=tool_schemas)`, execute any tool calls (looking up each in `spec.tools`, catching exceptions as error strings), feed results back, loop. When provider returns text-only, return `AgentRunResult(final_content, messages, tools_used, "completed")`.
7. **`RESPOND`** — `_state_respond` publishes `OutboundMessage(channel, chat_id, content=ctx.result.final_content or "")`. Returns `DONE`.
8. `match/case` loop exits on `state is DONE`.
9. `CLIChannel._write_stdout` prints to stdout.

## Python concepts introduced in v0.3

- `enum.Enum` + `auto()` for state sentinels. Identity comparison: `state is TurnState.DONE`.
- `match/case` structural pattern matching (Python 3.10+) for FSM routing. The `case _:` default catches unknown states.
- **Module separation by responsibility** — `loop.py` is orchestration, `runner.py` is execution. Each file holds one concept.
- **Dataclass-based input/output contracts** (`AgentRunSpec`, `AgentRunResult`) — well-defined interfaces between modules.
- **Mutable context object** (`_TurnContext`) passed between handlers — keeps handler signatures uniform without globals.
- **Test doubles at different layers** — `ScriptedProvider` for runner tests, `ScriptedRunner` for loop tests. Each layer exercised against the interface of the layer below.

## Test surface (v0.3)

```
tests/
├── agent/
│   ├── test_loop.py              (8 tests, rewritten for FSM)
│   ├── test_runner.py            (9 tests, new — runner coverage)
│   └── tools/
│       └── test_add.py           (6 tests, from v0.1)
├── bus/
│   ├── test_events.py            (4 tests, from v0.1)
│   └── test_queue.py             (4 tests, from v0.1)
├── channels/
│   └── test_cli.py               (2 tests, from v0.1)
├── providers/
│   ├── test_anthropic.py         (24 tests, from v0.2)
│   ├── test_base.py              (6 tests, from v0.2)
│   └── test_scripted_provider.py (3 tests, from v0.2)
└── test_e2e.py                   (1 test, from v0.2)
                                  ───
                                  67 tests total
```
