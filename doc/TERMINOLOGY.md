# QonQrete Terminology

**Version:** `v1.0.4-stable` (See `VERSION` file for the canonical version).

This document defines the official vocabulary for the QonQrete Secure AI Construction Loop System.

### Core Components & Roles
- **Qrane**: The orchestrator (`qrane/qrane.py`) that manages the agent pipeline inside the container.
- **worQer**: An AI agent that performs a specific role (`instruQtor`, `construQtor`, `inspeQtor`, etc.).
- **Qrew**: The collection of agents that work together inside the `Qage`.
- **tasqLeveler**: An optional agent that runs ONCE on Cycle 1 to enhance tasq.md with golden path tests, dependency graphs, mock infrastructure, and success criteria. Commented out by default in `pipeline_config.yaml`.
- **qompressor**: A deterministic agent that "skeletonizes" the codebase into `bloq.d/`. Zero AI cost.
- **qontextor**: A dual-mode agent that generates a machine-readable symbol map. Runs locally (AST, Jedi, heuristics, sentence-transformers) or via AI.
- **qontrabender**: A policy-driven hybrid caching agent. Only active when ConstruQtor uses Gemini (for Gemini's context caching).
- **calqulator**: A local agent that provides token and cost estimates. Zero AI cost.
- **QontractGuard**: A deterministic AST-based contract verification module (`qontract_guard.py`) that enforces `qontract.json` invariants against generated code. Zero AI cost.
- **LoQal Verifier**: A deterministic local verification agent that checks syntax and imports without AI.
- **Local Provider**: A provider type for agents that run completely locally (e.g., `calqulator`, `qompressor`, `qontextor`).

### Environment & Structure
- **Qage**: The secure Docker/Podman container (or Microsandbox) that houses the `Qrew`. Named `qage_YYYYMMDD_HHMMSS`.
- **Qodeyard**: The output directory (`qodeyard/`) — the single source of truth for current-cycle code.
- **worQspace**: The shared volume (`worqspace/`) for configuration and agent communication.
- **qontract.d**: The contract directory containing `qontract.md` (human-readable) and `qontract.json` (machine-parseable). Generated on Cycle 1, enforced thereafter.
- **bloq.d**: Skeleton cache from `qompressor`.
- **qontext.d**: Semantic index from `qontextor`.
- **briq.d**: Planned steps (briqs) from `instruQtor`.
- **exeq.d**: Per-briq execution summaries from `construQtor`.
- **reqap.d**: Review summaries from `inspeQtor`.
- **struqture**: Console/event logs per agent.
- **sqrapyard**: Persistent seed directory (`worqspace/sqrapyard/`). Requires `-s` flag.
- **Qonstruction**: A saved project output in `worqspace/qonstructions/`.

### Workflow & Data
- **cyQle**: A full Plan → Execute → Review loop.
- **tasQ**: The high-level user request (`worqspace/tasq.md`).
- **briQ**: A single, atomic step of the plan from `instruQtor`.
- **exeQ**: A per-briq execution summary from `construQtor`.
- **reQap**: A review/recap summary from `inspeQtor`.
- **QONTRACT**: The project constitution — invariants extracted from the tasq on Cycle 1 and enforced on all subsequent cycles (forbidden imports, schema rules, ID strategies, required endpoints).
- **Operational Mode**: Agent persona setting (`--mode`): `program`, `enterprise`, `security`, `performance`, etc.
- **Briq Sensitivity**: Granularity setting (0-16). Higher = more briqs. Enforced with hard min/max ranges.
- **Batched Briq Generation**: 2-phase approach (v1.0.3+) for sensitivity >= 8: Blueprint (JSON) → Fabrication (batched XML). Enables 50-250+ briqs.
- **CheQpoint**: Pause after a cyQle. `true` = user-gated, `false` = autonomous.
- **Universal File Rule**: If a file EXISTS → modify/extend it; if MISSING → create it.

### Container Runtime (v1.0.4)
- **Container Engine**: Docker, Podman, or Microsandbox (MSB). Auto-detected.
- **Build Backend**: `buildx` or `plain`. Auto-detected.
- **OS Detection**: Linux, Darwin (macOS), WSL, MSYS (Git Bash/MinGW).
- **Engine Wrappers**: `engine_build()`, `engine_run()`, `engine_run_helper()` — engine-agnostic.
- **Security Flags**: `--read-only`, `--cap-drop=ALL`, resource limits, tmpfs — applied to container runs.

### Caching & Fidelity
- **Variable Fidelity**: Mixing full code (MEAT) and skeletons (BONES) in cache payloads.
- **MEAT**: Full source code from `qodeyard/`.
- **BONES**: Skeleton code from `bloq.d/`.
- **Volatile**: Frequently changing files excluded from cache.
- **Caching Policy**: Configuration in `caching_policy.yaml` for Qontrabender modes.
- **Core Score**: Computed value (0.0-1.0) indicating file importance.

### User Interaction
- **gateQeeper**: The human user at the `CheQpoint`.
- **CheQpoint Options**: `[Q]ontinue`, `[T]weaQ` (edit), `[X]Quit`.
- **Qommander**: TUI top panel (main execution flow).
- **Qonsole**: TUI bottom panel (raw agent logs).

### Persistence & Resume
- **Resume**: Continue from a previous Qage via `./qonqrete.sh resume`.
- **Interactive Picker**: kubectx-style menu for Qage selection.
- **meta.yaml**: Qonstruction metadata (project name, source qage, date, version).

### Security
- **qrane (user)**: Orchestrator user, runs `qrane.py` via gosu.
- **worqer (user)**: Agent runner user.
- **qrew (group)**: Shared group for qrane/worqer collaboration.
- **Root Dropping**: Start as root → fix permissions → drop to qrane via gosu.
- **lib_security.py**: Path validation, jail enforcement, symlink prevention, structured logging.
