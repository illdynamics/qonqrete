# QonQrete IntelliJ Plugin

IntelliJ IDEA integration for [QonQrete](https://qonqrete.sh) - the local-first multi-agent AI orchestration system for autonomous code generation.

## Features

- **Run Tasq** - Execute QonQrete builds from your project root `tasq.md`
- **Run Any Markdown** - Run any `.md` file as a temporary tasq
- **Configuration** - Full config: sensitivity, cycles, mode, autonomous, sqrapyard, engine, TUI, wonqrete
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
3. Select `build/distributions/qonqrete-intellij-1.1.9.zip`

### From Source
```bash
./gradlew runIde    # Run in sandbox
./gradlew test      # Run tests
./gradlew buildPlugin  # Build distributable
```

## Usage

### Quick Start
1. Open a QonQrete project in IntelliJ
2. Create or edit `tasq.md` at the project root
3. Press `Ctrl+Alt+Q` or use Tools → QonQrete → Run Tasq

### Tool Window
- **Status Panel** - Shell, run, container, version status
- **Configuration** - All QonQrete CLI options with tooltips
- **Actions** - Run, Init, Resume, Clean, Clean All, Open Tasq
- **Qage Browser** - Click qages to browse artifacts, double-click files to open

### Keyboard Shortcuts
- `Ctrl+Alt+Q` - Run Tasq

### Context Menu
Right-click any `.md` file to "Run as QonQrete Tasq"

## Configuration

Settings → Tools → QonQrete:

| Setting | Default | Description |
|---------|---------|-------------|
| Default Sensitivity | 6 | Briq sensitivity (0-16) |
| Default Cycles | 3 | AI iteration cycles |
| Default Mode | program | QonQrete mode |
| Default Autonomous | false | Auto mode |
| Use Sqrapyard | false | Incremental builds |
| Container Engine | auto | docker/podman/auto |
| Enable TUI | false | Terminal UI |
| Enable Wonqrete | false | Experimental features |
| Custom QonQrete Path | - | Override auto-detection |
| Custom Bash Path | - | Override bash detection |
| Auto Open Tool Window | true | Open on run |
| Qage List Limit | 10 | Max qages shown |
| Marker Timeout | 60 | Minutes before timeout |

## Known Limitations

- Hard-killing the terminal during temp tasq flow may interrupt restore (next startup will recover)
- Windows requires Git Bash, WSL, or MSYS2 for bash shell

## License

AGPL-3.0 - Same as QonQrete core

## Author

WoNQ / Ill Dynamics
https://qonqrete.sh
