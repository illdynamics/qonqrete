# QonQrete Migration Compound

## Purpose
This document is the authoritative transition map from current QonQrete repository reality to the intended target operating model.

It exists separately from the execution plan because the execution plan defines intended architecture direction, while this document defines how current modules, artifacts, states, and flows bridge into that target.

It exists separately from the hard ruleset because the hard ruleset defines non-negotiable constraints, while this document defines the migration path that must satisfy those constraints.

It exists separately from future Qonscience or later contract documents because migration must be executable before those future documents fully exist.

## Migration Summary
QonQrete is migrating from a qage-local, cycle-promoted, file-contract runtime with `tasqleveler -> instruqtor -> construqtor -> inspeqtor` as the practical core into a repo-native, manifest-centered, Qrystallizer-fronted architecture with explicit task clarification, guard, planning, build, validation, realization, inspection, and targeted repair stages.

The core architectural shift is:
- from mutable `tasq.md` enhancement to structured Task Spec generation
- from multi-cycle promotion via `reqap -> next tasq` to single-pass execution plus targeted repair
- from fragmented logs and stage-local outputs to one authoritative run manifest with linked artifacts
- from qage-only operational state to repo-native `.qonqrete/` state with compatibility bridges
- from implicit evidence spread across markdown and logs to first-class validation and realization artifacts

The highest-risk migration areas are task/front-door replacement, cycle removal without losing continuity, partial-write containment, manifest introduction, validator expansion, and coexistence between qage-era and `.qonqrete`-era state.

## Current-to-Target Transition Overview
Current operating model:
- Host CLI creates qages under `worqspace/qage_*`
- Task input is copied into qage and may be mutated by `tasqleveler`
- `qrane.py` executes configured stages in pipeline order
- `instruqtor` emits briqs and cycle-1 contract files
- `construqtor` writes incrementally into `qodeyard/`
- `inspeqtor` performs deterministic checks plus AI review and emits `reqap`
- Continuation occurs by promoting `reqap` into the next cycle task
- Resume is qage cloning, not manifest-native continuation
- Audit is fragmented across logs, exeQ files, reqaps, and optional cache manifests

Target operating model:
- CLI operates repo-natively and stores runtime state under `.qonqrete/`
- Task input becomes a structured Task Spec produced by Qrystallizer
- Guard stage evaluates policy and attaches effective constraints before planning
- instruQtor emits structured plan artifacts, completion criteria, validation plan, and grouped execution plan
- construQtor executes scoped build groups with safe-write boundaries
- system validators run deterministic validation and tests where available
- realization becomes a first-class artifact layer before inspection
- inspeQtor judges intent versus evidence and emits final verdicts or targeted repair plans
- continuation becomes repair-plan-driven or user-requested continuation, not `reqap -> next tasq`
- run state is linked through one authoritative manifest

Biggest deltas:
- `tasqleveler` mutation replaced by `Qrystallizer` structured clarification
- cycle-centric orchestration replaced by single-pass plus targeted repair
- qage-first state replaced by `.qonqrete` run roots with compatibility bridging
- review-centric evidence replaced by explicit validation plus realization artifacts
- fragmented logging replaced by manifest-linked dual-layer audit
- implicit or ad hoc statuses replaced by canonical enums

Highest-risk transitions:
- preserving resumability while removing cycle promotion
- introducing safe writes without breaking current build behavior
- reconciling current stage names and order with canonical target names
- migrating qage artifacts into `.qonqrete` without losing audit continuity
- avoiding false claims of language-agnostic validation parity during transition
- keeping docs, runtime, config, and manifests aligned while compatibility aliases still exist

Explicit inconsistencies that remain part of migration reality:
- Current repo has `tasqleveler` and no `Qrystallizer`
- No `Qualifier` agent exists; validator logic is currently system-level and partially embedded
- Current docs/comments and runtime stage order disagree
- Current `qache_dir` path handling is inconsistent between helper path logic and actual cache behavior
- Current runtime still uses cycle promotion via `reqap`, which conflicts with target repair-plan continuation

## Migration Truth Table
### `tasqleveler`
- Current Module / Component / Artifact: `worqer/tasqleveler.py`
- Current Role: Cycle-1 task enhancer that rewrites `tasq.md` in place after backup
- Target Role: None as a final stage; superseded by Qrystallizer
- Action: REPLACE
- Dependency / Prerequisite: Canonical Task Spec artifact, Qrystallizer stage, compatibility alias handling
- Migration Notes: Must not become a hidden compatibility path that still mutates canonical input; temporary adapter may map existing task enhancement calls into Qrystallizer-compatible output generation without in-place overwrite
- Done Criteria: No canonical run path depends on task mutation in place; `tasqleveler` removed or compatibility-gated only; Task Spec is the only front-door artifact

### `Qrystallizer` (future target)
- Current Module / Component / Artifact: Not present
- Current Role: None
- Target Role: Sole task-clarification stage that asks bounded questions, resolves assumptions, and emits structured Task Spec plus readiness status
- Action: ADD
- Dependency / Prerequisite: Canonical stage registry, Task Spec schema, no-mid-run-question rule, guard-stage input contract
- Migration Notes: Must replace both task enhancement and ad hoc ambiguity handling; only phase allowed to ask questions
- Done Criteria: Every canonical run starts from a Task Spec produced or accepted by Qrystallizer; execution does not begin without readiness state

### `instruQtor`
- Current Module / Component / Artifact: `worqer/instruqtor.py`
- Current Role: Reads cycle tasq, emits briqs, extracts cycle-1 contract
- Target Role: Structured planning stage that emits execution blueprint, grouped build plan, dependency/interactions, validation plan, completion criteria, and optional repair eligibility
- Action: ADAPT
- Dependency / Prerequisite: Task Spec input, guard result artifact, grouped build model, canonical planning artifacts
- Migration Notes: Must stop treating raw task markdown as sole source; briqs become internal build-unit planning, not the sole public plan artifact
- Done Criteria: Planning stage consumes Task Spec plus effective constraints and emits structured plan artifacts used by build, validation, realization, and inspection

