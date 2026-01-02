# QonQrete Quickstart Guide

**Version:** `v1.0.1` (See `VERSION` file for the canonical version).

This guide will walk you through running your first `cyQle` with the QonQrete system.

## What's New in v1.0.1

- **HuggingFace Cache Fix**: Fixed permission errors when using Qontextor `complex` mode in Docker hardened containers
- **Pre-downloaded Models**: The sentence-transformers model is now pre-downloaded during Docker build
- **Graceful Fallback**: Qontextor now falls back to AST-only analysis if semantic embeddings fail

## What's New in v0.9.8

- **pycg Reliability**: Fixed module invocation using `sys.executable -m pycg`
- **Cache Support**: Added writable tmpfs for sentence-transformers caching
- **Default Tuning**: `briq_sensitivity: 6`, `auto_cycle_limit: 3`
- **Ignore Updates**: Qonstructions now excluded from git/docker

## What's New in v0.9.6

- **Resume Command**: Continue work from previous Qages with `./qonqrete.sh resume`
- **Qonstructions**: Save completed runs as persistent projects
- **Interactive Clean**: Pick which Qages to delete with kubectx-style selection
- **Security Hardening**: Container runs as non-root with proper user isolation
- **Explicit Sqrapyard**: Use `-s/--sqrapyard` flag to seed from sqrapyard (no longer automatic)
- **Interactive TasQ Editor**: Opens `$EDITOR` if no tasq.md exists

## Prerequisites
- **Docker:** Ensure the Docker daemon is running (or see ../README.md for Microsandbox setup).
- **API Keys:** Before running, you must export the API keys for the AI providers you intend to use. The system will automatically check for the necessary keys based on your `worqspace/config.yaml` and exit with an error if they are not set.
  - `export OPENAI_API_KEY='your-key'`
  - `export GOOGLE_API_KEY='your-key'` (or `GEMINI_API_KEY`)
  - `export ANTHROPIC_API_KEY='your-key'`
  - `export DEEPSEEK_API_KEY='your-key'`
  - `export QWEN_API_KEY='your-key'`

## 1. First-Time Setup
Build the secure `Qage` environment. You only need to do this once.
```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

## 2. Define Your TasQ
For a new project, edit `worqspace/tasq.md` to define your initial objective. For example:
```markdown
Create a simple Python web server that listens on port 8080 and returns "Hello, QonQrete!" for all requests. The script should be executable.
```

**New in v0.9.1:** If no `tasq.md` exists, QonQrete will automatically open your `$EDITOR` (default: vim) with a template!

## 3. Run a CyQle
This is the default manual mode. You can combine flags for different behaviors.
```bash
# Basic fresh start
./qonqrete.sh run

# Run with sqrapyard seeding
./qonqrete.sh run -s

# Run with the TUI and security-focused agent personas [EXPERIMENTAL]
./qonqrete.sh run --tui --mode security

# Run in auto mode with highly granular task breakdown
./qonqrete.sh run --auto --briq-sensitivity 1

# Force user-gated mode, overriding a `cheqpoint: false` setting in config.yaml
./qonqrete.sh run --user
```
At the `CheQpoint`, you will be prompted to `[Q]ontinue`, `[T]weaQ`, or `[X]Quit`.

## 4. Saving Your Work (Qonstructions)

After each run completes, QonQrete will ask if you want to save the result:

```
┌─────────────────────────────────────────────────────────────┐
│           QonQrete Session Complete                         │
└─────────────────────────────────────────────────────────────┘

Save this run as a Qonstruction? [y/N] y
Enter project name [project_20251226_115701]: my-awesome-api
Saving Qonstruction to: qonstructions/my-awesome-api
Qonstruction saved successfully!
Delete original Qage? [y/N] y
```

Qonstructions are saved to `worqspace/qonstructions/<name>/` with all context preserved.

## 5. Resuming Previous Work

Resume from a previous Qage to continue development:

```bash
# Interactive picker (kubectx-style)
./qonqrete.sh resume

