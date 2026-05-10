## v1.4.0 — MLcon Edition: Truthful Inspection, Streaming UX Cleanup, Hybrid Venice Alignment + IntelliJ Compatibility Series (v1.4.0–v1.4.5)

### Core runtime (v1.4.0)

This release ships a coordinated patch pass across inspection truthfulness, terminal streaming UX, runtime wiring, and IDE plugin alignment, and corresponds to the MLcon-proven release snapshot.

#### Inspection / Truthfulness
- Final-file evidence from `qodeyard/` is now explicitly marked authoritative in InspeQtor review prompts.
- Batched and per-briq review snippets now include deterministic metadata:
  - `file_bytes`
  - `snippet_chars`
  - `snippet_truncated`
- Prompt snippet truncation is now treated as prompt-budget clipping only, never as proof that the on-disk file is truncated.
- InspeQtor tactical/meta AI review calls now disable previous-log injection to reduce stale relay influence.
- Final verdict synthesis now prioritizes deterministic validation and completion criteria over advisory AI review noise.
- Advisory briq-review findings are downgraded when deterministic gates pass and no longer force a blocking verdict by themselves.

#### Frontend deterministic validation
- localStorage key checks now resolve:
  - direct string literals
  - const literal indirection
  - simple alias chains
  - simple const-object member indirection (`STORAGE_KEYS.foo`)
- Truly missing required keys and undeclared extra keys remain deterministic failures.

#### Streaming UX (terminal rendering)
- Removed outer Qrane heartbeat chatter.
- Removed inner ConstruQtor `[Still working] ...` chatter.
- Preserved full raw stream capture to qonsole/audit logs.
- Added concise default terminal rendering for streamed heredoc payloads:
  - `Writing <file>...`
  - `Wrote <file>`
  - fallback `Writing code...`
- Added TTY-only runtime toggles:
  - `TAB` => raw stream mode
  - `Shift+TAB` => concise mode
- Mode hints are edge-triggered status messages only; they are not prefixed per streamed line and are not leaked into child logs.

#### Runtime wiring / defaults
- Primary agent defaults aligned to `venice / deepseek-v3.2`:
  - `qrystallizer`
  - `instruqtor`
  - `construqtor`
  - `inspeqtor`
- ConstruQtor default `coding_mode` is now `hybrid`.
- Runtime config defaults in `worqspace/config.yaml` aligned to the same target bindings.
- Launcher now supports `-N/--no-sync`:
  - default behavior still syncs generated output back to the repo root
  - `--no-sync` skips that sync-back and keeps output in Qage/Qonstruction paths
  - run lineage now records `repo_sync_mode` (`sync_to_repo_root` or `no_sync`) for audit truthfulness

#### IDE plugin alignment
- VS Code and IntelliJ AI-config surfaces now focus on the four primary runtime agents:
  - `qrystallizer`, `instruqtor`, `construqtor`, `inspeqtor`
- Removed stale shared-sidebar/provider surfaces for local-only runtime providers (`mlx`, `llama-cpp`).
- Updated plugin AI defaults to `venice / deepseek-v3.2` for the primary agents.

#### Control-flow and continuation hardening (v1.3.x → v1.4.0 line)
- Resume semantics preserve pass lineage explicitly:
  - queued `pending_next_pass_kind` is honored
  - interrupted active-pass semantics are restored instead of silently defaulting to build
- Intake clarification blocking uses explicit `BLOCKED` / `RUN_WAITING_FOR_INPUT` states and resume re-enters cycle-1 clarification semantics when applicable.
- Validation execution-mode reporting is evidence-driven (`NONE`, `STATIC_ONLY`, `EXECUTED`, `MIXED`) and no longer overclaims executed coverage from markdown presence alone.

### v1.4.1–v1.4.5 — IntelliJ compatibility patch series

The v1.4.x patches (v1.4.1 through v1.4.5) are IDE-plugin-only updates. No core runtime changes. The series resolves all IntelliJ Platform API deprecation warnings across IDE versions 2023.3–2026.2 EAP.

#### v1.4.1 — JetBrains Compatibility & Auto Briq Sense Default-On
- Replaced 8 scheduled-for-removal API usages (`AnActionEvent.createFromDataContext`, deprecated constructors, OverrideOnly `actionPerformed` calls).
- Fixed startup timeout caused by modal `showAndGet()` during project startup (replaced with non-blocking notification balloon).
- Made **Auto Briq Sensitivity** the default for both IDE plugins.

#### v1.4.2 — Apache License Migration & JetBrains API (Final Pass)
- **License changed from AGPL-3.0 to Apache-2.0** for broader permissive use.
- Resolved remaining `TextFieldWithBrowseButton.addBrowseFolderListener()` deprecation.
- `CredentialAttributes(String)` usages annotated with `@Suppress("DEPRECATION")` — modern Builder API unavailable on 2023.3 minimum.

