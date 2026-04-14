# Project Current State Analysis

## Architecture Overview
QonQrete is currently a file-based, container-driven orchestration system with three practical layers: a host CLI in `qonqrete.sh`, an in-container orchestrator in `qrane/qrane.py`, and a set of worker modules in `worqer/` that operate against a per-run qage directory under `worqspace/qage_*`.

A fresh run creates a new qage, copies config and task material into it, optionally seeds `qodeyard/` from `worqspace/sqrapyard/`, then launches the container with the qage mounted as `QONQ_WORKSPACE=/qonq`. Inside the container, `qrane.py` reads `config.yaml` and `pipeline_config.yaml` from that mounted qage and executes agents in configured order.

The working state is qage-local, not centralized. Each qage contains task files, briqs, code, review artifacts, context artifacts, logs, and optional cache artifacts. Resume works by cloning a prior qage into a new qage and continuing from there. Qonstructions are just copied qage snapshots saved under `worqspace/qonstructions/`.

There is no Qrystallizer in the repository. There is no Qualifier agent in the repository. The current architecture is still tasq enhancement + planning + codegen + review + context/caching helpers.

## Core Components
- `qonqrete.sh`: Host entrypoint. Detects OS and container engine, builds image, creates qages, copies workspace files, supports `init`, `run`, `resume`, `clean`, qage deletion, and qonstruction save flow.
- `qrane/qrane.py`: Runtime orchestrator. Resolves mode/sensitivity/cycles, validates provider env vars, performs optional warmup scans, executes pipeline stages, handles cheqpoints, and promotes `reqap` into the next cycle’s tasq.
- `qrane/paths.py`: Path helper for qage-local directories and log file naming.
- `worqer/instruqtor.py`: AI planning agent. Decomposes tasq into briqs and generates `qontract.d/qontract.{json,md}` on cycle 1.
- `worqer/construqtor.py`: AI code generation agent. Writes directly into `qodeyard/`, performs per-briq local validation, optional per-briq AI quick review, optional per-briq QontractGuard gating, and writes per-briq execution summaries.
- `worqer/inspeqtor.py`: Review pipeline. Runs deterministic contract checks, deterministic local verification, per-briq AI review, then AI meta-review, and writes final `reqap`.
- `worqer/tasqleveler.py`: Cycle-1 tasq enhancer that rewrites the tasq in place after backing up the original.
- `worqer/loqal_verifier.py`: Deterministic verifier for Python syntax, local-import resolution, and `qontext` signature comparison.
- `worqer/qontract_guard.py`: Deterministic Python-AST contract enforcement for imports, schema fields, ID rules, and required endpoints.
- `worqer/qontextor.py`: Context indexer. Local mode is mostly Python-aware AST/Jedi-based analysis; non-Python gets summary-style output.
- `worqer/qompressor.py`: Deterministic skeletonizer. Strongest behavior is Python-specific; other languages use a regex-based structural strip.
- `worqer/qontrabender.py`: Policy-driven cache payload builder with manifest and SQLite ledger in `qache.d/`.
- `worqer/calqulator.py`: Local token/cost estimator that annotates briq headers in place.
- `worqer/lib_ai.py`: Provider abstraction for OpenAI, Gemini, Anthropic, DeepSeek, Qwen, OpenRouter, with prompt budget assembly.
- `worqer/lib_security.py`: Security utilities for jailed path validation, safe reads/writes, signal handling, and structured security logging, but it is only lightly integrated into the active runtime.
- `vscode-extension/` and `intellij-plugin/`: IDE wrappers around the CLI. They deploy the runtime into `.qonqrete/` and invoke `./qonqrete.sh`, they do not replace the core runtime.

