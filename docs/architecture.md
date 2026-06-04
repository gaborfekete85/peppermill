# PepperMill — Architecture (as of v0.4)

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
       ┌──── TurnState FSM (RESTORE → BUILD → RUN → SAVE → RESPOND → DONE) ──┐
       │                                                                     │
       │ RESTORE ─► load session history from ~/.peppermill/sessions/      │
       │ BUILD   ─► seed initial_messages + tool_schemas                   │
       │ RUN     ─► build AgentRunSpec, await self._runner.run             │
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
       │ SAVE    ─► persist turn summary to history.jsonl        │
       │ RESPOND ─► publish OutboundMessage from runner result   │
       └──────────────────────────────────────────────────────────┘
              │
              ▼
       MessageBus.outbound (asyncio.Queue)
              │ consume_outbound
              ▼
       CLIChannel._write_stdout ──► stdout
```

## Components (v0.4)

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
| `peppermill/session/types.py` | `TurnSummary` dataclass for history storage. |
| `peppermill/session/history.py` | Low-level I/O: load_history, append_turn, ensure_session_dir. |
| `peppermill/session/manager.py` | `SessionManager` — high-level async API for session persistence. |
| `tests/_helpers/scripted_provider.py` | Test-only `ScriptedProvider`. Used by runner tests + e2e. |
| `tests/_helpers/scripted_runner.py` | Test-only `ScriptedRunner`. Used by FSM-level loop tests. |
| `tests/_helpers/in_memory_session_manager.py` | Test-only SessionManager (dict-backed, no disk). |

## The TurnState FSM (v0.4)

```python
class TurnState(Enum):
    RESTORE = auto()    # load session history from disk
    BUILD   = auto()    # seed messages + tool_schemas from inbound
    RUN     = auto()    # delegate LLM loop to AgentRunner
    SAVE    = auto()    # persist turn summary to history.jsonl
    RESPOND = auto()    # publish OutboundMessage from runner result
    DONE    = auto()    # sentinel — exit FSM
```

`run_once` drives transitions with `match/case` on the current state.
Each `_state_X(ctx)` handler returns the next `TurnState` directly —
no transition-table dict yet (only useful when a state has N-way
branching, which arrives with COMMAND in a later version).

`_TurnContext` (mutable dataclass) is passed between handlers; each
handler reads/writes only the fields it owns.

## What changed from v0.3

- **New**: `peppermill/session/` package (`types.py`, `history.py`, `manager.py`).
- **New**: `tests/session/` test modules (history I/O, SessionManager).
- **New**: `tests/_helpers/in_memory_session_manager.py` (test double).
- **Rewritten**: `peppermill/agent/loop.py` — FSM extended to 6 states (RESTORE → SAVE added). SessionManager injected. `_TurnContext` extended with session_key and history_records.
- **Modified**: `peppermill/__main__.py` — instantiate and wire SessionManager.
- **Modified**: `tests/agent/test_loop.py` — FSM tests for RESTORE/SAVE.

## What is NOT in v0.4 yet

(Each item is one or more future versions — see the [project spec](superpowers/specs/2026-05-29-peppermill-reimplementation-design.md).)

- TTL-based session cleanup (v0.5)
- Atomic writes / durability (v0.9)
- Per-user session isolation (v0.10)
- Full message audit logs (v0.9)
- Compression for large histories (v0.10)
- History format versioning (v0.5)
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

## One turn in detail (v0.4)

1. User types `What is 2+3? Use add.` on stdin.
2. `CLIChannel._read_stdin` reads, publishes `InboundMessage` to `bus.inbound`.
3. `AgentLoop.run_forever` consumes it, calls `run_once`.
4. `run_once` constructs `_TurnContext(inbound=msg)`, sets `state = RESTORE`.
5. **`RESTORE`** — `_state_restore` loads session history from disk via SessionManager. Converts past turns to user/assistant messages and seeds `ctx.messages`. Returns `BUILD`.
6. **`BUILD`** — `_state_build` appends new user message to `ctx.messages` (which may already have history) and builds `ctx.tool_schemas`. Returns `RUN`.
7. **`RUN`** — `_state_run` builds an `AgentRunSpec` from `ctx`, awaits `self._runner.run(spec)`, stores the `AgentRunResult` on `ctx.result`. Returns `SAVE`.
   - Inside the runner: `for _ in range(max_iterations)`, call `provider.chat(messages, tools=tool_schemas)`, execute any tool calls (looking up each in `spec.tools`, catching exceptions as error strings), feed results back, loop. When provider returns text-only, return `AgentRunResult(final_content, messages, tools_used, "completed")`.
8. **`SAVE`** — `_state_save` builds a `TurnSummary` (turn number, ISO timestamp, user_message, assistant_response, tools_used, stop_reason) and persists it to history.jsonl via SessionManager. Returns `RESPOND`.
9. **`RESPOND`** — `_state_respond` publishes `OutboundMessage(channel, chat_id, content=ctx.result.final_content or "")`. Returns `DONE`.
10. `match/case` loop exits on `state is DONE`.
11. `CLIChannel._write_stdout` prints to stdout.
12. Next turn (for same session): RESTORE loads 2 turns from history, seeds context with both, new turn appended, loop repeats.

## Python concepts introduced in v0.3

- `enum.Enum` + `auto()` for state sentinels. Identity comparison: `state is TurnState.DONE`.
- `match/case` structural pattern matching (Python 3.10+) for FSM routing. The `case _:` default catches unknown states.
- **Module separation by responsibility** — `loop.py` is orchestration, `runner.py` is execution. Each file holds one concept.
- **Dataclass-based input/output contracts** (`AgentRunSpec`, `AgentRunResult`) — well-defined interfaces between modules.
- **Mutable context object** (`_TurnContext`) passed between handlers — keeps handler signatures uniform without globals.
- **Test doubles at different layers** — `ScriptedProvider` for runner tests, `ScriptedRunner` for loop tests. Each layer exercised against the interface of the layer below.

## Test surface (v0.4)

```
tests/
├── session/
│   ├── test_history.py              (6 tests, new)
│   └── test_manager.py              (3 tests, new)
├── agent/
│   ├── test_loop.py                 (12 tests, 4 new RESTORE/SAVE)
│   ├── test_runner.py               (9 tests, unchanged)
│   └── tools/
│       └── test_add.py              (6 tests, unchanged)
├── bus/
│   ├── test_events.py               (4 tests, unchanged)
│   └── test_queue.py                (4 tests, unchanged)
├── channels/
│   └── test_cli.py                  (2 tests, unchanged)
├── providers/
│   ├── test_anthropic.py            (24 tests, unchanged)
│   ├── test_base.py                 (6 tests, unchanged)
│   └── test_scripted_provider.py    (3 tests, unchanged)
└── test_e2e.py                      (1 test, unchanged)
                                    ───
                                    80 tests total
```