#### v1.4.3 — Final API Compatibility & Marketplace Cleanup
- `ComboBox(E[])` → `ComboBox(DefaultComboBoxModel(E[]))` (6 usages).
- `JBPasswordField()` → `JPasswordField()` (2 usages).
- `DialogWrapper(Project, boolean)` → `DialogWrapper(Project)` (1 usage).
- Removed unused variables and stale `build.gradle.kts.bak`. Marketplace verdict clean across all IDE versions.

#### v1.4.4 — Plugin API Cleanup & Release Hygiene
- Replaced 8 `ActionUtil.invokeAction()` calls with modern `AnActionEvent` pattern.
- Suppressed 2 deprecated `CredentialAttributes()` constructor warnings.
- Fixed bootstrap/hygiene: executable `qonqrete-bootstrap.sh`, zip packaging fixes, smoke tests, stale task file cleanup.

#### v1.4.5 — JetBrains API Deprecation Resolution (Zero Warnings)
- `AnActionEvent.createFromDataContext()` → direct `AnActionEvent()` constructor.
- Override-only `actionPerformed()` → `ActionManager.tryToExecute()`.
- `CredentialAttributes(serviceName)` → `CredentialAttributes(serviceName, key)` (2-arg constructor).
- **Result: 0 scheduled-for-removal, 0 override-only, 0 deprecated API.** Marketplace clean across 2023.3–2026.2 EAP.

---

## v1.3.12 — Hardened `direct` Coding Mode & Determinism

Significant upgrades to ConstruQtor's tool-based coding system and execution determinism.

### ConstruQtor Hardening
- **Mode-Aware Prompt Building:** Monolithic prompts split into strategy-specific builders. `direct` mode now receives a clean tool-first contract with no heredoc leakage.
- **Hardened Direct Write:** All tool-based writes now route through `safe_write_file` with a mandatory `validation-root` jail. Rejects path traversal and symlink escapes.
- **Cumulative Sandbox Validation:** Repair-forward loop now validates the full cumulative candidate delta in the attempt workspace, catching cross-file regressions early.
- **Robust Fallback:** If tool calls are absent, the system now automatically falls back to fenced Markdown block extraction if present, or fails loudly if no usable output exists.
- **Manifest Propagation:** `coding_mode` is now explicitly recorded in all attempt manifests and build reports for downstream auditability.

### Determinism & Stability
- **Sorted Sandbox Diffs:** `os.walk` iterations are now sorted, ensuring deterministic changed-file discovery order.
- **Deterministic Staging:** File staging and commit sequences are sorted by relative path for stable manifests.
- **Strict Config Validation:** `coding_mode` is strict and fails loud on invalid values.

## v1.3.0 — Hardened Sandbox, Agent Renames, Legacy Cleanup

Major security hardening, agent identity cleanup, and removal of accumulated legacy compatibility layers.

### Security & Container Hardening

- **gosu eliminated** — container runs as `qrane` via Dockerfile `USER` directive. No root phase, no privilege transition at runtime.
- **HOST_UID build-arg matching** — on Linux/WSL, container qrane UID matches host user UID at build time. Bind-mounted files are natively owned by the host user. No chmod/chown helpers needed.
- **Zero capabilities** — `--cap-drop=ALL` with no caps added. Combined with `--security-opt=no-new-privileges` to block any re-escalation.
- **Read-only rootfs** — `--read-only` on the container, dev code mounts (`qrane/`, `worqer/`) mounted `:ro`.
- **Hardened tmpfs** — `/tmp` and `/home/qrane/.cache` mounted with `noexec,nosuid,nodev`.
- **docker-entrypoint.sh eliminated** — umask inlined in Dockerfile `ENTRYPOINT`. One less file, one less attack surface.
- **API key passthrough** — keys passed via `-e KEY` (env passthrough) instead of `-e KEY=VALUE` (argv exposure).
- **Helper containers deleted** — `fix_qage_permissions` and `engine_run_helper` removed entirely. UID matching makes them unnecessary.
- **File permissions tightened** — dirs `0750`, files `0640`, world gets nothing. No more `a+rwX` sprays.

### Agent Renames

- `guard.py` → `qonstrictor.py` (Qonstrictor)
- `qontract_guard.py` → `qonfirmer.py` (Qonfirmer)
- `loqal_verifier.py` → `qualifier.py` (Qualifier)
- Display-name override system deleted — agent display names now derive from filenames via `.replace('q','Q')`.

### Engine & Build

- **Podman preferred** over Docker in auto-detection (rootless-native, no daemon).
- **Buildx is Docker-only** — podman always uses plain builds.
- `CONTAINER_ENGINE` env override bug fixed (was captured after being blanked).
- Image tag includes host UID on Linux/WSL for per-user cache correctness.
- Resource limits removed — container gets full host resources.

### Versioning

- `VERSION` file is the single source of truth. No hardcoded fallbacks.
- Variable naming unified: `QONQ_V` → `QONQ_VERSION` everywhere.
- `QONQ_VERSION` passed to container via `-e` at runtime, not baked into image.
- `IMAGE_NAME_LEGACY` tag removed (was duplicate of `:latest`).

### Legacy Removal

