# QonQrete IntelliJ Plugin

IntelliJ IDEA integration for [QonQrete](https://qonqrete.sh) - the local-first multi-agent AI orchestration system for autonomous code generation.

## AI Configuration (v2.0.1)

- The shared AI configuration dialog now targets the four primary runtime agents:
  - `qrystallizer`, `instruqtor`, `construqtor`, `inspeqtor`
- Default binding is `venice / deepseek-v3.2`.
- Local-only runtime providers (`mlx`, `llama-cpp`) are not shown in the shared provider/model picker.

## Features

- **Run Tasq** - Execute QonQrete from the default project task file
- **Run Any Markdown** - Run any `.md` file directly as the task input
- **Configuration** - Full config: sensitivity, cycles, mode, autonomous, no-sync, repository seeding and engine
- **Tool Window** - Control panel with status, config, qage browser
- **Status Widget** - Real-time status with version in status bar
- **Shell Verification** - Auto-detects and verifies bash shell
- **Run State Tracking** - Marker-based exit code detection
- **Qage Browser** - Browse artifacts with timestamps and counts
- **Auto-Refresh** - Tool window updates when run completes

## Requirements

- IntelliJ IDEA 2023.3 or newer
- Bash shell (Git Bash on Windows, native on macOS/Linux)
- Docker or Podman for container execution
- QonQrete project with `qonqrete.sh`

## Installation

### From ZIP
1. Build: `./gradlew buildPlugin`
2. Install: Settings → Plugins → ⚙️ → Install Plugin from Disk
3. Select `build/distributions/qonqrete-intellij-2.0.1.zip`

### From Source
```bash
./gradlew runIde    # Run in sandbox
./gradlew test      # Run tests
./gradlew buildPlugin  # Build distributable
```

## Usage

### Quick Start
1. Open a QonQrete project in IntelliJ
2. Create or edit your project task file at the root (`tasq.md` remains the default starter)
3. Press `Ctrl+Alt+Q` or use Tools → QonQrete → Run Tasq

### Tool Window
- **Status Panel** - Shell, run, container, version status
- **Configuration** - All QonQrete CLI options with tooltips
- **Actions** - Run, Init, Resume, Clean, Clean All, Open Tasq
- **Qage Browser** - Click qages to browse artifacts, double-click files to open

### Keyboard Shortcuts
- `Ctrl+Alt+Q` - Run Tasq

### Context Menu
Right-click any `.md` file to run it directly as the QonQrete task file

## Configuration

Settings → Tools → QonQrete:

| Setting | Default | Description |
|---------|---------|-------------|
| Default Sensitivity | 1 | Briq sensitivity (0-16) |
| Default Auto Briq Sensitivity | false | Use `--auto-briq-sensitivity` |
| Default Cycles | 1 | AI iteration cycles |
| Default Mode | program | QonQrete mode |
| Default Autonomous | true | Auto mode |
| Default No Sync | false | Keep outputs in qage/qonstructions (`--no-sync`) |
| Seed Repo | false | Seed qodeyard from repository (`--seed-repo`) |
| Container Engine | auto | docker/podman/auto |
| Custom QonQrete Path | - | Override auto-detection |
| Custom Bash Path | - | Override bash detection |
| Auto Open Tool Window | true | Open on run |
| Qage List Limit | 10 | Max qages shown |
| Marker Timeout | 60 | Minutes before timeout |

## Known Limitations

- Windows requires Git Bash, WSL, or MSYS2 for bash shell

## Validation Reality

Deterministic validation in the current bridge is strongest for Python. Other ecosystems still run through the workflow, but deterministic compile/test coverage is weaker and should be treated accordingly.

## License

Apache-2.0 - Same as QonQrete core

## Author

WoNQ / Ill Dynamics
https://qonqrete.sh
