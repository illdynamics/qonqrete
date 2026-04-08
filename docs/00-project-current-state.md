# Project Current State Analysis

## Architecture Overview

QonQrete is a repo-local, containerized, file-driven multi-stage build system with three main layers:

1. Host CLI/runtime bootstrap
   - `qonqrete.sh` detects Docker/Podman/MSB, creates a per-run `qage_*` workspace, mounts it into the container, and launches `qrane/qrane.py`.
   - `entrypoint.sh` prepares `/qonq`, fixes ownership, sets HF cache env, then drops to the non-root `qrane` user.

2. Orchestrator
   - `qrane/qrane.py` is the actual runtime coordinator.
   - It loads `worqspace/config.yaml` and `worqspace/pipeline_config.yaml`, resolves mode/sensitivity/cycles, checks provider env vars, runs the configured agents in order, handles checkpoints, and promotes `reqap` into the next cycle’s `tasq`.

3. Worker/agent layer
   - `worqer/` contains both AI-backed stages and deterministic local helpers.
   - The system is heavily file-contract based: every stage reads and writes convention-based directories inside the current `qage_*`.

The architecture is not a centralized “engine serving arbitrary repos.” The real model is still workspace-local/runtime-local deployment, especially in `.qonqrete/` for IDE flows.

## Core Components

Core runtime:
- `qonqrete.sh`: CLI entrypoint, init/run/resume/clean, qage creation, sqrapyard seeding, qonstruction save/delete.
- `qrane/qrane.py`: orchestration loop, agent execution, checkpoint logic, TUI integration, log filtering.
- `qrane/paths.py`: path conventions for qage artifacts and logs.
- `qrane/tui.py`: optional split-screen terminal UI.

Primary AI or pipeline stages:
- `worqer/tasqleveler.py`: optional cycle-1 tasq enhancer.
- `worqer/instruqtor.py`: briq planner and QONTRACT generator.
- `worqer/construqtor.py`: code generation/modification with retries and per-briq local validation.
- `worqer/inspeqtor.py`: deterministic + AI review aggregation.

Deterministic/local support:
- `worqer/calqulator.py`: token/cost estimation and briq annotation.
- `worqer/loqal_verifier.py`: syntax/import/skeleton-match verification.
- `worqer/qontract_guard.py`: AST-based contract enforcement.
- `worqer/runtime_checks.py`: fail-fast contract presence checks.
- `worqer/qompressor.py`: deterministic skeletonizer.
- `worqer/qontextor.py`: context/index generation, mostly AST/local with optional semantic model/AI mode.
- `worqer/qontrabender.py`: cache payload assembly/ledger, mainly for Gemini caching workflows.
- `worqer/lib_ai.py`: provider abstraction and prompt budgeting.
- `worqer/lib_security.py`: path jail, safe I/O helpers, structured security logging, config validation.

IDE wrappers:
- `vscode-extension/`
- `intellij-plugin/`

## Execution Flow

Actual runtime flow today:

1. User edits `worqspace/tasq.md` or workspace-root `tasq.md` via IDE wrapper.
2. `qonqrete.sh run` creates `worqspace/qage_YYYYMMDD_HHMMSS/`.
3. It copies config and tasq into the qage.
4. If `--sqrapyard` is set, `worqspace/sqrapyard/*` is copied into `qage/.../qodeyard/`.
5. Container starts and mounts that qage as `/qonq`.
6. `qrane.py` runs inside the container with `QONQ_WORKSPACE=/qonq`.
7. If seeded `qodeyard/` is non-empty, warmup runs:
   - `qompressor`
   - `qontextor`
   - `qontrabender`
8. For each cycle, `qrane.py` reads `pipeline_config.yaml` and executes agents in listed order.
9. After `inspeqtor`, `qrane.py` hits a checkpoint:
   - autonomous: auto-promotes reqap into next cycle tasq
   - user-gated: user chooses continue/tweak/quit
10. Resume copies an old qage into a new qage, overlays updated workspace config/tasq, then continues as a new run.
11. End of run:
   - preserve qage
   - delete qage
   - or save as `worqspace/qonstructions/<name>/`

Important implementation note:
- The actual pipeline order in `worqspace/pipeline_config.yaml` is:
  - `tasqleveler`
  - `instruqtor`
  - `calqulator`
  - `construqtor`
  - `qontextor`
  - `qompressor`
  - `qontrabender`
  - `inspeqtor`
