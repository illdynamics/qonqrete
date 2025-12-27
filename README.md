# QonQrete - Secure AI Construction Loop System
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Repo Views](https://komarev.com/ghpvc/?username=illdynamics-qonqrete&label=Repo+Views&color=blue)

![Splash](qrane/splash.jpg)


QonQrete is a Secure AI Construction Loop System, using a Multi-Agent Pipeline Orchestrator in a Sandbox environment with YAML Configuration. In short: it spawns 3 AI agents in a sandbox/container and makes them work together on tasks. It can run with a hard requirement for user approval between steps, or in a fully autonomous mode where it keeps running until the user decides to stop it.

QonQrete is a multi-agent orchestration system designed for secure, observable, and human-in-the-loop software construction. It operates on the principle of a secure build environment (`Qage`), managed by a host-level orchestrator (`Qrane`).

This architecture ensures that AI-generated code and processes cannot affect the host system, providing a robust framework for autonomous and semi-autonomous development.

## Version

**Version:** `v1.0.0-stable` (See `VERSION` file for the canonical version).

> **Note on Experimental Features:**
>
> The following features are marked as **[EXPERIMENTAL]** and may have bugs:
> - **TUI Mode** (`-t/--tui`): Text-based User Interface
> - **Microsandbox** (`-M/--msb`): Alternative to Docker runtime
>
> We welcome community contributions! If you encounter any issues or have suggestions, please report them.

---

## What's New in v1.0.0 🎉

### 🚨 PRODUCTION RELEASE - ENFORCED BRIQ SENSITIVITY

The first stable production release! This fixes the critical briq sensitivity inconsistency bug.

**The Problem:** `briq_sensitivity` was just a "hint" to the AI, resulting in wildly inconsistent outputs (1-10 briqs with same setting).

**The Fix:** Briq counts are now **ENFORCED** with hard min/max ranges:
- Too few briqs → System retries with stronger prompt
- Too many briqs → System merges briqs automatically

### 📊 NEW BRIQ SENSITIVITY SCALE

| Level | Name | Briq Range | Use Case |
|-------|------|------------|----------|
| **9** | Monolithic | 1 | Single-file scripts |
| **8** | Very Broad | 2-3 | Backend/Frontend split |
| **7** | Broad | 3-5 | **RECOMMENDED DEFAULT** |
| **6** | Feature | 5-8 | Feature-level decomposition |
| **5** | Component | 8-12 | Component-level |
| **4** | Balanced | 10-15 | Medium complexity |
| **3** | Standard | 15-20 | Standard granularity |
| **2** | High Gran. | 20-30 | High granularity |
| **1** | Very High | 30-40 | Very fine-grained |
| **0** | Atomic | 40-60 | Maximum decomposition |

### 🎯 RECOMMENDED CONFIGURATIONS

| Project Type | Sensitivity | Cycles | Expected Result |
|--------------|-------------|--------|-----------------|
| **Simple** (API, web server) | 7 | 4 | B+ to A- grade |
| **Medium** (full-stack app) | 6 | 5 | B to B+ grade |
| **Complex** (multi-service) | 5 | 6 | Comprehensive coverage |

### ⚙️ New Defaults

| Setting | Old | New |
|---------|-----|-----|
| `briq_sensitivity` | 8 | **7** |
| `auto_cycle_limit` | 2 | **4** |

---

## What's New in v0.9.9-stable

### 🎨 Cleaner Console Output

Less noise, more signal:

| Component | Change |
|-----------|--------|
| **TasqLeveler** | Only `[TasqLeveler]` status lines shown |
| **InspeQtor** | Only final assessment displayed |
| **Table dividers** | Hidden from output |
| **pycg warnings** | Removed (package broken, using jedi instead) |

---

## What's New in v0.9.8-stable

### 🐛 Critical Bug Fixes

Two critical bugs discovered during multi-cycle builds:

| Issue | Fix |
|-------|-----|
| **Skeleton overwrites code** | ConstruQtor now detects and skips Qompressor skeleton markers |
| **Exit code 1 after inspeqtor** | Removed duplicate loqal_verifier from pipeline |

### 🔧 Technical Details

The skeleton bug occurred when AI copied `bloq.d/` skeletons from context back to `qodeyard/`, overwriting working code with broken `# ... (body stripped by Qompressor) ...` stubs.

---

## What's New in v0.9.7-stable

### 🔧 Reliability Fixes

Fixes discovered during real-world multi-cycle builds:

| Issue | Fix |
|-------|-----|
| **Cache write errors** | Added `--tmpfs /home/qrane/.cache:rw,size=500m` for model caching |
| **PATH issues** | Added `ENV PATH="/usr/local/bin:${PATH}"` to Dockerfile |

### 📦 Default Configuration Updates

| Setting | New Default | Previous |
|---------|-------------|----------|
| `briq_sensitivity` | 6 (fine-grained) | 3 |
| `auto_cycle_limit` | 3 cycles | 7 |

### 🗂️ Ignore File Updates

- Added `worqspace/qonstructions/*` to `.gitignore` and `.dockerignore`
- Qonstructions are now excluded from version control (user-specific outputs)

---

## What's New in v0.9.6-stable

### 🔄 Resume & Qonstructions - Persistent Project Workflow

No more losing your work! QonQrete now supports resuming from previous runs and saving projects permanently.

| Feature | Command | Description |
|---------|---------|-------------|
| **Resume (Interactive)** | `./qonqrete.sh resume` | kubectx-style picker for previous Qages |
| **Resume (Direct)** | `./qonqrete.sh resume -q qage_20251226` | Resume specific Qage |
| **Qonstructions** | Auto-prompt after run | Save completed runs to `qonstructions/` |
| **Clean (Interactive)** | `./qonqrete.sh clean` | Pick which Qage to delete |
| **Clean (Specific)** | `./qonqrete.sh clean -q qage_20251226` | Delete specific Qage |
| **Clean (All)** | `./qonqrete.sh clean -A` | Delete all Qages |

### 🛡️ Security Hardening

QonQrete implements defense-in-depth security:

#### Container Security
| Feature | Protection |
|---------|------------|
| **Non-root execution** | `gosu` drops to `qrane` user after permission fix |
| **Read-only filesystem** | Container root is read-only |
| **Capability dropping** | `--cap-drop=ALL` then adds only required caps |
| **Resource limits** | Memory (4GB), CPU (2 cores), PIDs (100) |
| **Secure /tmp** | `--tmpfs /tmp:rw,noexec,nosuid,size=100m` |
| **Writable cache** | `--tmpfs /home/qrane/.cache:rw,size=500m` |

**Required Capabilities:** SETUID, SETGID, CHOWN, FOWNER, DAC_OVERRIDE

#### Code Security
| Feature | Protection |
|---------|------------|
| **Path jail enforcement** | All file ops validated against `/qonq` |
| **Symlink protection** | Paths resolved before validation |
| **API timeouts** | 5-minute timeout on all AI calls |
| **Retry limits** | Hard cap of 10 retries |
| **Size limits** | tasq.md: 100KB, generated files: 1MB |
| **Config validation** | JSON Schema validation for config.yaml |

#### Dependency Security
| Feature | Protection |
|---------|------------|
| **Pinned base image** | Ubuntu with SHA256 digest |
| **Pinned packages** | `requirements.txt` with exact versions |
| **Minimal install** | `--no-install-recommends` |

### 🚀 Explicit Sqrapyard Control

Sqrapyard seeding is now **opt-in** to prevent accidental imports:

```bash
# Fresh start (default) - ignores sqrapyard
./qonqrete.sh run

# Seed from sqrapyard
./qonqrete.sh run -s
./qonqrete.sh run --sqrapyard
```

### ✏️ Interactive TasQ Editor

No `tasq.md`? No problem! QonQrete opens your `$EDITOR` automatically:

```bash
./qonqrete.sh run
# -> Opens vim/nano/code with template
# -> Write your task, save, run!
```

### 🏷️ Flag Changes

| Old Flag | New Flag | Purpose |
|----------|----------|---------|
| `-s/--msb` | `-M/--msb` | Microsandbox mode |
| (none) | `-s/--sqrapyard` | Seed from sqrapyard |

---

## What's New in v0.9.0-stable

### 🚀 TasqLeveler - Automatic Tasq Enhancement

A new agent that supercharges your tasq.md automatically on Cycle 1:

| Enhancement | Impact |
|-------------|--------|
| 📦 Dependency Graph | Prevents circular imports |
| 🎯 Golden Path Tests | Defines success explicitly |
| 🧪 Mock Infrastructure | Test without real services |
| 📋 Success Criteria | Clear pass/fail |
| ⏱️ Phase Priority | Better token allocation |

**+15-20% improvement in output quality!**

```yaml
# config.yaml - TasqLeveler uses instruqtor's config by default
agents:
  tasqleveler:
    provider: openai
    model: gpt-4.1-mini
```

### 🔧 Universal File Rule (s00permode)

One simple rule for ALL cycles:
- 📁 File EXISTS? → MODIFY/EXTEND it (never recreate)
- 📄 File MISSING? → CREATE it (new modules welcome!)

No more rebuild-from-scratch bugs on multi-cycle builds!

---

## What's New in v0.8.0-stable

### 🌀 Qontrabender - The Cache Bender

A new policy-driven hybrid caching agent with Variable Fidelity:

- **Policy-Based Configuration**: All behavior controlled via `caching_policy.yaml`
- **6 Operational Modes**: `local_fast`, `local_smart`, `cyber_bedrock`, `cyber_aggressive`, `paranoid_mincloud`, `debug_repro`
- **Variable Fidelity**: Intelligently mixes full code (MEAT) + skeletons (BONES)
- **Schema Validation**: Bad YAML can't brick your flow
- **Improved Volatile Detection**: Cycle-based, diff-based, git diff, mtime fallback

```yaml
# Select mode in config.yaml
agents:
  qontrabender:
    policy_file: "./caching_policy.yaml"
    mode: "local_smart"
```

See [QONTRABENDER.md](./doc/QONTRABENDER.md) for full documentation.

---

## The Triple-Core Memory System

QonQrete now features a **Triple-Core Memory System**:

| Agent | Role | Output |
|-------|------|--------|
| **Qompressor** | Skeletonizer | `bloq.d/` - AST-stripped code structures |
| **Qontextor** | Symbol Mapper | `qontext.d/` - Semantic YAML maps |
| **Qontrabender** | Cache Bender | `qache.d/` - Policy-driven cache payloads |

### The Data Lake Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DATA LAKE (Local)                                │
│                                                                         │
│   qodeyard/ (MEAT)           bloq.d/ (BONES)        qontext.d/ (SOUL)   │
│   Full source code           AST skeletons          Semantic maps       │
│                                                                         │
│             │                        │                      │           │
│             └───────────┬────────────┴──────────────────────┘           │
│                         ▼                                               │
│              ┌───────────────────────┐                                  │
│              │    QONTRABENDER       │ ← Policy-driven compositor       │
│              │   caching_policy.yaml │                                  │
│              └──────────┬────────────┘                                  │
│                         ▼                                               │
│                   qache.d/ (Cache Ledger)                               │
│                   └─ Variable fidelity payloads                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Performance Metrics

**Scenario:** Medium-sized project (50 files, ~10,000 lines of code)

| Metric | Old Approach | Triple-Core | Improvement |
|--------|--------------|-------------|-------------|
| **Context Sent** | 100,000 Tokens | ~4,000 Tokens | **96% Reduction** |
| **Indexing Cost** | High (AI-based) | **Zero** (Local) | **∞ Cheaper** |
| **Cost per Run** | ~$0.25 (GPT-4o) | ~$0.01 (GPT-4o) | **25x Cheaper** |
| **Cache Reuse** | None | Hash-based dedup | **Near-zero churn** |

---

## Core Principles

1.  **Isolation by Design**: All agent execution occurs within the `Qage`, a Docker container that acts as a secure sandbox.
2.  **Configuration-Driven**: Agent models, modes, and policies defined in YAML.
3.  **File-Based Communication**: Agents communicate via markdown files, creating transparent audit trails.
4.  **Human-in-the-Loop Control**: CheQpoints pause for user review. Can be configured for autonomous mode.
5.  **Local Sovereignty**: Keep intelligence local with policy-driven caching.

---

## Architecture Overview

-   `qrane/`: The **Qrane** orchestrator and CLI
-   `worqer/`: AI agent scripts (`tasqLeveler`, `instruQtor`, `construQtor`, `inspeQtor`, `qompressor`, `qontextor`, `qontrabender`)
-   `worqspace/`: Shared data plane with configuration and generated artifacts
    - `qonstructions/`: Saved project outputs (NEW in v0.9.1)
    - `sqrapyard/`: Input seed code for projects

---

## The Workflow CyQle

1.  **Enhance (`tasqLeveler`)**: *Cycle 1 only* - Supercharges tasq with golden paths and mocks
2.  **Plan (`instruQtor`)**: Reads the `tasQ` and creates `briQ` files with detailed plans
3.  **Execute (`construQtor`)**: Processes each `briQ` and generates code in `qodeyard/`
4.  **Review (`inspeQtor`)**: Reviews generated code and produces `reQap` with assessment
5.  **CheQpoint (`gateQeeper`)**: Pauses for user command to proceed

---

## System Requirements

### Docker (Required)

-   **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
-   **Linux**: `sudo apt-get install docker-ce docker-ce-cli containerd.io`
-   **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)

