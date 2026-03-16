# Changelog

All notable changes to the QonQrete IntelliJ Plugin.

## [1.1.9] - 2026-03-13 - Production Hardening Pass

### Fixed
- **Gradle wrapper**: Now ships a VALID gradle-wrapper.jar that actually works from clean checkout
- **Marker watcher**: Uses daemon thread (proper JVM shutdown, no blocking)
- **Auto-refresh**: Tool window auto-refreshes when run completes
- **Status widget**: Now shows version + run state
- **Resume popup**: Shows timestamps and artifact counts
- **Config files path**: Fixed double-slash issue for root-level config files

### Added
- **CommandBuilder utility**: Centralized command assembly with proper shell escaping
- **QonQreteValidation utility**: Centralized input validation
- **ShellEscape utility**: Single source of truth for bash escaping
- **"Clean All" button**: In tool window for bulk cleanup with confirmation
- **"Open Tasq" button**: Quick access to tasq.md from tool window
- **Tooltips**: All config controls have helpful tooltips
- **Qage timestamps**: Displayed in qage list with artifact counts
- **Comprehensive tests**: 40+ tests covering actual utility implementations
- **Disposable**: Tool window panel properly implements Disposable

### Changed
- **Deterministic repo discovery**: Persists choice when multiple paths found
- **Structured command building**: No more ad-hoc shell string concatenation
- **Settings properly used**: All settings actually affect behavior

## [1.1.8] - 2026-03-13

### Fixed
- Unix execution now ALWAYS uses verified bash (not system default)
- Command construction with proper shell escaping
- autoOpenToolWindowOnRun now works
- Full artifact browser with per-file click-to-open
- Repo discovery with ambiguity handling

### Added
- gradle-wrapper.jar for clean builds (was invalid HTML)
- Comprehensive unit tests (were weak)

## [1.1.7] - 2026-03-13

### Added
- Initial production-ready release
