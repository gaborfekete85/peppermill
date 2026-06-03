# PepperMill — Architecture (as of v0.2)

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
       LLMProvider.chat ──► AnthropicProvider.chat ─► httpx POST /v1/messages
              │                                            (api.anthropic.com)
              │       (loop: tool_calls → execute → chat again)
              │
              │     AddTool.execute
              │
              ▼ (final text)
       MessageBus.outbound (asyncio.Queue)
              │ consume_outbound
              ▼
       CLIChannel._write_stdout ──► stdout
```

## Components (v0.2)

| File | Responsibility |
|---|---|
| `peppermill/bus/events.py` | `InboundMessage`, `OutboundMessage` dataclasses. |
| `peppermill/bus/queue.py` | `MessageBus` — two asyncio.Queue wrappers. |
| `peppermill/channels/cli.py` | Reads stdin, publishes inbound; consumes outbound, prints. |
| `peppermill/agent/loop.py` | `AgentLoop` — linear LLM-call + tool-execution loop. |
| `peppermill/agent/tools/add.py` | `AddTool` — sums two ints. |
| `peppermill/providers/base.py` | `LLMProvider` ABC + `LLMResponse`, `ToolCallRequest` dataclasses. |
| `peppermill/providers/anthropic.py` | `AnthropicProvider` — real LLM via Anthropic Messages API. |
| `peppermill/__main__.py` | Wires everything. Requires `ANTHROPIC_API_KEY`. |
| `tests/_helpers/scripted_provider.py` | Test-only `ScriptedProvider`. Hermetic test double. |

## What changed from v0.1

- **New**: `peppermill/providers/base.py` (`LLMProvider` ABC).
- **New**: `peppermill/providers/anthropic.py` (real provider).
- **New**: `tests/_helpers/scripted_provider.py` (test-only LLMProvider).
- **New**: `tests/providers/test_base.py`, `test_anthropic.py`.
- **Deleted**: `peppermill/providers/fake.py`, `tests/providers/test_fake.py`.
- **Rewritten**: `peppermill/__main__.py` (now uses AnthropicProvider).
- **Rewritten**: `tests/agent/test_loop.py`, `tests/test_e2e.py` (use ScriptedProvider).
- **New runtime dep**: `httpx>=0.27`.

## What is NOT in v0.2 yet

(Each item is one or more future versions — see the [project spec](superpowers/specs/2026-05-29-peppermill-reimplementation-design.md).)

- TurnState FSM, AgentRunner extraction (v0.3)
- Sessions, persistence (v0.4)
- Tool registry, more tools, workspace restriction (v0.5)
- ContextBuilder, Jinja2 templates (v0.6)
- Streaming (v0.7)
- Context governance (v0.8)
- Crash-recovery checkpoints (v0.9)
- Concurrency primitives (v0.10)
- BaseChannel ABC, WebSocket channel (v0.11)
- Provider factory + OpenAI-compatible provider (v0.12)
- Config (Pydantic) (v0.13)
- Web tool + SSRF (v0.14)
- Retries, structured error recovery (deferred)

## One turn in detail (v0.2)

1. User types `What is 2+3? Use add.` on stdin.
2. `CLIChannel._read_stdin` reads, publishes `InboundMessage` to `bus.inbound`.
3. `AgentLoop.run_forever` consumes it, calls `run_once`.
4. `run_once` builds `messages=[{"role": "user", "content": "..."}]` and calls
   `AnthropicProvider.chat(messages, tools=[add_schema])`.
5. `AnthropicProvider._build_request` translates messages + tools to
   Anthropic's API format, builds headers, and `httpx.AsyncClient.post`s
   to `/v1/messages`.
6. `_parse_response` extracts text + `tool_use` blocks, maps `stop_reason`
   → `finish_reason`.
7. If the response has tool calls: `AgentLoop` executes them, appends
   results, calls `provider.chat` again (loops).
8. When the response is final text: an `OutboundMessage` is published.
9. `CLIChannel._write_stdout` prints to stdout.

## Python concepts introduced in v0.2

- `abc.ABC`, `@abstractmethod`, `TypeError` on instantiation of an
  unimplemented abstract class.
- `Protocol` (from v0.1) vs `ABC` — structural duck typing vs nominal
  is-a enforcement. Both still appear in this codebase.
- `httpx.AsyncClient` lifecycle: build → reuse → `await aclose()`.
- `httpx.MockTransport`: hermetic HTTP testing.
- `os.environ.get(...)` + fail-fast at constructor.
- Dependency injection via optional constructor parameter.
- `monkeypatch.setenv`, `monkeypatch.delenv`, `pytest.parametrize`.

## Test surface (v0.2)

```
tests/
├── bus/
│   ├── test_events.py            (4 tests, from v0.1)
│   └── test_queue.py             (4 tests, from v0.1)
├── channels/
│   └── test_cli.py               (2 tests, from v0.1)
├── agent/
│   ├── test_loop.py              (4 tests, rewritten)
│   └── tools/
│       └── test_add.py           (6 tests, from v0.1)
├── providers/
│   ├── test_base.py              (6 tests, new)
│   ├── test_scripted_provider.py (3 tests, new)
│   └── test_anthropic.py         (24 tests, new)
└── test_e2e.py                   (1 test, rewritten)
```