- `--legacy-cycle-continuation` flag removed from CLI.
- `legacy_cycle_continuation_enabled()` function deleted.
- `promote_reqap()` function deleted (was the legacy reqap→tasq continuation path).
- `QONQ_LEGACY_QAGE_ID` and `QONQ_CANONICAL_RUN_ROOT` env vars removed.
- `runs/` and `state/` directories deleted — no more symlink tracking. `resolve_target_qage` uses filesystem timestamps.
- `legacy_alias` parameter renamed to `agent_name` throughout manifest system.
- All `legacy_*` manifest field names cleaned.

### Shell Script Cleanup

- `set -euo pipefail` restored (was `set -uo` due to a landmine in `print_runtime_info()` — fixed with `return 0`).
- `PY_ARGS` converted from string to bash array — no shell-injection surface.
- `resolve_absolute_path()` rewritten using `python3 os.path.abspath` — no edge-case bugs.
- Manifest parsing via `python3 json.load`, not `grep | sed`.
- `save_qonstruction_core()` extracted from duplicate save paths.
- Dead code removed: `CONFIG_FILE`, `host_gid()`, shadow symlinks, `IMAGE_NAME_LEGACY`.
- `copy_dir_contents` excludes `.DS_Store` and `._*` automatically.

### IDE Plugins

- Phantom CLI flags (`--tui`, `--msb`, `--wonqrete`) removed from both VS Code and IntelliJ.
- Agent config editors updated: `tasqleveler` → `qrystallizer`, added `qonstrictor`.
- Stale `entrypoint.sh` references removed from deploy actions.
- VS Code dead import (`ALL_API_KEYS`) removed.
- Secret management verified: VS Code uses `SecretStorage` (OS keychain), IntelliJ uses `PasswordSafe`.

### CI/CD

- `runtime-release.yml` updated — removed stale `entrypoint.sh`, `Sandboxfile`, root `qonqrete.jpg`.

### Documentation

- README image path fixed (`qonqrete.jpg` → `qrane/qonqrete.jpg`).
- All docs updated to current agent names and CLI flags.
- Version strings synchronized to `1.3.0` across all manifests.

## v1.2.0 — Workspace Deployment & Hassle-Free Bootstrap

This is the **first globally-publishable release** of both the VS Code extension and IntelliJ plugin. Users can now install QonQrete from the IDE marketplace and be productive in under a minute — no manual cloning, no command line setup.

### Headline: One-Click Workspace Deployment

Both IDE integrations now implement identical workspace-local deployment:

1. Install the extension/plugin
2. Run **"QonQrete: Deploy to Workspace"**
3. Create a **tasq.md** at your project root
4. Run — auto-init handles the rest

The runtime deploys into `<workspace>/.qonqrete/` as a hidden directory, keeping the project clean. The user-facing `tasq.md` lives at the workspace root. The IDE syncs it into the runtime before each run.

### New commands (both IDEs)

| Command | What it does |
|---------|-------------|
| **Deploy to Workspace** | Downloads versioned release zip → extracts to `.qonqrete/` → validates → updates `.gitignore` |
| **Create tasq.md** | Creates a starter template at workspace root and opens it |
| **Run Tasq** | Now auto-syncs root tasq, auto-inits if image missing, offers Deploy if runtime not found |

### Core runtime changes

- **Versioned image naming**: `qonqrete-qage:1.2.0` (also tagged `:latest` and legacy untagged for backward compat)
- Runtime remains fully script-relative — zero architectural disruption

### VS Code extension v1.2.0

- New: `Deploy to Workspace` command with zip download + git clone fallback
- New: `Create tasq.md` command
- New: Auto-init on first Run Tasq (builds container image automatically)
- New: Root tasq.md sync before every run
- New: `.gitignore` auto-management
- New: `.qonqrete/qonqrete.sh` added to path discovery (preferred over legacy paths)
- New: Sidebar Deploy + Create Tasq buttons
- Updated: Status bar suggests Deploy when runtime not found
- Updated: Welcome message offers Deploy
- Updated: Activation events include `.qonqrete/qonqrete.sh`

### IntelliJ plugin v1.2.0

- New: `Deploy to Workspace` action with zip download + git clone fallback
- New: `Create tasq.md` action
- New: Auto-init on first Run Tasq
- New: Root tasq.md sync before every run
- New: `.gitignore` auto-management
- New: `.qonqrete/qonqrete.sh` in path discovery (preferred)
- New: Tool window Deploy + Create Tasq buttons
- Updated: RunTasq offers Deploy when runtime missing, Create tasq when tasq missing
- Updated: Versioned image detection

### Backward compatibility

- Legacy paths (`qonqrete.sh` at workspace root, `qonqrete/qonqrete.sh` subdirectory) remain as fallback detection
- Legacy untagged `qonqrete-qage` image name still checked
- Existing worqspace-only workflows continue to work
- No changes to core runtime architecture

---

## v1.1.9-stable

This release syncs the repository around the `v1.1.9-stable` state and reflects the biggest shift since `v1.0.4-stable`: **QonQrete is no longer just a core CLI runtime — the repo now also includes IDE integrations for VS Code and JetBrains tooling.**

(See previous release notes for v1.1.9 and earlier details.)
