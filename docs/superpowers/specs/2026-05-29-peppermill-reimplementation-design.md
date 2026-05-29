# PepperMill — Project A: Reimplementing the nanobot core stack for deep understanding

**Status:** approved
**Date:** 2026-05-29
**Author:** Gabor Fekete
**Reference:** [`hermes/nanobot/docs/architecture.md`](../../../../nanobot/docs/architecture.md)

---

## 1. Goal

Reimplement the core nanobot agent stack as a new Python package, **PepperMill** (import name: `peppermill`), with the primary aims of:

1. **Deeply understanding** how a modern LLM-agent framework is put together — every state transition, every queue, every retry, every safety guard.
2. **Learning Python on a master scale** — async, ABCs, Protocols, Pydantic, asyncio primitives, packaging, plugin discovery, Jinja2, JSON-line persistence, atomic writes, structured testing.
3. Producing a working, comprehensible, end-to-end agent runtime that the author wrote line by line and can defend every choice in.

**Non-goals (explicitly out of scope for Project A):**

- Production readiness, observability, deployment.
- All-channel and all-provider parity with nanobot.
- Niche features: MCP, cron, heartbeat, Dream/consolidation, subagents, sandbox backends, OpenAI-compatible API server, WebUI React app, image generation, transcription, the TypeScript bridge.

Project A's terminal state is a comprehensible v1.0. Projects B (DB-backed dynamic Agent/Skill registry) and C (autoscaling worker node) each get their own brainstorm pass later.

---

## 2. Approach

**Approach A — Mini-nanobot: same file shape, minimal contents.**

The package mirrors nanobot's top-level directory layout (`bus/`, `channels/`, `agent/`, `providers/`, …) but each file begins as a tiny, single-purpose version. The author can put PepperMill side-by-side with nanobot at any time and diff to see precisely what nanobot adds on top.

This was chosen over:

- **Clean-room rebuild** — too easy to reinvent worse abstractions and miss nanobot's real design wisdom.
- **Annotated rewrite (line-by-line with comments)** — glacial, and "understanding nanobot's code" is not the same as "knowing how to build a clone".

**Rule of thumb:** read the corresponding nanobot file in full, close it, rewrite from notes. **Never copy code.**

---

## 3. Terminal state — v1.0 definition of "done"

PepperMill v1.0 is a Python package that:

- Mirrors nanobot's directory layout under `peppermill/`.
- Runs end-to-end against **real LLMs** with:
  - **2 channels:** CLI (stdin/stdout), WebSocket.
  - **2 providers:** Anthropic, OpenAI-compatible.
  - **6 tools:** `add`, `read_file`, `write_file`, `list_dir`, `exec` (shell), `web_fetch`.
  - **Session persistence** across restarts.
  - **Context-window snipping** so long conversations don't blow token limits.
  - **Crash-recovery checkpoints** so mid-tool-call crashes resume cleanly.
  - **Streaming** token-by-token output.
  - **SSRF protection** on `web_fetch`.
  - **Config file** at `~/.peppermill/config.json` with Pydantic validation and `${VAR}` resolution.
- Has tests covering each version step.
- Has a `docs/architecture.md` that grows version by version and matches the final state.

---

## 4. Versioning ladder

Each version is a stop where everything runs end-to-end. The next version only begins when the previous is clean and every line is understood.