### `construQtor`
- Current Module / Component / Artifact: `worqer/construqtor.py`
- Current Role: Processes briqs and writes directly into `qodeyard/`, with limited validation and summaries
- Target Role: Scoped build executor over build groups with safe application boundaries, build reports, and changed-scope evidence
- Action: ADAPT
- Dependency / Prerequisite: Grouped execution plan, safe-write strategy, build-group contract, manifest-linked outputs, validator handoff
- Migration Notes: Must move from direct unscoped writes toward staged or attributable writes; must stop being the primary source of judgment-like summaries
- Done Criteria: Build writes are attributable, scoped, manifest-linked, and diagnosable; build output is separated from inspection verdicts

### `inspeQtor`
- Current Module / Component / Artifact: `worqer/inspeqtor.py`
- Current Role: Runs deterministic contract/local checks and AI review, then emits final `reqap`
- Target Role: Inspection stage that judges plan versus validation and realization evidence, emits verdict and targeted repair intent when needed
- Action: ADAPT
- Dependency / Prerequisite: Validation bundle, realization bundle, completion criteria, canonical verdict artifact
- Migration Notes: Must stop acting as an overloaded source of both evidence and verdict; must no longer be the canonical continuation mechanism through `reqap`
- Done Criteria: inspeQtor consumes explicit validation and realization artifacts and emits structured verdicts and targeted repair artifacts

### system validators / local verification
- Current Module / Component / Artifact: `loqal_verifier.py`, `qontract_guard.py`, ad hoc per-briq validation in construQtor, environment checks
- Current Role: Deterministic Python-centric checks and runtime guardrails
- Target Role: Explicit validator layer with declared execution mode, ecosystem coverage, and machine-readable results
- Action: SPLIT
- Dependency / Prerequisite: Validator stage contract, validation result bundle, capability-mode declarations
- Migration Notes: Must be represented as system-level validators, not conversational agents; current Python-heavy coverage must remain explicitly disclosed during migration
- Done Criteria: Validators emit structured results, coverage disclosures, and stage-linked outputs regardless of language strength

### `QontractGuard` / guard stage
- Current Module / Component / Artifact: `worqer/qontract_guard.py` and InspeQtor substage usage
- Current Role: Deterministic Python AST contract enforcement, plus partial per-briq use in construQtor
- Target Role: Canonical guard stage before planning, with later validation reuse where needed
- Action: SPLIT
- Dependency / Prerequisite: Guard result artifact, effective constraints model, policy source, Task Spec input
- Migration Notes: Current implementation is Python-specific and currently placed late or per-briq; migration must separate a pre-plan guard stage from later validation enforcement
- Done Criteria: Guard stage exists before planning, emits pass/review/fail plus effective constraints, and later validation can reference the same rules without duplicating stage identity

### `calQulator`
- Current Module / Component / Artifact: `worqer/calqulator.py`
- Current Role: Local cost estimation and briq annotation
- Target Role: Estimation and optional gating stage for plan-level and repair-level cost visibility
- Action: ADAPT
- Dependency / Prerequisite: Structured execution plan, repair plan model, manifest-linked stage records
- Migration Notes: Must move from briq annotation side effect into stage artifact emission; should remain advisory unless user gating is enabled
- Done Criteria: Estimation artifacts exist for main pass and repair pass, linked in manifest with confidence and basis

### qage runtime model
- Current Module / Component / Artifact: `worqspace/qage_*`
- Current Role: Primary run state boundary and resumable snapshot
- Target Role: Compatibility runtime container and transitional persistence envelope
- Action: KEEP
- Dependency / Prerequisite: `.qonqrete` state model, coexistence rules, lineage mapping
- Migration Notes: qage remains valid during migration but must stop being the only source of truth; bridge must map qage artifacts into canonical run manifest
- Done Criteria: qage runs can be imported, mirrored, or wrapped by canonical run state without ambiguity

### `.qonqrete/` target state model
- Current Module / Component / Artifact: Present in IDE deployment flow but not canonical run-state model
- Current Role: IDE-local deployment and wrapper location
- Target Role: Canonical repo-native runtime state root
- Action: ADAPT
- Dependency / Prerequisite: run root layout, manifest design, CLI flow changes, coexistence rules
- Migration Notes: Must become the stable state location for new repo-native flows while supporting qage bridging
- Done Criteria: Canonical runs persist under `.qonqrete/` with manifest, artifacts, continuation metadata, and compatibility links to any qage-era state

### `sqrapyard` flow
- Current Module / Component / Artifact: `worqspace/sqrapyard/` plus `--sqrapyard`
- Current Role: Optional project seeding into qage `qodeyard/`
- Target Role: Internal compatibility-only seed/import concept; not primary user-facing flow
- Action: RETIRE
- Dependency / Prerequisite: repo-native CLI flow, in-place repo execution, `.qonqrete` state model
- Migration Notes: Term should be removed from primary UX; any remaining implementation should be hidden behind import or seed semantics
- Done Criteria: Canonical UX no longer requires copying project into sqrapyard or using `-s`; repo-native execution is default

### CLI flow
- Current Module / Component / Artifact: `qonqrete.sh init|run|resume|clean`
- Current Role: qage-oriented lifecycle and container launch interface
- Target Role: repo-native, task-first, one-command primary UX with continuation awareness
- Action: ADAPT
- Dependency / Prerequisite: `.qonqrete` state model, Task Spec intake, manifest, continuation model
- Migration Notes: Existing CLI must retain compatibility commands during migration; target default is `qonqrete [task?]`
- Done Criteria: Canonical user flow does not require `init` then `run`, does not require fixed `tasq.md`, and does not expose `sqrapyard` as primary concept

