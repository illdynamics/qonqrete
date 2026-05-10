# QonQrete VS Code Extension - Changelog

## 1.4.5 — v1.4.x Line: Runtime Alignment & Version Sync

### v1.4.x cumulative changes
- AI config UI now targets the four primary runtime agents only:
  - `qrystallizer`, `instruqtor`, `construqtor`, `inspeqtor`
- Default primary-agent binding: `venice / deepseek-v3.2`
- Shared provider/model picker no longer exposes local-only runtime providers (`mlx`, `llama-cpp`).
- Added run-level `--no-sync` wiring to settings, config wizards, and sidebar (`qonqrete.noSync`).
- Corrected docs/settings defaults to match runtime-backed values (`sensitivity=1`, `cycles=1`, `autonomous=true`).
- **License:** AGPL-3.0 → Apache-2.0 (v1.4.2)
- **Auto Briq Sensitivity** default-on in settings (v1.4.1)
- **Package-lock.json:** Fixed stale version (was stuck at 1.4.0 since v1.4.1) (v1.4.5)

### Notes
- Local runtime providers remain supported by core runtime config files, but are no longer presented in the shared sidebar/panel provider picker.
- No core runtime changes in any v1.4.x patch — IDE plugins only.

## 1.3.0 - Current Runtime Alignment

### Added
- **Deploy to Workspace** command — one-click runtime install into `.qonqrete/`
- **Create tasq.md** command — starter template at workspace root
- **Auto-init** on first Run Tasq (builds container image automatically)
- **Root tasq.md sync** — user-facing tasq at workspace root, auto-synced to runtime before runs
- **.gitignore management** — auto-adds `.qonqrete/` on deploy
- `.qonqrete/qonqrete.sh` added to path discovery (preferred over older paths)
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
