<proposed_plan>
# QonQrete Migration Compound

## Purpose

This document is the authoritative transition map from the current implemented QonQrete runtime to the intended target architecture.

It exists separately because:

- `docs/01-project-execution-plan.md` defines what to build and in what broad order.
- `docs/02-project-qonscience.md` defines relationship contracts and authority boundaries.
- `docs/03-project-hard-ruleset.md` defines non-negotiable operating rules.
- `docs/04-project-target-state.md` defines the destination system shape.
- This document defines the bridge: what current subsystem becomes what target subsystem, what is kept vs retired, and how runtime state, artifacts, and control flow transition without hand-wavy rewrites.

This document does not replace those sources. It reconciles them into one migration truth map.

## Migration Summary

QonQrete is migrating from a qage-local, multi-cycle, file-promotion pipeline into a repo-native, single-pass orchestration system with targeted repair, explicit artifact contracts, one authoritative run manifest, and `.qonqrete/` as the persistent state root.

The main transition is not “replace all stages.” It is:

- replace `tasqleveler` with `Qrystallizer` as the only ambiguity-clearing front door
- convert current cycle promotion (`reqap -> next tasq`) into a bounded repair model
- keep `Instruqtor`, `Constrqutor`, `Inspeqtor`, `Calqulator`, and deterministic validators, but re-anchor them to stable target contracts
- retire `sqrapyard` and qage-centric runtime state as the canonical UX/state model
- introduce one run manifest that links all planning, build, validation, audit, and verdict artifacts together

## Current-to-Target Transition Overview

### Current operating model

- User task enters via `tasq.md`, usually through workspace-local or IDE wrapper flows.
- `qonqrete.sh` creates a per-run `worqspace/qage_*` workspace.
- Runtime executes configured agents in YAML order.
- Current flow is file-contract driven and cycle-based.
- `inspeqtor` emits `reqap`, and `qrane.py` may promote that into the next cycle’s `tasq`.
- Logging and evidence exist, but are fragmented across markdown artifacts, logs, qage directories, and optional cache state.

### Target operating model

- User runs QonQrete inside an existing repo.
- Runtime state persists under `.qonqrete/`.
- `Qrystallizer` is the single clarification phase and outputs a structured `Qrystalized Task Spec`.
- Guard/policy validation produces effective constraints before planning.
- `Instruqtor` creates one stable planning package.
- `Constrqutor` builds component groups using internal mini-briqs.
- Deterministic validators and controlled execution produce validation bundles.
- `Inspeqtor` issues a final verdict or a targeted repair plan.
- Repair is bounded to affected scopes only; no default whole-run recursive cycling.

### Biggest deltas

- `tasqleveler` heuristic enhancement becomes `Qrystallizer` readiness + gap resolution.
- `reqap -> next tasq` promotion becomes targeted repair metadata, not new task truth.
- qage-root artifact sprawl becomes `.qonqrete/runs/<run_id>/...`.
- fragmented logs become one authoritative run manifest plus dual-layer audit.
- current briq-first execution becomes component-group execution with internal briqs.
- optional `sqrapyard` seeding becomes repo-native in-place repo operation.

### Highest-risk transitions

- removing cycle semantics without losing continuation/resume safety
- preserving current validator value while changing their orchestration role
- migrating from qage-local artifacts to repo-native `.qonqrete/` without breaking inspection/debuggability
- keeping audit continuity during a period where current and target flows coexist
- avoiding doc/code drift during staged rollout

### Explicit inconsistencies to preserve as migration facts

These are current-reality inconsistencies and must not be silently normalized:

- `worqspace/pipeline_config.yaml` header comments describe `instruqtor -> calqulator -> construqtor -> inspeqtor -> qontextor -> qompressor`, but the actual configured agent order is `tasqleveler -> instruqtor -> calqulator -> construqtor -> qontextor -> qompressor -> qontrabender -> inspeqtor`.
- `qrane/paths.py` defines `qache_dir` as `sqrapyard/qache.d`, while current pipeline config and `qontrabender` treat `qache.d/` as a run/qage artifact.
- `worqspace/qage_20260402_172204/` contains a historical `Qrystallizer/Qualifier` concept. It is experimental residue, not current runtime truth and not target-state truth.

## Migration Truth Table

