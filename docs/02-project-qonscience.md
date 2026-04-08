# QonQrete Qonscience

## Purpose of Qonscience
Qonscience is the authoritative relational contract layer for QonQrete. It defines how system parts are allowed to relate, what each part owns, what each handoff must contain, where decisions are allowed, where they are forbidden, and how evidence flows from task intake to completion verdict.

It is the connective model between:
- the current implemented pipeline and artifact layout
- the intended future agent architecture
- the hard operational rules
- the target repo-native product shape
- the chat direction toward sharp gap detection, bounded autonomy, clean audit, zero-config UX, and explicit capability modes

Qonscience is not a rebuild plan, not a rewritten ruleset, and not a target-state restatement. It is the structural and behavioral contract that tells every part of QonQrete how it may connect to every other part.

## System Relationship Model
QonQrete is a system-owned orchestration authority with bounded AI stages and deterministic validation services.

Core relationship rules:
- The system owns orchestration, sequencing, gating, persistence, audit, repair caps, and final operational control.
- AI agents own bounded reasoning or bounded execution within explicit contracts only.
- Deterministic validators own mechanical truth checks and executed evidence.
- Planning authority and execution authority are separate.
- Validation authority and judgment authority are separate.
- Clarification authority exists in one place only: `Qrystallizer` in the target model, `tasqleveler` only as current transitional residue.
- Downstream stages must consume structured artifacts, not depend on prose interpretation alone.
- No agent may silently redefine architecture, constraints, completion criteria, or dependency wiring after planning is locked.
- The build path is one primary clarify/guard/plan/build/validate/judge flow with bounded targeted repair only. Current multi-cycle promotion exists in code, but the intended relational contract treats it as transitional, not canonical.

System authority hierarchy:
1. QonQrete system contracts and guards
2. Deterministic validation evidence
3. Planning artifacts
4. AI execution outputs
5. AI judgment outputs

## Agent Contracts

### tasQleveler / Qrystallizer Transition Contract
- Current state:
  - `tasqleveler` exists and can rewrite cycle-1 task input heuristically.
  - It is optional, conservative, and not structurally authoritative.
  - Current runtime still supports cycle-based task promotion through `reqap -> next tasq`.
- Replacement direction:
  - `Qrystallizer` replaces `tasqleveler` as the sole front door for ambiguity handling.
  - It moves task intake from heuristic enhancement to explicit readiness assessment.
  - It produces a structured `Qrystalized Task Spec` instead of rewriting raw task prose.
- Compatibility expectations:
  - During transition, anything equivalent to task clarification must preserve downstream ability to feed `instruqtor`.
  - `tasqleveler` may exist in code, but Qonscience treats it as deprecated and non-canonical.
  - No later-stage behavior may depend on long-term coexistence of both agents.

### Qrystallizer
Input:
- Raw task input from file or user-selected task source
- Repo context signals allowed by system
- Default policy baseline and configured overrides
- Optional prior continuation state

Output:
- `Qrystalized Task Spec`
- Readiness state: `READY` or `NOT_READY`
- Locked assumptions
- Blocking gaps
- Non-blocking unknowns
- High-impact clarified decisions only

Responsibilities:
- Extract goal, inputs, constraints, desired outcomes, and material unknowns
- Detect only high-impact gaps
- Ask bounded questions once, before execution
- Convert unresolved low-impact ambiguity into explicit assumptions
- Prepare a structured, plan-ready task artifact

Must NOT:
- Generate architecture
- Generate code
- Decide execution profile
- Run validation
- Ask questions after readiness is locked
- Turn into an open-ended interview or form-filler

### Instruqtor
Input:
- `READY` `Qrystalized Task Spec`
- Effective constraints from guard/system policy validation
- Repo and codebase context needed for planning
- Capability mode and system limits

Output:
- Planning package containing:
  - Architecture Foundation
  - Execution Plan
  - Dependency & Interaction Contract
  - Component Contracts
  - Validation Plan
  - Completion Criteria
- Internal execution shape decisions
- Complexity and batch profile decisions

Responsibilities:
- Convert clarified intent into a stable build design
- Define component boundaries and dependency wiring
- Define allowed interaction paths and forbidden shortcuts
- Define what completion means before code generation starts
- Define what validators must prove and what Inspeqtor must judge
- Select bounded execution shape

Must NOT:
- Ask questions mid-run
- Redesign user intent
- Delegate architecture decisions to builders
- Emit only prose without structured contracts
- Treat global briq generation as sufficient architecture

### Constrqutor
Input:
- Locked planning package
- Component Contract for current build scope
- Dependency & Interaction Contract
- Effective constraints
- Capability mode and execution boundary rules
- Existing repo/qode state for scoped targets

