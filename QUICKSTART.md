# Qq + qq-tui Quickstart Guide

## Overview

Qq is a multi-agent coding harness that orchestrates `Qlarifier → instruQtor → (construQtor ↔ inspeQtor)`.  
`qq-tui` is the companion terminal UI — a sticky status-bar agent cockpit with streamed agent output.

## Installation

```bash
# From the Qq repo root:
pip install -e .

# Build qq-tui (Rust):
cd qq-tui && cargo build --release
# Binary is at: qq-tui/target/release/qq-tui
```

## Running Qq

```bash
# Run a task through the full agent loop:
python3 -m qq run task.md --provider codeseeq

# Stream agent output live:
python3 -m qq run task.md --provider codeseeq --stream-agent-output

# With sticky status line + streaming:
python3 -m qq run task.md --provider codeseeq \
  --stream-agent-output \
  --stream-status-line bottom

# Dry run (no API calls):
python3 -m qq run task.md --dry-run

# Image smoke test:
CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES=true \
CODESEEQ_RUNTIME_MODE=host \
python3 -m qq image-smoke-test
```

## Running qq-tui

### Start the TUI

```bash
# From qq-tui/ directory:
cargo run

# Or with the built binary:
./qq-tui/target/release/qq-tui
```

### TUI layout

```
╭─[ꝖꝖ]─❯❯❯qonqrete-agent ⣷ M=QON-7B C=42 · T=01:12 · A=00:39 · B=26 · P≈46% [↯↯]─╮
┌──────────────────────────────────────────────────────────────────────────────┐
│  [AssistantMessage] Starting task...                                         │
│  [ToolOutput] python3 -m pytest -q                                           │
│  ....28 passed in 0.24s                                                      │
│  [ToolEnd] exit_code=0                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
> /run python3 -m qq run task.md
```

### Keybindings

| Key       | Action                       |
|-----------|------------------------------|
| Ctrl+C    | Quit / interrupt             |
| Ctrl+P    | Command palette              |
| ?         | Help modal                   |
| Esc       | Close modal                  |
| Enter     | Submit input                 |
| PageUp    | Scroll output up             |
| PageDown  | Scroll output down           |
| Home      | Jump to top                  |
| End       | Jump to bottom               |
| Ctrl+L    | Clear visible output         |
| Ctrl+R    | Force redraw                 |
| Ctrl+S    | Pause auto-scroll            |
| Ctrl+G    | Show diagnostics panel       |

### Commands

| Command              | Description                    |
|----------------------|--------------------------------|
| `/help`             | Show help modal                |
| `/quit`             | Exit qq-tui                    |
| `/clear`            | Clear output view              |
| `/status`           | Show current session status    |
| `/debug`            | Show diagnostics panel         |
| `/run <cmd>`        | Run a subprocess command       |
| `/shell <cmd>`      | Run a shell command            |
| `/theme`            | Show theme info                |
| `/ascii`            | Toggle ASCII mode              |
| `/filter <type>`    | Filter output by event type    |
| `/save <path>`      | Save session to JSONL          |
| `/replay <path>`    | Replay a JSONL session         |

### Custom status line (Claude-style)

```bash
# Create a statusline script:
cat > ~/.config/qq-tui/statusline.sh << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

json="$(cat)"

agent="$(printf '%s' "$json" | jq -r '.agent.name // "qonqrete-agent"')"
model="$(printf '%s' "$json" | jq -r '.agent.model // "QON-LOCAL"')"
cycle="$(printf '%s' "$json" | jq -r '.status.cycle // 0')"
budget="$(printf '%s' "$json" | jq -r '.status.budget // 26')"
progress="$(printf '%s' "$json" | jq -r '.status.progress // 0')"
elapsed="$(printf '%s' "$json" | jq -r '.session.elapsed_seconds // 0')"
active="$(printf '%s' "$json" | jq -r '.status.active_seconds // 0')"

fmt_time() {
  local s="$1"
  printf "%02d:%02d" "$((s / 60))" "$((s % 60))"
}

printf '╭─[ꝖꝖ]─❯❯❯%s ⣷ M=%s C=%s · T=%s · A=%s · B=%s · P≈%s%% [↯↯]─╮\n' \
  "$agent" "$model" "$cycle" "$(fmt_time "$elapsed")" "$(fmt_time "$active")" "$budget" "$progress"
SCRIPT

chmod +x ~/.config/qq-tui/statusline.sh

# Run qq-tui with custom statusline:
qq-tui --status-command ~/.config/qq-tui/statusline.sh
```

