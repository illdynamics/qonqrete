# QonQrete Quickstart Guide

**Version:** `v0.8.0-beta` (See `VERSION` file for the canonical version).

This guide will walk you through running your first `cyQle` with the QonQrete system.

## What's New in v0.8.0

- **Qontrabender**: Policy-driven hybrid caching with Variable Fidelity
- **caching_policy.yaml**: Comprehensive configuration for cache behavior
- **6 Operational Modes**: From `local_fast` to `debug_repro`
- **Schema Validation**: Bad YAML can't brick your flow

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

To start with existing code, see the "Seeding a Project with Sqrapyard" section below.

## 3. Run a CyQle
This is the default manual mode. You can combine flags for different behaviors.
```bash
# Run with the TUI and security-focused agent personas
./qonqrete.sh run --tui --mode security

# Run in auto mode with highly granular task breakdown
./qonqrete.sh run --auto --briq-sensitivity 1

# Force user-gated mode, overriding a `cheqpoint: false` setting in config.yaml
./qonqrete.sh run --user
```
At the `CheQpoint`, you will be prompted to `[Q]ontinue`, `[T]weaQ`, or `[X]Quit`.

## 4. Seeding a Project with Sqrapyard
To begin a `cyQle` with a pre-existing codebase:
1.  Place your code files into the `worqspace/sqrapyard/` directory.
2.  If you have a specific objective for the first cycle, create a `worqspace/sqrapyard/tasq.md` file.
3.  Run `./qonqrete.sh run`. The system will automatically copy the contents of `sqrapyard` into the active `qodeyard` and use your `tasq.md` as the first instruction.

## 5. Configuration
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
-   **`caching_policy.yaml`** (NEW in v0.8.0):
    -   Defines Qontrabender behavior and operational modes
    -   Available modes: `local_fast`, `local_smart`, `cyber_bedrock`, `cyber_aggressive`, `paranoid_mincloud`, `debug_repro`
    -   See [QONTRABENDER.md](./QONTRABENDER.md) for full documentation
-   **`pipeline_config.yaml`**:
    -   `microsandbox`: Set to `true` to make Microsandbox (`msb`) the default container runtime.

## 6. Qontrabender Quick Setup
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

## 7. Cleaning the Workspace
To remove all `qage_<timestamp>` run directories, use the `clean` command.
```bash
./qonqrete.sh clean
```