Output:
- Code and file changes within allowed scope
- Build Report per component/group
- Changed-file manifest
- Execution summary
- Logged assumptions used during build

Responsibilities:
- Implement scoped component groups against locked contracts
- Use briqs only as internal construction units inside shared component context
- Preserve contract conformance while changing code
- Surface assumptions explicitly in build artifacts
- Hand deterministic validation enough evidence to verify what changed

Must NOT:
- Ask the user questions
- Redesign architecture
- Change dependency contracts
- Invent new completion criteria
- Treat itself as planner, validator, or final judge
- Bypass deterministic validation
- Perform hidden scope expansion

### Inspeqtor
Input:
- Planning package
- Build Reports and changed-file manifests
- Validator Result Bundles
- Test outputs or explicit simulation-mode absence of test execution
- Effective constraints and assumptions

Output:
- `Inspection Verdict`
- Status: `done` or `repair required`
- Repair targets
- Reasons tied to explicit evidence
- Residual risk notes when applicable

Responsibilities:
- Judge built output against explicit plans and evidence
- Compare implementation against Architecture Foundation, Dependency & Interaction Contract, Validation Plan, and Completion Criteria
- Determine whether repair is required and where
- Keep repair targeting scoped to affected components/groups

Must NOT:
- Execute tests itself
- Replace deterministic validation
- Rescue vague upstream architecture by intuition
- Ask mid-run questions
- Declare completion without artifact and validator evidence

### System Validators (Non-AI)
Input:
- Planned validation scope
- Changed files and build manifests
- Repo state under allowed execution boundaries
- Contracts and mechanical rules

Output:
- `Validation Result Bundle`
- Machine-readable results
- Condensed human-readable summaries
- Test outputs where execution mode allows them

Responsibilities:
- Own syntax, parseability, import/interface/schema checks, required artifact checks, contract/policy/mechanical checks, grouped component coherence checks, and sandboxed test execution
- Produce evidence for Inspeqtor and audit
- Enforce non-subjective guardrails
- Represent execution truth honestly by capability mode

Must NOT:
- Plan architecture
- Decide product intent
- Judge overall completion by themselves
- Present heuristic AI review as mechanical proof
- Exist as a standalone AI `Qualifier` agent in the target model

## Data Contracts

### Task Input Contract
Contains:
- User task source
- Task content
- Task source path or input origin
- Repo target identity
- Optional continuation reference
- Explicit user-provided constraints only

Rules:
- Raw input is not execution-ready by default
- Task input may be incomplete
- Task input is the only stage allowed to be ambiguous before clarification

### Qrystalized Task Spec Contract
Contains:
- Goal
- Known inputs
- Constraints
- Locked assumptions
- Critical decisions confirmed
- Blocking gaps
- Non-blocking unknowns
- Readiness status

Rules:
- This is the only artifact allowed to carry pre-execution ambiguity resolution
- `READY` is required before planning
- `NOT_READY` blocks planning and building
- After this artifact is locked, ambiguity becomes assumptions, not questions

### Execution Plan Contract
Contains:
- Architecture Foundation
- Execution Plan
- Dependency & Interaction Contract
- Component Contracts
- Validation Plan
- Completion Criteria
- Bounded repair allowance
- Execution shape metadata

Rules:
- Must be stable before build starts
- Becomes the planning authority for builders, validators, and Inspeqtor
- May only be updated by explicit repair-plan mechanics, not by silent builder adaptation

### Component Contract
Contains:
- Component identity
- Inputs and outputs
- Exposed interfaces
- Dependencies
- Allowed collaborators
- Forbidden direct links
- Constraints
- Acceptance conditions

Rules:
- Constrqutor builds against this unit
- Validators verify coherence against this unit
- Components may depend only on declared interfaces and allowed collaborators
- Components must not bypass their declared boundary

### Build Report Contract
Contains:
- Component/group scope
- Changed-file manifest
- Summary of work performed
- Assumptions used
- Declared touched interfaces/dependencies
- Local build issues and outcomes
- Capability mode used during execution

Rules:
- Must describe what changed and why
- Must identify which assumptions influenced output
- Must be sufficient for downstream validation and audit

### Inspection Verdict Contract
Contains:
- `done` or `repair required`
- Repair targets if any
- Evidence references
- Reasons mapped to explicit criteria
- Remaining risk notes
- Final confidence conditioned on capability mode

Rules:
- Cannot be issued without validator evidence
- Cannot use vague intuition as sole basis
- Must target repairs precisely, not request global reruns by default

### Validation Result Contract
Contains:
- Validator identity
- Scope checked
- Mechanical outcome
- Violations/errors/warnings
- Test execution results if executed
- Summary suitable for audit and inspection