| Version | What it adds | What runs at end | Python concepts touched |
|---|---|---|---|
| **v0.1** | Bus (`InboundMessage`, `OutboundMessage`, `MessageBus`) + CLI channel + minimal AgentLoop (linear dispatch, no FSM yet) + FakeProvider with canned tool-call/answer sequence + 1 trivial tool (`add(a,b)`). | `python -m peppermill` → "what's 2+3?" → fake provider asks for `add(2,3)` → tool runs → fake provider returns "5". | `dataclasses`, `asyncio.Queue`, `asyncio.create_task`, `async def` / `await`, type hints, basic ABCs. |
| **v0.2** | Replace FakeProvider with real **AnthropicProvider** (non-streaming). Introduce `LLMProvider` ABC + `LLMResponse` / `ToolCallRequest`. | Same CLI, real Claude answers. | `abc.ABC`, `abstractmethod`, `httpx` async client, env-var-driven secrets, `typing.Optional`. |
| **v0.3** | Promote AgentLoop to the **TurnState FSM** (`RESTORE→COMPACT→COMMAND→BUILD→RUN→SAVE→RESPOND→DONE`). Extract AgentRunner from AgentLoop. | Same behaviour visibly, internals now match nanobot's shape. | `enum.Enum`, structural pattern matching (`match/case`), state-machine patterns, separating orchestration from execution. |
| **v0.4** | **Sessions**: `SessionManager`, JSON file on disk under `workspace/sessions/`, history replay across CLI restarts. | Quit and restart CLI, conversation continues. | `pathlib`, JSON serialization, atomic file writes (temp + fsync + rename + dir fsync), `datetime` with timezone-aware `utcnow`. |
| **v0.5** | **More tools** (`read_file`, `write_file`, `list_dir`, `exec`). `ToolRegistry` + auto-discovery via `pkgutil`. Workspace path restriction via `_resolve_path`. | Agent can poke around a sandbox workspace. | `pkgutil.iter_modules`, `importlib.import_module`, `Protocol` vs `ABC`, `pathlib.Path.resolve(strict=False)`, `asyncio.create_subprocess_exec`. |
| **v0.6** | **ContextBuilder** + Jinja2 templates (`identity.md`, runtime context block). System prompt assembly extracted from runner. | Same behaviour, cleaner architecture. | `jinja2.Environment`, `importlib.resources`, package data in `pyproject.toml`. |
| **v0.7** | **Streaming**: `chat_stream` on provider, streaming deltas through bus to CLI with `_stream_delta`/`_stream_end` metadata protocol. | Token-by-token output in the CLI. | Async generators (`async def` + `yield`), `AsyncIterator`, async-iter consumer patterns, callback vs stream tradeoffs. |
| **v0.8** | **Context governance**: drop orphan tool results, tool-result budget, history snipping by token budget. | Long conversations don't blow context limits. | `collections.deque`, generator-based pipelines, tokenizer integration (`tiktoken` or equivalent), defensive iteration over mutable lists. |
| **v0.9** | **Crash-recovery checkpoints**: `runtime_checkpoint` in `Session.metadata`, restore on next turn. | Kill peppermill mid-tool-call, restart → conversation resumes. | Exception handling discipline, `try/finally` for invariants, serializable state design, dataclass `asdict`. |
| **v0.10** | **Concurrency**: per-session `asyncio.Lock`, global `asyncio.Semaphore`, mid-turn message injection queue. | Two CLI sessions (or test harness) interleave correctly. | `asyncio.Lock`, `asyncio.Semaphore`, `asyncio.Queue(maxsize=…)`, `asyncio.TaskGroup` (3.11+), backpressure patterns, deadlock avoidance. |
| **v0.11** | **Second channel**: WebSocket. Add `BaseChannel` ABC properly, `ChannelManager` discovery. | A tiny HTML page (or `wscat`) talks to the agent. | `websockets` library, async server patterns, multiple-method ABCs, lifecycle management (`start`/`stop`). |
| **v0.12** | **Second provider**: OpenAI-compatible. Provider factory + model→provider registry. | Switch between Claude and GPT-4 via config. | Factory pattern, registry pattern, dispatch by model-name prefix, dependency injection. |
| **v0.13** | **Config**: Pydantic `PepperMillConfig`, `~/.peppermill/config.json` loading, `${VAR}` resolution with no-silent-fallback semantics. | Everything driven by a real config file. | `pydantic.BaseModel`, custom validators (`@field_validator`), `model_validator`, env-var resolution with strict failure semantics, camelCase aliases. |
| **v0.14** | **Web tool**: `web_fetch` with `validate_url_target` SSRF guard in `security/network.py`. | Tool can fetch URLs but is blocked from localhost, 169.254.169.254, RFC1918, link-local. | `ipaddress.ip_address`, `urllib.parse.urlparse`, defensive parsing of untrusted strings, network-class enumeration. |
| **v1.0** | Cleanup pass, README, end-to-end integration test exercising both channels and both providers. | Project A done. | Test pyramid revisited; doc-driven cleanup. |

