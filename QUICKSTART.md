# QonQrete Quickstart Guide

**Version:** `v0.1.0` (See `VERSION` file for the canonical version).

This guide will walk you through running your first `cyQle` with the QonQrete system.

## Prerequisites
- **Docker:** Ensure the Docker daemon is running.
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

- **Press `q`:** Approves the `reQap` and starts the next cycle, using the `reQap` as the new set of instructions.
- **Press `t`:** Pauses the cycle and opens the `reQap.md` file in your default editor (`$EDITOR`, e.g., `vim`). You can add new instructions, correct the AI's plan, or give feedback. After you save and close the editor, you will be returned to this prompt.
- **Press `x`:** Gracefully ends the session.

## 4. Run in Autonomous Mode
To run the system without manual confirmation at each CheQpoint, use the `--auto` flag. The system will loop, feeding the `reQap` from one cycle to the `instruqtor` of the next, until it reaches a `Success` state or the cycle limit.
```bash
./qonqrete.sh run --auto
```
You can stop the loop at any time with `Ctrl+C`.

## 5. Configuration
Advanced options can be set in `worqspace/config.yaml`.
- **`auto_cycle_limit`**: Set the maximum number of cycles for auto-mode. `0` means infinite.
- **Agent Models**: You can change the specific AI models used by the `instruqtor`, `construqtor`, and `inspeqtor`.