Rules:
- Must distinguish executed validation from simulated/non-executed validation
- Must not overclaim coverage
- Must remain deterministic and machine-consumable

## Dependency & Interaction Map

### Agent-to-Agent Links
- `Qrystallizer -> Instruqtor`
  - Sends `READY` `Qrystalized Task Spec`
  - Allowed only when blocking gaps are resolved or converted into acceptable assumptions
- `Guard/System policy stage -> Instruqtor`
  - Sends effective constraints, warnings, and pass/fail/review status
  - Planning allowed only on non-blocking guard outcomes
- `Instruqtor -> Calqulator`
  - Sends planned execution shape, estimated scope, and complexity metadata
  - Calqulator may estimate but must not redesign plan
- `Instruqtor -> Constrqutor`
  - Sends locked planning package and current component/group scope
  - Constrqutor may execute only within these contracts
- `Constrqutor -> System Validators`
  - Sends changed-file manifests, component/build reports, and produced artifacts
  - Validation runs on what was actually changed and what the plan required
- `System Validators -> Inspeqtor`
  - Send validator result bundles and test evidence
  - Inspeqtor consumes but does not replace them
- `Constrqutor -> Inspeqtor`
  - Sends build reports and assumption logs
- `Inspeqtor -> Constrqutor`
  - Sends targeted repair plan only when verdict is `repair required`
  - Must target affected groups/components only

Forbidden agent links:
- `Constrqutor -> user`
- `Inspeqtor -> user` mid-run
- `Constrqutor -> planning artifact rewrite`
- `Inspeqtor -> architecture rewrite`
- Any direct AI-agent shortcut that bypasses system guard or validator evidence

### Component-to-Component Links
Allowed:
- Through declared interfaces in the Dependency & Interaction Contract
- Through planned dependency edges
- Through approved shared contracts/config boundaries

Forbidden:
- Direct calls that bypass declared intermediary layers
- Hidden shortcuts from outer layers directly into deep internal layers
- Runtime coupling not declared in component contracts
- Builder-invented links absent from planning artifacts
- Validation-bypassing modifications to cross-component interfaces

Current-state note:
- Current system is still briq/file-contract oriented rather than fully component-contract-native; Qonscience defines the intended stable interaction model that should govern that evolution.

### System-to-Agent Links
System-owned decisions:
- Stage order
- Readiness gates
- Guard enforcement
- Repair caps
- Capability mode
- Persistence and audit format
- Deterministic validation boundaries

AI-interpreted but not mechanically sovereign:
- Gap detection reasoning
- Architecture/planning synthesis
- Scoped implementation decisions within contracts
- Evidence-based completion judgment

System must validate mechanically:
- Required artifact presence
- Contract/rule conformance where deterministic checks exist
- Syntax/import/schema/interface checks
- Test execution boundaries and outcomes
- Audit completeness of critical stage records

AI may interpret but must not mechanically decide alone:
- Whether a task is sufficiently clarified before readiness without structured criteria
- Whether architecture is good enough without mapped completion criteria
- Whether code is correct without validator/test evidence
- Whether policy has passed when deterministic policy checks say otherwise

## Data Flow Model
Canonical target flow:
1. Task input enters system
2. `Qrystallizer` clarifies and emits `Qrystalized Task Spec`
3. Guard/system policy validation checks spec and emits effective constraints
4. `Instruqtor` emits stable planning package
5. `Calqulator` estimates cost/execution shape and may support a single pre-build gate
6. `Constrqutor` builds scoped component groups and emits Build Reports
7. System Validators run deterministic checks and sandboxed tests where capability mode allows
8. `Inspeqtor` issues verdict
9. If complete, run finishes with audit and continuation state
10. If not complete, `Inspeqtor` emits targeted repair plan; only affected groups re-enter build and validation
11. Repair passes are capped; cap hit results in explicit non-success verdict

Current-state compatibility flow:
- Runtime currently operates through qage-local directories and cycle promotion from `reqap` into next `tasq`
- Warmup helpers (`qompressor`, `qontextor`, `qontrabender`) are file-context support services, not planning authorities
- Qonscience treats the current multi-cycle file flow as an implementation-era transport mechanism, not the desired long-term behavioral contract

Checkpoints and gates:
- Readiness gate before planning
- Guard/policy gate before build
- Optional cost/user gate before build and optionally before repair
- Validator evidence gate before inspection verdict
- Repair cap gate after bounded repair attempts

Repair-pass flow:
- Repair is scoped by Inspeqtor targets
- Repair reuses the locked planning package unless an explicit repair-plan update is emitted
- Repair must not reopen user questioning
- Repair must not silently escalate into full autonomous rerun loops