- This conflicts with several docs/comments that describe `inspeqtor` before `qontextor`/`qompressor`.

## Current Agents

- `tasqleveler`
  - Present.
  - Optional, cycle-1-only.
  - Reads `tasq.d/cyqle1_tasq.md`, may overwrite it with an AI-expanded version, and writes a backup as `*_original.md`.
  - Adds dependency graph, golden-path tests, mock infrastructure, success criteria, token-priority guidance.
  - Has a complexity gate. With current defaults (`min_complexity_score: 200`, `min_lines: 200`), it will skip many normal tasks.
  - Quality checks are heuristic only: length thresholds, marker detection, simple truncation detection.
  - Limitations:
    - no deterministic validation of enhancement correctness
    - whole-document rewrite, not structured augmentation
    - AI failure silently falls back to original tasq
    - effectively conservative due to high skip thresholds

- `instruqtor`
  - Present.
  - Main planner.
  - Decomposes tasq into briqs with enforced briq-count ranges based on sensitivity.
  - Uses a two-phase blueprint/fabrication approach for very high briq counts.
  - Generates QONTRACT in cycle 1:
    - `qontract.d/qontract.json`
    - `qontract.d/qontract.md`
  - Extracts invariants from tasq text heuristically:
    - forbidden imports
    - schema fields
    - forbidden fields
    - id type/strategy
    - required endpoints
  - Injects relevant contract snippets into briqs based on inferred scope tags.

- `construqtor`
  - Present.
  - Primary code-writing agent.
  - Reads briqs and writes directly into `qodeyard/`.
  - Supports retry config and interleaved per-briq processing.
  - Per briq:
    - AI generation
    - local syntax/import validation
    - optional per-briq QontractGuard
    - optional AI quick review
    - per-briq exeQ markdown
  - Loads constitutional context from:
    - `qontract.md`
    - cycle 1 tasq
    - structure snapshot
    - `qontext.d`/`bloq.d` or `qodeyard`
  - Fail-fast on missing contract for cycles > 1.

- `inspeqtor`
  - Present.
  - Final review stage.
  - Runs:
    - Stage 0: full-cycle QontractGuard
    - Stage 1: LoQal verification
    - Stage 2: per-briq AI reviews
    - Stage 3: meta-review aggregation
  - Writes review artifacts into `reqap.d/`.
  - If QontractGuard fails, overall result is forced to failure.

- Other present components
  - `calqulator`
  - `qontextor`
  - `qompressor`
  - `qontrabender`
  - `qontract_guard`
  - `loqal_verifier`

Absent components explicitly confirmed:
- No `Qrystallizer`
- No `Qualifier` agent

## Validation & Guardrails

- local (syntax/tests)
  - Local verification exists in-repo and is deterministic, not AI-based.
  - `loqal_verifier.py` checks Python syntax, local import resolution, and optional skeleton-vs-qontext signature matching.
  - `qontract_guard.py` enforces contract invariants via Python AST.
  - `runtime_checks.py` fail-fast checks for mandatory QONTRACT files on cycles > 1.
  - `construqtor.py` also runs a lighter per-briq local validator before moving on.
  - This is local/system logic, not an AI reviewer.

- AI-based (if any)
  - `tasqleveler`, `instruqtor`, `construqtor`, and `inspeqtor` use AI providers through `lib_ai.py`.
  - `construqtor` can run optional AI quick review per briq.
  - `inspeqtor` does per-briq and meta AI review.
  - Guardrails are stronger on Python than on other languages because the deterministic checks are AST/Python-centric.

Other guardrail/security mechanisms:
- container hardening in `qonqrete.sh`
- non-root runtime in `entrypoint.sh`
- prompt budget enforcement in `lib_ai.py`
- path jail / safe read-write / structured security logging in `lib_security.py`

Important caveat:
- `lib_security.py` is more capable than what the rest of the code actively uses. The security helper library exists, but broad adoption across the pipeline is limited.

## CLI / Sqrapyard Flow

CLI behavior:
- `init`: builds versioned image.
- `run`: fresh qage.
- `resume`: clones an existing qage into a new qage, then re-runs.
- `clean`: deletes qages interactively or directly.
- optional flags:
  - `--auto`
  - `--user`
  - `--mode`
  - `--briq-sensitivity`
  - `--cyqles`
  - `--sqrapyard`
  - `--qonstruction-name`
  - runtime engine flags