| Current Module / Artifact | Current Role | Target Role | Action | Dependency / Prerequisite | Migration Notes | Done Criteria |
| --- | --- | --- | --- | --- | --- | --- |
| `tasqleveler` | Optional cycle-1 task enhancer, heuristic rewrite | Replaced by `Qrystallizer` front door | `REPLACE` | `Qrystalized Task Spec` schema, readiness gate, bounded question flow | Do not preserve long-term hybrid behavior. Keep only as temporary compatibility shim if needed. | No run depends on `tasqleveler`; all clarification enters through `Qrystallizer`. |
| `Qrystallizer` | Not implemented | Sole ambiguity-clearing stage, emits `READY/NOT_READY` task spec | `KEEP` as new target module | task-spec contract, question policy, continuation input shape | Must ask at most bounded high-impact questions and lock assumptions. | Structured spec exists and is consumed by guard/planning only. |
| `Instruqtor` | Briq planner + current QONTRACT generator | Planning authority producing full planning package | `ADAPT` | `Qrystalized Task Spec`, effective constraints, component/dependency contracts | Expand beyond briq decomposition into Architecture Foundation, Dependency Contract, Validation Plan, Completion Criteria. | Produces stable planning artifacts before build starts. |
| `Constrqutor` | Briq-by-briq code writer into `qodeyard/` | Component-group build engine using internal mini-briqs | `ADAPT` | component contracts, dependency contract, build report schema | Shift from global briq-first execution to component-first execution. | Emits component/group build reports, changed-file manifests, assumption logs. |
| `Inspeqtor` | Final review stage using guard + local verification + AI review | Evidence-based judge and repair target issuer | `ADAPT` | validator bundle schema, verdict schema, repair-plan schema | Must judge against explicit planning artifacts, not cycle prose. | Emits `done` or `repair required` with precise targets and evidence refs. |
| system validators / local verification | Mechanical syntax/import/AST checks, Python-heavy | System-owned validator architecture | `ADAPT` | validator registry, bundle schema, execution mode disclosure | Keep current deterministic modules, move them under explicit validator authority. | Validation outputs are machine-readable bundles, not scattered side effects. |
| `QontractGuard` / guard stage | AST-based contract enforcement during build/review | Pre-build guard + validation contributor | `SPLIT` | guard-result schema, effective-constraints model | Current enforcement role remains, but target model needs an earlier guard result plus continued deterministic enforcement later. | Guard result exists pre-plan; enforcement still runs in validation/build where applicable. |
| `Calqulator` | Cost estimator that mutates briq headers | Estimation/gating service | `ADAPT` | planning package, execution profile metadata, manifest cost fields | Remove requirement that cost annotation live inside briq files. Estimates belong in artifacts/manifest. | Cost data recorded in manifest/audit, not only via briq mutation. |
| qage runtime model | Per-run workspace clone under `worqspace/qage_*` | Transitional runtime adapter only | `RETIRE` | `.qonqrete/` state root, continuation model | qage can remain as a compatibility shell during migration, but not canonical target state. | Default repo-native runs no longer require qage mental model. |
| `.qonqrete/` target state model | Not canonical today | Canonical persistent state root | `KEEP` as target state | run identity, artifact hierarchy, continuation metadata | Becomes source of truth for run reasoning/evidence, not for repo code. | New runs persist under `.qonqrete/` with stable hierarchy. |
| `sqrapyard` flow | Optional seed-copy staging flow | Hidden internal compatibility path only, then retired from main UX | `RETIRE` | repo-native CLI entry, in-place repo execution | Users should not need `-s` or repo copying. | Main UX works in existing repo with one command. |
| CLI flow (`init/run/resume/clean`) | Manual multi-command lifecycle | `qonqrete [task-file?]` one-command mental model | `ADAPT` | auto-init, repo detection, continuation prompt, task-path support | Preserve lower-level commands only if needed for advanced/debug use. | Happy path requires no `init` + `run` split and no forced `tasq.md` name. |
| audit trail system | Fragmented markdown/log/marker artifacts | One authoritative run manifest + dual-layer audit | `MERGE` | run manifest schema, timeline format, deep trace structure | Existing logs stay as raw evidence, but must be indexed by manifest. | Every major event is traceable through manifest + timeline + deep trace. |
| run manifest | Missing as authoritative record | Primary per-run linkage/index object | `KEEP` as new target artifact | run lifecycle hooks in orchestrator | Must tie all artifacts, statuses, costs, validator results, and final verdicts together. | Every run has exactly one manifest with append/update discipline. |
| cycle promotion flow | `reqap.d/cyqleN_reqap.md -> tasq.d/cyqleN+1_tasq.md` | Targeted repair plan and continuation metadata | `REPLACE` | repair-plan schema, target scope identifiers | Promotion stops being task truth creation. Repair references existing plan + affected scopes. | No default full-cycle promotion path in canonical runs. |
| targeted repair flow | Not canonical; whole-cycle continuation dominates | Bounded repair pass model | `KEEP` as target behavior | verdict schema, repair-plan schema, repair cap policy | Repair must be scope-limited and capped. | Rebuild/revalidate only affected component groups. |
| pipeline config / pipeline order | YAML-driven order with comment drift and current stale helper ordering | Explicit phase model with authoritative stage registry/order | `ADAPT` | target phase map, manifest stage IDs | Current helper ordering drift must be resolved explicitly, not by comments. | One source of truth defines actual stage order and names. |
| `qache` / cache / path inconsistencies | Mixed qage-level vs `sqrapyard` path assumptions | Stable cache/artifact placement under `.qonqrete/` | `ADAPT` | artifact hierarchy, cache ownership rules | Cache support artifacts must not act as hidden planning truth. | No path disagreement exists between runtime paths and documentation. |
| historical experimental pipeline artifacts | Old `Qrystallizer/Qualifier` concepts in historical qage | Historical reference only | `RETIRE` from active contract | none | Keep as archive only; do not let them shape active design claims. | Historical artifacts are explicitly labeled non-canonical. |
| `qontextor`, `qompressor`, `qontrabender` | Warmup/context/cache support services | Support services beneath planning/build/validation authority | `ADAPT` | artifact placement rules, manifest stage indexing | Keep as non-authoritative support layers. They must never define plan truth or verdict truth. | Support outputs are indexed as auxiliary artifacts only. |

