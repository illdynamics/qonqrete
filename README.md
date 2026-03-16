# QonQrete - The First 100% File-Based Local-First Secure Agentic AI System
![Release](https://img.shields.io/github/v/release/illdynamics/qonqrete)
[![Build VS Code Extension](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml)
[![Build IntelliJ Plugin](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Repo Views](https://komarev.com/ghpvc/?username=illdynamics-qonqrete&label=Repo+Views&color=blue)

![QonQrete](qonqrete.jpg)

QonQrete is a **local-first, file-based AI software construction system** that runs a structured multi-agent build loop inside a hardened container. It plans work into briqs, generates code in a Qage, reviews the result, and iterates with either **user-gated cheQpoints** or **fully autonomous cycles**.

## Version

**Current repository version:** `v1.1.9-stable`  
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

## What changed between `v1.0.4-stable` and `v1.1.9-stable`

### Core platform
- container runtime auto-detection for Docker / Podman / MSB
- enforced contract workflow via `qontract.d/`
- stricter deterministic run behavior and anti-drift hardening
- resume / clean / qonstruction workflow
- sqrapyard seeding as an explicit opt-in flow
- QONTRACT fail-fast enforcement on later cycles

### VS Code integration
- full VS Code extension with commands, sidebar, status bar, config UI, resume and clean flows
- shell detection / verification and honest run-state handling
- run `worqspace/tasq.md` directly from the IDE
- run any Markdown file temporarily as a QonQrete tasq
- qage browsing and manual packaging as `.vsix`

### IntelliJ / JetBrains integration
- IntelliJ plugin project with tool window, actions, settings, status widget, qage browser, and run controls
- manual packaging flow via Gradle
- local/manual installation path for JetBrains IDEs

## Core principles

- **Isolation by design** — AI execution happens in a Qage container, not directly on the host.
- **File-based communication** — tasqs, briqs, reviews, skeletons, contracts, and logs are visible on disk.
- **Structured iteration** — QonQrete works in cyQles with planning, build, review, and checkpoint phases.
- **Human control when wanted** — autonomous mode exists, but user-gated cheQpoints remain first-class.
- **Local-first supporting stack** — several helper agents run fully locally with zero AI-token cost.

## Architecture in one glance

- **`qonqrete.sh`** — host entrypoint and runtime bootstrap
- **`qrane/`** — orchestrator, TUI, path handling, cost helpers
- **`worqer/`** — agent scripts and security/provider utilities
- **`worqspace/`** — config, task input, sqrapyard, qages, qonstructions
- **`vscode-extension/`** — VS Code integration
- **`intellij-plugin/`** — JetBrains integration

## Main workflow

1. **Enhance** — `tasqleveler` (optional, cycle 1 only)
2. **Plan** — `instruqtor` creates briqs and contract files
3. **Estimate** — `calqulator` estimates token/cost usage
4. **Build** — `construqtor` generates and updates code in `qodeyard/`
5. **Review** — `inspeqtor` validates and reviews results
6. **Index / compress** — `qontextor` and `qompressor` refresh context artifacts
7. **Checkpoint** — continue, tweaQ, or quit

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
│   ├── sqrapyard/
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
- Qwen
- `local` for non-remote helper agents

Required environment variables depend on your selected providers:

```bash
export OPENAI_API_KEY='...'
export GOOGLE_API_KEY='...'        # or GEMINI_API_KEY
export ANTHROPIC_API_KEY='...'
export DEEPSEEK_API_KEY='...'
export QWEN_API_KEY='...'
```

## System requirements

### Container engine
QonQrete auto-detects container runtime support.

Supported runtime paths in the current repo:
- Docker
- Podman
- Microsandbox / MSB (**experimental**)

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
worqspace/tasq.md
```

### 3. Run

```bash
./qonqrete.sh run
```

Useful variants:

```bash
./qonqrete.sh run --auto
./qonqrete.sh run --user
./qonqrete.sh run -s
./qonqrete.sh run -a -n myproject
./qonqrete.sh run --mode security --briq-sensitivity 6 --cyqles 3
```

### 4. Resume

```bash
./qonqrete.sh resume
./qonqrete.sh resume -q qage_YYYYMMDD_HHMMSS
```

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

Commands:
  init
  run
  resume
  clean

Run options:
  -a, --auto
  -u, --user
  -t, --tui
  -m, --mode <name>
  -b, --briq-sensitivity <0-16>
  -c, --cyqles <1-50>
  -n, --qonstruction-name <name>
  -s, --sqrapyard
  -M, --msb
  -d, --docker
  -p, --podman
  -w, --wonqrete
```

## Documentation map

- [QUICKSTART.md](./doc/QUICKSTART.md) — shortest path to first run
- [DOCUMENTATION.md](./doc/DOCUMENTATION.md) — full technical reference
- [ARCHITECTURE.md](./doc/ARCHITECTURE.md) — architecture and pipeline layout
- [RELEASE-NOTES.md](./doc/RELEASE-NOTES.md) — version history and notable changes
- [TERMINOLOGY.md](./doc/TERMINOLOGY.md) — QonQrete vocabulary

## Current limitations / honesty section

- The bundled IDE integrations are present and usable, but official store publishing is a separate distribution step.
- The repo snapshot does **not** implement a central per-user QonQrete engine installer / bootstrap flow.
- The committed `worqspace/config.yaml` is a working configuration example, not a promise that every default value is ideal for every task.
- `TUI` and `MSB` remain experimental paths.
- Qontrabender only becomes relevant when the active ConstruQtor provider is Gemini.

## License

QonQrete is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See [LICENSE](LICENSE).