### audit trail system
- Current Module / Component / Artifact: `struqture/` logs, `exeq.d/`, `reqap.d/`, cache logs
- Current Role: Fragmented audit and evidence store
- Target Role: Dual-layer audit linked through authoritative manifest
- Action: MERGE
- Dependency / Prerequisite: run manifest, canonical stage IDs, event schema, artifact linkage
- Migration Notes: Existing files remain as legacy artifact sources, but canonical audit must point to them or absorb them
- Done Criteria: Run timeline and deep evidence are reconstructable from one run-level record without tribal knowledge

### run manifest
- Current Module / Component / Artifact: No canonical run manifest; `qontrabender` has a cache manifest only
- Current Role: Missing at run level
- Target Role: Authoritative run-level record linking stages, artifacts, statuses, and continuation
- Action: ADD
- Dependency / Prerequisite: canonical enums, artifact paths, stage contracts
- Migration Notes: Must not be confused with cache manifest; must survive partial failure and coexist with legacy files
- Done Criteria: Every canonical run has a run manifest created at intake and updated through terminal state

### cycle promotion flow
- Current Module / Component / Artifact: `promote_reqap()` and `tasq.d/cyqle{N+1}_tasq.md`
- Current Role: Canonical continuation logic today
- Target Role: Compatibility-only continuation path, replaced by repair intent and explicit continuation requests
- Action: RETIRE
- Dependency / Prerequisite: repair-plan artifact, continuation metadata, run manifest transitions
- Migration Notes: Must not remain hidden canonical logic after targeted repair is introduced
- Done Criteria: Canonical continuation no longer depends on `reqap -> next tasq`; legacy promotion is compatibility-only or removed

### targeted repair flow
- Current Module / Component / Artifact: Not present as canonical artifact flow
- Current Role: Implicitly approximated by extra cycles and `reqap` promotion
- Target Role: Explicit bounded repair stage with repair intent artifact and scoped re-entry
- Action: ADD
- Dependency / Prerequisite: verdict artifact, repair target model, lifecycle enums, build-group scope model
- Migration Notes: Must replace fuzzy cycle reruns; must be bounded and evidence-driven
- Done Criteria: Repair is a distinct lifecycle path with explicit targets, bounded attempts, manifest linkage, and no whole-run ambiguity

### result / realization layer
- Current Module / Component / Artifact: Diffuse across `exeq.d/`, changed-file lists, validator outputs, logs
- Current Role: Partial observed execution evidence without a dedicated stage identity
- Target Role: First-class realization stage and artifact domain
- Action: MERGE
- Dependency / Prerequisite: validation bundle, build outputs, changed-scope capture, canonical artifact hierarchy
- Migration Notes: Existing `exeq` outputs are useful precursors but must not remain the only evidence source
- Done Criteria: Realization outputs exist before inspection and separate actual outcomes from verdicts

### pipeline config / pipeline order
- Current Module / Component / Artifact: `worqspace/pipeline_config.yaml`
- Current Role: Runtime stage order and stage metadata
- Target Role: Compatibility pipeline config during migration, later generated or validated against canonical registry
- Action: ADAPT
- Dependency / Prerequisite: formal stage registry, alias map, migration phase gates
- Migration Notes: Current order conflicts with docs and target flow; migration must introduce canonical order without breaking compatibility too early
- Done Criteria: Runtime stage order validates against canonical registry or alias map; documentation and runtime agree

### `qache` / cache / path inconsistencies
- Current Module / Component / Artifact: `qrane/paths.py`, `qontrabender.py`, `qache.d/`, policy defaults
- Current Role: Cache payload persistence with inconsistent path assumptions
- Target Role: Stable cache artifact domain under canonical run root or explicit shared cache policy
- Action: ADAPT
- Dependency / Prerequisite: `.qonqrete` hierarchy, path normalization, manifest linkage
- Migration Notes: Cache manifest is not run manifest; path inconsistency must be explicitly corrected during migration
- Done Criteria: There is one documented and implemented cache path model and it is distinct from run manifest storage

### historical / experimental pipeline artifacts
- Current Module / Component / Artifact: `qontextor`, `qompressor`, `qontrabender`, current warmup stages, old doc order
- Current Role: Supporting context, skeleton, and cache helpers with mixed placement
- Target Role: Supporting services or optional phases, not ambiguous core stages
- Action: SPLIT
- Dependency / Prerequisite: canonical stage taxonomy, optional-service taxonomy, manifest stage typing
- Migration Notes: They may remain valuable, but migration must decide whether each is canonical stage, optional helper, or background support service
- Done Criteria: Each helper is explicitly categorized as final stage, optional stage, support service, or deprecated artifact producer

## Formal Stage Registry (CURRENT OBSERVED VS CANONICAL TARGET)
Current observed outer stage names and order:
1. `tasqleveler`
2. `instruqtor`
3. `calqulator`
4. `construqtor`
5. `qontextor`
6. `qompressor`
7. `qontrabender`
8. `inspeqtor`

Current observed warmup stage names and order:
1. `qompressor_warmup`
2. `qontextor_initial`
3. `qontrabender_warmup`

Current observed inspeQtor substages:
1. `QontractGuard`
2. `LoQal Verification`
3. `Per-Briq Tactical Reviews`
4. `Global Meta-Review`

Target canonical stage names and order:
1. `intake`
2. `clarification`
3. `guard`
4. `planning`
5. `estimation`
6. `build`
7. `validation`
8. `realization`
9. `inspection`
10. `repair`
11. `finalize`

Stage alias cleanup requirements:
- `tasqleveler` is a compatibility alias for pre-canonical clarification behavior and must not remain final
- `instruqtor` maps to canonical `planning`
- `calqulator` maps to canonical `estimation`
- `construqtor` maps to canonical `build`
- `inspeqtor` maps to canonical `inspection`
- `QontractGuard` currently appears as an inspeQtor substage but must become canonical `guard` before planning and may also appear later as validation rule reuse
- `LoQal Verification` maps to canonical `validation`
- `qontextor`, `qompressor`, and `qontrabender` require explicit classification as support services or optional pre-build/context services rather than silently remaining core lifecycle stages
- warmup aliases must not be confused with canonical lifecycle stages