## Bridge Flow

### Layer 1: Task intake and ambiguity control

Current:
- Raw `tasq.md` enters runtime.
- `tasqleveler` may rewrite cycle-1 task heuristically.
- Important ambiguity may survive into later stages.
- Current multi-cycle model compensates for unclear tasking by allowing later correction.

Target:
- Raw task input becomes `Task Input`.
- `Qrystallizer` performs one bounded clarification pass.
- It emits `Qrystalized Task Spec` with:
  - goal
  - known inputs
  - constraints
  - locked assumptions
  - blocking gaps
  - non-blocking unknowns
  - readiness
- If `NOT_READY`, planning/build do not start.
- No later phase may ask the user anything.

Bridge:
- Treat current `tasqleveler` as deprecated compatibility residue.
- Introduce `Qrystallizer` before current planning, initially feeding `instruqtor` with a structured spec while current downstream file contracts still exist.
- Remove any dependency on cycle-1 task rewrite as a planning prerequisite.
- Convert unresolved low-impact ambiguity into explicit assumptions, not future cycle prompts.

### Layer 2: Guard and constraints

Current:
- `QontractGuard` exists mainly as enforcement inside build/review.
- Guardrails are real, but early pre-plan policy resolution is not a first-class stage.

Target:
- A guard stage validates the clarified task before planning.
- It outputs:
  - `pass | fail | review`
  - blocking issues
  - warnings
  - effective constraints

Bridge:
- Split current guard responsibility into:
  - pre-build guard result
  - continued deterministic enforcement in validation/build
- Keep current AST enforcement where it works, but move constraint truth earlier in the run.

### Layer 3: Planning and execution shape

Current:
- `instruqtor` creates briqs and current QONTRACT artifacts.
- cycle count and sensitivity are runtime tuning inputs.
- planning authority is present but narrower than target requirements.

Target:
- `Instruqtor` becomes the stable planning authority.
- It outputs:
  - Architecture Foundation
  - Execution Plan
  - Dependency & Interaction Contract
  - Component Contracts
  - Validation Plan
  - Completion Criteria
  - execution profile / repair allowance

Bridge:
- Expand `instruqtor` outputs first without immediately replacing all internal mechanics.
- Preserve current briq machinery as internal execution detail.
- Shift public planning truth from “briqs + contract markdown” to “planning package + contracts.”

### Layer 4: Build model transition

