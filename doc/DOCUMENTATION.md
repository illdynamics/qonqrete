# QonQrete Documentation

**Version:** `v1.0.4-stable` (See `VERSION` file for the canonical version).

This document provides a comprehensive technical reference for the QonQrete Secure AI Construction Loop System.

## Table of Contents
- [System Overview](#system-overview)
- [Execution Flows](#execution-flows)
- [Agent Reference](#agent-reference)
- [Contract System (QONTRACT)](#contract-system-qontract)
- [Container Runtime](#container-runtime)
- [Context & Memory Layers](#context--memory-layers)
- [Configuration Reference](#configuration-reference)
- [Security Model](#security-model)
- [Getting Started](#getting-started)

---

## System Overview

QonQrete is a multi-agent AI orchestration system for secure, observable, and human-in-the-loop software construction. It spawns a crew of AI agents inside a hardened container (the "Qage"), orchestrated by the Qrane, to plan, build, review, and iterate on code.

The core pipeline per cycle is:

```
instruqtor → calqulator → construqtor → inspeqtor → qontextor → qompressor
```

Key architectural principles:
- **Sandboxed execution**: All AI-generated code runs inside containers with dropped capabilities, read-only root, and resource limits.
- **Contract enforcement**: A project constitution (`qontract.d/`) is generated on Cycle 1 and deterministically enforced on all subsequent cycles via AST-based verification.
- **Multi-provider support**: Supports OpenAI, DeepSeek, Gemini, Anthropic, and Qwen through a unified abstraction layer (`lib_ai.py`).
- **Cross-platform**: Auto-detects Docker/Podman on Linux, macOS, WSL, and Windows (Git Bash).
- **Local-first where possible**: Skeleton generation, context indexing, cost estimation, syntax verification, and contract checking are all zero-AI-cost local operations.

---

## Execution Flows

### 1. Initialization (`./qonqrete.sh init`)

1. `qonqrete.sh` detects the OS, container engine, and build backend.
2. Builds the `qonqrete-qage` container image using the appropriate engine and backend.
3. The Dockerfile installs dependencies, creates security users (qrane/worqer), pre-downloads the sentence-transformers model, and configures the entrypoint for privilege dropping.

### 2. Run (`./qonqrete.sh run`)

1. **Validation**: Checks for `config.yaml`, `pipeline_config.yaml`, and `tasq.md` (opens `$EDITOR` if missing).
2. **Qage Creation**: Creates `qage_<timestamp>/` with subdirectories: `tasq.d/`, `exeq.d/`, `reqap.d/`, `qodeyard/`, `struqture/`, `qontext.d/`, `bloq.d/`, `briq.d/`, `qontract.d/`.
3. **Sqrapyard**: If `-s` flag is set and `worqspace/sqrapyard/` has content, copies it into `qodeyard/`.
4. **Config Copy**: Copies `config.yaml`, `pipeline_config.yaml`, and `tasq.md` into the Qage.
5. **Container Launch**: Runs the container with security flags, volume mounts, and API key env vars. The entrypoint fixes permissions and drops to the qrane user.
6. **Qrane Orchestration**: Inside the container:
   - Validates API keys for configured providers.
   - Runs warmup phase if qodeyard has content (Qompressor → Qontextor → Qontrabender).
   - Enters the CyQle loop, executing agents per `pipeline_config.yaml`.
   - At each CheQpoint: autonomous mode continues, user-gated mode prompts for `[Q]ontinue / [T]weaQ / [X]Quit`.
   - ReQap is promoted to become the next cycle's tasq.
7. **Post-Run**: Prompts to save as Qonstruction (or auto-saves with `-n` flag).

### 3. Resume (`./qonqrete.sh resume`)

1. Displays kubectx-style interactive picker of available Qages (or accepts `-q <name>`).
2. Copies all content from the selected Qage to a new `qage_<timestamp>/`.
3. Updates config files from the workspace and injects the latest `tasq.md` as the next cycle.
4. Proceeds as a normal run with full previous context preserved.

### 4. Clean (`./qonqrete.sh clean`)

Three modes:
- **Interactive**: Displays picker, user selects which Qage to delete.
- **Specific**: `./qonqrete.sh clean -q <qage>` — deletes named Qage after confirmation.
- **All**: `./qonqrete.sh clean -A` — deletes all `qage_*` directories after confirmation.

Uses engine-aware deletion (runs a helper container if needed to handle container-created file permissions).

---

## Agent Reference

### Qrane Orchestrator (`qrane/qrane.py`)

The central control loop. Responsibilities:
- Dynamic pipeline loading from `pipeline_config.yaml`
- Agent execution with subprocess management and output filtering
- CheQpoint handling (autonomous/user-gated)
- ReQap promotion to next cycle's tasq
- Warmup phase orchestration (Qompressor → Qontextor → Qontrabender)
- Display filtering: categorizes output into VISIBLE (status), BLOCKED (noise), and CONTENT (code) for clean terminal output

### TasqLeveler (`worqer/tasqleveler.py`) — Optional

- **Runs**: Once, Cycle 1 only (commented out by default in `pipeline_config.yaml`)
- **Purpose**: Enhances tasq.md with dependency graphs, golden path tests, mock infrastructure, success criteria, and phase priority guidance
- **Impact**: +15-20% improvement in output quality
- **Backup**: Original preserved as `tasq_original.md`
- **Complexity Gating**: Skips enhancement for simple tasqs (configurable `min_complexity_score` and `min_lines`)

### InstruQtor (`worqer/instruqtor.py`) — AI Agent

- **Purpose**: Decomposes tasq into atomic briqs and generates the project QONTRACT on Cycle 1
- **Sensitivity Scale**: 0-16, higher = more briqs. Each level has enforced min/max ranges
- **Batched Generation** (v1.0.3+): For sensitivity >= 8, uses 2-phase approach:
  1. Blueprint (JSON) — compact list of briq titles/objectives
  2. Fabrication (batched XML) — full content in chunks of 5
- **QONTRACT Generation** (v1.0.4): Extracts invariants from the tasq (rule headers, imperative patterns) and generates `qontract.d/qontract.md` + `qontract.d/qontract.json`
- **Universal File Rule**: If file EXISTS → modify/extend; if MISSING → create
- **Context**: Reads qodeyard contents, bloq.d skeletons, existing qontract

### CalQulator (`worqer/calqulator.py`) — Local Agent

- **Purpose**: Estimates token count and cost for the upcoming ConstruQtor cycle
- **Logic**: Sums briq content + base context (bloq.d or qodeyard) + deep-read files
- **Output**: Annotates each briq with estimated tokens/cost, prints summary table
- **Cost**: Zero (local calculations only)
- **Skipped**: When construqtor uses `local` provider (no API costs)

### ConstruQtor (`worqer/construqtor.py`) — AI Agent

- **Purpose**: Generates code from briqs, writing to qodeyard
- **Interleaved Pipeline**: For each briq:
  1. Gather context (qontract.md + bloq.d + qontext.d + qodeyard tree)
  2. AI generates code
  3. Parse response, extract files, write to qodeyard
  4. QontractGuard check (contract-relevant briqs)
  5. LoQal verification (syntax + imports)
  6. Retry on failure (up to 3 attempts)
- **Context Wiring** (v1.0.4): Always includes `qontract.d/qontract.md`, Cycle 1 tasq, qodeyard file tree
- **Fail-Fast**: Requires `qontract.d/` to exist for cycles > 1 (via `runtime_checks.py`)
- **Language Detection**: 400+ language identifiers covering all major AI model output formats. Prevents `py` or `js` being created as filenames

### InspeQtor (`worqer/inspeqtor.py`) — AI Agent

Multi-stage review system:
- **Stage 0 — QontractGuard** (deterministic): AST-based check of all qodeyard files against `qontract.json`. FAIL = forces cycle FAIL.
- **Stage 1 — LoQal Verification** (deterministic): Syntax and import checks.
- **Stage 2 — Per-Briq Tactical Reviews** (AI): Reviews each briq with context. Can run batched (90% fewer API calls) or individually.
- **Stage 3 — Global Meta-Review** (AI): Consolidates all per-briq reviews into final reQap with Assessment: SUCCESS / PARTIAL / FAILURE.
- **Context**: Always includes `qontract.d/qontract.md`. Primary source is `qodeyard/*`. Optional: `bloq.d/*` and `qontext.d/*` (with staleness warnings since they run after inspeqtor in the pipeline).
- **Fail-Fast**: Requires `qontract.d/` for cycles > 1.

### QontractGuard (`worqer/qontract_guard.py`) — Local Agent

Deterministic contract verification using Python AST parsing:
- **Forbidden imports**: Detects use of banned modules (e.g., `uuid`)
- **Exact schema fields**: Verifies Pydantic model field sets match contract
- **Forbidden field names**: Class-level detection of banned fields
- **ID type rules**: Annotation checking for int vs str
- **Monotonic ID strategy**: Verifies `next_id=1` + increment or `max()+1` patterns
- **Required endpoints**: Checks route decorators for mandated paths
- **Never silently skips**: Empty or missing contract = FAIL with `CONTRACT_MISSING`

### LoQal Verifier (`worqer/loqal_verifier.py`) — Local Agent

Deterministic post-cycle validation:
- **Syntax validation**: Python `compile()` check
- **Import resolution**: Verifies imported modules exist as files
- **Skeleton comparison**: Expected vs actual function signatures
- **Cross-file consistency**: Function calls match definitions

### Qompressor (`worqer/qompressor.py`) — Local Agent

The "Skeletonizer" — mirrors qodeyard into bloq.d with stripped bodies:
- **Python**: Uses AST to preserve imports, class/function signatures, decorators, docstrings. Bodies replaced with deterministic summaries (mentions called functions, DB mutations, return types).
- **Other languages**: Regex-based structural extraction.
- **Preserves**: Import statements, module-level constants, Pydantic model bodies, route decorators, first N meaningful statements.
- **Indentation Fix** (v1.0.4): Summary comments use actual function body indentation (not hardcoded 4-space). Correct for module-level, class methods, and nested defs.
- **Cost**: Zero (pure local processing)

### Qontextor (`worqer/qontextor.py`) — Dual-Mode Agent

Generates machine-readable symbol maps in qontext.d/:
- **Local Mode** (default, recommended): Deterministic analysis stack:
  - Python AST for structure extraction
  - Docstring parsing for purpose extraction
  - Verb heuristics for purpose inference when docstrings are missing
  - Jedi for type inference and cross-file understanding
  - **Fast mode**: AST + Jedi + heuristics
  - **Complex mode**: Adds sentence-transformers embeddings for semantic search
- **AI Mode** (legacy): Uses an AI provider to generate YAML summaries
- **HuggingFace Cache** (v1.0.1): Model pre-downloaded to `/opt/hf_cache` during build, survives tmpfs mount
- **Cost**: Zero in local mode

### Qontrabender (`worqer/qontrabender.py`) — Local Agent

Policy-driven hybrid caching with variable fidelity:
- **Only active** when ConstruQtor uses Gemini (for Gemini's context caching feature)
- **Modes**: `local_fast`, `local_smart`, `cyber_bedrock`, `cyber_aggressive`, `paranoid_mincloud`, `debug_repro`
- **Variable Fidelity**: Mixes MEAT (full code) and BONES (skeletons) based on configurable rules
- **Schema validation**: Validates caching_policy.yaml before use
- See [QONTRABENDER.md](./QONTRABENDER.md) for full documentation

### AI Provider Abstraction (`worqer/lib_ai.py`)

Unified interface for all AI interactions:
- **OpenAI**: Official library, reads `OPENAI_API_KEY`
- **Gemini**: Official library, reads `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- **Anthropic**: Official library, reads `ANTHROPIC_API_KEY`
- **DeepSeek**: Built-in `DeepSeekProvider` class (OpenAI-compatible API), reads `DEEPSEEK_API_KEY`
- **Qwen**: CLI wrapper around `@qwen-code/qwen-code`, reads `QWEN_API_KEY`
- **Security**: Hardened with timeouts (`MAX_TIMEOUT_SECONDS`), retry limits, and sanitized tracebacks
- **Budget Enforcement**: Tracks token usage per call

---

## Contract System (QONTRACT)

The QONTRACT is QonQrete's project constitution — a set of invariants that ensure code consistency across cycles.

### Lifecycle

1. **Cycle 1 — Generation**: InstruQtor analyzes the tasq for rule headers (`Rules`, `Requirements`, `Constraints`, `Invariants`) and imperative patterns (`MUST`, `SHALL`, `NEVER`, `ALWAYS`, `EXACTLY`). Extracts them into:
   - `qontract.d/qontract.md` — human-readable rules document
   - `qontract.d/qontract.json` — machine-parseable invariants (forbidden imports, schema fields, ID rules, required endpoints)

2. **Cycle 2+ — Enforcement**: Both ConstruQtor and InspeQtor call `runtime_checks.ensure_qontract_present()` at startup. If `qontract.d/` is missing, the pipeline FAIL-FASTSs with an actionable error message. QontractGuard runs deterministic AST checks against all generated code.

3. **Per-Briq Gating**: During ConstruQtor's interleaved build, contract-relevant briqs are checked by QontractGuard after each generation attempt. Violations trigger retries with the violation report injected into the prompt.

### Invariant Types

| Type | What It Checks | Method |
|------|---------------|--------|
| Forbidden Imports | Banned modules (e.g., `uuid`) | AST import node scanning |
| Schema Fields | Exact field sets for named Pydantic models | AST class body analysis |
| Forbidden Fields | Banned field names in classes | AST annotation scanning |
| ID Type | `int` vs `str` for ID fields | AST annotation checking |
| ID Strategy | Monotonic integer (`next_id=1` + increment) | AST pattern matching |
| Required Endpoints | Route decorator paths | AST decorator scanning |

---

## Container Runtime

### Auto-Detection (v1.0.4)

`qonqrete.sh` automatically detects the runtime environment:

**OS Detection**: `uname -s` → Linux / Darwin / WSL (via `/proc/version`) / MSYS (Git Bash)

**Engine Priority**: `CONTAINER_ENGINE` env → CLI flags (`--docker`/`--podman`/`--msb`) → MSB config → auto-detect (docker → podman → error)

**Build Backend**: `BUILD_BACKEND` env → auto-detect (docker checks buildx availability, podman uses plain)

**macOS + Podman**: Automatically runs `podman machine init` and `podman machine start` if needed.

**Windows/MSYS**: Normalizes volume mount paths (`/c/Users/...` → `C:/Users/...`).

### Security Hardening

Container runs with:
- `--read-only` root filesystem (only `/qonq` is writable)
- `--cap-drop=ALL` with minimal add-backs (SETUID, SETGID, CHOWN, FOWNER, DAC_OVERRIDE)
- Resource limits: `--memory=4g`, `--cpus=2`, `--pids-limit=100`
- `--tmpfs /tmp:rw,noexec,nosuid,size=100m`
- Non-root execution via gosu (entrypoint drops from root to qrane user)
- Pinned base image with digest for reproducibility
- Pinned Python dependency versions

---

## Context & Memory Layers

QonQrete provides AI agents with structured, layered context:

| Layer | Directory | Source | Purpose | Cost |
|-------|-----------|--------|---------|------|
| Directive | `tasq.d/` | User + promoted reQaps | Current cycle objective | — |
| Contract | `qontract.d/` | InstruQtor (Cycle 1) | Project invariants | — |
| Structural | `bloq.d/` | Qompressor | Architecture skeletons | Zero |
| Semantic | `qontext.d/` | Qontextor | Symbol maps + embeddings | Zero (local) |
| Code | `qodeyard/` | ConstruQtor | Current source of truth | — |
| Build Log | `exeq.d/` | ConstruQtor | Per-briq summaries | — |
| Review | `reqap.d/` | InspeQtor | Cycle assessments | — |
| Plans | `briq.d/` | InstruQtor | Atomic build steps | — |
| Logs | `struqture/` | All agents | Console + event logs | — |
| Previous | `QONQ_PREVIOUS_LOG` env | Qrane | Previous agent's output | — |

The context assembly in `lib_ai.py` combines base prompt + previous log + relevant context files, optimizing for the AI's context window.

---

## Configuration Reference

### `worqspace/config.yaml`

**Retry Configuration:**
- `retry.enabled`: Enable retry mechanism (default: `true`)
- `retry.max_attempts`: Max attempts per briq (default: `3`)
- `retry.stop_on_briq_fail`: Fail-fast vs fail-tolerant (default: `false`)
- `retry.retry_delay`: Seconds between retries (default: `2`)

**Interleaved Pipeline:**
- `interleaved.enabled`: Per-briq build+verify loop (default: `true`)
- `interleaved.local_validation`: Local syntax check per briq (default: `true`)
- `interleaved.ai_quick_review`: AI review per briq (default: `false`)
- `interleaved.retry_on_review_fail`: Retry on AI review failure (default: `true`)

**Local Verification:**
- `verification.enabled`: Post-cycle verification (default: `true`)
- `verification.checks.syntax`: Python compile check (default: `true`)
- `verification.checks.imports`: Import resolution (default: `true`)
- `verification.checks.skeleton_match`: Signature comparison (default: `true`)

**Agent Configuration:**
- `agents.<name>.provider`: AI provider (`openai`, `deepseek`, `gemini`, `anthropic`, `qwen`, `local`)
- `agents.<name>.model`: Model name
- `agents.inspeqtor.batch_mode`: Batch reviews (default: `false`)
- `agents.inspeqtor.batch_token_roof`: Max tokens per batch (default: `30000`)
- `agents.qontextor.local_mode`: `fast` or `complex` (default: `complex`)
- `agents.qontrabender.mode`: Caching mode (default: `local_smart`)

**Options:**
- `options.cheqpoint`: User-gated mode (default: `false`)
- `options.auto_cycle_limit`: Max cycles (default: `4`)
- `options.briq_sensitivity`: Granularity 0-16 (recommended: `5`)
- `options.mode`: Operational mode (default: `program`)
- `options.use_qompressor`: Enable skeleton generation (default: `true`)
- `options.use_qontextor`: Enable semantic indexing (default: `true`)
- `options.use_qontrabender`: Enable Gemini caching (default: `false`)

### `worqspace/pipeline_config.yaml`

Defines agent execution order. Each agent entry has:
- `name`: Agent identifier
- `script`: Python script filename
- `input`: Input path(s) with `{N}` cycle substitution
- `output`: Output path(s) with `{N}` cycle substitution
- `cycle_1_only`: Only run on Cycle 1 (for TasqLeveler)

### `worqspace/caching_policy.yaml`

Qontrabender configuration. See [QONTRABENDER.md](./QONTRABENDER.md).

---

## Security Model

### Container Security
- Root filesystem is read-only
- All Linux capabilities dropped, only minimal set re-added
- Resource limits prevent DoS (memory, CPU, PIDs)
- `/tmp` mounted as tmpfs with `noexec`
- Non-root execution via gosu

### User Model
- **qrane** (user): Orchestrator, owns `/qonq`
- **worqer** (user): Agent runner
- **qrew** (group): Shared group with setgid for file inheritance

### Code Security
- `lib_security.py`: Path validation, jail enforcement (prevents directory traversal), symlink prevention, file size limits
- `runtime_checks.py`: Fail-fast guards for mandatory pipeline prerequisites
- Dynamic agent loader validates model names against `^[a-zA-Z0-9_]+$`
- API keys only passed via environment variables, never stored in config files

---

## Getting Started

For a step-by-step guide, see **[QUICKSTART.md](./QUICKSTART.md)**.

For architecture diagrams, see **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

For terminology, see **[TERMINOLOGY.md](./TERMINOLOGY.md)**.
