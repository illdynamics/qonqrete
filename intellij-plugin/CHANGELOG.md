# QonQrete IntelliJ Plugin - Changelog

## 1.4.4 - Plugin API Cleanup & Release Fixes

### Changes
- Replaced 8 deprecated ActionUtil.invokeAction() calls with modern AnActionEvent pattern.
- Suppressed 2 deprecated CredentialAttributes() constructor warnings (Builder unavailable on 2023.3 minimum).
- Zero compatibility warnings across all verified IDE versions (2023.3.8–2026.2 EAP).
- Verified marketplace compatibility: Success on all 4 tiers.


### Changed
- AI config UI now targets the four primary runtime agents only:
  - `qrystallizer`, `instruqtor`, `construqtor`, `inspeqtor`
- Default primary-agent binding in the AI config flow is now:
  - provider: `venice`
  - model: `deepseek-v3.2`
- Shared provider/model picker no longer exposes local-only runtime providers (`mlx`, `llama-cpp`).
- Venice model suggestions now include `deepseek-v3.2`.
- Added run-level `--no-sync` wiring to settings, dialogs, and tool window controls.
- Corrected docs/UI default-value text to match runtime-backed defaults (`sensitivity=1`, `cycles=1`, `autonomous=true`).

### Notes
- Local runtime providers remain supported by core runtime config files, but are no longer presented in the shared tool-window AI provider picker.

## 1.3.0 - Current Runtime Alignment

### Added
- **Deploy to Workspace** action — one-click runtime install into `.qonqrete/`
- **Create tasq.md** action — starter template at project root
- **Auto-init** on first Run Tasq (builds container image automatically)
- **Root tasq.md sync** — user-facing tasq at project root, auto-synced to runtime before runs
- **.gitignore management** — auto-adds `.qonqrete/` on deploy
- `.qonqrete/qonqrete.sh` added to path discovery (preferred over older paths)
- Tool window Deploy + Create Tasq buttons

### Changed
- Run Tasq offers Deploy when runtime missing, Create tasq when tasq missing
- Versioned container image detection (`qonqrete-qage:<version>`)
- Identical behavior with VS Code extension

### Backward Compatible
- Older paths remain as fallback detection
- Untagged compatibility image still detected
- Existing worqspace-only workflows continue to work