Current:
- `construqtor` builds briq-by-briq.
- coherence is strengthened by retries and local checks, but working unit is still primarily the briq.
- partial writes land directly in `qodeyard/`.

Target:
- `Constrqutor` builds component groups.
- internal mini-briqs remain allowed, but only inside shared component context.
- each group produces a build report and changed-file manifest.

Bridge:
- Keep current briq generation support, but re-scope it under component/group ownership.
- Do not generate all briqs as isolated long-lived public artifacts.
- Make group-level validation and reporting the new stable handoff.

### Layer 5: Validation and judgment

Current:
- local validation exists
- `inspeqtor` runs guard, local verification, per-briq AI review, meta review
- output is `reqap`, which currently doubles as review record and next-cycle input candidate

Target:
- deterministic validators emit validator bundles
- `Inspeqtor` consumes planning package + build reports + validator bundles + tests
- output is a verdict plus optional targeted repair plan

Bridge:
- keep current validator code and `inspeqtor`, but change outputs:
  - validator bundles become distinct artifacts
  - `reqap` stops being the next-task transport
  - `Inspeqtor` verdict becomes authoritative for finish/repair
- testing/execution becomes an explicit validator responsibility, not hidden AI judgment.

### Layer 6: Finish, continuation, and repair

Current:
- autonomous or user-gated promotion may spawn new cycles
- resume copies old qage into a new qage
- “finished” and “continuable” are conceptually separate

Target:
- every run is continuable
- finish means verdict reached
- repair means scoped continuation from an existing run state
- continuation metadata decides whether the next action is inspect, repair, or new task extension

Bridge:
- replace cycle promotion with repair targets + continuation metadata
- use manifest state to reopen a run or fork a continuation
- keep old qage resume only as compatibility mode until `.qonqrete/` continuation is complete

## State Migration Design

### Current state locations

Workspace-level inputs:
- `worqspace/config.yaml`
- `worqspace/pipeline_config.yaml`
- `worqspace/tasq.md`
- `worqspace/sqrapyard/`
- `worqspace/caching_policy.yaml`

Per-run state:
- `worqspace/qage_*/`
- `tasq.d/`
- `briq.d/`
- `qontract.d/`
- `qodeyard/`
- `exeq.d/`
- `reqap.d/`
- `qontext.d/`
- `bloq.d/`
- `struqture/`
- current `qache.d/` expectations, with real path inconsistency

Saved snapshots:
- `worqspace/qonstructions/<name>/`

### Target state locations

Canonical state root:
- `.qonqrete/`

Suggested stable layout:
- `.qonqrete/config/`
- `.qonqrete/runs/<run_id>/`
- `.qonqrete/continuations/`
- `.qonqrete/cache/`
- `.qonqrete/index/`

### Migration boundaries

Repo source of truth remains:
- all actual code
- repo config
- task files the user explicitly provides
- git history and project structure

QonQrete state source of truth becomes:
- clarified task state
- guard result
- planning package
- build reports
- validator bundles
- inspection verdict
- audit trail
- continuation metadata
- run manifest
- support caches/context artifacts

### Continuity / resume / continuation model

During transition:
- old qage resume can still exist
- new repo-native runs must record enough state to continue without cloning qage directories

Target model:
- run continuation is manifest-based, not qage-copy based
- a run can be:
  - `running`
  - `awaiting_gate`
  - `repairable`
  - `completed`
  - `completed_with_risk`
  - `failed`
- a continuation references:
  - source run
  - reason
  - planned scope
  - inherited artifacts
  - whether planning is reused or refreshed

### Compatibility expectations during transition

- qage-backed runs may coexist temporarily with `.qonqrete` runs
- `tasqleveler` may exist in code temporarily, but must not be the canonical front door
- current validators remain valid transitional execution units
- `reqap` may persist as a human-readable review artifact, but not as the canonical next-task transport
- support helpers (`qontextor`, `qompressor`, `qontrabender`) may remain, but become auxiliary artifact producers under manifest indexing

## Authoritative Run Manifest Design

### Purpose of the manifest

The run manifest is the single authoritative record that ties one run’s inputs, stage outputs, evidence, status, audit, and continuation state together.

It exists to solve the current fragmentation problem.

### Where it lives

Primary:
- `.qonqrete/runs/<run_id>/run-manifest.json`