# Direct selection
./qonqrete.sh resume -q qage_20251226_115701
```

The resume command:
1. Copies all content from the selected Qage to a new Qage
2. Updates config files from the workspace
3. Uses your updated `tasq.md` as the next cycle's task
4. Starts the run with all previous context preserved

## 6. Seeding a Project with Sqrapyard

To begin a `cyQle` with a pre-existing codebase:
1. Place your code files into the `worqspace/sqrapyard/` directory.
2. Edit `worqspace/tasq.md` with your objective for this project.
3. Run `./qonqrete.sh run -s` (the `-s` flag is now required to use sqrapyard).

**Note:** Without the `-s` flag, sqrapyard contents are ignored to prevent accidental imports.

## 7. Configuration
Advanced options can be set in `worqspace/`.
-   **`config.yaml`**:
    -   `use_qompressor`: `true` to generate token-efficient code skeletons (default), `false` to use full code.
    -   `use_qontextor`: `true` to generate a semantic index of the code (default), `false` to disable.
    -   `use_qontrabender`: `true` to enable policy-driven hybrid caching (default), `false` to disable.
    -   `cheqpoint`: Sets the default behavior. `true` for user-gated mode, `false` for autonomous. Can be overridden with `--user` or `--auto`.
    -   `auto_cycle_limit`: Set the maximum number of cycles for auto-mode.
    -   `agents`: Change the AI models for each agent. For `qontextor`, set `provider: local` to use the new high-speed, zero-cost analysis mode.
    -   `mode`: Set the default operational mode for agent personas (e.g., `program`, `enterprise`, `security`, `performance`, `innovative`).
    -   `briq_sensitivity`: Set the default task breakdown granularity (0=atomic, 9=monolithic).
-   **`caching_policy.yaml`**:
    -   Defines Qontrabender behavior and operational modes
    -   Available modes: `local_fast`, `local_smart`, `cyber_bedrock`, `cyber_aggressive`, `paranoid_mincloud`, `debug_repro`
    -   See [QONTRABENDER.md](./QONTRABENDER.md) for full documentation
-   **`pipeline_config.yaml`**:
    -   `microsandbox`: Set to `true` to make Microsandbox (`msb`) the default container runtime. [EXPERIMENTAL]

## 8. Qontrabender Quick Setup
To configure the cache bender:

1. Edit `worqspace/config.yaml` to select your mode:
```yaml
agents:
  qontrabender:
    policy_file: "./caching_policy.yaml"
    mode: local_smart  # Options: local_fast, local_smart, cyber_bedrock, etc.
```

2. Run Qontrabender commands:
```bash
# Check status
python worqer/qontrabender.py --status

# Analyze file fidelity decisions
python worqer/qontrabender.py --analyze

# Validate policy file
python worqer/qontrabender.py --validate

# List available modes
python worqer/qontrabender.py --modes
```

## 9. Cleaning the Workspace

Multiple options for cleanup:

```bash
# Interactive selection (pick which Qage to delete)
./qonqrete.sh clean

# Delete specific Qage
./qonqrete.sh clean -q qage_20251226_115701

# Delete ALL Qages (original behavior)
./qonqrete.sh clean -A
```

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `./qonqrete.sh init` | Build the Qage container |
| `./qonqrete.sh run` | Start fresh session |
| `./qonqrete.sh run -s` | Start with sqrapyard seeding |
| `./qonqrete.sh resume` | Interactive resume picker |
| `./qonqrete.sh resume -q <name>` | Resume specific Qage |
| `./qonqrete.sh clean` | Interactive delete picker |
| `./qonqrete.sh clean -q <name>` | Delete specific Qage |
| `./qonqrete.sh clean -A` | Delete ALL Qages |

## Flags Reference

| Flag | Description |
|------|-------------|
| `-a, --auto` | Autonomous mode |
| `-u, --user` | User-gated mode |
| `-t, --tui` | TUI mode [EXPERIMENTAL] |
| `-m, --mode <n>` | Operational mode |
| `-b, --briq-sensitivity <N>` | Granularity (0-9). Default: 7 |
| `-c, --cyqles <N>` | Max auto-cycles (1-10). Default: 4 |
| `-s, --sqrapyard` | Seed from sqrapyard |
| `-M, --msb` | Microsandbox mode [EXPERIMENTAL] |
| `-d, --docker` | Force Docker |
| `-q, --qage <name>` | Specify Qage (resume/clean) |
| `-A, --all` | All Qages (clean) |