## Execution Flow
A normal `run` flow is:
1. `qonqrete.sh run` validates `worqspace/config.yaml` and `worqspace/pipeline_config.yaml`.
2. It creates `worqspace/qage_<timestamp>/` with `tasq.d`, `briq.d`, `qodeyard`, `exeq.d`, `reqap.d`, `struqture`, `qontext.d`, `bloq.d`, and `qontract.d`.
3. It copies `config.yaml`, `pipeline_config.yaml`, and `tasq.md` into the qage. If `--sqrapyard` is used, it copies `worqspace/sqrapyard/*` into `qodeyard/`.
4. It launches the container and runs `python3 qrane/qrane.py`.
5. `qrane.py` optionally performs warmup if seeded `qodeyard/` is non-empty: `qompressor`, `qontextor`, then `qontrabender`.
6. For each cycle, `qrane.py` loads `pipeline_config.yaml`, resolves agent scripts, and executes them in pipeline order.
7. After the pipeline, `handle_cheqpoint()` either continues automatically or prompts the user, and `promote_reqap()` writes `tasq.d/cyqle{N+1}_tasq.md`.
8. When the container exits, `qonqrete.sh` optionally saves the qage as a qonstruction or preserves/deletes it.

A `resume` flow clones a prior qage into a new qage, refreshes config and pipeline files from `worqspace/`, optionally adds a new tasq as the next cycle file, and then runs the same container/orchestrator flow.

## Current Agents
- `tasqleveler`
  - Present and active in `worqspace/pipeline_config.yaml`.
  - Runs only on cycle 1 by both pipeline metadata and runtime guard on `CYCLE_NUM`.
  - Reads the cycle tasq, computes a crude complexity score, may skip enhancement for simple tasqs, and uses AI to rewrite the tasq in place.
  - Backs up the original tasq as `tasq_original.md` before overwriting.
  - Limitations:
    - It mutates the canonical tasq file in place rather than producing a separate derived artifact.
    - If AI enhancement fails or looks truncated, it silently falls back to the original.
    - It uses prompt-level heuristics, not deterministic structure extraction.
    - It contains a code smell: it references `config` before config is actually loaded, guarded only by `'config' in dir()`.
    - Docs describe it as optional/commented-out, but the committed pipeline currently includes it.

- `instruqtor`
  - Reads the current cycle tasq and generates briqs for that cycle.
  - On cycle 1, extracts a machine-readable contract from tasq text into `qontract.json` and a human-readable `qontract.md`.
  - Enforces briq count ranges by sensitivity, with retry/merge behavior.
  - Injects contract-relevant invariant snippets into briqs based on inferred scope tags.
  - Writes briqs as `briq.d/cyqle{cycle}_tasq1_briqNNN_<slug>.md`.
  - Limitations:
    - Contract extraction is regex/pattern-based and only supports currently implemented invariant families.
    - Contract extraction and invariant injection are strongly Python/backend oriented.
    - Briq filenames are cycle-numbered but still contain `tasq1` in the name, which is misleading after cycle 1.

- `construqtor`
  - Processes briqs one by one.
  - Builds prompts from the briq plus contract text, cycle-1 tasq, project tree summary, and context files.
  - Writes AI output directly into `qodeyard/` as soon as code blocks are parsed.
  - Performs per-briq Python-only local validation and optional per-briq AI quick review.
  - For `Contract-Relevant: yes` briqs, runs per-briq QontractGuard and retries with an injected correction directive.
  - Writes per-briq exeQ markdown into `exeq.d/cyqle{N}/`.
  - Writes aggregate `cyqle{N}_summary.md` and `cyqle{N}_changed.md`.
  - Limitations:
    - No staging area; writes are incremental and immediate.
    - Local validation only covers `.py` files.
    - Contract guard only checks Python files.
    - On retry, previously written files are not reverted before another attempt.
    - Partial or failed attempts can leave mixed filesystem state in `qodeyard/`.

- `inspeqtor`
  - Runs deterministic guardrails first, then AI review layers.
  - Writes contract guard outputs, verification outputs, per-briq reqaps, and final cycle reqap.
  - Forces overall failure if QontractGuard fails.
  - Downgrades `SUCCESS` to `PARTIAL` if local verification finds errors.
  - Limitations:
    - AI review is still allowed in report-only mode after contract failure; it does not repair anything itself.
    - Meta-review is another AI synthesis layer, not a deterministic aggregator.
    - It treats `bloq.d` and `qontext.d` as optional and possibly stale because actual pipeline order places them after review.

- Other present agents/helpers
  - `calqulator`: deterministic cost estimation and briq annotation.
  - `qontextor`: local or AI context generation; strongest for Python.
  - `qompressor`: deterministic skeletons; strongest for Python.
  - `qontrabender`: cache assembly and persistence ledger.
  - `loqal_verifier`: deterministic Python-only verifier.
  - `qontract_guard`: deterministic Python-only contract guard.
  - No Qualifier agent exists.
  - No Qrystallizer exists.