---

## 5. Project layout

```
peppermill/                         ← /Users/gaborfekete/my-projects/my-agent/hermes/peppermill/
├── pyproject.toml
├── README.md
├── docs/
│   ├── architecture.md             ← grows version by version
│   ├── notes/                      ← per-step reading notes
│   │   ├── v0.1-bus-and-loop.md
│   │   ├── v0.2-anthropic-provider.md
│   │   └── …
│   └── superpowers/
│       └── specs/                  ← per-step design docs land here
│           └── 2026-05-29-peppermill-reimplementation-design.md
├── peppermill/                     ← the package
│   ├── __init__.py
│   ├── __main__.py                 ← `python -m peppermill`
│   ├── bus/
│   │   ├── events.py               ← InboundMessage, OutboundMessage
│   │   └── queue.py                ← MessageBus
│   ├── channels/
│   │   ├── base.py                 ← BaseChannel ABC (v0.11)
│   │   ├── manager.py              ← ChannelManager (v0.11)
│   │   ├── cli.py                  ← stdin/stdout (v0.1)
│   │   └── websocket.py            ← (v0.11)
│   ├── agent/
│   │   ├── loop.py                 ← AgentLoop / TurnState FSM
│   │   ├── runner.py               ← AgentRunner (extracted v0.3)
│   │   ├── context.py              ← ContextBuilder (v0.6)
│   │   └── tools/
│   │       ├── base.py
│   │       ├── registry.py
│   │       ├── loader.py
│   │       ├── add.py              ← v0.1
│   │       ├── filesystem.py       ← v0.5
│   │       ├── shell.py            ← v0.5
│   │       └── web.py              ← v0.14
│   ├── providers/
│   │   ├── base.py                 ← LLMProvider ABC (v0.2)
│   │   ├── factory.py              ← (v0.12)
│   │   ├── fake.py                 ← v0.1
│   │   ├── anthropic.py            ← v0.2
│   │   └── openai_compat.py        ← v0.12
│   ├── session/
│   │   └── manager.py              ← (v0.4)
│   ├── config/
│   │   ├── schema.py               ← (v0.13)
│   │   └── loader.py
│   ├── security/
│   │   └── network.py              ← validate_url_target (v0.14)
│   └── templates/
│       └── identity.md             ← (v0.6)
└── tests/
    └── …                           ← grows alongside each version step
```

---

## 6. Per-step workflow — the "deep understanding" methodology

Every v0.X step follows the same five-phase loop:

1. **Read the nanobot original.** Open the corresponding nanobot file(s), read top-to-bottom, take notes in `docs/notes/vX.Y-<topic>.md` answering:
   - What does this file do?
   - What are its inputs and outputs?
   - What design choices did nanobot make and why?
   - What Python features does it use that are new to me?

   No code yet.

2. **Spec the slice.** Write a tiny design doc (`docs/superpowers/specs/YYYY-MM-DD-vX.Y-<topic>.md`) saying what this step adds, what stays out, and what "done" looks like — usually 1–2 paragraphs + a one-paragraph test plan.

3. **TDD the implementation.** Write a failing test for the new behaviour, implement minimally, watch it pass. Use the `superpowers:test-driven-development` skill — followed exactly.

4. **Verify end-to-end.** Run the package (`python -m peppermill`), exercise the new behaviour by hand, confirm. Use the `superpowers:verification-before-completion` skill before claiming done.

5. **Commit + chapter mark.** One commit per step, clean message. Update `docs/architecture.md` to reflect the new state.

Each step produces: (a) reading notes, (b) a small spec, (c) tests, (d) working code, (e) updated arch doc, (f) one commit. After 14 steps there is a complete paper trail.