Deprecated or transitional stage identities:
- `tasqleveler`
- `cycle promotion`
- `reqap promotion`
- `qompressor_warmup`
- `qontextor_initial`
- `qontrabender_warmup`
- `per-briq tactical reviews` as a stand-alone lifecycle identity
- `global meta-review` as a top-level lifecycle identity

Compatibility-only versus final:
- Compatibility-only: `tasqleveler`, cycle stages, warmup stage IDs, `reqap promotion`, qage-era substage names
- Final: `intake`, `clarification`, `guard`, `planning`, `estimation`, `build`, `validation`, `realization`, `inspection`, `repair`, `finalize`

## Canonical Enum Appendix
### Stage IDs
- `INTAKE`
- `CLARIFICATION`
- `GUARD`
- `PLANNING`
- `ESTIMATION`
- `BUILD`
- `VALIDATION`
- `REALIZATION`
- `INSPECTION`
- `REPAIR`
- `FINALIZE`

### Lifecycle States
- `CREATED`
- `READY_FOR_CLARIFICATION`
- `CLARIFYING`
- `BLOCKED`
- `GUARDING`
- `PLANNING`
- `ESTIMATING`
- `AWAITING_GATE`
- `BUILDING`
- `VALIDATING`
- `REALIZING`
- `INSPECTING`
- `REPAIRING`
- `CONTINUABLE`
- `COMPLETED`
- `PARTIAL`
- `FAILED`
- `ABORTED`

### Run Statuses
- `RUN_CREATED`
- `RUN_ACTIVE`
- `RUN_WAITING_FOR_INPUT`
- `RUN_WAITING_FOR_GATE`
- `RUN_REPAIR_PENDING`
- `RUN_COMPLETED`
- `RUN_PARTIAL`
- `RUN_FAILED`
- `RUN_ABORTED`

### Repair Statuses
- `REPAIR_NOT_REQUIRED`
- `REPAIR_PROPOSED`
- `REPAIR_APPROVED`
- `REPAIR_IN_PROGRESS`
- `REPAIR_COMPLETED`
- `REPAIR_EXHAUSTED`
- `REPAIR_BLOCKED`

### Capability Modes
- `SIMULATION`
- `EXECUTION`
- `EXECUTION_PREFERRED`
- `MIXED_REASONING_EXECUTION`

### Validation Execution Modes
- `NONE`
- `SIMULATED`
- `STATIC_ONLY`
- `EXECUTED`
- `MIXED`

### Evidence / Confidence Status Enums
- `EVIDENCE_MISSING`
- `EVIDENCE_PARTIAL`
- `EVIDENCE_COMPLETE`
- `CONFIDENCE_LOW`
- `CONFIDENCE_MEDIUM`
- `CONFIDENCE_HIGH`

### Stage Alias Map
- `tasqleveler -> CLARIFICATION`
- `instruqtor -> PLANNING`
- `calqulator -> ESTIMATION`
- `construqtor -> BUILD`
- `inspeqtor -> INSPECTION`
- `LoQal Verification -> VALIDATION`
- `QontractGuard -> GUARD`
- `reqap promotion -> REPAIR` compatibility only
- `cycle promotion -> REPAIR` compatibility only

This appendix is the canonical shared vocabulary for migration and must be referenced by manifests, pipeline compatibility layers, docs, and runtime output.

## Bridge Flow
### 1. Task intake and front door
Current state:
- task arrives as `tasq.md`
- `tasqleveler` may mutate it in place
- continuation may append new cycle tasks

Bridge:
- raw task input remains acceptable during migration
- canonical intake creates a run and stores the raw task as immutable intake input
- `tasqleveler` behavior is wrapped or replaced by a clarification bridge that emits Task Spec rather than mutating canonical input
- any existing `tasq_original.md` backup logic becomes legacy evidence only

Target:
- Qrystallizer is the front door
- Task Spec is the only canonical clarified task artifact
- no later stage asks the user questions

### 2. Current multi-cycle qage behavior to single-pass plus targeted repair
Current state:
- cycles are first-class
- `promote_reqap()` turns review output into next-cycle task input
- “continue” means another whole pass

Bridge:
- first, keep qage cycle files for compatibility but mark only cycle 1 as canonical main pass
- later, additional cycles become compatibility-only wrappers around explicit repair attempts
- `reqap` no longer becomes canonical next task; it becomes legacy inspection output that may seed a repair intent
- manifest records whether a continuation is canonical repair or legacy cycle promotion

Target:
- one main pass
- zero or more bounded targeted repair attempts
- no canonical whole-run cycle reruns

### 3. Current file-based artifacts to `.qonqrete/` hierarchy
Current state:
- artifacts live inside qage directories under names like `tasq.d`, `briq.d`, `exeq.d`, `reqap.d`, `struqture`
- qage is the only practical state container

Bridge:
- canonical run root lives under `.qonqrete/runs/<run_id>/`
- qage may still exist during transition
- compatibility import or mirror records map legacy qage artifact paths into canonical manifest entries
- new artifacts are emitted into `.qonqrete` first even if legacy mirrors are still written

Target:
- `.qonqrete/` is canonical state root
- qage becomes compatibility runtime envelope or import source

### 4. Fragmented logging to authoritative run manifest and dual-layer audit
Current state:
- stage logs, exeQ files, reqaps, and cache manifests are separate
- no run-level authoritative manifest exists

Bridge:
- create run manifest at intake
- every stage appends status, timestamps, artifact references, and capability mode
- preserve legacy files but link them from the manifest
- top-level audit summary and deep event logs become linked layers

Target:
- run manifest is authoritative
- high-level audit and deep evidence are both reconstructable from it