Optional readable mirror:
- `.qonqrete/runs/<run_id>/run-manifest.md`

### When it is created

- immediately after task intake is accepted and a run ID is allocated
- before `Qrystallizer` executes

### When it is updated

Append/update points:
- task intake registration
- `Qrystallizer` completion
- guard completion
- planning completion
- cost estimate completion
- each build group completion
- each validator completion
- `Inspeqtor` verdict
- each repair pass start/end
- final run closure
- continuation creation

### What stages append to it

- orchestrator always
- `Qrystallizer`
- guard stage
- `Instruqtor`
- `Calqulator`
- `Constrqutor`
- system validators
- `Inspeqtor`

### How it links all artifacts together

It stores:
- run metadata
- stage statuses
- artifact paths
- artifact hashes if desired
- scope identifiers
- assumption references
- cost actuals/estimates
- validator bundle references
- verdict references
- audit index references
- continuation links

### How it supports audit, continuation, validation, and final verdicts

- audit: points to timeline and deep trace entries by stage and event
- continuation: records current status, repairability, inherited artifacts, and next-action metadata
- validation: indexes every validator bundle and its scope
- final verdict: stores authoritative verdict status plus evidence references

### Concrete schema example

```json
{
  "run_id": "run_2026-04-08T14-22-31Z_repo-slug_ab12cd",
  "repo": {
    "root": "/repo",
    "git_head": "abc123def456",
    "task_input_path": "tasks/feature-auth.md"
  },
  "mode": {
    "capability_mode": "simulation",
    "execution_mode": "local_system",
    "repair_cap": 2
  },
  "status": {
    "lifecycle": "repairable",
    "current_stage": "inspection",
    "final_verdict": null
  },
  "inputs": {
    "task_input_artifact": "artifacts/task/task-input.md",
    "continuation_from_run": null
  },
  "clarification": {
    "status": "ready",
    "artifact": "artifacts/task/qrystalized-task-spec.json",
    "questions_asked": 3,
    "locked_assumptions": [
      "Use existing auth module naming conventions",
      "Prefer repo-default test runner"
    ]
  },
  "guard": {
    "status": "pass",
    "artifact": "artifacts/guard/guard-result.json",
    "effective_constraints_artifact": "artifacts/guard/effective-constraints.json"
  },
  "planning": {
    "status": "complete",
    "artifacts": {
      "architecture_foundation": "artifacts/plan/architecture-foundation.md",
      "execution_plan": "artifacts/plan/execution-plan.md",
      "dependency_contract": "artifacts/plan/dependency-interaction-contract.md",
      "component_contracts": [
        "artifacts/plan/components/auth-service.json",
        "artifacts/plan/components/api-layer.json"
      ],
      "validation_plan": "artifacts/plan/validation-plan.json",
      "completion_criteria": "artifacts/plan/completion-criteria.json"
    }
  },
  "estimation": {
    "estimated_cost_usd": 4.83,
    "actual_cost_usd": 2.11,
    "confidence": "medium",
    "artifact": "artifacts/plan/cost-estimate.json"
  },
  "build": {
    "groups": [
      {
        "group_id": "auth-service",
        "status": "complete",
        "artifacts": {
          "build_report": "artifacts/build/groups/auth-service/build-report.json",
          "changed_files": "artifacts/build/groups/auth-service/changed-files.json"
        }
      }
    ]
  },
  "validation": {
    "bundles": [
      "artifacts/validation/bundles/syntax.json",
      "artifacts/validation/bundles/contracts.json",
      "artifacts/validation/bundles/tests.json"
    ],
    "summary_artifact": "artifacts/validation/validation-summary.md"
  },
  "inspection": {
    "status": "repair_required",
    "artifact": "artifacts/verdict/inspection-verdict.json",
    "repair_plan_artifact": "artifacts/verdict/repair-plan.json"
  },
  "audit": {
    "timeline_artifact": "artifacts/audit/timeline.jsonl",
    "deep_trace_artifact": "artifacts/audit/deep-trace.jsonl"
  },
  "continuation": {
    "repair_passes_used": 0,
    "repair_targets": ["auth-service"],
    "resume_token": "run_2026-04-08T14-22-31Z_repo-slug_ab12cd"
  }
}
```

## Artifact Hierarchy Design

### Ownership model

