# QonQrete Quickstart Guide

**Version:** `v0.4.7-alpha` (See `VERSION` file for the canonical version).

This guide will walk you through running your first `cyQle` with the QonQrete system.

## Prerequisites
- **Docker:** Ensure the Docker daemon is running (or see `README.md` for Microsandbox setup).
- **API Keys:** You must have `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and `ANTHROPIC_API_KEY` exported in your shell environment.

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
    -   `cheqpoint`: Sets the default behavior. `true` for user-gated mode, `false` for autonomous. Can be overridden with `--user` or `--auto`.
    -   `auto_cycle_limit`: Set the maximum number of cycles for auto-mode.
    -   `agents`: Change the AI models for each agent.
    -   `mode`: Set the default operational mode for agent personas (e.g., `program`, `enterprise`, `security`, `performance`, `innovative`).
    -   `briq_sensitivity`: Set the default task breakdown granularity (0=atomic, 9=monolithic).
-   **`pipeline_config.yaml`**:
    -   `microsandbox`: Set to `true` to make Microsandbox (`msb`) the default container runtime.

## 6. Cleaning the Workspace
To remove all `qage_<timestamp>` run directories, use the `clean` command.
```bash
./qonqrete.sh clean
```