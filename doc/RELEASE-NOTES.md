# QonQrete Release Notes

## v1.2.0-stable — Workspace Deployment & Hassle-Free Bootstrap

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
