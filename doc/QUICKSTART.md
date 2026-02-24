# QonQrete Quickstart Guide

**Version:** `v1.0.4-stable` (See `VERSION` file for the canonical version).

Get up and running with QonQrete in minutes. The system automatically detects your OS, container engine (Docker/Podman), and build backend — so there's one unified workflow for all platforms.

## Prerequisites

- **Container Engine:** Docker or Podman installed and running.
  - **macOS + Podman:** QonQrete auto-initializes and starts the Podman machine for you.
  - **Windows:** WSL2 with Docker Desktop recommended. Git Bash works but WSL2 is preferred.
- **API Keys:** Export keys for the AI providers configured in `worqspace/config.yaml`:
  ```bash
  export OPENAI_API_KEY='your-key'
  export DEEPSEEK_API_KEY='your-key'
  # Optional depending on config:
  export GOOGLE_API_KEY='your-key'     # or GEMINI_API_KEY
  export ANTHROPIC_API_KEY='your-key'
  export QWEN_API_KEY='your-key'
  ```
  The system checks for required keys at startup and tells you exactly which ones are missing.

## 1. Build the Qage

One-time setup. QonQrete auto-detects Docker vs Podman and buildx vs plain build:

```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

You can force a specific engine if needed:
```bash
./qonqrete.sh init --docker    # Force Docker
./qonqrete.sh init --podman    # Force Podman
```

## 2. Define Your TasQ

Edit `worqspace/tasq.md` with your project objective:

```markdown
Create a Python FastAPI server with CRUD endpoints for a todo list.
Use SQLite for storage. Include proper error handling and input validation.
```

If no `tasq.md` exists, QonQrete opens your `$EDITOR` (default: vim) with a template.

## 3. Run a CyQle

```bash
# Basic fresh start (auto-detects everything)
./qonqrete.sh run

# Autonomous mode with custom settings
./qonqrete.sh run --auto --briq-sensitivity 6 --cyqles 3

# With sqrapyard seeding (existing code)
./qonqrete.sh run -s

# Force user-gated mode
./qonqrete.sh run --user

# Auto-save result without prompts
./qonqrete.sh run -a -n myproject
```

At the CheQpoint, you'll be prompted: `[Q]ontinue`, `[T]weaQ` (edit), or `[X]Quit`.

## 4. Saving Your Work

After each run, QonQrete asks if you want to save the result as a Qonstruction:

```
┌─────────────────────────────────────────────────────────────┐
│           QonQrete Session Complete                         │
└─────────────────────────────────────────────────────────────┘

Save this run as a Qonstruction? [y/N] y
Enter project name [project_20260223_115701]: my-api
Qonstruction saved successfully!
```

Qonstructions are stored in `worqspace/qonstructions/<name>/` with full context preserved.

For automated pipelines, use the `-n` flag:
```bash
./qonqrete.sh run -a -b 6 -c 3 -n myproject
```

## 5. Resuming Previous Work

```bash
# Interactive picker (kubectx-style, newest first)
./qonqrete.sh resume