### Configuration

Config file at `~/.config/qq-tui/config.toml`:

```toml
[agent]
name = "qonqrete-agent"
model = "QON-7B"
budget = 26

[ui]
theme = "qonqrete"
ascii = false
color = true
spinner_refresh_ms = 120
status_refresh_ms = 1000
show_borders = true
status_position = "top"

[statusline]
enabled = true
command = "~/.config/qq-tui/statusline.sh"
refresh_interval_ms = 1000
timeout_ms = 300
allow_ansi = true

[events]
write_jsonl = true
path = "~/.local/share/qq-tui/session.jsonl"

[keys]
quit = "ctrl-c"
command_palette = "ctrl-p"
help = "?"
```

### Environment Variables

| Variable              | Description                     |
|-----------------------|---------------------------------|
| `QQ_AGENT_NAME`       | Agent name for the status bar   |
| `QQ_AGENT_MODEL_CODE` | Model code                      |
| `QQ_B`                | Budget value                    |
| `QQ_P`                | Progress value                  |
| `QQ_TUI_THEME`        | Theme (qonqrete, dark, light)   |
| `QQ_TUI_ASCII`        | Force ASCII mode (=1)           |
| `QQ_TUI_NO_COLOR`     | Disable colors (=1)             |
| `QQ_STATUSLINE_COMMAND`| Custom statusline script path   |
| `QQ_EVENTS_OUT`       | Events JSONL output path        |
| `QQ_DEBUG_LOG`        | Debug log file path             |

### Spinner + Sticky Bar

The `qq-tui` owns the terminal entirely. The status bar:

- Is rendered by the TUI itself (not a shell prompt hack)
- Updates every 120ms by default (smooth spinner animation)
- Never wraps — uses Unicode width-aware truncation
- Falls back to ASCII when `TERM=dumb` or `--ascii` is passed
- Updates total time, active time, cycle count, budget, and progress

### ASCII Fallback

```bash
# Force ASCII mode:
qq-tui --ascii

# ASCII bar:
+-[QQ]->>>agent * M=QON-7B C=42 . T=01:12 . A=00:39 . B=26 . P~46% [!!]-+
```

### Non-TTY / CI Mode

When stdin/stdout are not a TTY, `qq-tui` automatically:

- Emits no terminal escape codes
- No borders or spinners
- No raw mode
- Safe for CI, cron, codex exec, and shell pipelines

### Session Replay

```bash
# Record a session:
qq-tui --events-out ./session.jsonl

# Replay later:
qq-tui replay ./session.jsonl
```

### Troubleshooting

| Issue                         | Solution                        |
|-------------------------------|---------------------------------|
| Terminal looks broken         | Press `Ctrl+R` to force redraw, or `reset` in shell |
| Custom statusline not showing | Run `qq-tui statusline-test <script>` to debug |
| Spinner not smooth            | Lower `spinner_refresh_ms` to 60 |
| Colors missing                | Set `QQ_TUI_THEME=qonqrete` |

---

**Uploaded artifact:** `dist/qonqrete-qq-v2.0.0.zip` — This is the clean release zip itself, not a source-folder wrapper.

**QonQrete cybersquid image test finished.**  
Image saved at: `qonqrete_cybersquid.png`

---

*QonQrete v2.0.0 — No duct-tape PS1 madness. Proper terminal beast mode.*