> **Docker Desktop Users:** Grant Docker permission to access the project directory via **Settings > Resources > File Sharing**.

### Microsandbox (Optional) [EXPERIMENTAL]

Lightweight alternative to Docker. See [Microsandbox repository](https://github.com/a-i-s-r/microsandbox).

---

## Getting Started

See **[QUICKSTART.md](./doc/QUICKSTART.md)** for the full guide.

### API Keys

Export keys for your AI providers:

```bash
export OPENAI_API_KEY='your-key'
export GOOGLE_API_KEY='your-key'
export ANTHROPIC_API_KEY='your-key'
export DEEPSEEK_API_KEY='your-key'
```

### Initialize

```bash
./qonqrete.sh init
```

### Run

```bash
# Fresh start (default)
./qonqrete.sh run

# With sqrapyard seeding
./qonqrete.sh run -s

# With TUI [EXPERIMENTAL]
./qonqrete.sh run --tui --mode security

# Autonomous mode
./qonqrete.sh run --auto --briq-sensitivity 2

# User-gated mode
./qonqrete.sh run --user
```

### Resume

```bash
# Interactive picker
./qonqrete.sh resume

# Specific Qage
./qonqrete.sh resume -q qage_20251226_115701
```

### Clean

```bash
# Interactive picker
./qonqrete.sh clean

# Specific Qage
./qonqrete.sh clean -q qage_20251226_115701

# All Qages
./qonqrete.sh clean -A
```

---

## Configuration

### config.yaml

```yaml
agents:
  tasqleveler:
    provider: openai
    model: gpt-4.1-mini  # Runs once on Cycle 1
    
  instruqtor:
    provider: openai
    model: gpt-4.1-mini

  construqtor:
    provider: gemini
    model: gemini-2.5-pro

  inspeqtor:
    provider: openai
    model: gpt-4.1

  qontextor:
    provider: local
    model: qontextor
    local_mode: complex

  qompressor:
    provider: local
    model: qompressor

  qontrabender:
    provider: local
    model: qontrabender
    policy_file: "./caching_policy.yaml"
    mode: local_smart

options:
  use_qompressor: true
  use_qontextor: true
  use_qontrabender: true
  cheqpoint: false
  auto_cycle_limit: 4      # Recommended: 4 for simple, 5-6 for complex
  briq_sensitivity: 7      # Recommended: 7 for simple, 5-6 for complex
```

### Qontrabender Modes

| Mode | Description |
|------|-------------|
| `local_fast` | Ultra-fast, skeleton only |
| `local_smart` | Variable fidelity, balanced (default) |
| `cyber_bedrock` | Remote cache for stable bedrock |
| `cyber_aggressive` | Aggressive remote caching |
| `paranoid_mincloud` | Minimal cloud exposure |
| `debug_repro` | Maximum audit logging |

---

## CLI Reference

```
Usage: ./qonqrete.sh [COMMAND] [OPTIONS]

Commands:
  init              Build the Qage container image.
  run               Start fresh QonQrete session.
  resume            Resume from a previous Qage.
  clean             Remove Qage directories.

Global Options:
  -h, --help        Show help message.
  -V, --version     Show version information.

Run Options:
  -a, --auto                   Enable Autonomous Mode.
  -u, --user                   Force User-gated Mode.
  -t, --tui                    Enable TUI Mode. [EXPERIMENTAL]
  -m, --mode <n>               Set Operational Mode.
  -b, --briq-sensitivity <N>   Set Granularity (0-9). Default: 7
  -c, --cyqles <N>             Set max auto-cycles (1-10). Default: 4
  -s, --sqrapyard              Seed from sqrapyard/ directory.
  -M, --msb                    Force Microsandbox. [EXPERIMENTAL]
  -d, --docker                 Force Docker.

Resume Options:
  -q, --qage <n>               Resume from specific Qage.
  (no args)                    Interactive selection.

Clean Options:
  -q, --qage <n>               Clean specific Qage.
  -A, --all                    Clean ALL Qages.
  (no args)                    Interactive selection.
```

---

## Documentation

- [QUICKSTART.md](./doc/QUICKSTART.md) - Getting started guide
- [DOCUMENTATION.md](./doc/DOCUMENTATION.md) - Full system documentation
- [QONTRABENDER.md](./doc/QONTRABENDER.md) - Cache bender documentation
- [RELEASE-NOTES.md](./doc/RELEASE-NOTES.md) - Version history
- [TERMINOLOGY.md](./doc/TERMINOLOGY.md) - QonQrete terminology
- [TESTS_v1.0.0.md](./doc/TESTS_v1.0.0.md) - Configuration A/B testing results

---

## License

QonQrete is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See the [LICENSE](LICENSE) file for full text.

![Scarf](https://static.scarf.sh/a.png?x-pxid=242de794-2b10-4e34-a6cd-eab9e46cc793)