### 5. Current validator reality to target validator architecture
Current state:
- deterministic validation is Python-heavy and distributed
- `QontractGuard` is partly inside inspeQtor and partly per-briq in construQtor
- no general test runner is canonical

Bridge:
- separate `guard` from `validation`
- create explicit validator result bundle even if initial contents are still Python-centric
- add capability disclosures to every validation result
- keep static-only and simulated modes explicit where execution coverage is absent

Target:
- validators are system-level
- guard is pre-plan
- validation is explicit, ecosystem-scoped, and linked to plan and build scope

### 6. Execution evidence to first-class realization
Current state:
- observed execution is split across changed-file lists, exeQ summaries, logs, and validator outputs

Bridge:
- define realization artifact domain immediately
- initially populate it from current `exeq` outputs, command results, changed-file manifests, and validator bundles
- later emit realization directly as its own stage

Target:
- realization is a required artifact before inspection
- inspection consumes realization rather than reconstructing it indirectly

### 7. Current CLI and sqrapyard flow to repo-native one-command UX
Current state:
- qage-oriented CLI with `init`, `run`, `resume`, `clean`
- `sqrapyard` copy-and-run flow
- fixed `tasq.md` convention in practical usage

Bridge:
- keep compatibility commands
- add canonical repo-native command path that operates in place and stores state under `.qonqrete`
- accept explicit task file path and later optional interactive intake
- map old `--sqrapyard` behavior into internal seed/import compatibility only

Target:
- `qonqrete [task?]`
- repo-native execution
- no required `-s`
- no required copy flow

### 8. Shared enum vocabulary across migration
Current state:
- stage names and statuses differ across runtime, docs, IDEs, and logs

Bridge:
- manifest records both canonical enum and legacy alias during transition
- docs and runtime output must show canonical value first when available
- legacy names remain for compatibility until removed

Target:
- one shared vocabulary across code, config, docs, manifests, and audit outputs

## Stage Transition Lifecycle (Machine-Level State Diagram)
```text
States:
  CREATED
  READY_FOR_CLARIFICATION
  CLARIFYING
  BLOCKED
  GUARDING
  PLANNING
  ESTIMATING
  AWAITING_GATE
  BUILDING
  VALIDATING
  REALIZING
  INSPECTING
  REPAIRING
  CONTINUABLE
  COMPLETED
  PARTIAL
  FAILED
  ABORTED

Transitions:
  CREATED -> READY_FOR_CLARIFICATION
    condition: run manifest created and intake artifact stored

  READY_FOR_CLARIFICATION -> CLARIFYING
    condition: clarification stage starts

  CLARIFYING -> BLOCKED
    condition: Task Spec not ready and blocking ambiguity remains

  CLARIFYING -> GUARDING
    condition: Task Spec emitted with READY status

  BLOCKED -> CLARIFYING
    condition: user provides clarification or policy override path re-enters clarification

  BLOCKED -> ABORTED
    condition: user cancels or system cannot proceed

  GUARDING -> FAILED
    condition: guard returns fail with blocking issues

  GUARDING -> PLANNING
    condition: guard returns pass or review-with-constraints accepted by policy

  PLANNING -> ESTIMATING
    condition: plan artifacts, completion criteria, and validation plan emitted

  ESTIMATING -> AWAITING_GATE
    condition: user gate configured and decision required

  ESTIMATING -> BUILDING
    condition: no gate required or gate auto-approved

  AWAITING_GATE -> BUILDING
    condition: user approves

  AWAITING_GATE -> ABORTED
    condition: user rejects or cancels

  BUILDING -> FAILED
    condition: build fails without valid continuation path

  BUILDING -> VALIDATING
    condition: build outputs emitted for planned scope or partial scoped outputs emitted with continuation allowed

  VALIDATING -> FAILED
    condition: validator hard failure with no repair allowed

  VALIDATING -> REALIZING
    condition: validation bundle emitted

  REALIZING -> INSPECTING
    condition: realization bundle emitted

  INSPECTING -> COMPLETED
    condition: verdict is success and completion criteria satisfied

  INSPECTING -> PARTIAL
    condition: verdict is partial and no repair approved or available

  INSPECTING -> REPAIRING
    condition: verdict requires targeted repair and repair is allowed

  REPAIRING -> VALIDATING
    condition: repair build applied and repair validation begins

  REPAIRING -> FAILED
    condition: repair attempt fails and no further repair allowed

  REPAIRING -> PARTIAL
    condition: repair exhausted or blocked with unresolved scope remaining

  COMPLETED -> CONTINUABLE
    condition: user initiates explicit continuation as a new run linked to prior run

  PARTIAL -> CONTINUABLE
    condition: user initiates explicit continuation or approved follow-up work

Terminal states:
  COMPLETED
  PARTIAL
  FAILED
  ABORTED

Invalid transitions:
  BUILDING -> CLARIFYING
  VALIDATING -> CLARIFYING
  INSPECTING -> PLANNING without explicit new run or repair plan
  COMPLETED -> BUILDING without explicit continuation linkage
  any state -> REPAIRING without prior inspection verdict
```

## State Migration Design
Current state locations:
- `worqspace/qage_*` as run roots
- `tasq.d/`, `briq.d/`, `qodeyard/`, `exeq.d/`, `reqap.d/`, `qontract.d/`, `qontext.d/`, `bloq.d/`, `struqture/`, `qache.d/`

Target state locations:
- `.qonqrete/runs/<run_id>/` as canonical run root
- `.qonqrete/state/` for stable repo-local runtime metadata if needed
- `.qonqrete/cache/` or run-local cache subtrees by policy
- `.qonqrete/index/` for continuation and lineage lookup if needed

Migration boundaries:
- Source repo remains source of truth for user code and task inputs
- `.qonqrete` becomes source of truth for QonQrete runtime state, manifests, artifacts, and continuation metadata
- qage remains compatibility state boundary until qage-free canonical flow is stable

