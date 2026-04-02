# QonQrete IntelliJ Plugin - Changelog

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