## Validation & Guardrails
- local (syntax/tests)
  - There is no general test runner in the core pipeline. Current deterministic validation is syntax/import/AST-oriented, not full project test execution.
  - `construqtor` runs `run_local_validation()` after each briq, but only on written `.py` files.
  - `loqal_verifier` runs at InspeQtor stage 1 and only scans Python files in `qodeyard/`.
  - `qontract_guard` is deterministic and Python-AST-based.
  - `qompressor` validates its own Python skeleton output by reparsing it with `ast.parse`.
  - `runtime_checks.ensure_qontract_present()` is fail-fast for cycles greater than 1.
  - Container hardening in `qonqrete.sh` is a runtime guardrail, not code validation.

- AI-based (if any)
  - `tasqleveler` is fully AI-based.
  - `instruqtor` is AI-based for briq generation.
  - `construqtor` is AI-based for code generation.
  - `construqtor` can run optional AI quick review per briq.
  - `inspeqtor` per-briq review and meta-review are AI-based.
  - AI validation is advisory except where deterministic layers force failure.

## CLI / Sqrapyard Flow
The CLI surface is `init`, `run`, `resume`, and `clean`. `run` seeds a brand-new qage. `resume` clones an existing qage into a new qage and continues there. `clean` deletes qages interactively or directly. `init` builds the container image and tags versioned, `latest`, and legacy image names.

`sqrapyard` behavior is simple file seeding, not a complex stateful subsystem in the core run path. With `--sqrapyard`, `qonqrete.sh` copies `worqspace/sqrapyard/*` into the new qage’s `qodeyard/`. If `sqrapyard/tasq.md` exists, it is explicitly ignored in favor of `worqspace/tasq.md`. Without `--sqrapyard`, the CLI logs that sqrapyard exists but does not use it.

IDE behavior is workspace-local deployment. Both IDE integrations prefer `.qonqrete/qonqrete.sh`, sync the root `tasq.md` into `.qonqrete/worqspace/tasq.md`, and run the same CLI. The IDEs expose `sqrapyard` as a run option that maps to `--sqrapyard`.

## State Management
The primary persistent state unit is the qage directory. State is file-backed and scoped to each qage:
- `tasq.d/`: cycle tasks
- `briq.d/`: per-cycle briqs
- `qodeyard/`: mutable working code state
- `exeq.d/`: execution summaries and changed-file manifests
- `reqap.d/`: review artifacts
- `qontract.d/`: project constitution
- `qontext.d/`: context index
- `bloq.d/`: skeleton cache
- `struqture/`: logs and tree/context logs
- `qache.d/`: optional cache payloads, manifest, ledger, active cache markers

State progression is file-copy based, not database-centered. `resume` copies the whole previous qage into a new qage. `qonstruction` save also copies qage contents wholesale.

`qontrabender` is the main exception: it persists a `manifest.json`, `ledger.db`, payload files, sync log, decisions log, and active cache metadata inside `qache.d/`.

## Audit / Logging Reality
Logging exists, but it is fragmented and mostly plain-file based rather than a unified audit system.
- `qrane.py` writes `struqture/qonsole_<agent>.log` and `struqture/events_<agent>.log` per agent.
- `inspeqtor.py` overwrites `struqture/qonsole_inspeqtor.log` with a context inventory log.
- `construqtor` writes exeQ summaries in `exeq.d/cyqleN/`.
- `inspeqtor` writes contract guard reports, verification reports, per-briq reqaps, and final reqaps.
- `qontrabender` maintains `qache.d/sync.log`, `qache.d/decisions.log`, `qache.d/manifest.json`, and `qache.d/ledger.db`.
- `qonstruction` save writes a `meta.yaml` file.

`lib_security.py` contains structured JSON logging support, but the active runtime barely uses it. The current runtime is not consistently emitting structured security audit events.

