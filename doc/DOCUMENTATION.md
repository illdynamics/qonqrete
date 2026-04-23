# QonQrete Documentation

**Version:** `v1.4.0`

This document is the synced technical reference for the current `v1.4.0` repository snapshot.

## Current release deltas (`v1.4.0`)

- Final inspection paths now treat final `qodeyard/` files as authoritative evidence over relay/log snippets.
- Frontend localStorage deterministic validation now supports compact constant/alias/object key indirection.
- Verdict synthesis downgrades advisory briq-review noise when deterministic gates pass.
- Qrane/ConstruQtor heartbeat chatter is removed from terminal output.
- Streamed heredoc terminal rendering is concise by default, with TTY-only hotkeys:
  - `TAB` => raw stream view
  - `Shift+TAB` => concise view
- Launcher now supports `-N/--no-sync` to skip repo-root sync-back and keep run output in Qage/Qonstruction paths.
- Primary agent defaults are aligned to `venice / deepseek-v3.2`, and ConstruQtor default coding mode is `hybrid`.

## Table of contents
- [1. What QonQrete is](#1-what-qonqrete-is)
- [2. Current repository scope](#2-current-repository-scope)
- [3. Core execution flows](#3-core-execution-flows)
- [4. Agent reference](#4-agent-reference)
- [5. QONTRACT system](#5-qontract-system)
- [6. Context and memory layers](#6-context-and-memory-layers)
- [7. Configuration reference](#7-configuration-reference)
- [8. Providers and API keys](#8-providers-and-api-keys)
- [9. IDE integrations](#9-ide-integrations)
- [10. Security model](#10-security-model)
- [11. Current limitations](#11-current-limitations)
- [12. Workspace Deployment (v1.2.0+)](#12-workspace-deployment-v120)
- [13. Cost Confirmation Gate (GateQeeper)](#13-cost-confirmation-gate-gatekeeper)
- [14. OpenRouter Provider Support](#14-openrouter-provider-support)
- [15. Venice Provider Support *(v1.3.12)*](#15-venice-provider-support-v1312)
- [16. MLX and Llama-cpp Provider Support *(v1.3.12)*](#16-mlx-and-llama-cpp-provider-support-v1312)

## 1. What QonQrete is

QonQrete is a **structured AI construction loop** for building software inside a hardened runtime. It takes a high-level task, decomposes it into briqs, generates or modifies code, reviews the result, and optionally continues into more build/repair passes when the runtime allows it.

The system is designed around:
- local file visibility
- repeatable pipeline stages
- contract enforcement
- container isolation
- clear review artifacts

## 2. Current repository scope

The current repo includes:

### Core runtime
- `qonqrete.sh`
- `qrane/`
- `worqer/`
- `worqspace/`

### IDE integrations
- `vscode-extension/`
- `intellij-plugin/`

### Documentation
- `doc/`

Starting with v1.2.0, both IDE integrations implement a workspace-local deployment model. Users run "Deploy to Workspace" to install the runtime into `.qonqrete/`. The runtime remains script-relative and repo-shaped, deployed locally per workspace.

## 3. Core execution flows

### 3.1 Initialization

```bash
./qonqrete.sh init
```

Initialization:
1. detects OS
2. detects or accepts explicit runtime engine
3. detects build backend
4. builds the Qage image

Supported runtime paths in the repo:
- Docker
- Podman

### 3.2 Fresh run

```bash
./qonqrete.sh tasq.md
./qonqrete.sh run -f tasq.md
```

Current run flow:
1. validate runtime prerequisites
2. validate required config/task files
3. create a new `qage_YYYYMMDD_HHMMSS`
4. default to an empty `qodeyard/` (no repo seed) and copy task material into `tasq.md` + `tasq.d/cyqle1_tasq.md`
5. optionally seed repository code into `qodeyard/` when `--seed-repo` (or legacy `-s/--sqrapyard`) is used
6. launch the container
7. let Qrane execute clarification, qonstrictor, planning, build, validation/realization, and inspection
8. by default, sync changed outputs back to repo root with non-seeded collision protection
9. when `-N/--no-sync` is passed, skip that sync-back and keep output in Qage/Qonstruction paths (`lineage.repo_sync_mode = no_sync`)
10. optionally save as a qonstruction

### 3.3 Resume

```bash
./qonqrete.sh resume
./qonqrete.sh resume -q qage_YYYYMMDD_HHMMSS
```

Resume flow:
1. choose an existing qage (interactive or direct)
2. copy the selected qage into a new qage
3. refresh workspace-driven config/task material
4. continue as a new run with previous state available
5. if `execution.state.pending_next_pass_kind` is present, resume honors that queued pass exactly
6. if no queued next pass exists and the previous run shows an interrupted active pass, resume restores that interrupted active pass semantics (including interrupted repair passes)
7. if legacy manifests are missing explicit resume markers, resume uses conservative inference and avoids silently fabricating a different pass kind
8. if the source run is blocked on intake clarification (`RUN_WAITING_FOR_INPUT` + `BLOCKED`), resume re-enters cycle-1 clarification semantics instead of skipping cycle-1-only intake stages

### 3.4 Clean

```bash
./qonqrete.sh clean
./qonqrete.sh clean -q qage_YYYYMMDD_HHMMSS
./qonqrete.sh clean -A
```

Clean flow supports:
- interactive delete
- direct delete
- delete all

## 4. Agent reference

## 4.1 `qrystallizer.py`
Canonical intake / clarification stage.
- cycle-1-only behavior
- writes `task/task-spec.v1.json`, `task/clarification-log.v1.json`, and `task/clarification-summary.md`
- optionally consumes deterministic clarification responses from `task/clarification-response.v1.json`
- if readiness stays `NOT_READY`, Qrane marks the run as `BLOCKED` / `RUN_WAITING_FOR_INPUT` instead of treating intake clarification as a generic failure
- only clarification asks user questions; no mid-run questioning is allowed after readiness is accepted
- does not mutate the canonical task input

## 4.2 `qonstrictor.py`
Canonical pre-plan constraint gate.
Responsibilities:
- evaluate task readiness before planning proceeds
- turn declared constraints into effective runtime constraints
- emit deterministic pass/review/fail output to `qontract.d/`
- stop planning when intake readiness or scope rules are violated (fallback guard after clarification gate)

## 4.3 `instruqtor.py`
Planning agent.
Responsibilities:
- read the current tasq
- create briqs in `briq.d/`
- generate QONTRACT files on the first build pass
- honor sensitivity settings and decomposition logic

## 4.4 `calqulator.py`
Local estimation helper.
Responsibilities:
- estimate token/cost footprint
- annotate planning flow with rough cost expectations
- zero AI-token cost

## 4.5 `construqtor.py`
Code generation / modification agent.
Responsibilities:
- consume briqs
- write or update files in `qodeyard/`
- emit execution summaries to `exeq.d/`
- use contract-aware and validation-aware build retries

## 4.6 `inspeqtor.py`
Review agent.
Responsibilities:
- run deterministic checks
- optionally run smoketest checks via `smoqetester` (scoped or full mode)
- run AI-assisted review stages
- emit final recap material to `reqap.d/`
- drive success / partial / failure assessment logic
- classify validation execution mode as `NONE`, `STATIC_ONLY`, `EXECUTED`, or `MIXED` using explicit evidence (not markdown presence alone)

## 4.7 `qontextor.py`
Context indexing helper.
Responsibilities:
- build deterministic structural maps in `qontext.d/`, including per-file extractor metadata and a run manifest
- run in local mode according to config
- provide cheaper context reuse than shoving full source trees into prompts

## 4.8 `qompressor.py`
Deterministic multi-language structural skeletonizer.
Responsibilities:
- compress code structure into `bloq.d/`, including a run manifest that records native vs fallback processing paths
- preserve useful structure while stripping bulky implementation bodies
- support first-class skeletonization for Python, shell, JS/TS, and HTML/CSS in the shipped/provisioned environment
- use Tree-sitter as an optional fallback for unsupported parseable languages when explicitly installed; default tests report its status honestly and an opt-in integration path can exercise it for real
- reduce prompt weight for later iterations

## 4.9 `qontrabender.py`
Cache composer / variable-fidelity helper.
Responsibilities:
- assemble cache payloads
- use policy-driven selection rules
- practically relevant when Gemini context caching is the chosen path

## 4.10 `qonfirmer.py`
Deterministic contract verifier.
Responsibilities:
- enforce machine-readable invariants from `qontract.json`
- catch forbidden imports / schema mismatches / endpoint rules / ID strategy violations

## 4.11 `qualifier.py`
Deterministic local verifier.
Responsibilities:
- syntax checks
- import resolution checks
- structural consistency checks
- pluggable language-aware validation (Python, shell, JS/TS, HTML, plain CSS)

## 4.12 `lib_ai.py`
Unified provider abstraction.
Current provider support in the repo:
- OpenAI
- Gemini
- Anthropic
- DeepSeek
- Qwen
- OpenRouter
- Venice *(v1.3.12 — Venice API, OpenAI-compatible)*
- mlx *(v1.3.12 — local/LAN OpenAI-compatible runtimes)*
- llama-cpp *(v1.3.12 — local/LAN OpenAI-compatible runtimes)*

Also handles timeout / retry behavior and provider-specific adapters.

## 5. QONTRACT system

QONTRACT is the repository’s constitution-like enforcement layer.

### Generation
On the first build pass, InstruQtor creates:
- `qontract.d/qontract.md`
- `qontract.d/qontract.json`

### Use later in the pipeline
Later build passes and repair passes expect contract material to exist.
The runtime uses fail-fast checks so later stages do not silently proceed without the contract.

### Current documented invariant types
The current repo / doc / code set indicates checks around:
- forbidden imports
- exact field expectations
- forbidden field names
- ID type rules
- monotonic ID strategy patterns
- required endpoints

## 6. Context and memory layers

| Layer | Location | Role |
|------|----------|------|
| Task | `tasq.d/` / `worqspace/tasq.md` | current objective |
| Contract | `qontract.d/` | project invariants |
| Current code | `qodeyard/` | canonical current output |
| Execution summaries | `exeq.d/` | per-briq execution trace |
| Reviews | `reqap.d/` | review and iteration recap |
| Skeleton cache | `bloq.d/` | compressed architecture view |
| Structural context map | `qontext.d/` | lighter-weight context intelligence |
| Cache payloads | `qache.d/` | Qontrabender output when used |
| Logs | `struqture/` | console and event traces |

## 7. Configuration reference

Main config file:

```text
worqspace/config.yaml
```

### Important top-level sections
- `retry`
- `interleaved`
- `verification`
- `agents`
- `options`

### Notable current settings
#### retry
- `enabled`
- `max_attempts`
- `stop_on_briq_fail`
- `retry_delay`

#### interleaved
- `enabled`
- `local_validation`
- `ai_quick_review`
- `retry_on_review_fail`

#### verification
- `enabled`
- `checks.syntax`
- `checks.imports`
- `checks.skeleton_match`

#### agents.construqtor
- `provider`: AI provider (openai, gemini, anthropic, etc.)
- `model`: model name
- `coding_mode`: `heredoc` | `direct` | `hybrid`
  - `heredoc`: Legacy Markdown fenced-block output.
  - `direct`: Tool-based direct editing in an attempt-workspace.
    - Uses `write_file_direct` tool.
    - Hardened via `safe_write_file` with `validation-root` jail.
    - Features cumulative repair-forward validation within the loop.
    - Fallback to fenced blocks if tools are missing but files are present.
  - `hybrid` (default): Deterministic per-file transport policy.
    - Default: new file creation uses `heredoc`; edits to existing files use `direct`.
    - One-way anti-flapping lock: direct can escalate to heredoc on deterministic failure triggers.
    - Attempt manifests include transport decision records and fallback reasons.

#### agents.inspeqtor.smoketest
- `enabled` (default: false)
- `mode` (`scoped` or `full`)
- `timeout_seconds`
- `max_output_chars`
- `adapters.<adapter>.enabled`
- `adapters.<adapter>.command` / `commands` (optional manual overrides)
- `adapters.<adapter>.append_changed_files`
- `adapters.python.auto_unittest_discover`
- `adapters.python.auto_cli_help`
- `adapters.js_ts.auto_tsc_no_emit`
- `adapters.js_ts.allow_script_execution`
- `adapters.js_ts.require_dependencies`

Smoketest output semantics:
- per-check evidence includes `execution_kind` (`static` or `executed`)
- `validation_execution_mode` only becomes `EXECUTED` / `MIXED` when genuine executed evidence exists
- static-only checks (for example `tsc --noEmit` or shell syntax checks) do not inflate executed coverage

#### options
- `use_qompressor`
- `use_qontextor`
- `use_qontrabender`
- `cheqpoint`
- `max_total_iterations` (legacy alias: `auto_cycle_limit`)
- `max_build_passes`
- `cycle_estimate_mode` (`advisory` or `scheduler`)
- `briq_sensitivity`
- `mode`

#### repair
- `max_attempts_per_build_pass` (legacy alias: `max_attempts`)
- same-run repairs consume `max_total_iterations` budget but do not increment `max_build_passes`

### Important reality check about defaults
The committed repo config is a **working example config**, not a universal recommendation. CLI overrides and per-project tuning are expected.

## 8. Providers and API keys

QonQrete checks provider usage against required environment variables.

### Environment variables used by the repo
```bash
OPENAI_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
QWEN_API_KEY
OPENROUTER_API_KEY
VENICE_API_KEY          # v1.3.12 — required when provider: venice
MLX_API_KEY             # v1.3.12 — optional, used when provider: mlx
LLAMA_CPP_API_KEY       # v1.3.12 — optional, used when provider: llama-cpp
```

### Current provider notes
- Gemini can use `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- DeepSeek support is built through an OpenAI-compatible adapter inside `lib_ai.py`
- Venice support is built through an OpenAI-compatible adapter; it requires a dedicated `VENICE_API_KEY` and does **not** fall back to `OPENAI_API_KEY`
- mlx and llama-cpp support are built through an OpenAI-compatible adapter; they require `api_base_url` in the per-agent config block and work with or without an API key
- `local` is used for non-remote helper agents

## 9. IDE integrations

## 9.1 VS Code extension
Location:

```text
vscode-extension/
```

### What it currently does
- command palette commands for init / run / resume / clean / show status
- right-click run support for `tasq.md`
- right-click “run as QonQrete tasq” for other Markdown files
- sidebar control panel
- status bar state updates
- shell detection and verification
- qage browsing helpers
- settings-backed run defaults aligned to current runtime (`sensitivity=1`, `cycles=1`, `autonomous=true`)
- run option wiring includes `--no-sync` (`qonqrete.noSync`) and `--seed-repo`

### Important current behavior
- it executes the existing CLI in a terminal-driven way
- it assumes a repo-local QonQrete project
- it does not magically replace the core runtime
- it does not yet implement the separate “central engine shared across many normal repos” flow

### Packaging
```bash
cd vscode-extension
npm install
npm run compile
npx vsce package
```

## 9.2 IntelliJ / JetBrains plugin
Location:

```text
intellij-plugin/
```

### What is present in this repo snapshot
- Gradle plugin project
- plugin README / changelog
- manual packaging path
- tool-window-oriented UX concept for running and browsing QonQrete flows
- settings + run dialogs wired to current launcher options, including `--no-sync`

### Packaging
```bash
cd intellij-plugin
./gradlew buildPlugin
```

### Important current behavior
Like the VS Code extension, the bundled IntelliJ plugin in this repo wraps the existing repo-local QonQrete CLI workflow.

## 10. Security model

The repository is designed around defense in depth.

### Container security
- isolated Qage container runtime
- reduced capabilities
- read-only root patterns with writable work areas
- non-root execution after entrypoint privilege handling
- tmpfs / resource-limiting patterns in runtime setup

### File/path safety
Implemented helper concepts include:
- jail enforcement
- path validation
- symlink-aware checks
- size limits for key files

### Provider safety
`lib_ai.py` and related code enforce:
- timeout handling
- bounded retry behavior
- sanitized error reporting

## 11. Current limitations

These limitations should be documented honestly for `v1.4.0`:

1. **Repo-local workflow remains the active implementation model.**
   The central engine / per-project metadata architecture is a future/product direction, not the current repo behavior.

2. **IDE store publishing is outside the core runtime itself.**
   The repo includes the extension/plugin projects and packaging paths, but that is distinct from the runtime behavior.

3. **Experimental paths remain experimental.**
   The standard CLI and IDE wrappers are the maintained execution surfaces.

4. **Provider/model lists are whatever the current config and code support.**
   Documentation should not invent providers or models that the repo does not actually implement.

5. **Qontrabender is not universally useful for every provider path.**
   The repo repeatedly documents its practical relevance to Gemini-oriented caching workflows.

## Related docs
- [README.md](../README.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [QUICKSTART.md](./QUICKSTART.md)
- [RELEASE-NOTES.md](./RELEASE-NOTES.md)
- [TERMINOLOGY.md](./TERMINOLOGY.md)

## 12. Workspace Deployment (v1.2.0+)

### Deployment model
The IDE integrations now support one-click workspace deployment:

1. **Deploy to Workspace** downloads a versioned release zip and extracts it into `<workspace>/.qonqrete/`
2. The runtime remains fully script-relative — `qonqrete.sh` derives `SCRIPT_DIR` from its own location
3. User-facing `tasq.md` lives at workspace root; the IDE syncs it into `.qonqrete/worqspace/tasq.md` before runs
4. Auto-init builds the container image on first run if missing
5. `.qonqrete/` is automatically added to `.gitignore`

### Command flow
```text
Install extension/plugin
  → Deploy to Workspace
  → Create tasq.md
  → Configure Run (optional)
  → Run Tasq (auto-init if needed, auto-sync tasq)
```

### Image versioning
Container images are now tagged with the version:
- `qonqrete-qage:1.4.0` (example current version)
- `qonqrete-qage:latest` (convenience alias)
- `qonqrete-qage` (untagged compatibility alias)

## 13. Cost Confirmation Gate (GateQeeper)

QonQrete supports an optional cost confirmation gate after CalQulator estimates the run cost.

### Configuration

In `worqspace/config.yaml`:

```yaml
options:
  cost_confirmation_gate: false   # default: false
```

When set to `true`, after CalQulator finishes, the GateQeeper prompts:

```
GateQeeper: Cost estimate above. Proceed with this run? [y/N]
```

The user must confirm before ConstruQtor begins. This prevents accidental expensive runs.

### Behavior
- Only triggers after CalQulator completes successfully
- Skipped if CalQulator is skipped (e.g., local construqtor)
- In non-interactive terminal usage, the gate shows as a log message instead of prompting

## 14. OpenRouter Provider Support

OpenRouter is supported as a provider through its OpenAI-compatible API endpoint.

### Configuration

```yaml
agents:
  construqtor:
    provider: openrouter
    model: anthropic/claude-sonnet-4
```

### Environment variable

```bash
export OPENROUTER_API_KEY='...'
```

### Supported models (via OpenRouter)
- `anthropic/claude-sonnet-4`
- `openai/gpt-4.1`
- `google/gemini-2.5-pro`
- `deepseek/deepseek-chat-v3`
- Any model available on OpenRouter's platform

## 15. Venice Provider Support *(v1.3.12)*

Venice is supported as a provider through its OpenAI-compatible API endpoint at `https://api.venice.ai/api/v1`. A real Venice model ID is set in the agent's `model` field (not a profile selector — Venice uses actual model identifiers).

### Configuration

```yaml
agents:
  construqtor:
    provider: venice
    model: "qwen3-coder-480b-a35b-instruct-turbo"
    # api_base_url: "https://api.venice.ai/api/v1"   # default, override only if proxying
    venice_parameters:
      include_venice_system_prompt: false
    # max_tokens: 8192
    # context_window: 131072
```

### Environment variable

```bash
export VENICE_API_KEY='...'
```

`VENICE_API_KEY` is **required**. Venice does NOT fall back to `OPENAI_API_KEY`. `qrane` fails early with a clear error if the key is missing while any agent is configured for `provider: venice`.

### Example Venice models

The user may set any valid Venice text model ID. The following is a representative list at v1.3.12 release time; the authoritative list is always `GET https://api.venice.ai/api/v1/models`:

- `venice-uncensored`
- `qwen3-coder-480b-a35b-instruct-turbo`
- `qwen3-235b` / `qwen3-235b-a22b-instruct` / `qwen3-235b-a22b-thinking`
- `qwen3-next-80b`
- `qwen3-4b`
- `qwen-2.5-qwq-32b`
- `qwen-2.5-coder-32b`
- `qwen-2.5-vl`
- `mistral-31-24b`
- `mistral-small-3.2-24b-instruct`
- `llama-3.3-70b`
- `llama-3.2-3b`
- `llama-3.1-405b`
- `dolphin-2.9.2-qwen2-72b`
- `deepseek-r1-671b`
- `deepseek-r1-llama-70b`
- `deepseek-coder-v2-lite`
- `claude-opus-4.6`
- `claude-sonnet-4.6`
- `glm-5`
- `glm-4.7-flash-heretic`
- `minimax-2.5`

The model string is passed through verbatim — QonQrete does not enforce or hardcode any specific Venice model.

### `venice_parameters` pass-through

When `venice_parameters` is set under a Venice-configured agent, QonQrete passes the entire dict through to the request body under the `venice_parameters` key (via the OpenAI SDK's `extra_body`). It is never transformed. By default QonQrete does NOT disable Venice's system prompt; set `include_venice_system_prompt: false` explicitly if you want that behavior.

## 16. MLX and Llama-cpp Provider Support *(v1.3.12)*

The `mlx` and `llama-cpp` providers are designed for local or LAN OpenAI-compatible LLM runtimes (e.g. MLX server, `llama.cpp` server).

### Configuration

```yaml
agents:
  construqtor:
    provider: mlx                              # mlx | llama-cpp
    api_base_url: "http://localhost:8080/v1"   # REQUIRED
    # model: "optional-model-string"
    # max_tokens: 8192
    # context_window: 16384
```

`api_base_url` is **required** for actual usage and must be set in the per-agent config block. If the `model` field is omitted or empty, QonQrete allows the upstream runtime to choose the model (the `model` field is omitted from the outbound JSON payload). This is achieved via a dedicated direct HTTP request path for these providers.

`qrane` does not fail on missing API keys for these providers — they run without authentication by default.

### Environment variables (optional)

```bash
export MLX_API_KEY='...'         # used when provider: mlx
export LLAMA_CPP_API_KEY='...'   # used when provider: llama-cpp
```

Both are **optional**. If present, the matching key is sent as Bearer auth. If absent, the request proceeds without auth.

### Profile defaults

| Provider | `context_window` | `max_tokens` |
|---------|------------------|--------------|
| `mlx`        | 16384 | 8192 |
| `llama-cpp`  |  8192 | 4096 |

Per-agent `context_window` / `max_tokens` overrides take priority over these defaults.
