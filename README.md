# QonQrete - The First 100% File-Based Local-First Secure Agentic AI System (v1.4.1 - MLcon Edition)
![Release](https://img.shields.io/github/v/release/illdynamics/qonqrete)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Repo Views](https://komarev.com/ghpvc/?username=illdynamics-qonqrete&label=Repo+Views&color=blue)
[![Build VS Code Extension](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml)
[![Build IntelliJ Plugin](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml)

![QonQrete](qonqrete.jpg)

QonQrete is a **local-first, file-based AI software construction system** that runs a structured multi-agent build loop inside a hardened container. It plans work into briqs, generates code in a Qage, reviews the result, and iterates with either **user-gated cheQpoints** or **fully autonomous global-iteration loops**.

## Version

**Current repository version:** `v1.4.1`
**Release context:** `v1.4.1 - MLcon Edition`
Canonical source of truth: `VERSION`

## What this repository contains

This repository currently ships three things:

1. **QonQrete core CLI/runtime**
   - `qonqrete.sh`
   - `qrane/`
   - `worqer/`
   - `worqspace/`
2. **VS Code extension** in `vscode-extension/`
3. **IntelliJ / JetBrains plugin** in `intellij-plugin/`

The IDE integrations let you trigger the existing CLI workflow from inside the IDE. They do **not** replace the core runtime.

> **v1.4.1 - MLcon Edition** — Truthful Inspection, Clean Streaming UX, Hybrid Venice Wiring

This release focuses on three coordinated fixes:

- **QonQrete-native Sqrewdriver repair controller**
  - `qrane/sqrewdriver_controller.py` now owns the artifact-driven stop-or-repair decision after InspeQtor.
  - QonQrete does not run the root-level `sqrewdriver/` desktop app and does not add Bun/Electrobun to the runtime.
  - Repairs are driven by InspeQtor verdicts, `repair-plan.v1.json`, validation bundles, and a generated `verdict/sqrewdriver-repair-brief.v1.md`.

- **Inspection truthfulness hardening**
  - Final artifact evidence from `qodeyard/` is now explicitly authoritative in review prompts.
  - Review snippets now carry deterministic metadata (`file_bytes`, `snippet_chars`, `snippet_truncated`) so prompt clipping is never mistaken for file truncation.
  - InspeQtor review calls now disable previous-log injection for tactical/meta review to reduce stale relay influence.
  - Verdict synthesis now prioritizes deterministic gates; advisory briq-review noise no longer blocks completion when deterministic checks pass.

- **Frontend localStorage false-negative fix**
  - Deterministic validation now resolves direct literals plus compact constant/alias/object indirection for localStorage keys (for example `const KEY`, alias chains, `STORAGE_KEYS.foo`).

- **Streaming UX cleanup (without losing audit capture)**
  - Outer Qrane heartbeat chatter removed.
  - Inner ConstruQtor `[Still working] ...` chatter removed.
  - Full raw stream capture to qonsole/audit remains intact.
  - Terminal defaults to concise rendering for streamed heredoc payloads:
    - `Writing <file>...`
    - `Wrote <file>`
  - TTY hotkeys:
    - `TAB` => raw stream mode
    - `Shift+TAB` => concise mode
  - Mode hints are edge-triggered (single status messages), never prefixed per streamed line.

- **Execution wiring defaults**
  - Primary agents remain per-agent configurable; this workspace's live-test config uses DeepSeek for intake/planning/inspection and CodeSeeq only for ConstruQtor.
  - ConstruQtor default coding mode is now `hybrid`.
  - New launcher switch `-N/--no-sync` keeps outputs in qage/qonstruction paths and skips repo-root sync-back.

> **v1.3.0** — Hardened Sandbox, Agent Renames, Legacy Cleanup

QonQrete is a deterministic AI coding agent that builds software inside hardened containers. It takes a high-level task, decomposes it into briqs, generates code, reviews the result, and optionally continues into more build/repair passes when the runtime allows it — all locally, all file-based, all yours.

## Quick Start (IDE)

### VS Code
1. Install **QonQrete** from the VS Code Marketplace
2. `Ctrl+Shift+P` → **QonQrete: Deploy to Workspace**
3. `Ctrl+Shift+P` → **QonQrete: Create Task File** — creates the starter `tasq.md`
4. `Ctrl+Shift+P` → **QonQrete: Run Tasq** — runs the default task file directly, auto-init on first run

### IntelliJ / JetBrains
1. Install **QonQrete** from the JetBrains Marketplace
2. `Ctrl+Shift+A` → **QonQrete: Deploy to Workspace**
3. `Ctrl+Shift+A` → **QonQrete: Create Task File**
4. `Ctrl+Alt+Q` → **Run Tasq**

### What happens
```
my-project/
  tasq.md              ← you edit this
  .qonqrete/           ← runtime (hidden, gitignored)
    qonqrete.sh
    worqspace/
    qrane/
    worqer/
    ...
```

## Quick Start (CLI)

### Option 1: curl-bash install (recommended)

```bash
curl -fsSL https://qonqrete.sh/install.sh | bash
```

This downloads the latest release, then walks you through an interactive setup:
1. Choose your AI provider (OpenAI, DeepSeek, Gemini, Anthropic, Venice, CodeSeeq, and more)
2. Select a model from that provider's supported list
3. Enter your API key (auto-detected if already set in your environment)

After setup, QonQrete automatically configures all agents, runs `init`, and creates a starter `tasq.md`. You're ready to build.

For a specific version:
```bash
curl -fsSL https://qonqrete.sh/install.sh | bash -s -- v1.4.1
```

### Version-specific install

```bash
curl -fsSL https://qonqrete.sh/install.sh | bash -s -- v1.4.1
```

For CI/non-interactive use:
```bash
QONQRETE_AUTO=1 QONQRETE_PROVIDER=deepseek QONQRETE_MODEL=deepseek-chat \
  curl -fsSL https://qonqrete.sh/install.sh | bash
```

### Option 2: Git clone + bootstrap

```bash
git clone https://github.com/illdynamics/qonqrete.git
cd qonqrete
./qonqrete-bootstrap.sh /path/to/your-project
```

Same interactive setup as the curl-bash install.

### Option 3: IDE Extensions

Install **QonQrete** from the VS Code or JetBrains marketplace. On first launch, a setup wizard guides you through provider selection, model choice, and API key entry — then auto-configures everything. One click and you're ready.

## How It Works

`cyqle{N}` folder numbering tracks the **global iteration index**. A repair pass stays attached to the most recent build pass and does **not** increment the build-pass count. By default, InstruQtor's estimated build-pass count is recorded as **advisory** unless scheduler mode is enabled. Resume honors explicitly queued next-pass metadata, and when interruption happens mid-pass it restores the interrupted active pass semantics instead of silently defaulting to build.


```
User defines a task file
  → Qrystallizer clarifies the task (first build pass)
  → InstruQtor decomposes into briqs + generates QONTRACT
  → CalQulator estimates cost
  → ConstruQtor generates/modifies code in qodeyard/
  → InspeQtor reviews and produces verdict/repair artifacts
  → Sqrewdriver controller stops only when hard gates pass, otherwise writes a repair brief
  → Qontextor indexes deterministic multi-language structural context (Python, shell, JS/TS, HTML/CSS)
  → Qompressor creates deterministic multi-language structural skeletons (Python, shell, JS/TS, HTML/CSS)
  → Qrane launches a bounded repair pass when required
  ```

### Sqrewdriver Repair Controller

QonQrete includes a native Sqrewdriver-inspired controller in `qrane/sqrewdriver_controller.py`. It uses the control pattern from the sibling `sqrewdriver/` project as inspiration only; the desktop app, Bun runtime, and Electrobun packaging are not runtime dependencies.

The controller runs after InspeQtor. A run stops cleanly only when InspeQtor hard gates pass, repair is not requested, required completion files exist in `qodeyard/`, and no current hard validation or stale artifact failures remain. When that gate fails and repair caps allow another pass, it writes `verdict/sqrewdriver-repair-brief.v1.md` plus `.json`, augments `verdict/repair-plan.v1.json`, and Qrane starts a same-run repair pass. ConstruQtor receives the brief through `QONQ_SQREWDRIVER_REPAIR_BRIEF_PATH`, while `repair-plan.v1.json` remains the structured source for target files, allowed edit paths, and locked files.

Success is therefore artifact-gated: an AI statement that the task is done is not enough without InspeQtor hard-gate evidence.

  ### Coding Modes

  ConstruQtor supports three coding strategies via the `coding_mode` configuration:

  - **`heredoc`:** Legacy mode. The AI generates file content wrapped in Markdown code blocks.
  - **`direct`:** Advanced tool-based mode. The AI uses a dedicated `write_file_direct` tool to mutate files inside a hardened attempt-workspace (`validation-root`). This mode features iterative repair-forward validation within the sandbox before committing to `qodeyard`.
  - **`hybrid` (Default):** Deterministic transport-policy mode. Default per-file policy is:
    - new files → `heredoc`
    - existing files → `direct`
    Deterministic fallback/escalation forces `heredoc` for coherence/reliability when direct transport is fragile or output quality degrades.

All execution happens inside a **hardened container** with:

- Read-only root filesystem
- Dropped capabilities
- Non-root runtime

## Qontextor context model

Qontextor now defaults to a deterministic structural graph path. The local extractor stack builds shared graph records plus language-specific extraction for the current runtime:
- Python via stdlib AST
- Shell via `shfmt -tojson` when available in the shipped environment (heuristic fallback only in reduced environments)
- JavaScript / TypeScript via a repo-shipped Node helper backed by the TypeScript Compiler API
- HTML via a repo-shipped Node helper backed by `parse5`
- CSS via a repo-shipped Node helper backed by `postcss`

## Qompressor skeleton model

Qompressor now defaults to adapter-based multi-language structural skeletonization for the current runtime:
- Python AST skeletons
- Shell skeletons backed by `shfmt -tojson` when available in the shipped environment
- JavaScript / TypeScript skeletons backed by a repo-shipped Node helper using the TypeScript Compiler API
- HTML skeletons backed by `parse5`
- CSS skeletons backed by `postcss`

Tree-sitter is an optional fallback path for unsupported parseable languages. It is **not** shipped by default; install `requirements-optional-tree-sitter.txt` when you want that fallback enabled. Use `python worqer/qontextor.py --capabilities` or `python worqer/qompressor.py --capabilities` to see exactly which native and fallback paths are active in your current runtime. The default test suite stays offline-safe; real Tree-sitter integration is an opt-in path for environments that deliberately install it.

The default path is offline-safe and does **not** depend on embeddings.

## Architecture

```
qonqrete/
├── qonqrete.sh           # Host entrypoint
├── qrane/                 # Orchestrator
├── worqer/                # Agents (InstruQtor, ConstruQtor, InspeQtor, etc.)
├── worqspace/             # Config + runtime data
├── vscode-extension/      # VS Code integration
├── intellij-plugin/       # JetBrains integration
└── doc/                   # Documentation
```

## Supported AI Providers

| Provider | Env Variable |
|----------|-------------|
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| CodeSeeq | `DEEPSEEK_API_KEY` + executable `codeseeq` CLI |
| Qwen | `QWEN_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Venice | `VENICE_API_KEY` *(required, no fallback)* |
| mlx | `MLX_API_KEY` *(optional — works without auth)* |
| llama-cpp | `LLAMA_CPP_API_KEY` *(optional — works without auth)* |

## Container Engines

- **Podman** (default auto-detected path)
- **Docker** (explicit via `--docker` or `CONTAINER_ENGINE=docker`)
- **Repo-native host mode** (`CONTAINER_ENGINE=none`, and also auto-selected when Podman is unavailable)
## CLI Reference

```bash
./qonqrete.sh init                           # Build container image
./qonqrete.sh tasq.md              # Task-first run
./qonqrete.sh run -f tasq.md       # Explicit task-file run
./qonqrete.sh run --auto                     # Autonomous mode
./qonqrete.sh run -b 6 -c 3                  # Sensitivity 6, 3 total iterations (build + repair passes)
./qonqrete.sh run --mode security            # Security-focused mode
./qonqrete.sh run --seed-repo                # Continue from current repo code (default run starts empty)
./qonqrete.sh run --no-sync                  # Skip repo-root sync-back only; qage/qodeyard artifacts remain
./qonqrete.sh run -a -n myproject            # Auto + save as qonstruction
./qonqrete.sh resume                         # Resume from previous qage
./qonqrete.sh status                         # Latest run state + manifest paths
./qonqrete.sh audit                          # Latest audit timeline + artifact paths
./qonqrete.sh clean                          # Interactive qage cleanup
./qonqrete.sh clean -A                       # Delete all qages
python worqer/qontextor.py --capabilities    # Current extractor capability report
python worqer/qompressor.py --capabilities   # Current compressor capability report
python -m worqer.smoqetester qodeyard --cycle 1 --config worqspace/config.yaml --json
```

## IDE Commands (v1.4.1)

Both VS Code and IntelliJ support identical commands:

| Command | Description |
|---------|-------------|
| **Deploy to Workspace** | Install runtime into `.qonqrete/` |
| **Create Task File** | Create starter `tasq.md` at project root |
| **Configure Run** | Set sensitivity, cycles, mode, engine, repo-seed, and no-sync |
| **Run Tasq** | Run the default task file directly with auto-init when needed |
| **Run Markdown as Task** | Run any markdown file directly as task input |
| **Resume Run** | Continue from previous qage |
| **Clean Qages** | Delete old qage directories |
| **Init Workspace** | Manually build container image |
| **Set AI Configuration** | Configure providers, models, and API keys |
| **Show Status** | Display full status info |

## Modes

| Mode | Focus |
|------|-------|
| `program` | General programming (default) |
| `enterprise` | Enterprise applications |
| `security` | Security-focused development |
| `data` | Data processing and analysis |
| `devops` | DevOps and infrastructure |
| `web` | Web development |

## Local Node helper setup

The shipped container installs the default Node-based helper stack for JS/TS and HTML/CSS. For repo-local runs outside that container, install the pinned helper dependencies from `.qonqrete/package.json`:

```bash
cd .qonqrete
npm ci
npm run qonq-native-capabilities
```

`npm ci` is the supported reproducible workflow here; `package-lock.json` is the install authority for exact versions.

Runtime discovery prefers repo-local `node_modules` first, then global Node modules. Reduced local environments may still run, but Qontextor/Qompressor will honestly report and artifact any fallback path they had to use.

## Documentation

- [Quickstart](doc/QUICKSTART.md)
- [Architecture](doc/ARCHITECTURE.md)
- [Documentation](doc/DOCUMENTATION.md)
- [Terminology](doc/TERMINOLOGY.md)
- [Release Notes](doc/RELEASE-NOTES.md)

## Validation Reality

Deterministic validation in the current bridge is strongest for Python. Other ecosystems still benefit from workflow orchestration, artifact capture, and AI review, but they do not yet have equivalent deterministic compile/test coverage.

Smoketest evidence is explicitly classified:
- `execution_kind=static` for static validation (syntax/type/parse style checks)
- `execution_kind=executed` for genuine runtime smoke commands

`validation_execution_mode` only reports `EXECUTED` or `MIXED` when genuine executed smoke evidence is present.

## Project

- **Website:** [qonqrete.sh](https://qonqrete.sh)
- **Author:** [Ill Dynamics](https://illdynamics.com) / WoNQ
- **License:** [AGPL-3.0](LICENSE)

## Secure API Key Handling

API keys are **never** stored in plain-text settings files, terminal commands, or logs.

### VS Code
Keys are stored in the **OS keychain** via VS Code's `SecretStorage` API. They are injected into the QonQrete process via the terminal's environment map — never in command text.

### IntelliJ / JetBrains
Keys are stored in IntelliJ's **PasswordSafe** (encrypted credential store). They are injected via `PtyCommandLine.environment` — directly into the OS process environment table, never in shell text or temp files.

### Environment variable precedence
1. **Real shell environment** (`OPENAI_API_KEY=...` in your terminal) — always wins
2. **IDE secure storage** — injected only if the env var is not already set
3. **Neither** — the IDE prompts you to enter the key

### Gemini / Google equivalence
`GOOGLE_API_KEY` and `GEMINI_API_KEY` are treated as equivalent. If either is set, the Gemini provider is considered configured.

## AI Configuration Panel

Both IDEs include a **"Set AI Configuration"** command that lets you:
- Set the **provider** and **model** for each primary AI agent (Qrystallizer, InstruQtor, ConstruQtor, InspeQtor)
- Set **API keys** for each provider (stored securely)
- See at a glance which keys are set and which are missing

Changes are written directly to `.qonqrete/worqspace/config.yaml`.

After deploying QonQrete to a workspace, the IDE will prompt you to configure AI providers and API keys.

## Cost Confirmation Gate (GateQeeper)

QonQrete can optionally prompt you to confirm a run after the CalQulator estimates cost.

In `worqspace/config.yaml`:

```yaml
options:
  cost_confirmation_gate: false   # set to true to enable
```

When enabled, after CalQulator runs, QonQrete will display the cost estimate and ask:

```
GateQeeper: Cost estimate above. Proceed with this run? [y/N]
```

You must answer `y` or `yes` to continue. Any other answer cancels the run.

This is useful for preventing accidental expensive runs with high sensitivity or many iterations.

## v1.4.1 - MLcon Edition Snapshot Highlights

- **Truthful inspection + deterministic evidence upgrades** in final review paths
- **Streaming UX cleanup** with concise-default rendering and TAB/Shift+TAB raw/concise toggles
- **Launcher `-N/--no-sync`** run control to keep output in qage/qonstruction paths
- **Primary AI provider wiring** remains per-agent configurable; ConstruQtor supports `hybrid` by default and can be routed through CodeSeeq.
- **Versioned container images** (`qonqrete-qage:<version>`; Linux/WSL builds include a host-UID suffix)
- **Aligned IDE behavior** in VS Code and IntelliJ around the same runtime and task-file model

## Core principles

- **Isolation by design** — AI execution happens in a Qage container, not directly on the host.
- **File-based communication** — task specs, plans, build evidence, validation, realization, verdicts, and logs are visible on disk.
- **Evidence-gated execution** — QonQrete runs clarification, planning, build, validation, realization, and inspection with bounded repair instead of implicit endless looping.
- **Human control when wanted** — autonomous mode exists, but user-gated cheQpoints remain first-class.
- **Local-first supporting stack** — several helper agents run fully locally with zero AI-token cost.

## Architecture in one glance

- **`qonqrete.sh`** — host entrypoint and runtime bootstrap
- **`qrane/`** — orchestrator, path handling, and cost helpers
- **`worqer/`** — agent scripts and security/provider utilities
- **`worqspace/`** — config, compatibility task copy, qages, qonstructions
- **`vscode-extension/`** — VS Code integration
- **`intellij-plugin/`** — JetBrains integration

## Main workflow

1. **Clarify** — `qrystallizer` is the canonical intake stage
2. **Clarification Gate** — if readiness is `NOT_READY`, Qrane pauses in `BLOCKED` / `RUN_WAITING_FOR_INPUT` and captures bounded clarification responses
3. **Qonstrictor** — `qonstrictor` evaluates readiness and effective constraints before planning as a fallback guard
4. **Plan** — `instruqtor` emits execution blueprint, build groups, validation plan, and contract files
5. **Estimate** — `calqulator` emits estimation artifacts
6. **Build** — `construqtor` performs scoped staged writes with attempt/recovery evidence
7. **Validate + Realize** — deterministic validation and realization bundles are produced before judgment
8. **Inspect** — `inspeqtor` emits structured verdicts and repair plans
9. **Continue only if justified** — bounded repair or explicit linked continuation when the repair plan warrants it

Questioning policy:
- only intake clarification asks user questions
- once readiness is accepted, mid-run questioning is disabled

## Directory overview

```text
qonqrete/
├── qonqrete.sh
├── qrane/
├── worqer/
├── worqspace/
│   ├── config.yaml
│   ├── pipeline_config.yaml
│   ├── caching_policy.yaml
│   ├── tasq.md
│   ├── qonstructions/
│   └── qage_YYYYMMDD_HHMMSS/
├── doc/
├── vscode-extension/
└── intellij-plugin/
```

## Supported AI providers

The current repo supports these providers through `worqer/lib_ai.py` and config:

- OpenAI
- Gemini
- Anthropic
- DeepSeek
- CodeSeeq *(CLI-backed provider through sibling `./codeseeq`; uses DeepSeek underneath)*
- Qwen
- OpenRouter
- Venice *(Venice API, OpenAI-compatible, requires `VENICE_API_KEY`)*
- mlx *(local/LAN OpenAI-compatible runtimes; API key optional)*
- llama-cpp *(local/LAN OpenAI-compatible runtimes; API key optional)*
- `local` for non-remote helper agents

CalQulator default target for cost estimation is `gemini / gemini-2.5-flash-lite` unless overridden in `agents.calqulator`.

Required environment variables depend on your selected providers:

```bash
export OPENAI_API_KEY='...'
export GOOGLE_API_KEY='...'        # or GEMINI_API_KEY
export ANTHROPIC_API_KEY='...'
export DEEPSEEK_API_KEY='...'
# provider: codeseeq also requires DEEPSEEK_API_KEY and the CodeSeeq CLI
export QWEN_API_KEY='...'
export OPENROUTER_API_KEY='...'
export VENICE_API_KEY='...'        # required for provider: venice
export MLX_API_KEY='...'           # optional, used when provider: mlx
export LLAMA_CPP_API_KEY='...'     # optional, used when provider: llama-cpp
```

### CodeSeeq provider

`provider: codeseeq` keeps QonQrete on its existing `worqer/lib_ai.py` abstraction. QonQrete flattens the agent request and invokes the CodeSeeq CLI; CodeSeeq owns the Responses-to-DeepSeek bridge.

QonQrete-level tool calls are not passed through this provider. ConstruQtor uses heredoc/fenced-block transport for `codeseeq` even if the default coding mode is `hybrid`.

The Sqrewdriver repair controller is independent of CodeSeeq hooks. CodeSeeq can be used for ConstruQtor, but the inspection-to-repair loop remains QonQrete-native and artifact-driven.

Supported CodeSeeq models:

- `deepseek-v4-flash`
- `deepseek-v4-flash-thinking`
- `deepseek-v4-pro`
- `deepseek-v4-pro-thinking`

The default QonQrete container does not mount sibling `./codeseeq` or include local Codex/CodeSeeq tooling. For host-mode testing:

```bash
export CONTAINER_ENGINE=none
export QONQ_UNSAFE_HOST_MODE=1
export QONQ_CODESEEQ_BIN="$PWD/codeseeq/codeseeq"
```

## System requirements

### Container engine
QonQrete auto-detects container runtime support.

Supported runtime paths in the current repo:
- Podman (default auto-detected path)
- Docker (explicit via `--docker` or `CONTAINER_ENGINE=docker`)
- Repo-native host mode (`CONTAINER_ENGINE=none`, and auto fallback when Podman is unavailable)

### Tested platform notes from the repo/docs
- Linux + Docker / Docker Desktop
- macOS + Docker Desktop / Podman
- Windows 11 + WSL2 + Docker Desktop
- Git Bash / MSYS support exists, but WSL2 is still the cleaner Windows experience

## Quickstart

### 1. Initialize the Qage image

```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

Optional engine forcing:

```bash
./qonqrete.sh init --docker
./qonqrete.sh init --podman
```

### 2. Write your task

Edit:

```text
tasq.md
```

### 3. Run

```bash
./qonqrete.sh tasq.md
```

Useful variants:

```bash
./qonqrete.sh run -f tasq.md
./qonqrete.sh run --auto
./qonqrete.sh run --user
./qonqrete.sh run -a -n myproject
./qonqrete.sh run --mode security --briq-sensitivity 6 --cyqles 3   # 3 total iterations max
./qonqrete.sh run -B --cyqles 3                       # force auto briq sensitivity, 3 total iterations max
./qonqrete.sh status
./qonqrete.sh audit
```

### 4. Resume

```bash
./qonqrete.sh resume
./qonqrete.sh resume -q qage_YYYYMMDD_HHMMSS
```

If the source run ended in intake clarification waiting (`BLOCKED` / `RUN_WAITING_FOR_INPUT`), resume re-enters cycle-1 clarification semantics instead of skipping cycle-1-only intake stages.

### 5. Clean

```bash
./qonqrete.sh clean
./qonqrete.sh clean -q qage_YYYYMMDD_HHMMSS
./qonqrete.sh clean -A
```

## IDE integrations

### VS Code extension
Location: `vscode-extension/`

Main capabilities in this repo snapshot:
- run canonical `worqspace/tasq.md`
- run any Markdown file as a temporary tasq
- sidebar control panel
- status bar state reporting
- init / run / resume / clean commands
- qage browsing

Manual build/package:

```bash
cd vscode-extension
npm install
npm run compile
npx vsce package
```

### IntelliJ / JetBrains plugin
Location: `intellij-plugin/`

Main capabilities in this repo snapshot:
- tool window with run controls
- settings/config UI
- run, resume, clean, and qage browsing actions
- status widget / shell verification concepts

Manual build/package:

```bash
cd intellij-plugin
./gradlew buildPlugin
```

## Important current-state note

As shipped in this repository, QonQrete is still fundamentally a **repo-local workflow**:
- the core runtime expects `qonqrete.sh` and `worqspace/` in the project
- the bundled IDE integrations are built around that repo-local model
- a fully centralized “single engine outside all projects” bootstrap flow is **not** implemented in this repository snapshot

## CLI reference

```text
Usage: ./qonqrete.sh [COMMAND] [OPTIONS]
       ./qonqrete.sh <task-file.md> [OPTIONS]

Commands:
  init
  run
  resume
  status
  audit
  clean
  clean-outputs

Run options:
  -f, --task-file <path>
  -a, --auto
  -u, --user
  -m, --mode <name>
  -b, --briq-sensitivity <N>
  -B, --auto-briq-sensitivity
  -c, --cyqles <N>
  -n, --qonstruction-name <name>
  --seed-repo
  -s, --sqrapyard     (legacy alias for --seed-repo)
  -N, --no-sync       (skip repo-root sync-back; keep qage/qonstruction output)
  -d, --docker
  -p, --podman
  -q, --qage <name>   (resume/status/audit/clean target)
  -A, --all           (clean all qages)
```

## Documentation map

- [QUICKSTART.md](./doc/QUICKSTART.md) — shortest path to first run
- [DOCUMENTATION.md](./doc/DOCUMENTATION.md) — full technical reference
- [ARCHITECTURE.md](./doc/ARCHITECTURE.md) — architecture and pipeline layout
- [RELEASE-NOTES.md](./doc/RELEASE-NOTES.md) — version history and notable changes
- [TERMINOLOGY.md](./doc/TERMINOLOGY.md) — QonQrete vocabulary

## Current limitations / honesty section

- The bundled IDE integrations are present and usable, but official store publishing is a separate distribution step.
- The repo snapshot now includes `qonqrete-bootstrap.sh` (git-clone users) and `qonqrete-install.sh` (website curl-bash) for central per-user engine installation.
- The committed `worqspace/config.yaml` is a working configuration example, not a promise that every default value is ideal for every task.
- The active runtime surface is the standard CLI plus IDE wrappers.
- Qontrabender only becomes relevant when the active ConstruQtor provider is Gemini.

## License

QonQrete is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See [LICENSE](LICENSE).
