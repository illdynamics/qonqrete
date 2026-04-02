# QonQrete Documentation

**Version:** `v1.2.0`

This document is the synced technical reference for the current `v1.2.0` repository snapshot.

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

## 1. What QonQrete is

QonQrete is a **structured AI construction loop** for building software inside a hardened runtime. It takes a high-level task, decomposes it into briqs, generates or modifies code, reviews the result, and optionally continues into more cycles.

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
- MSB / Microsandbox (experimental)

### 3.2 Fresh run

```bash
./qonqrete.sh run
```

Current run flow:
1. validate runtime prerequisites
2. validate required config/task files
3. create a new `qage_YYYYMMDD_HHMMSS`
4. optionally seed from `worqspace/sqrapyard/` when `-s` is used
5. copy config/task material into the new Qage workspace
6. launch the container
7. let Qrane execute the pipeline
8. optionally save as a qonstruction

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

## 4.1 `tasqleveler.py`
Optional task enhancer.
- cycle-1-only behavior
- enriches a tasq with success criteria / structure / testing guidance
- controlled by config and pipeline presence

## 4.2 `instruqtor.py`
Planning agent.
Responsibilities:
- read the current tasq
- create briqs in `briq.d/`
- generate QONTRACT files on cycle 1
- honor sensitivity settings and decomposition logic

## 4.3 `calqulator.py`
Local estimation helper.
Responsibilities:
- estimate token/cost footprint
- annotate planning flow with rough cost expectations
- zero AI-token cost

## 4.4 `construqtor.py`
Code generation / modification agent.
Responsibilities:
- consume briqs
- write or update files in `qodeyard/`
- emit execution summaries to `exeq.d/`
- use contract-aware and validation-aware build retries

## 4.5 `inspeqtor.py`
Review agent.
Responsibilities:
- run deterministic checks
- run AI-assisted review stages
- emit final recap material to `reqap.d/`
- drive success / partial / failure assessment logic

## 4.6 `qontextor.py`
Context indexing helper.
Responsibilities:
- build structural / semantic maps in `qontext.d/`
- run in local mode according to config
- provide cheaper context reuse than shoving full source trees into prompts

## 4.7 `qompressor.py`
Skeletonizer.
Responsibilities:
- compress code structure into `bloq.d/`
- preserve function/class-level shape while stripping large bodies
- reduce prompt weight for future cycles

## 4.8 `qontrabender.py`
Cache composer / variable-fidelity helper.
Responsibilities:
- assemble cache payloads
- use policy-driven selection rules
- practically relevant when Gemini context caching is the chosen path

## 4.9 `qontract_guard.py`
Deterministic contract verifier.
Responsibilities:
- enforce machine-readable invariants from `qontract.json`
- catch forbidden imports / schema mismatches / endpoint rules / ID strategy violations

## 4.10 `loqal_verifier.py`
Deterministic local verifier.
Responsibilities:
- syntax checks
- import resolution checks
- structural consistency checks

## 4.11 `lib_ai.py`
Unified provider abstraction.
Current provider support in the repo:
- OpenAI
- Gemini
- Anthropic
- DeepSeek
- Qwen
- OpenRouter
- `llamacpp` for host-side `llama-server` endpoints
- `local` for helper-agent script routing

Also handles timeout / retry behavior and provider-specific adapters.

## 5. QONTRACT system

QONTRACT is the repository’s constitution-like enforcement layer.

### Generation
On cycle 1, InstruQtor creates:
- `qontract.d/qontract.md`
- `qontract.d/qontract.json`

### Use later in the pipeline
Later cycles expect contract material to exist.
The runtime uses fail-fast checks so later stages do not silently proceed without the contract.

### Current documented invariant types
The current repo/docs/code indicate checks around:
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
| Reviews | `reqap.d/` | review and cycle recap |
| Skeleton cache | `bloq.d/` | compressed architecture view |
| Semantic map | `qontext.d/` | lighter-weight context intelligence |
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
- `providers`
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

#### options
- `use_qompressor`
- `use_qontextor`
- `use_qontrabender`
- `cheqpoint`
- `auto_cycle_limit`
- `briq_sensitivity`
- `mode`

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
LLAMACPP_ENDPOINT        # optional override
QONQ_LLAMACPP_ENDPOINT   # optional override
LLAMACPP_API_KEY         # optional if your llama-server is fronted by auth
```

### Current provider notes
- Gemini can use `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- DeepSeek support is built through an OpenAI-compatible adapter inside `lib_ai.py`
- OpenRouter is supported through its OpenAI-compatible API
- `llamacpp` talks to an already-running host-side `llama-server` over HTTP and requires no cloud API key by default
- On Mac laptops such as an M1 Max, run `llama-server` on macOS itself, then let the QonQrete container reach it through `host.docker.internal` (Docker Desktop) or `host.containers.internal` (Podman)
- `local` is used for non-remote helper agents and is **not** the llama.cpp path