What remains repo source of truth:
- working project files
- user task files
- declared configuration checked into the repo when applicable

What becomes QonQrete state source of truth:
- Task Spec
- execution plan
- validation bundle
- realization bundle
- verdicts
- repair intent
- run manifest
- continuation lineage

Continuity / resume / continuation model:
- Resume: continue the same run when lifecycle permits and stage state is incomplete
- Repair: continue same run through `REPAIRING` with bounded scope
- Continuation: start a new run linked to a prior run when follow-up work begins after a terminal or continuable state
- Legacy qage clone resume remains supported during transition but must map into canonical lineage

Compatibility expectations during transition:
- qage-era and `.qonqrete` artifacts may coexist
- canonical manifest must record both legacy and canonical artifact paths when both exist
- runtime may still launch qage containers while storing canonical artifacts under `.qonqrete`

Precedence rules during coexistence:
1. Canonical manifest metadata wins over unlinked legacy files
2. Canonical Task Spec wins over mutated task markdown
3. Canonical repair intent wins over `reqap -> next tasq` promotion
4. Canonical lifecycle and status enums win over legacy text labels
5. Legacy artifacts remain evidence, not authority, unless no canonical counterpart exists yet

## Authoritative Run Manifest Design
Purpose:
- make one run reconstructable without tribal knowledge
- link every major stage, artifact, status, capability mode, and continuation relationship
- support audit, validation interpretation, repair, resume, and final verdicts

Where it lives:
- `.qonqrete/runs/<run_id>/run-manifest.v1.json`

When it is created:
- immediately at intake, before clarification begins

When it is updated:
- on every stage start
- on every stage completion
- on every gate or user decision
- on every repair proposal and repair completion
- on every terminal transition

What stages append to it:
- intake
- clarification
- guard
- planning
- estimation
- build
- validation
- realization
- inspection
- repair
- finalize
- compatibility adapters for legacy qage artifacts where still applicable

How it links all artifacts together:
- stores canonical artifact slots and per-stage outputs
- records file paths, stage IDs, statuses, timestamps, capability mode, validation mode, and lineage IDs
- references legacy artifact paths where needed

How it supports audit, continuation, validation, and final verdicts:
- audit can reconstruct timeline and deep evidence from stage records
- continuation can discover last valid state and prior repair history
- validation can tie findings to specific build scopes and capability modes
- final verdict can point to the exact evidence bundle used

Concrete schema example:
```json
{
  "schema_version": "run-manifest.v1",
  "run_id": "run_20260410_143015_a1b2c3",
  "repo_root": "/repo",
  "state_root": ".qonqrete/runs/run_20260410_143015_a1b2c3",
  "lineage": {
    "parent_run_id": null,
    "continued_from_run_id": null,
    "legacy_qage_id": "qage_20260410_143015"
  },
  "current_stage": "INSPECTION",
  "lifecycle_state": "INSPECTING",
  "run_status": "RUN_ACTIVE",
  "capability_mode": "MIXED_REASONING_EXECUTION",
  "validation_execution_mode": "MIXED",
  "evidence_status": "EVIDENCE_PARTIAL",
  "task": {
    "raw_input_path": "task/raw-input.md",
    "task_spec_path": "task/task-spec.v1.json",
    "task_spec_ready": true
  },
  "plan": {
    "execution_plan_path": "planning/execution-plan.v1.json",
    "execution_plan_md_path": "planning/execution-plan.md",
    "completion_criteria_path": "planning/completion-criteria.v1.json",
    "validation_plan_path": "planning/validation-plan.v1.json"
  },
  "artifacts": {
    "guard_result": "guard/guard-result.v1.json",
    "build_output": "build/build-report.v1.json",
    "validation_output": "validation/validation-bundle.v1.json",
    "realization_output": "realization/realization-bundle.v1.json",
    "inspection_output": "verdict/inspection-verdict.v1.json",
    "repair_plan": null,
    "audit_summary": "audit/timeline.md",
    "audit_events": "audit/events.ndjson"
  },
  "stages": [
    {
      "stage_id": "INTAKE",
      "status": "completed",
      "started_at": "2026-04-10T14:30:15Z",
      "ended_at": "2026-04-10T14:30:16Z",
      "artifacts": ["task/raw-input.md"]
    },
    {
      "stage_id": "CLARIFICATION",
      "status": "completed",
      "started_at": "2026-04-10T14:30:16Z",
      "ended_at": "2026-04-10T14:31:01Z",
      "artifacts": ["task/task-spec.v1.json", "task/task-spec.md"],
      "capability_mode": "SIMULATION"
    },
    {
      "stage_id": "BUILD",
      "status": "completed",
      "started_at": "2026-04-10T14:31:45Z",
      "ended_at": "2026-04-10T14:38:12Z",
      "artifacts": ["build/build-report.v1.json", "build/changed-files.v1.json"],
      "scope_id": "scope_build_group_01"
    }
  ],
  "legacy_links": {
    "qage_root": "worqspace/qage_20260410_143015",
    "legacy_exeq_dir": "worqspace/qage_20260410_143015/exeq.d",
    "legacy_reqap_dir": "worqspace/qage_20260410_143015/reqap.d"
  },
  "terminal": {
    "final_verdict": null,
    "completed_at": null
  }
}
```

## Transaction / Rollback Strategy
Current construQtor partial-write reality:
- writes incrementally into `qodeyard/`
- no stage-local transaction boundary
- no rollback on failed retry
- changed-file summaries exist, but partial state may remain mixed

Target write model:
- build applies by scoped build group
- every build group has declared scope before application
- writes occur through staged application, atomic replacement, or attributable snapshot-based recovery
- every applied change is tied to a build attempt ID and scope ID

Scope application boundaries:
- build group is the minimum scoped application unit
- scope includes intended files, allowed paths, and declared component or module boundary
- validator and realization artifacts must reference the same scope ID

