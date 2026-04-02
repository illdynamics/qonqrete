# QonQrete Release Notes

## v1.2.2

### 🔄 Refactor
- Migrated `loqal_verifier` into Qualifier
- Removed fragmented validation paths
- Centralized all execution and validation logic

### 🧪 Quality System
- Qualifier is now the single execution authority
- All build/test/runtime validation runs through Qualifier
- Introduced unified `quality.d/` validation artifacts

### 🧠 Architecture
- Clear separation:
  - ConstruQtor (build)
  - Qualifier (execute)
  - InspeQtor (evaluate)
  - Qrane (decide)
- Eliminated duplicate validation responsibilities

### 🚀 Improvements
- More reliable completion detection
- Reduced false positives (“it works” when it doesn’t)
- Cleaner validation pipeline

### 🐛 Fixes
- Inconsistent validation across agents
- Hidden execution paths outside main pipeline
- Fragmented verification logic

---

## v1.2.1 — Autonomous Execution & Quality Assurance

This release brings the most significant shift in project architecture to date: **Deterministic Quality Gates**. With the introduction of Qrystallizer and Qualifier, QonQrete now moves from "hope-based execution" to "validation-based completion."

### 🚀 New
- **Qrystallizer agent**: Performs preflight analysis on Cycle 1 to extract stable requirements, assumptions, and readiness gaps. Prevents AI "scope drift" by anchoring the project constitution.
- **Qualifier agent**: The dedicated execution-validation agent. It is the only agent permitted to run builds, tests, and smoke commands. Outputs structured logs to `quality.d/`.
- **Structured Verdict JSON**: Cycle completion is now determined by a machine-readable `verdict.json` produced by InspeQtor, integrating Guard, Quality, and Review statuses.
- **Auto-cycle mode (`cycles = 0`)**: QonQrete now dynamically estimates the required number of cycles and stops automatically when requirements are met and quality gates pass.
- **`program` vs `innovative` mode split**: `program` mode enforces strict compliance with the requirement ledger, while `innovative` mode allows for architectural and UX enhancements.
- **`llamacpp` provider**: Support for external LLM endpoints (OpenAI-compatible) allowing for local model execution or custom service integration.

### 🔧 Improvements
- **Robust stop-on-success logic**: Replaced fragile markdown parsing with deterministic verdict evaluation.
- **Pipeline Clarity**: Clearly separated code generation (ConstruQtor) from runtime validation (Qualifier).
- **Context Injection**: Better wiring of Cycle 1 requirements and QONTRACT artifacts into subsequent cycles.
- **IDE Integration**: Syncing of auto-mode and provider settings across VS Code and IntelliJ.

### 🧠 Architecture
- **Layered Validation**: Introduces `qrystal.d/` (preflight), `quality.d/` (execution), and `reqap.d/` (review/verdict) as the three pillars of project integrity.
- **Requirement-Driven Lifecycle**: Groundwork for automated requirement coverage tracking.
- **Provider Abstraction**: Decoupled agent logic from specific LLM providers.

### 🐛 Fixes
- Autonomous mode failing to stop when project was technically complete.
- Hallucinations causing the creation of redundant files during complex refactors.
- Retry paths occasionally losing specific provider configurations.
- Documentation drift regarding pipeline ordering and artifact locations.

---

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