## Stage & Status Reality (CURRENT, PRE-CANONICAL)
Actual observed outer orchestration order in the committed pipeline config is:
1. `tasqleveler` on cycle 1 only
2. `instruqtor`
3. `calqulator`
4. `construqtor`
5. `qontextor`
6. `qompressor`
7. `qontrabender`
8. `inspeqtor`

Actual warmup order before cycle 1, when seeded `qodeyard/` is non-empty, is:
1. `qompressor_warmup`
2. `qontextor_initial`
3. `qontrabender_warmup`

Actual InspeQtor substage order is:
1. `STAGE 0: QontractGuard`
2. `STAGE 1: LoQal Verification`
3. `STAGE 2: Per-Briq Tactical Reviews`
4. `STAGE 3: Global Meta-Review`

Actual cheqpoint outcomes are `QONTINUE` or `QUIT`. In autonomous mode it always promotes the reqap and continues until cycle limit.

Actual status/lifecycle concepts present in code include:
- Qrane/session: `session_failed`, `user_aborted`, autonomous vs user-gated, cycle limit hit.
- IDE run state: `idle`, `running`, `completed`, `failed`, `timeout`.
- ConstruQtor per-briq: `success`, `partial`, `failure`.
- ConstruQtor cycle summary: `Success`, `Partial`, `Failure`, `Halted`.
- InspeQtor assessment: `[SUCCESS]`, `[PARTIAL]`, `[FAILURE]`, sometimes `[UNKNOWN]`.
- LoQal verifier overall: `SUCCESS`, `PARTIAL`, `FAILURE`.
- QontractGuard overall: `PASS`, `FAIL`.
- Qontrabender ledger status: `pending`, `synced`, `superseded` are present in behavior.

Observed mismatches between code, configs, docs, or comments:
- `README.md` and `doc/ARCHITECTURE.md` describe a pipeline where `inspeqtor` runs before `qontextor` and `qompressor`; the actual `pipeline_config.yaml` runs `inspeqtor` last.
- `pipeline_config.yaml` comments say the order is `instruqtor → calqulator → construqtor → inspeqtor → qontextor → qompressor`, but the actual YAML list places `qontextor`, `qompressor`, and `qontrabender` before `inspeqtor`.
- `inspeqtor.py` logs correctly acknowledge that `bloq.d` and `qontext.d` may be stale because those stages run after InspeQtor in current order.
- `doc/DOCUMENTATION.md` and `doc/ARCHITECTURE.md` describe `tasqleveler` as optional/uncomment-to-enable; the committed pipeline includes it actively.
- `qrane/paths.py` defines `qache_dir` as `root / "sqrapyard" / "qache.d"`, but `qontrabender.py` actually uses `root / "qache.d"` by default and the pipeline passes `qache.d/` explicitly.
- `README.md` and docs still speak broadly about qodeyard as current truth and additional stages, but the current execution truth is pipeline-config-driven and currently puts context generation after review.
- `RunTasqAction.kt` comments claim the `-n` flag renames the resulting qage directory; the CLI actually uses `-n` to auto-save a qonstruction and then deletes the original qage.
- `qonqrete.sh` help advertises `resume -q qage_20251226`, but actual qage names include `YYYYMMDD_HHMMSS`.

## Transaction / Partial Write Reality
ConstruQtor writes incrementally and directly into `qodeyard/` during each briq. There is no staging directory, no commit phase, and no per-briq transactional boundary. Files are created or overwritten as soon as `_write_ai_output_to_qodeyard()` parses code blocks.

Writes are scoped only by path safety checks under `qodeyard/`; they are not transactionally scoped. Retry does not revert previous failed writes before the next attempt. A later attempt may overwrite some files and leave others from a prior failed attempt intact.

Rollback does not exist today for code generation. The only atomic write utility in the repo is `lib_security.safe_write_file()`, but ConstruQtor does not use it. Resume/recovery is qage-level, not transaction-level.

On failure today:
- Per-briq failures still leave whatever files were already written.
- Per-briq exeQ summaries are written even for failures when possible.
- Aggregate summary and changed-file manifests are written from observed results.
- If `stop_on_briq_fail=false`, the cycle can continue after a failed briq.
- If `stop_on_briq_fail=true`, the cycle halts early, but prior writes remain.