- orchestrator owns run root, manifest, stage status, continuation metadata
- `Qrystallizer` owns clarified task artifacts
- guard owns guard result and effective constraints
- `Instruqtor` owns planning package
- `Constrqutor` owns build reports and changed-file manifests
- validators own validation bundles and test outputs
- `Inspeqtor` owns verdicts and repair plans
- audit system owns timeline and deep trace
- support helpers own only auxiliary context/cache artifacts

### Concrete example tree

```text
.qonqrete/
  config/
    defaults.json
    models.json
  cache/
    context/
    payloads/
  index/
    latest-run.json
    runs.json
  runs/
    run_2026-04-08T14-22-31Z_repo-slug_ab12cd/
      run-manifest.json
      artifacts/
        task/
          task-input.md
          qrystalized-task-spec.json
        guard/
          guard-result.json
          effective-constraints.json
        plan/
          architecture-foundation.md
          execution-plan.md
          dependency-interaction-contract.md
          validation-plan.json
          completion-criteria.json
          components/
            auth-service.json
            api-layer.json
        build/
          groups/
            auth-service/
              build-report.json
              changed-files.json
              execution-log.txt
            api-layer/
              build-report.json
              changed-files.json
        validation/
          bundles/
            syntax.json
            imports.json
            contracts.json
            component-coherence.json
            tests.json
          validation-summary.md
        verdict/
          inspection-verdict.json
          repair-plan.json
          final-verdict.md
        audit/
          timeline.jsonl
          deep-trace.jsonl
          prompts/
          model-outputs/
          command-logs/
        continuation/
          state.json
          resume.json
        support/
          qontext/
          bloq/
          qache/
```

### Intended hierarchy rules

- run root is the unit of auditability and continuation
- task artifacts are immutable inputs/clarified inputs for that run
- planning artifacts are stable unless an explicit repair-plan update says otherwise
- build artifacts are grouped by build scope, not by global cycle count
- validation artifacts are grouped by validator/bundle identity
- verdict artifacts are authoritative outputs of `Inspeqtor`
- audit artifacts are append-only event streams
- continuation metadata references existing artifacts; it does not duplicate planning truth unless forked intentionally

## Migration Phases

### Phase 1: Canonical contracts and manifest spine

Goal:
- introduce the target artifact contracts and run manifest without replacing the whole runtime

Scope:
- define manifest schema
- define `Qrystalized Task Spec`, `Guard Result`, planning package, validator bundle, verdict schemas
- wire stage indexing into manifest
- make audit timeline/deep trace explicit

Why this order:
- everything else depends on a stable state and artifact model

Dependencies:
- none beyond current orchestrator access

Success criteria:
- every run can be indexed through one manifest
- stage outputs have stable names and ownership
- audit no longer depends on artifact scavenging

What not to change yet:
- do not remove qage runtime yet
- do not rewrite `construqtor` build strategy yet
- do not add new execution backends yet

### Phase 2: Front-door replacement and guard split

Goal:
- replace `tasqleveler` semantics with `Qrystallizer` + pre-plan guard result

Scope:
- add `Qrystallizer`
- add readiness gate
- add pre-build guard stage and effective constraints
- stop relying on task rewrites as the planning input truth

Why this order:
- target architecture requires ambiguity to be resolved once, before planning

Dependencies:
- Phase 1 contracts and manifest support

Success criteria:
- planning consumes structured clarified task input
- no later stage asks user questions
- guard result exists before `Instruqtor`

What not to change yet:
- do not fully remove old validators
- do not fully retire qage compatibility mode yet

### Phase 3: Planning package expansion and component-group execution

Goal:
- move planning/build handoff from briq-centric public truth to component/group contracts

Scope:
- expand `Instruqtor` outputs
- introduce Dependency & Interaction Contract
- introduce Component Contracts
- adapt `Constrqutor` to execute component groups with internal mini-briqs
- emit group-level build reports

Why this order:
- targeted repair and meaningful validation need stable scope identities

Dependencies:
- Phases 1-2

Success criteria:
- build scope is component/group based
- changed-file manifests and assumptions are group-scoped
- `Inspeqtor` can target repair precisely

What not to change yet:
- do not fully retire briq internals if still useful
- do not overbuild multi-backend execution

### Phase 4: Validation architecture and repair model

Goal:
- convert current review/cycle semantics into validator bundles + verdict + targeted repair

