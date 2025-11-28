# QonQrete Quickstart Guide

**Version:** `v0.2.0-alpha` (See `VERSION` file for the canonical version).

This guide will walk you through running your first `cyQle` with the QonQrete system.

## Prerequisites
- **Docker:** Ensure the Docker daemon is running (or see `README.md` for Microsandbox setup).
- **API Keys:** You must have `OPENAI_API_KEY` and `GOOGLE_API_KEY` exported in your shell environment.

## 1. First-Time Setup
Build the secure `Qage` environment. You only need to do this once.
```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

## 2. Define Your TasQ
Edit `worqspace/tasq.md` to define your initial objective. For example:
```markdown
Create a simple Python web server that listens on port 8080 and returns "Hello, QonQrete!" for all requests. The script should be executable.
```

## 3. Run a Manual CyQle (Interactive Mode)
This is the default mode. The system will run one full Plan-Execute-Review cycle and then pause for your input.
```bash
./qonqrete.sh run
```
After the agents have run, the `inspeQtor`'s review will be displayed, and you will be presented with the `gateQeeper` prompt:

```
Result: Success. [Q]ontinue, [T]weaQ, [X]Quit
```

- **Press `q`:** Approves the `reQap` and starts the next cycle.
- **Press `t`:** Pauses and opens the `reQap.md` file in your default editor (`$EDITOR`).
- **Press `x`:** Gracefully ends the session.

## 4. Run in TUI Mode
For a more detailed view, run the system with the `--tui` flag. This launches a split-screen interface.
```bash
./qonqrete.sh run --tui
```
-   **Qommander (Top View):** Shows the main execution flow.
-   **Qonsole (Bottom View):** Shows raw agent logs.
-   **Key Shortcuts:**
    -   `[Spacebar]`: Toggle the Qonsole on/off for a fullscreen Qommander view.
    -   `[Esc]`: Quit the application.

## 5. Run in Autonomous Mode
To run the system without manual confirmation at each CheQpoint, use the `--auto` flag.
```bash
./qonqrete.sh run --auto
```
You can stop the loop at any time with `Ctrl+C`.

## 6. Configuration
Advanced options can be set in `worqspace/`.
-   **`config.yaml`**: Set `auto_cycle_limit` and change the AI models for each agent.
-   **`pipeline_config.yaml`**: Set the default runtime environment by adding `microsandbox: true`.

## 7. Cleaning the Workspace
The `run` command creates a `qage_<timestamp>` directory for each execution. To remove all of them, use the `clean` command.
```bash
./qonqrete.sh clean
```