## Responsibility Separation
AI owns:
- Clarification reasoning
- Architecture/planning synthesis
- Scoped implementation generation
- Evidence-based completion judgment

Deterministic code owns:
- Orchestration
- Policy and boundary enforcement
- Mechanical validation
- Sandboxed execution control
- Persistence and audit wiring
- Repair caps and gating

Execution/test systems own:
- Running approved commands/tests
- Producing objective execution outputs
- Respecting sandbox limits
- Returning logs and status bundles

Audit/logging owns:
- High-level timeline
- Deep technical trace
- Assumption records
- Capability-mode disclosure
- Event linkage across all stages

## Validation Ownership Matrix
- Syntax:
  - System Validators
- Tests:
  - System Validators / controlled execution layer
- Policy:
  - Guard/system validation, plus deterministic contract enforcement where implemented
- Architecture:
  - Planned by Instruqtor, mechanically checked where possible by validators, judged by Inspeqtor against explicit contracts
- Contract conformance:
  - Deterministic validators first, Inspeqtor second for evidence-based interpretation of remaining non-mechanical gaps
- Completion judgment:
  - Inspeqtor, using planning package plus validator evidence

## Execution Boundaries
- `Qrystallizer` may clarify only before readiness
- `Instruqtor` may plan only after readiness and guard pass
- `Constrqutor` may modify code only within scoped component/build boundaries
- System Validators may execute only approved validation/test actions within sandbox boundaries
- `Inspeqtor` may judge and target repairs only after evidence exists

Absolute prohibitions:
- No hidden decision-making after readiness
- No mid-run questioning outside `Qrystallizer`
- No architecture rewriting by builders
- No planner authority in validators
- No execution authority in Inspeqtor
- No AI claims of mechanical correctness without deterministic or executed evidence
- No silent degraded-mode operation
- No silent contract mutation

## Repo / File Contracts
Current-state artifact roots:
- Workspace persistent inputs under `worqspace/`
- Per-run state under `worqspace/qage_*`
- Saved snapshots under `worqspace/qonstructions/`

Target-state persistence contract:
- Repo-native state under `.qonqrete/`
- Stable artifact hierarchy by run and component/group
- Continuation metadata treated as first-class state

Expected docs and state classes:
- Current state document
- Execution plan
- Hard ruleset
- Target state
- Run artifacts: clarified task, guard result, planning package, build reports, validator bundles, inspection verdicts, audit records

Naming expectations:
- Artifact names should reflect stage authority and handoff purpose
- Contract artifacts must remain distinct from narrative docs
- Validation bundles must distinguish mechanical result from AI judgment

Persistence boundaries:
- Repo code remains source of truth for code
- QonQrete-managed state remains source of truth for run reasoning, constraints, evidence, and verdicts
- Support caches/context artifacts must not become hidden planning authorities

Artifact ownership:
- `Qrystallizer` owns clarified task spec
- Guard/system stage owns effective constraints
- `Instruqtor` owns planning package
- `Constrqutor` owns build reports and changed-file manifests
- Validators own validation bundles and test outputs
- `Inspeqtor` owns verdicts and repair targets
- Orchestrator owns run timeline, linkage, and continuation metadata

## Inconsistencies or Open Structural Risks
- Current pipeline order in [worqspace/pipeline_config.yaml](/Users/wicked/x/qonqrete/worqspace/pipeline_config.yaml) includes `tasqleveler -> instruqtor -> calqulator -> construqtor -> qontextor -> qompressor -> qontrabender -> inspeqtor`, while the same file’s header comments still describe `instruqtor -> calqulator -> construqtor -> inspeqtor -> qontextor -> qompressor`, and current-state docs note broader doc/order drift. This is a real structural inconsistency.
- [qrane/paths.py](/Users/wicked/x/qonqrete/qrane/paths.py) defines `qache_dir` as `sqrapyard/qache.d`, while runtime docs and pipeline contracts treat `qache.d/` as a qage/run artifact. This is a real path-model inconsistency.
- Historical run artifacts under `worqspace/qage_20260402_172204/` include an alternative `Qrystallizer/Qualifier` pipeline concept that conflicts with both current primary state and the intended no-Qualifier target. Those artifacts should be treated as historical experiments, not current contract truth.
- Current runtime still relies on cycle promotion semantics and qage-local state, while the intended relational contract is single-pass plus targeted repair with repo-native `.qonqrete/` state. This is an acknowledged architecture transition boundary, not a silent equivalence.
- Deterministic validation remains strongest for Python-centric flows. Qonscience therefore requires honest capability disclosure and forbids claiming uniform mechanical validation coverage where it does not yet exist.