Scope:
- formalize validator bundles
- keep current deterministic validators, re-anchor them under validator ownership
- separate validator output from `Inspeqtor` judgment
- replace `reqap -> next tasq` promotion with repair plan artifacts and continuation metadata

Why this order:
- this is the actual bridge from multi-cycle runtime to target single-pass + repair

Dependencies:
- Phases 1-3

Success criteria:
- canonical runs no longer depend on full-cycle task promotion
- repair touches only affected groups
- repair cap is enforced and visible in audit

What not to change yet:
- do not force Codex/external execution integration
- do not remove all historical compatibility artifacts immediately

### Phase 5: Repo-native UX and qage retirement

Goal:
- make `.qonqrete/` and one-command repo-native UX canonical

Scope:
- flatten CLI to `qonqrete [task-file?]`
- remove user-facing dependence on `sqrapyard`
- support task-file path input
- auto-detect continuation
- retire qage/sqrapyard from happy-path UX

Why this order:
- UX should be the last thing flattened after internal contracts are stable

Dependencies:
- Phases 1-4

Success criteria:
- user can run inside a repo without copy/staging flow
- `.qonqrete/` holds authoritative state
- qage mode is compatibility/debug only or removed

What not to change yet:
- do not expand into full GitOps/CI/CD orchestration
- do not promise broader backend parity than actually exists

## Transition Risks

- contract drift between old file contracts and new manifest/contracts during coexistence
- qage and `.qonqrete/` state duplicating or disagreeing if migration boundary is unclear
- `reqap` continuing to act as implicit task truth after targeted repair is introduced
- validator claims outrunning actual deterministic coverage, especially outside Python-centric flows
- build coherence regressions if component-group execution is introduced without clear component contracts
- audit inflation if every old artifact is mirrored instead of indexed
- CLI flattening before continuation/state semantics are stable
- support helpers (`qontextor`, `qompressor`, `qontrabender`) accidentally remaining hidden planning authorities
- path inconsistencies around `qache` causing stale or misplaced support artifacts
- historical experimental configs being mistaken for target truth

## Non-Goals During Migration

- full rebuild of the runtime before the staged bridge exists
- introducing a standalone `Qualifier` AI agent
- preserving open-ended autonomous cycle reruns as a first-class architecture
- making external execution agents the orchestrator or planner
- rewriting all deterministic validators before re-anchoring their ownership model
- solving all non-Python validation depth before the architecture transition is complete
- full GitOps/CI/CD platform expansion during the migration bridge
- replacing every markdown artifact with machine-only artifacts; readable artifacts still matter
- hiding capability differences between simulation and execution-enabled modes

## Readiness Criteria For Post-Migration Architecture

Migration is sufficiently complete when all of the following are true:

- canonical runs start with `Qrystallizer`, not `tasqleveler`
- no stage after clarification asks the user questions
- one run manifest exists per run and links all major artifacts
- `.qonqrete/` is the canonical persistent run-state root
- current qage/sqrapyard flow is no longer the happy path
- planning truth is a stable planning package, not cycle prose plus inferred side effects
- build scope is expressed as component/group contracts with group build reports
- validator outputs are first-class bundles, separate from `Inspeqtor` judgment
- `Inspeqtor` outputs `done` or targeted `repair required`, with evidence references
- canonical runs do not rely on `reqap -> next tasq` promotion
- repair is bounded, scoped, and capped
- audit has both a high-level timeline and deep technical trace
- support artifacts such as `qontext`, `bloq`, and `qache` are auxiliary, not hidden sources of authority
- pipeline order is defined by one authoritative source and no longer conflicts with comments/docs
- `qache` path ownership is consistent in runtime code and documentation
- historical `Qrystallizer/Qualifier` artifacts are explicitly archived as non-canonical

## Assumptions and Defaults

- `docs/00-project-current-state.md` remains the primary truth for current implementation, except where verified repo inconsistencies are explicitly listed above.
- `Qrystallizer` fully replaces `tasqleveler` in the target architecture; any coexistence is temporary compatibility only.
- No standalone `Qualifier` agent is introduced; validation remains system-owned.
- Single-pass plus targeted repair is the target canonical execution model.
- `.qonqrete/` is the target state root; qage is transitional only.
- Existing deterministic validators are preserved and re-anchored before any major rewrite.
</proposed_plan>