# Direct selection
./qonqrete.sh resume -q qage_20260223_115701
```

Resume copies all state from the selected Qage, updates configs from the workspace, and uses your latest `tasq.md` as the next cycle's task.

## 6. Seeding with Sqrapyard

To start from an existing codebase:

1. Place your code in `worqspace/sqrapyard/`
2. Edit `worqspace/tasq.md` with your objective
3. Run with the `-s` flag: `./qonqrete.sh run -s`

Without `-s`, sqrapyard contents are ignored (prevents accidental imports).

## 7. Configuration

### `worqspace/config.yaml`

| Setting | Description | Default |
|---------|-------------|---------|
| `agents.<name>.provider` | AI provider per agent (`openai`, `deepseek`, `gemini`, `anthropic`, `qwen`, `local`) | varies |
| `agents.<name>.model` | Model name per agent | varies |
| `options.cheqpoint` | `true` = user-gated, `false` = autonomous | `false` |
| `options.auto_cycle_limit` | Max cycles in auto-mode (1-50) | `4` |
| `options.briq_sensitivity` | Granularity (0-16). Higher = more briqs. | `5` recommended |
| `options.mode` | Operational mode (`program`, `enterprise`, `security`, etc.) | `program` |
| `options.use_qompressor` | Enable skeleton generation | `true` |
| `options.use_qontextor` | Enable semantic indexing | `true` |
| `options.use_qontrabender` | Enable hybrid caching (Gemini only) | `false` |
| `retry.max_attempts` | Max attempts per briq | `3` |
| `retry.stop_on_briq_fail` | Fail-fast vs fail-tolerant | `false` |
| `interleaved.enabled` | Per-briq build+verify loop | `true` |
| `interleaved.local_validation` | Local syntax check per briq | `true` |

### `worqspace/pipeline_config.yaml`

Defines the agent execution order. The default pipeline is:

```
instruqtor → calqulator → construqtor → inspeqtor → qontextor → qompressor
```

TasqLeveler is available but commented out by default. To enable, uncomment its block.

### Environment Overrides

```bash
CONTAINER_ENGINE=docker|podman   # Override engine auto-detection
BUILD_BACKEND=buildx|plain       # Override build backend auto-detection
```

## 8. Cleaning Up

```bash
# Interactive selection (pick which Qage to delete)
./qonqrete.sh clean

# Delete specific Qage
./qonqrete.sh clean -q qage_20260223_115701

# Delete ALL Qages
./qonqrete.sh clean -A
```

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `./qonqrete.sh init` | Build the Qage container |
| `./qonqrete.sh run` | Start fresh session |
| `./qonqrete.sh run -s` | Start with sqrapyard seeding |
| `./qonqrete.sh run -a` | Autonomous mode |
| `./qonqrete.sh run -a -n <name>` | Auto-save as Qonstruction |
| `./qonqrete.sh resume` | Interactive resume picker |
| `./qonqrete.sh resume -q <qage>` | Resume specific Qage |
| `./qonqrete.sh clean` | Interactive delete picker |
| `./qonqrete.sh clean -A` | Delete ALL Qages |

## Flags Reference

| Flag | Description |
|------|-------------|
| `-a, --auto` | Autonomous mode (no cheqpoints) |
| `-u, --user` | User-gated mode (force cheqpoints) |
| `-t, --tui` | TUI mode **[EXPERIMENTAL]** |
| `-m, --mode <name>` | Operational mode |
| `-b, --briq-sensitivity <N>` | Granularity (0-16). Default: 5 recommended |
| `-c, --cyqles <N>` | Max auto-cycles (1-50) |
| `-n, --qonstruction-name <name>` | Auto-save as Qonstruction |
| `-s, --sqrapyard` | Seed from sqrapyard |
| `-d, --docker` | Force Docker engine |
| `-p, --podman` | Force Podman engine |
| `-M, --msb` | Microsandbox mode **[EXPERIMENTAL]** |
| `-w, --wonqrete` | Experimental mode |
| `-q, --qage <name>` | Specify Qage (resume/clean) |
| `-A, --all` | All Qages (clean) |

## Briq Sensitivity Scale

| Level | Name | Briq Range | Use Case |
|-------|------|------------|----------|
| 0 | Monolithic | 1 | Single-file scripts |
| 1-2 | Broad | 2-5 | Large components |
| 3-4 | Feature | 5-12 | Per-feature/component |
| **5** | **Balanced** | **10-15** | **← RECOMMENDED** |
| 6-7 | High | 15-30 | Detailed split |
| 8-9 | Atomic | 30-60 | Fine-grained |
| 10-16 | Enterprise | 50-250 | Mega-projects (batched) |

Sensitivity >= 8 auto-enables batched briq generation (Blueprint → Fabrication pipeline).