Sqrapyard behavior:
- `--sqrapyard` is opt-in only.
- On fresh run, `worqspace/sqrapyard/*` is copied into the new qage’s `qodeyard/`.
- If `sqrapyard/tasq.md` exists, it is ignored in favor of `worqspace/tasq.md`.
- If seeded code is present, `qrane.py` does a warmup pass to build skeletons, context, and cache before cycle 1.

IDE behavior:
- VS Code and IntelliJ do not replace the CLI.
- They sync workspace-root `tasq.md` into internal `.qonqrete/worqspace/tasq.md`.
- They launch `./qonqrete.sh ...` in bash.
- They track completion via marker files like `.qonqrete_run_<ts>.marker`.
- They store run UI state separately from core runtime state.

## State Management

Primary persistent state is file-based.

Workspace-level persistent inputs:
- `worqspace/config.yaml`
- `worqspace/pipeline_config.yaml`
- `worqspace/tasq.md`
- `worqspace/sqrapyard/`
- `worqspace/caching_policy.yaml`

Per-run state:
- `worqspace/qage_YYYYMMDD_HHMMSS/`
- Main subdirs:
  - `tasq.d/`
  - `briq.d/`
  - `qontract.d/`
  - `qodeyard/`
  - `exeq.d/`
  - `reqap.d/`
  - `qontext.d/`
  - `bloq.d/`
  - `struqture/`

Saved snapshots:
- `worqspace/qonstructions/<name>/`

Cycle-to-cycle state progression:
- `reqap.d/cyqleN_reqap.md` is promoted into `tasq.d/cyqleN+1_tasq.md`.

Cache/persistence:
- `qontrabender` maintains payloads, manifest, ledger, active cache state, and sync metadata.

Notable inconsistency:
- `qrane/paths.py` defines `qache_dir` as `sqrapyard/qache.d`, while docs and pipeline descriptions treat `qache.d/` as a qage-level artifact. That looks like a real path-model mismatch.

## Strengths

- Clear file-based artifact model; easy to inspect runs after the fact.
- Good separation between orchestration and worker scripts.
- Deterministic contract enforcement exists and is not just prompt-based.
- Retry/interleaved processing in `construqtor` is more mature than the docs imply.
- IDE wrappers are pragmatic and thin; they mostly stay out of runtime logic.
- Resume/save/delete flow is concrete and operational.
- Container hardening is explicit and meaningful.

## Weaknesses / Gaps

- Documentation, comments, and actual pipeline order are not consistently aligned.
- No `Qrystallizer`.
- No `Qualifier`.
- Deterministic validation is heavily Python-centric.
- `lib_security.py` is stronger than its actual integration footprint.
- No strongly typed run-state object; most orchestration state is implicit in files, env vars, and cwd.
- `calqulator` mutates briq files by annotating headers, so it is not a pure estimator.
- Qontrabender/cache pathing appears internally inconsistent.
- Core logging is fragmented across markdown artifacts, raw logs, event logs, IDE marker files, and optional cache ledgers.
- The repo still depends on repo/workspace-local runtime deployment, not a more modular shared-engine architecture.

## Risks

- Pipeline-order mismatch is the biggest architectural risk. The code executes the YAML order, but docs and some in-code comments describe a different order. That can produce wrong operator assumptions.
- Contract and local verification mainly protect Python code. Non-Python generation has much weaker deterministic guardrails.
- `construqtor` writes incrementally into `qodeyard/` with no transactional rollback. Failed attempts can leave partial state.
- Tasq enhancement is heuristic and can silently skip or silently fall back.
- Contract extraction in `instruqtor` is regex/heuristic driven, so important invariants can be missed or mis-parsed.
- Security helper code exists, but broad usage is inconsistent, so some safety claims are stronger on paper than in active paths.
- Auditability exists, but there is no single authoritative run manifest tying all stage outcomes together.

## Observations

- The current repository is more advanced than a simple “plan/build/review” shell, especially in `construqtor` and `inspeqtor`.
- The intended architecture appears to be ahead of the implemented architecture in naming and documentation, but not in `Qrystallizer`/`Qualifier`; those are simply absent.
- “Local verification is handled by the system, not AI agents” is consistent with the codebase: deterministic checks are implemented locally in Python modules.
- The strongest current architectural pattern is not agent autonomy; it is staged file production plus deterministic gating.
- The most important gap vs intended architecture is not missing polish. It is inconsistency: docs, pipeline config, and stage assumptions do not fully agree.

Static analysis only. No files were modified.