Artifacts available for recovery/diagnosis:
- qage snapshot itself
- `struqture/qonsole_*.log`
- `struqture/events_*.log`
- `exeq.d/cyqleN_summary.md`
- `exeq.d/cyqleN_changed.md`
- `exeq.d/cyqleN/*_exeq.md`
- `reqap.d/*`
- `qontract_guard` JSON/markdown outputs
- qage cloning through `resume`

## Language / Ecosystem Capability Reality
Deterministic validation is strongest for Python.
- `loqal_verifier` only scans Python files.
- `construqtor` local validation only checks Python syntax/imports.
- `qontract_guard` only enforces against Python AST.
- `qompressor` has rich Python-specific AST preservation and reparses output for validity.
- `qontextor` local mode is most meaningful for Python through AST and optional Jedi enhancement.

Deterministic validation is weaker outside Python.
- Non-Python code written by ConstruQtor gets filename/path safety and little else.
- `qompressor` falls back to regex stripping for JS/TS/Go/Rust/Java/C/etc.; this is structural compression, not semantic validation.
- `qontextor` treats non-Python mostly as config/doc summaries unless AI mode is used.
- There is no deterministic compile/test/parse loop for JS/TS, Go, Rust, Java, or infra code in the current pipeline.

Language-specific vs generally applicable today:
- Generally applicable: qage state model, CLI/container orchestration, prompt budgeting, filename sanitization, file-path jail check inside ConstruQtor, briq planning flow, cache payload assembly.
- Python-specific: most meaningful deterministic verification and contract enforcement.
- Heuristic but language-broad: ConstruQtor filename/language-keyword filtering and extensionless-file allowlist.
- AI-dependent: most non-Python semantic quality assessment.

Current honesty gaps between implementation and claims:
- Claims of broad multi-language handling are stronger than deterministic verification coverage.
- Contract enforcement is described generically, but implemented only for Python files.
- Local verification is described broadly, but implemented as Python syntax/import/skeleton checks.
- Security library capabilities are broader than their active usage in the runtime.
- Some docs describe context artifacts as available to review, while the current pipeline often makes them stale relative to InspeQtor.

## Strengths
The system is genuinely file-based and inspectable. Every meaningful step emits artifacts that can be inspected or resumed from. Qage cloning gives practical recoverability at the run level.

The orchestration is configurable by pipeline YAML rather than hardcoded stage order. Contract generation and deterministic enforcement are already wired into the live pipeline.

Python support is materially stronger than surface-level marketing would suggest: contract extraction, AST guardrails, syntax verification, skeletonization, and context extraction are all real.

The CLI and IDE wrappers converge on the same runtime model rather than splitting behavior.

## Weaknesses / Gaps
There is no transactional write model. Partial or failed ConstruQtor attempts can leave mixed state in `qodeyard/`.

Deterministic validation is heavily Python-centric. Non-Python ecosystems rely mostly on AI judgment and coarse heuristics.

Documentation and configuration comments are out of sync with actual stage ordering and some current behaviors.

The security utility layer is underused by the active runtime. Most writes/logs do not go through the safer structured interfaces already present in the repo.

TasqLeveler mutates the task in place, which blurs original intent versus enhanced prompt material.

## Risks
The largest operational risk is silent partial state after failed briqs or retries. A later cycle may build on mixed outputs that were never atomically validated as a whole.

The second major risk is overclaiming cross-language rigor. Python has meaningful deterministic safeguards; other ecosystems do not currently receive equivalent verification.

Stage-order confusion is a practical risk because docs, config comments, and runtime behavior disagree. That can produce wrong debugging assumptions, wrong prompt/context expectations, and wrong demo narratives.

Qontrabender persistence is real but peripheral to the core build loop, and one path helper still points to the wrong location for `qache.d`, which is a latent inconsistency.

## Observations
Current reality is a tasQleveler-driven, InstruQtor/ConstruQtor/InspeQtor pipeline with supporting local helpers, not a broader future architecture with Qrystallizer or Qualifier.

The practical source of truth during a run is the current qage, especially `qodeyard/`, not the root workspace or a central engine state store.

The codebase already contains several honest signals about current limitations, especially in InspeQtor’s staleness logging and Qontrabender’s built-in conservative defaults. The main dishonesty comes from docs/comments that still describe older or intended ordering rather than the committed runtime behavior.