Changed-file manifest relationship:
- every build group emits a changed-file manifest
- manifest distinguishes intended files, created files, modified files, deleted files, and attempted-but-uncommitted files if applicable
- changed-file manifest becomes part of realization input and repair scoping

Rollback or recovery expectations:
- rollback is ideal but not assumed immediately
- until rollback exists, every partial write must be attributable and explicitly disclosed
- recovery must at minimum support snapshot-or-continue semantics at build-group granularity
- canonical run manifest must record whether the write strategy was staged, atomic, or direct-with-recovery-risk

What happens when a build group fails mid-application:
- build group is marked failed
- manifest records affected scope and attempted writes
- realization bundle includes partial-write disclosure
- inspection cannot classify the run as full success
- repair may target only that failed scope if continuation is allowed
- if no repair allowed, run becomes `FAILED` or `PARTIAL` based on outcome policy

What must be persisted to diagnose, recover, retry, or continue:
- build attempt ID
- scope ID
- changed-file manifest
- command and execution logs
- validator outputs for that attempt
- realization summary for that attempt
- recovery or cleanup status
- linkage to any snapshot or previous state boundary

Rollback / recovery interaction with run manifest and audit trail:
- run manifest records write strategy and recovery availability per build attempt
- audit records partial-write disclosure and recovery action taken
- repair and continuation must reference the failed build-group attempt, not infer state from workspace alone

## Repair-Plan Role in Migration Flow
When it appears:
- after inspection when verdict is not acceptable for completion and bounded repair is allowed
- optionally after a build-stage hard failure if inspection policy supports immediate repair proposal

What it targets:
- explicit components, build groups, files, interfaces, or validation failures
- never the whole run by default
- may include dependency or contract mismatches discovered during inspection

How it replaces `reqap -> next tasq` as canonical continuation logic:
- current `reqap` is a narrative review output
- repair plan becomes the machine-linkable continuation artifact
- canonical continuation transitions from “new cycle task generated from reqap” to “repair intent emitted and executed within the same run or linked continuation run”

What state and lifecycle transitions it triggers:
- `INSPECTING -> REPAIRING` when approved within same run
- `PARTIAL -> CONTINUABLE` when deferred as later continuation
- `RUN_REPAIR_PENDING` when generated but awaiting gate
- `REPAIR_EXHAUSTED` when bounded repair budget is used up

What later Qonscience artifact contract must formalize:
- final machine schema for repair plan
- repair target typing
- merge rules for multiple repair issues
- confidence and evidence requirements
- approval and override fields

Migration-facing expectations that later contract documents must satisfy:
- repair plan must identify target scope
- repair plan must cite the evidence that triggered it
- repair plan must declare whether same-run repair or future continuation is intended
- repair plan must link to affected validation and realization artifacts
- repair plan must be bounded and must not silently expand scope

## Artifact Hierarchy Design
Intended `.qonqrete/` hierarchy:
```text
.qonqrete/
  runs/
    run_20260410_143015_a1b2c3/
      run-manifest.v1.json
      task/
        raw-input.md
        task-spec.v1.json
        task-spec.md
        clarification-log.md
      guard/
        guard-result.v1.json
        guard-result.md
      planning/
        execution-plan.v1.json
        execution-plan.md
        architecture-foundation.md
        dependency-contract.v1.json
        dependency-contract.md
        validation-plan.v1.json
        completion-criteria.v1.json
      estimation/
        estimate.v1.json
        estimate.md
      build/
        groups/
          build-group-01/
            scope.v1.json
            build-report.v1.json
            changed-files.v1.json
            command-log.txt
          build-group-02/
            scope.v1.json
            build-report.v1.json
            changed-files.v1.json
        workspace-delta.v1.json
      validation/
        validation-bundle.v1.json
        static-checks.json
        test-results.json
        capability-disclosure.json
      realization/
        realization-bundle.v1.json
        structural-outcomes.json
        behavioral-outcomes.json
        system-impact.json
      verdict/
        inspection-verdict.v1.json
        inspection-verdict.md
        repair-plan.v1.json
      audit/
        timeline.md
        events.ndjson
        decisions.md
      continuation/
        lineage.v1.json
        continuation-request.v1.json
      legacy/
        qage-link.json
        exeq-link.json
        reqap-link.json
  cache/
  index/
```

Artifact ownership model:
- `task/`: intake and clarification
- `guard/`: pre-plan policy and effective constraints
- `planning/`: plan truth, dependency wiring, validation plan, completion criteria
- `estimation/`: cost and gating artifacts
- `build/`: construction evidence and changed-scope truth
- `validation/`: deterministic and executed checks
- `realization/`: what actually happened
- `verdict/`: inspection and repair intent
- `audit/`: high-level and deep logs
- `continuation/`: lineage and continuation metadata
- `legacy/`: qage-era compatibility links only

## Schema / Version Coexistence Notes
- Machine-readable canonical artifacts must be schema-versioned from the start
- Markdown companions may exist, but machine-readable versioned files are canonical where both exist
- Legacy artifacts such as `reqap.md`, `cyqleN_changed.md`, `qontract_guard.json`, or `exeq` markdown remain valid evidence but must be mapped into versioned canonical artifact domains
- During migration, manifest entries may include both `legacy_path` and `canonical_path`
- Coexistence rule: canonical versioned artifacts win when both exist and conflict
- Future schema-versioning rules should be owned by the later contract documentation set, but migration must begin with explicit version labels like `task-spec.v1.json`, `run-manifest.v1.json`, `validation-bundle.v1.json`

## Migration Phases
### Phase 1: Canonical vocabulary and manifest bridge
- Goal: establish one run-level source of truth without rewriting the whole engine
- Scope: canonical enums, run manifest, stage alias map, manifest-linked legacy artifact ingestion
- Why this order: every later migration step depends on shared stage and status vocabulary
- Dependencies: current-state truth table, artifact path mapping
- Success criteria: every run produces a run manifest; legacy stage outputs can be linked into it; canonical and legacy names coexist without drift
- What NOT to change yet: build write model, full CLI redesign, deep validator expansion

