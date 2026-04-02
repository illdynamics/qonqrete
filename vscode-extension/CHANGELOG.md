# QonQrete VS Code Extension - Changelog

## 1.2.4 - Production-Readiness & Forward Compatibility

### Fixed
- **Critical:** Auto-cycle mode (`--cyqles 0`) crash from `qrane_prefix` use-before-assignment in Qrane orchestrator.
- **Critical:** Crash when neither `--auto` nor `--user` flag passed.

### Improved
- Version consistency enforced across all source files.
- Documentation fully aligned with v1.2.4 architecture.
- All `@version` headers updated to 1.2.4.

## 1.2.4 - Deterministic Quality Gates & Auto-Cycle Mode

### Added
- **Auto-Cycle Mode** (`cycles = 0`) support in run configuration
- **llamacpp** provider support in AI Configuration
- Support for **Program** and **Innovative** operational modes
- Real-time status reporting for **Qrystallizer** and **Qualifier** agents

### Improved
- Robust stopping logic driven by structured `verdict.json`
- UI labels aligned with v1.2.4 deterministic pipeline
- Enhanced error reporting for build/test failures

## 1.2.0 - Workspace Deployment & Hassle-Free Bootstrap

### Added
- **Deploy to Workspace** command — one-click runtime install into `.qonqrete/`
- **Create tasq.md** command — starter template at workspace root
- **Auto-init** on first Run Tasq (builds container image automatically)
- **Root tasq.md sync** — user-facing tasq at workspace root, auto-synced to runtime before runs
- **.gitignore management** — auto-adds `.qonqrete/` on deploy
- `.qonqrete/qonqrete.sh` added to path discovery (preferred over legacy paths)
- Sidebar Deploy + Create Tasq buttons
- Activation event for `workspaceContains:**/.qonqrete/qonqrete.sh`

### Changed
- Status bar suggests Deploy when runtime not found (instead of Configure)
- Welcome message offers Deploy to Workspace
- Run Tasq offers Deploy when runtime missing, Create tasq when tasq missing
- Versioned container image detection (`qonqrete-qage:<version>`)

### Backward Compatible
- Legacy paths (root `qonqrete.sh`, `qonqrete/qonqrete.sh`) remain as fallback
- Legacy untagged `qonqrete-qage` image still detected
- Existing worqspace-only workflows continue to work

## 1.1.9 - Production Hardening

- Shell detection with verification
- Marker-based run state tracking
- Orphan backup recovery
- Qage browser with artifact details
- Full config wizard (quick + full modes)
- Status bar with run state display
- Windows Git Bash / WSL support

## 1.0.5 - Initial Extension

- Basic run/resume/clean/init commands
- Sidebar control panel
- Terminal-based execution