---

## 7. Testing strategy

Tests are a primary learning vehicle, not just verification. Each version step expands the pytest toolkit:

| Version | New test technique introduced |
|---|---|
| v0.1 | `pytest`, `pytest.mark.asyncio` (via `asyncio_mode = "auto"`), simple async-function tests, `pytest.fixture`. |
| v0.2 | `httpx.MockTransport` for hermetic provider tests, `pytest.fixture(scope="module")`. |
| v0.3 | Parameterized FSM transition tests with `@pytest.mark.parametrize`. |
| v0.4 | `tmp_path` fixture, file-system tests, JSON round-trip assertions. |
| v0.5 | `monkeypatch`, dynamic registry tests, subprocess testing with `capfd`. |
| v0.6 | Template rendering tests with golden files. |
| v0.7 | Async-iterator testing patterns, `async for` consumption in tests. |
| v0.8 | Property-style tests for context-snipping invariants (introduce `hypothesis` here). |
| v0.9 | Crash-simulation tests via injected exceptions and post-restart assertions. |
| v0.10 | Concurrency tests: `asyncio.gather`, race-condition probing, deadlock guards. |
| v0.11 | WebSocket integration tests with `websockets` test utilities. |
| v0.12 | Factory dispatch tests, registry override tests. |
| v0.13 | Pydantic validation tests: happy path, missing fields, bad types, missing `${VAR}` raises. |
| v0.14 | Security-guard tests: every IP class enumerated, URL parsing edge cases. |

**Standing rules:**

- pytest, `asyncio_mode = "auto"`.
- Tests mirror package structure under `tests/`.
- `ruff check` only — `ruff format` is forbidden (matches nanobot's hard rule about preserving git blame).
- Line length 100, E501 ignored, ruleset E/F/I/N/W (matches nanobot).
- Coverage is not a target. Behaviour coverage is — every public surface a step adds gets at least one test.

---

## 8. Risks and how they are managed

| Risk | Mitigation |
|---|---|
| **Skip-list drift** — "while I'm here I'll add MCP". | Skipped features (MCP, cron, heartbeat, Dream, subagents, sandbox, bridge, 11 channels, 5 providers) are explicitly out of Project A. Each gets its own brainstorm pass after v1.0. |
| **Copying nanobot code.** | Read → close file → rewrite from notes. Code-copying defeats the goal. |
| **Streaming step (v0.7) stalls.** | Permission to split into v0.7a (provider-side streaming, channel buffers) and v0.7b (channel emits deltas). |
| **Test-skill drift** — writing tests after the fact, or writing implementation-first tests. | TDD skill is rigid. Followed exactly: failing test first, implementation second, watch pass third. |
| **Python-learning shortcut** — using familiar patterns from another language. | Reading notes explicitly call out "Python concepts touched". Step is not "done" until the author can explain each in a sentence. |

---

## 9. What comes after v1.0

Project A → v1.0 is **not** the end of the broader effort. Future projects, each with their own brainstorm:

- **Project B** — DB-backed dynamic Agent/Skill registry: load agent and skill definitions from a database at runtime, hot-swap without restarts.
- **Project C** — Deployable autoscaling worker node: package PepperMill as a worker that scales horizontally based on inbound load.

Each will reference and build on PepperMill v1.0 as its foundation.

---

## 10. Relationship to implementation plans

This document is a **project-level spec / roadmap** for all of Project A. It does **not** define a single implementation plan covering all 14 versions — that would be premature, since later steps' structure depends on what earlier ones reveal.

The implementation cadence is:

1. **This spec is approved** by the author when every section reflects an explicit decision made during brainstorming, and the ladder/layout/methodology/testing strategy are signed off.
2. **Each v0.X gets its own short brainstorm-lite pass + writing-plans invocation when its turn comes**, producing a focused implementation plan for that step only.
3. **The immediate next action** after this spec is approved is invoking the `superpowers:writing-plans` skill to produce the plan **for v0.1 only**. v0.2's plan is written when v0.1 is done. And so on.
