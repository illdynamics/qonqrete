# QonQrete VS Code Extension
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Splash](assets/qonqrete-icon.png)

> Run QonQrete directly from VS Code

This extension integrates the QonQrete Agentic AI System into VS Code.

## AI Configuration (v1.4.4)

- The shared AI configuration surface now targets the four primary runtime agents:
  - `qrystallizer`, `instruqtor`, `construqtor`, `inspeqtor`
- Default binding is `venice / deepseek-v3.2`.
- Local-only runtime providers (`mlx`, `llama-cpp`) are not shown in the shared provider/model picker.

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| Linux | ✅ Full | Uses `$SHELL` or `/bin/bash` |
| macOS | ✅ Full | Uses `$SHELL` or `/bin/bash` |
| Windows + Git Bash | ✅ Full | Auto-detected |
| Windows + WSL | ✅ Full | Auto-detected |
| Windows + MSYS2 | ✅ Full | Auto-detected |
| Windows (no bash) | ❌ Blocked | Extension shows error |

**Important:** On Windows without bash, the extension **blocks execution entirely** rather than attempting a broken fallback.

## Shell Detection

The extension searches for bash in this order:

**Unix (Linux/macOS):**
1. `$SHELL` environment variable (if contains "bash")
2. `/bin/bash`

**Windows:**
1. `GIT_BASH` environment variable (custom path support)
2. `C:\Program Files\Git\bin\bash.exe`
3. `C:\Program Files (x86)\Git\bin\bash.exe`
4. `C:\Windows\System32\bash.exe` (WSL)
5. `C:\msys64\usr\bin\bash.exe`

**Custom Installations:** Set the `GIT_BASH` environment variable to your bash path, or use the `qonqrete.qonqretePath` setting.

## Shell Verification

On activation, the extension:
1. Detects available bash shell
2. Verifies shell works via `bash --version`
3. Status bar shows state:
   - `(verifying...)` — detection done, verification in progress
   - `Ready` — verified and ready
   - `(shell error)` — verification failed

**Clean Contract:** `canExecute()` returns `false` until shell is verified. All run paths (command palette AND sidebar) wait for verification to complete before proceeding.

**Retry on Failure:** If verification fails due to a transient issue, the extension clears the cached result and allows re-verification on the next run attempt.

## Run State Detection

The extension uses a **marker file** with **polling fallback**:

1. Creates unique marker file (`.qonqrete_run_*.marker`)
2. Appends to command: `echo $? > marker`
3. Detection via:
   - `fs.watch()` (primary)
   - 1-second polling (fallback for unreliable filesystems)
4. Reads exit code from marker file
5. Updates status accordingly

### Run States

| State | Meaning |
|-------|---------|
| `running` | Command sent to terminal |
| `completed` | Exit code 0 from marker |
| `failed` | Non-zero exit code from marker |
| `timeout` | Marker not detected within timeout |

**Honest Limitation:** If marker file is not detected, the extension reports `timeout` — it does NOT claim success or failure when it doesn't know.

## Orphan Cleanup

On activation, the extension automatically:
- Restores any orphaned `tasq.md` backup from interrupted sessions
- Cleans up stale marker files

This handles the edge case where a previous session was hard-killed mid-run.

## Features

### Command Palette

- **QonQrete: Run Tasq** — Run the default project task file
- **QonQrete: Resume Run** — Resume from a Qage
- **QonQrete: Init Workspace** — Build container image
- **QonQrete: Clean Qages** — Remove Qage directories
- **QonQrete: Show Status** — Display status including shell verification

### Context Menu

- **tasq.md files**: Runs that specific tasq.md
- **Other .md files**: Runs the selected markdown file directly as task input

### Sidebar

- **Configuration**: Sensitivity, cycles, mode, autonomous, repo-seed toggle
- **Run output control**: Optional `--no-sync` toggle to keep outputs in qage/qonstruction paths
- **Advanced**: Qonstruction name, container engine
- **Status**: Version, image, default task file, shell (with verification indicator)
- **Qage Browser**: Expandable list with artifact counts and file links

