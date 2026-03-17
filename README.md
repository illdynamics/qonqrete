# QonQrete - The First 100% File-Based Local-First Secure Agentic AI System
![Release](https://img.shields.io/github/v/release/illdynamics/qonqrete)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

> **v1.2.0-stable** — Workspace Deployment & Hassle-Free Bootstrap

QonQrete is a deterministic AI coding agent that builds software inside hardened containers. It takes a high-level task, decomposes it into briqs, generates code, reviews the result, and optionally continues into more cycles — all locally, all file-based, all yours.

## Quick Start (IDE)

### VS Code
1. Install **QonQrete** from the VS Code Marketplace
2. `Ctrl+Shift+P` → **QonQrete: Deploy to Workspace**
3. `Ctrl+Shift+P` → **QonQrete: Create tasq.md** — describe what to build
4. `Ctrl+Shift+P` → **QonQrete: Run Tasq** — auto-init on first run

### IntelliJ / JetBrains
1. Install **QonQrete** from the JetBrains Marketplace
2. `Ctrl+Shift+A` → **QonQrete: Deploy to Workspace**
3. `Ctrl+Shift+A` → **QonQrete: Create tasq.md**
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

```bash
# Prerequisites: Docker or Podman + AI API key(s)
export OPENAI_API_KEY='...'

# Build the runtime
chmod +x qonqrete.sh
./qonqrete.sh init

# Edit your task
vim worqspace/tasq.md

# Run
./qonqrete.sh run
./qonqrete.sh run --auto --mode security -b 6 -c 3
```

## How It Works

```
User defines tasq.md
  → TasqLeveler enhances the task (cycle 1)
  → InstruQtor decomposes into briqs + generates QONTRACT
  → CalQulator estimates cost
  → ConstruQtor generates/modifies code in qodeyard/
  → InspeQtor reviews and produces reqap
  → Qontextor indexes context
  → Qompressor creates skeletons
  → Repeat for N cycles
```

All execution happens inside a **hardened container** with:
- Read-only root filesystem
- Dropped capabilities
- Resource limits (memory, CPU, PIDs)
- Non-root runtime

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
| Qwen | `QWEN_API_KEY` |

## Container Engines

- **Docker** (default, auto-detected)
- **Podman** (auto-detected, macOS machine management included)
- **MicroSandbox** (experimental)

## CLI Reference

```bash
./qonqrete.sh init                           # Build container image
./qonqrete.sh run                            # Fresh run
./qonqrete.sh run --auto                     # Autonomous mode
./qonqrete.sh run -b 6 -c 3                  # Sensitivity 6, 3 cycles
./qonqrete.sh run --mode security            # Security-focused mode
./qonqrete.sh run -a -n myproject            # Auto + save as qonstruction
./qonqrete.sh run -s                         # Seed from sqrapyard
./qonqrete.sh resume                         # Resume from previous qage
./qonqrete.sh clean                          # Interactive qage cleanup
./qonqrete.sh clean -A                       # Delete all qages
```

## IDE Commands (v1.2.0)

Both VS Code and IntelliJ support identical commands:

| Command | Description |
|---------|-------------|
| **Deploy to Workspace** | Install runtime into `.qonqrete/` |
| **Create tasq.md** | Create starter template at project root |
| **Configure Run** | Set sensitivity, cycles, mode, engine |
| **Run Tasq** | Sync tasq → auto-init → execute |
| **Run as QonQrete Tasq** | Run any markdown as temp tasq |
| **Resume Run** | Continue from previous qage |
| **Clean Qages** | Delete old qage directories |
| **Init Workspace** | Manually build container image |
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

## Documentation

- [Quickstart](doc/QUICKSTART.md)
- [Architecture](doc/ARCHITECTURE.md)
- [Documentation](doc/DOCUMENTATION.md)
- [Terminology](doc/TERMINOLOGY.md)
- [Release Notes](doc/RELEASE-NOTES.md)

## Project

- **Website:** [qonqrete.sh](https://qonqrete.sh)
- **Author:** [Ill Dynamics](https://illdynamics.com) / WoNQ
- **License:** [AGPL-3.0](LICENSE)

## v1.2.0 Highlights

- **One-click workspace deployment** from both IDEs
- **Auto-init** builds container image on first run
- **Root tasq.md** at workspace root (synced to runtime automatically)
- **Versioned container images** (`qonqrete-qage:1.2.0`)
- **Identical behavior** in VS Code and IntelliJ
- No manual cloning, no manual init, no command line required
