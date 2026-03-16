# QonQrete Changelog

## [1.1.9] - 2026-03-13 - Production Hardening Pass

### IntelliJ Plugin
- **Fixed**: Gradle wrapper now ships VALID jar (builds from clean checkout)
- **Fixed**: Marker watcher uses daemon thread (proper JVM shutdown)
- **Fixed**: Auto-refresh when run completes
- **Fixed**: Status widget shows version + state
- **Added**: CommandBuilder utility for centralized command assembly
- **Added**: QonQreteValidation utility for input validation
- **Added**: ShellEscape utility for proper bash escaping
- **Added**: "Clean All" button with confirmation
- **Added**: "Open Tasq" button for quick editing
- **Added**: Tooltips on all config controls
- **Added**: Qage timestamps in list display
- **Added**: 40+ comprehensive unit tests

### VS Code Extension
- Version bump to 1.1.9

## [1.1.8] - 2026-03-13

### IntelliJ Plugin
- Fixed: Unix execution now ALWAYS uses verified bash
- Fixed: Command construction with proper shell escaping
- Fixed: autoOpenToolWindowOnRun now works
- Added: Full artifact browser with per-file click-to-open
- Added: Repo discovery with ambiguity handling
- Added: gradle-wrapper.jar for clean builds

## [1.1.7] - 2026-03-12

### IntelliJ Plugin
- Initial production-ready release