### Phase 2: Front door replacement and guard separation
- Goal: replace task mutation with structured clarification and move guard before planning
- Scope: Qrystallizer, Task Spec, guard result artifact, no-mid-run-question enforcement
- Why this order: clarification and guard define the authoritative inputs for all downstream stages
- Dependencies: Phase 1 manifest and canonical stage IDs
- Success criteria: canonical runs start from Task Spec; guard emits effective constraints before planning; `tasqleveler` becomes compatibility-only
- What NOT to change yet: full qage retirement, full repair system, full transaction model

### Phase 3: Planning and build-group bridge
- Goal: move from briq-only planning to grouped execution with structured planning artifacts
- Scope: instruQtor outputs, dependency contract, validation plan, completion criteria, build-group scope
- Why this order: targeted repair and realization require grouped scope, not only briq-level artifacts
- Dependencies: Task Spec and guard result
- Success criteria: planning outputs define completion and validation before build; build scopes are grouped and manifest-linked
- What NOT to change yet: full execution backend replacement, full CLI flattening

### Phase 4: Validation and realization separation
- Goal: separate system validation and realization from inspection
- Scope: validator bundles, validation mode disclosure, realization bundle, inspection input contract
- Why this order: inspection cannot become authoritative until evidence is first-class
- Dependencies: grouped build outputs and manifest linkage
- Success criteria: inspection always consumes validation and realization artifacts; `exeq` and `reqap` are no longer the only evidence sources
- What NOT to change yet: final qage removal, full rollback implementation

### Phase 5: Repair-plan and continuation migration
- Goal: replace `reqap -> next tasq` canonical continuation with repair-plan-driven flow
- Scope: repair intent artifact, repair lifecycle states, same-run repair, linked continuation run behavior
- Why this order: single-pass architecture is not real until continuation stops depending on cycles
- Dependencies: inspection verdicts, grouped scopes, canonical manifests
- Success criteria: repair is explicit and bounded; cycle promotion is compatibility-only
- What NOT to change yet: total elimination of legacy cycle files if compatibility users still depend on them

### Phase 6: Repo-native `.qonqrete/` state and CLI migration
- Goal: make `.qonqrete` the canonical runtime state root and flatten user UX
- Scope: repo-native state layout, one-command primary flow, task-file input, continuation-aware CLI
- Why this order: state and continuation must be stable before UX simplification becomes canonical
- Dependencies: manifest, Task Spec, repair-plan, artifact hierarchy
- Success criteria: canonical run roots live under `.qonqrete`; primary CLI no longer requires sqrapyard flow or fixed `tasq.md`
- What NOT to change yet: deep GitOps/CI features, distributed execution

### Phase 7: Transaction safety hardening and legacy retirement
- Goal: move from disclosed partial-write risk to safe scoped writes and retire obsolete compatibility layers
- Scope: staged writes, build-group recovery metadata, rollback/recovery policy, legacy path retirement
- Why this order: hardening is safer after canonical state and manifests already exist
- Dependencies: grouped scopes, manifest, repair and continuation model
- Success criteria: build groups are attributable and recoverable; legacy qage-only or cycle-only logic is no longer canonical
- What NOT to change yet: future non-essential platform expansions unrelated to core migration

## Transition Risks
- Hidden continuation logic may survive through `promote_reqap()` even after repair-plan introduction
- Legacy docs and runtime output may continue emitting non-canonical stage names and confuse operators
- `.qonqrete` and qage coexistence may create ambiguous source-of-truth disputes if precedence is not enforced
- Partial-write behavior may continue to produce mixed state that inspection could misread
- Validator expansion may overclaim coverage in non-Python ecosystems if disclosures lag implementation
- Cache manifests may be confused with run manifests if naming and placement stay unclear
- Build-group migration may leave briq artifacts half-canonical and half-legacy unless ownership is explicit
- Repo-native CLI migration may flatten UX while still depending on hidden qage assumptions underneath
- Canonical enums may drift immediately if runtime, manifest, and docs are not updated together
- Compatibility alias layers may live too long and become a permanent source of ambiguity

## Non-Goals During Migration
- Rewriting the entire engine before the bridge exists
- Inventing the full future Qonscience contract suite here
- Defining the final exhaustive repair-plan schema here
- Claiming full language parity in deterministic validation
- Shipping full GitOps, CI/CD, or distributed runner architecture as part of this bridge
- Treating CLI convenience as more important than state correctness and auditability
- Embedding external CLI agents as black-box orchestrators that bypass QonQrete control
- Eliminating qage immediately before `.qonqrete` state and manifests are proven stable
- Hiding incompatibilities or legacy behavior behind optimistic docs

## Readiness Criteria For Post-Migration Architecture
The migration is sufficiently complete when all of the following are true:
- canonical runs start with Task Spec, not mutated task markdown
- canonical run state lives under `.qonqrete/`
- every run has a run manifest created at intake and updated through terminal state
- canonical stage IDs and lifecycle enums are used consistently across runtime, manifests, docs, and outputs
- guard occurs before planning in canonical flow
- planning emits completion criteria and validation plan before build starts
- build emits scoped changed-file truth and build-group evidence
- validation emits explicit coverage and execution-mode disclosure
- realization exists as a first-class artifact before inspection
- inspection emits verdict plus repair intent when needed
- repair-plan replaces `reqap -> next tasq` as canonical continuation logic
- cycle promotion, if still present, is compatibility-only and explicitly marked as such
- partial-write behavior is either replaced with safe scoped writes or explicitly disclosed and manifest-linked for every affected build attempt
- qage-era artifacts can be imported or linked, but they are no longer the sole authoritative state
- sqrapyard is no longer a required user-facing flow
- one-command repo-native primary UX exists without breaking auditability or state correctness