### Status Bar States

| Text | Meaning |
|------|---------|
| `QonQrete Ready` | Verified and ready to run |
| `QonQrete (verifying...)` | Shell detected, verification in progress |
| `QonQrete (shell error)` | Shell verification failed |
| `QonQrete Running` | Currently executing (animated) |
| `QonQrete Done (0)` | Completed with exit code |
| `QonQrete Failed (1)` | Failed with exit code |
| `QonQrete Timeout` | Outcome unknown |
| `QonQrete (no bash)` | Blocked — no bash found |
| `QonQrete (init needed)` | Container image not built |
| `QonQrete (no tasq)` | tasq.md not found |

### Qonstruction Name Sanitization

When you enter a qonstruction name with invalid characters:
1. Extension shows warning: `Name sanitized: "my name!" → "my_name_"`
2. You choose "Use Sanitized Name" or "Cancel"
3. Only proceeds if you explicitly accept

Allowed characters: `a-z`, `A-Z`, `0-9`, `_`, `-`

## Installation

```bash
cd vscode-extension
npm install
npm run compile
npx vsce package
code --install-extension qonqrete-vscode-1.4.4.vsix
```

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `qonqrete.defaultSensitivity` | 1 | Briq sensitivity (0-16) |
| `qonqrete.defaultAutoBriqSensitivity` | false | Use `--auto-briq-sensitivity` by default |
| `qonqrete.defaultCycles` | 1 | Cycles (1-50) |
| `qonqrete.defaultMode` | "program" | Mode |
| `qonqrete.defaultAutonomous` | true | Autonomous mode |
| `qonqrete.noSync` | false | Skip repo-root sync-back by default (`--no-sync`) |
| `qonqrete.containerEngine` | "auto" | Container engine |
| `qonqrete.useSqrapyard` | false | Enable repository seeding (`--seed-repo`) |
| `qonqrete.qonqretePath` | "" | Custom path to qonqrete.sh |

## CLI Flag Mapping

The extension correctly maps to real `qonqrete.sh` flags:

| UI Option | CLI Flag |
|-----------|----------|
| Sensitivity | `--briq-sensitivity N` |
| Cycles | `--cyqles N` |
| Mode | `--mode MODE` |
| Autonomous | `--auto` |
| No Sync | `--no-sync` |
| Qonstruction Name | `--qonstruction-name NAME` |
| Seed Repo | `--seed-repo` |
| Docker | `--docker` |
| Podman | `--podman` |

Resume: `./qonqrete.sh resume --qage QAGE_NAME [--auto]`
Clean: `./qonqrete.sh clean --qage QAGE_NAME` or `--all`

## Limitations

**What the extension CAN do:**
- Detect exit codes via marker file
- Block execution until shell is verified
- Show honest `timeout` state when outcome unknown
- Auto-recover orphaned backups on activation
- Support custom bash paths via `GIT_BASH` env var

**What the extension CANNOT do:**
- Parse terminal output in real-time
- Cancel a running process gracefully
- Work on Windows without bash
- Guarantee exit code if terminal is killed before marker written

**Known Edge Cases:**
- Hard terminal kills can lose marker file → `timeout` state
- Custom bash installs need `GIT_BASH` env var or settings

## Validation Reality

Deterministic validation in the current bridge is strongest for Python. Other ecosystems still run through the workflow, but deterministic compile/test coverage is weaker.

## Requirements

- VS Code 1.80.0+
- Docker or Podman
- QonQrete repository with `qonqrete.sh`
- **Windows**: Git Bash, WSL, or MSYS2 (required)

## Development

```bash
npm install          # Install dependencies
npm run compile      # Build TypeScript
npm run watch        # Watch mode
npm run package      # Create .vsix
```

Press `F5` in VS Code to launch extension host.

## License

QonQrete is licensed under the Apache License, Version 2.0.
See the [LICENSE](LICENSE) file for full text.

Copyright (c) 2026 | QonQrete | Built by Ill Dynamics (Ricky van Poppel)
