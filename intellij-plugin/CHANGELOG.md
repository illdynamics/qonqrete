# QonQrete IntelliJ Plugin - Changelog

## 1.2.4 - Production-Readiness & Forward Compatibility

### Fixed
- **Critical:** Auto-cycle mode (`--cyqles 0`) crash from `qrane_prefix` use-before-assignment.
- **Critical:** Crash when neither `--auto` nor `--user` flag passed (unbound `is_autonomous`).
- Replaced deprecated `setItemChoosenCallback` with `setItemChosenCallback`.
- Replaced deprecated `postStartupActivity` with `backgroundPostStartupActivity`.

### Improved
- Forward compatibility verified for IntelliJ 2025.x and 2026.x.
- Version consistency enforced across all source files (51 files updated).
- Plugin verifier now tests against 2023.3 through 2026.1.

## 1.2.4 - Deterministic Quality Gates & Auto-Cycle Mode

### Added
- **Auto-Cycle Mode** (`cycles = 0`) support in run configuration.
- **llamacpp** provider support in AI Configuration panel.
- Support for **Program** and **Innovative** operational modes.
- Real-time status reporting for **Qrystallizer** and **Qualifier** agents in tool window.

### Improved
- Robust stopping logic driven by structured `verdict.json`.
- UI labels aligned with v1.2.4 deterministic pipeline.
- Improved error feedback for build/test failures in the container.

## 1.2.0 - Workspace Deployment & Hassle-Free Bootstrap

### Added
- **Deploy to Workspace** action — one-click runtime install into `.qonqrete/`
- **Create tasq.md** action — starter template at project root
- **Auto-init** on first Run Tasq (builds container image automatically)
- **Root tasq.md sync** — user-facing tasq at project root, auto-synced to runtime before runs
- **.gitignore management** — auto-adds `.qonqrete/` on deploy
- `.qonqrete/qonqrete.sh` added to path discovery (preferred over legacy paths)
- Tool window Deploy + Create Tasq buttons

### Changed
- Run Tasq offers Deploy when runtime missing, Create tasq when tasq missing
- Versioned container image detection (`qonqrete-qage:<version>`)
- Identical behavior with VS Code extension

### Backward Compatible
- Legacy paths remain as fallback detection
- Legacy untagged image still detected
- Existing worqspace-only workflows continue to work

## 1.1.9 - Production Hardening

- CommandBuilder utility for centralized command assembly
- QonQreteValidation utility for input validation
- ShellEscape utility for proper bash escaping
- Daemon thread marker watcher
- Auto-refresh on run complete
- Tool window with qage browser and artifact tree
- Status bar widget with version display
- 40+ unit tests
