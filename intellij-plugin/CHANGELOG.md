# QonQrete IntelliJ Plugin - Changelog

## 1.4.6 — IntelliJ Compatibility Series (v1.4.1–v1.4.6)

IDE-plugin-only patches that resolve all IntelliJ Platform API deprecation warnings across 2023.3–2026.2 EAP.
No core runtime changes.

### API deprecation fixes (cumulative)
- **`ActionUtil.invokeAction()`** (8 usages) → modern `AnActionEvent` pattern (v1.4.4)
- **`AnActionEvent.createFromDataContext()`** (1 usage) → direct `AnActionEvent()` constructor (v1.4.6)
- **Override-only `actionPerformed()`** (1 usage) → `ActionManager.tryToExecute()` (v1.4.6)
- **`CredentialAttributes(serviceName)`** (2 usages) → `CredentialAttributes(serviceName, key)` (v1.4.6)
- **`ComboBox(E[])`** (6 usages) → `ComboBox(DefaultComboBoxModel(E[]))` (v1.4.3)
- **`JBPasswordField()`** (2 usages) → `JPasswordField()` (v1.4.3)
- **`DialogWrapper(Project, boolean)`** (1 usage) → `DialogWrapper(Project)` (v1.4.3)
- **`TextFieldWithBrowseButton.addBrowseFolderListener()`** → `TextBrowseFolderListener` (v1.4.2)
- **License:** AGPL-3.0 → Apache-2.0 (v1.4.2)
- **Auto Briq Sensitivity** default-on (v1.4.1)
- **Startup timeout fix** — replaced modal dialog with non-blocking notification (v1.4.1)

### Marketplace compatibility status
- **Scheduled-for-removal API:** 0 usages ✅
- **OverrideOnly API violations:** 0 usages ✅
- **Deprecated API:** 0 usages ✅
- All IDE versions 2023.3–2026.2 EAP verified compatible

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