### Shared provider defaults
QonQrete now supports optional shared defaults under `providers.<provider>`, with per-agent values overriding shared provider defaults.

Example for llama.cpp:

```yaml
providers:
  llamacpp:
    endpoint: http://host.docker.internal:8080/v1
    timeout: 900  # valid for llama.cpp host-side runs
    max_tokens: 8192
    temperature: 0.2
    top_p: 0.9
    top_k: 40
    min_p: 0.05
    seed: -1
    repeat_penalty: 1.05
    presence_penalty: 0.0
    frequency_penalty: 0.0
    stop: []

agents:
  tasqleveler:
    provider: llamacpp
    model: /Users/ricky/Qoding/ai/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf

  instruqtor:
    provider: llamacpp
    model: /Users/ricky/Qoding/ai/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf

  construqtor:
    provider: llamacpp
    model: /Users/ricky/Qoding/ai/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf
    temperature: 0.15
    max_tokens: 12000

  inspeqtor:
    provider: llamacpp
    model: /Users/ricky/Qoding/ai/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf
```

Endpoint resolution order for `llamacpp` is:
1. `agents.<agent>.endpoint`
2. `providers.llamacpp.endpoint`
3. `LLAMACPP_ENDPOINT` or `QONQ_LLAMACPP_ENDPOINT`
4. `http://host.docker.internal:8080/v1`
5. `http://host.containers.internal:8080/v1`
6. `http://localhost:8080/v1`

Model matching preserves the raw configured model string for outbound fallback requests. QonQrete compares the raw value, env-expanded value, basename, and server aliases/roots from `/v1/models`, but if preflight cannot reconcile the model id it falls back to the raw configured string instead of a container-expanded `~` path.

QonQrete treats `llamacpp` as zero-cost from a billing perspective. Token estimation can still be shown, but dollar estimates remain `$0.00`. Both IDE integrations can store an optional `LLAMACPP_API_KEY` securely for auth-fronted endpoints without making it mandatory for normal local usage.

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

These limitations should be documented honestly for `v1.2.0`:

1. **Repo-local workflow remains the active implementation model.**
   The central engine / per-project metadata architecture is a future/product direction, not the current repo behavior.

2. **IDE store publishing is outside the core runtime itself.**
   The repo includes the extension/plugin projects and packaging paths, but that is distinct from the runtime behavior.

3. **Experimental paths remain experimental.**
   `TUI`, `MSB`, and `wonqrete` should still be treated as non-core flows.

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

## 12. Workspace Deployment (v1.2.0)

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
- `qonqrete-qage:1.2.0` (primary)
- `qonqrete-qage:latest` (convenience alias)
- `qonqrete-qage` (legacy untagged, backward compat)

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
- Skipped if CalQulator is skipped (for example when ConstruQtor uses the `local` helper-agent path). With `llamacpp`, CalQulator can still run and will report `$0.00` estimated cost
- In TUI mode, shows as a log message (non-interactive in TUI)

## 14. llama.cpp Provider Support

`llamacpp` is a distinct provider for talking to an already-running `llama-server` over its OpenAI-compatible HTTP API.

A typical host-side launch on a Mac M1 Max looks like:

```bash
llama-server \
  -m ~/Qoding/ai/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf \
  --port 8080 \
  --chat-template chatml \
  --n-gpu-layers 999 \
  --ctx-size 65536 \
  --batch-size 256 \
  --threads 10 \
  --mlock \
  --mmap \
  --parallel 1
```

Run that on the host OS, then let the QonQrete container connect to `http://host.docker.internal:8080/v1` on Docker Desktop or `http://host.containers.internal:8080/v1` on Podman.

### Configuration

```yaml
providers:
  llamacpp:
    endpoint: http://host.docker.internal:8080/v1
    timeout: 900  # valid for llama.cpp host-side runs
    max_tokens: 8192
    temperature: 0.2
    top_p: 0.9
    top_k: 40
    min_p: 0.05
    seed: -1
    repeat_penalty: 1.05
    presence_penalty: 0.0
    frequency_penalty: 0.0
    stop: []

agents:
  construqtor:
    provider: llamacpp
    model: /absolute/path/to/model.gguf
```

### Important behavior
- The server must already be running on the host
- The container tries `host.docker.internal`, then `host.containers.internal`, then `localhost` if no explicit endpoint is set
- `model` should remain your GGUF file path or a server-side alias
- The runtime preflights `/v1/models` and will prefer the server-reported model id when it can confidently match by exact id or basename
- No API key is required by default
- `local` still means helper-agent scripts, not llama.cpp inference

## 15. OpenRouter Provider Support

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
