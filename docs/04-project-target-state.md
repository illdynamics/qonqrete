# QonQrete Target State

## System Overview

QonQrete, when complete, is a repo-native AI software execution system that turns a task input and a target repository into a controlled, auditable build-and-validation run. It is the authority over clarification, constraints, planning, execution boundaries, validation evidence, repair scope, continuation state, and final verdicts, while models operate only within bounded roles.

Its core operating philosophy is simple:
- clarify once
- guard before build
- plan explicitly
- build by scoped components
- validate mechanically
- judge against explicit criteria
- repair only targeted scope
- persist one authoritative run record

It is autonomous in feel, but never opaque in control.

## Architecture

The final system is organized as a fixed, explicit runtime with seven functional layers:

1. Clarify
   - `Qrystallizer` converts raw task input into a structured `Qrystalized Task Spec`.

2. Guard
   - A system-owned guard/policy stage validates the clarified task and emits effective constraints.

3. Plan
   - `Instruqtor` transforms the ready task and effective constraints into the locked planning package.

4. Estimate
   - `Calqulator` computes estimated cost, expected execution shape, and confidence.

5. Build
   - `Constrqutor` builds component groups sequentially, using internal mini-briqs inside shared component context.

6. Validate
   - System validators perform deterministic checks and controlled test execution where capability mode allows.

7. Judge
   - `Inspeqtor` determines `done` or `repair required` against the planning package and validator evidence.

The runtime authority governs all sequencing, gates, manifest updates, persistence, repair caps, and continuation state. The architecture remains artifact-centric and file-contract-driven, but the contracts are explicit, stable, and manifest-linked under `.qonqrete/`.

## Agent Ecosystem

### Qrystallizer
- Role:
  - Sole ambiguity-clearing front door.
  - Produces the `Qrystalized Task Spec`.
- Interaction boundaries:
  - Receives raw task input and allowed repo context.
  - Hands off only to guard/policy validation and planning.
  - Is the only stage allowed to ask questions.
- Authority level:
  - Owns clarification only.
  - Does not plan, build, validate, or judge.

### Instruqtor
- Role:
  - Planning authority.
  - Produces the `Execution Blueprint`, Dependency & Interaction Contract, Component Contracts, Validation Plan, and Completion Criteria.
- Interaction boundaries:
  - Consumes only `READY` clarified tasks and effective constraints.
  - Hands off planning artifacts to estimation, build, validators, and `Inspeqtor`.
- Authority level:
  - Owns planning truth.
  - Does not execute code or declare completion.

### Constrqutor
- Role:
  - Scoped implementation engine.
  - Builds component groups using internal mini-briqs.
- Interaction boundaries:
  - Consumes locked planning artifacts and component scope.
  - Produces build reports, changed-file manifests, and execution summaries.
  - Hands off to validators and `Inspeqtor`.
- Authority level:
  - Owns implementation within assigned scope only.
  - Does not redefine contracts, completion criteria, or repair scope.

### Inspeqtor
- Role:
  - Judgment layer.
  - Determines whether the run is complete or which exact repair targets remain.
- Interaction boundaries:
  - Consumes planning artifacts, build reports, validator bundles, and test evidence.
  - Emits final verdict or targeted repair plan.
- Authority level:
  - Owns completion judgment and repair targeting.
  - Does not execute tests or mutate planning truth.

### Guard / Policy Validation Stage
- Role:
  - Pre-build constraint and policy enforcement stage.
  - Produces the `Guard Result`.
- Interaction boundaries:
  - Consumes clarified task artifacts and policy baselines.
  - Hands effective constraints into planning.
- Authority level:
  - Owns pre-plan constraint truth.
  - May block planning on failure.

### System Validators (non-AI)
- Role:
  - Mechanical correctness and executed evidence layer.
  - Produces `Validation Result Bundles`.
- Interaction boundaries:
  - Consumes planning contracts, build outputs, changed-file manifests, and repo state within execution boundaries.
  - Hands evidence to `Inspeqtor` and audit.
- Authority level:
  - Owns deterministic and executed validation truth.
  - Does not plan or decide final completion.

### Orchestration / Runtime Authority
- Role:
  - Runtime control plane.
  - Creates and updates the run manifest, enforces gates, tracks lifecycle state, and routes continuation/repair.
- Interaction boundaries:
  - Governs all stages.
  - Owns persistence, manifest linkage, audit wiring, repair caps, and continuation metadata.
- Authority level:
  - Highest runtime authority.
  - Does not itself generate architecture, code, or judgment content.

## Execution Model

QonQrete’s canonical execution model is one primary pass plus targeted repair.

Canonical flow:
1. Task intake
2. Clarification via `Qrystallizer`
3. Guard / policy validation
4. Planning via `Instruqtor`
5. Estimation via `Calqulator`
6. Build via `Constrqutor`
7. Validation via system validators
8. Judgment via `Inspeqtor`
9. Finish or targeted repair
10. Continuation if needed

Gating points:
- readiness gate before planning
- guard gate before planning/build
- optional estimate gate before build
- validator evidence gate before final judgment
- repair-cap gate before additional repair attempts
- continuation gate before resuming or extending a prior run

Completion rules:
- no uncontrolled cycles
- no recursive whole-run reruns as canonical behavior
- no mid-run questioning after clarification
- completion is determined only after explicit comparison against:
  - clarified task
  - effective constraints
  - execution blueprint
  - component contracts
  - validation plan
  - completion criteria
  - validator evidence

If the run is not complete, the system emits a targeted repair plan and rebuilds only the affected component groups. Repair remains bounded and explicit.

## Data & Artifact Model

QonQrete’s final data model is a fixed artifact chain. Each artifact has a single primary owner, a bounded lifecycle, and a manifest-linked role in the run.

### Qrystalized Task Spec
- Relationship:
  - Converts raw task input into execution-ready clarified intent.
- Lifecycle:
  - Created during clarification.
  - Locked before planning.
- Ownership:
  - Owned by `Qrystallizer`.

### Guard Result
- Relationship:
  - Validates clarified intent and emits effective constraints.
- Lifecycle:
  - Created after clarification.
  - Consumed before planning.
- Ownership:
  - Owned by Guard / Policy Validation Stage.

### Execution Blueprint
- Relationship:
  - Defines architecture, execution structure, interfaces, validation expectations, and completion truth.
- Lifecycle:
  - Created during planning.
  - Remains stable through build/validate/judge unless explicitly updated by repair mechanics.
- Ownership:
  - Owned by `Instruqtor`.

### Component Contracts
- Relationship:
  - Define scoped build units, interfaces, dependencies, constraints, and acceptance conditions.
- Lifecycle:
  - Created as part of planning.
  - Consumed by builders, validators, and `Inspeqtor`.
- Ownership:
  - Owned by `Instruqtor`.

### Build Reports
- Relationship:
  - Describe what changed, what assumptions were used, and what scope was touched.
- Lifecycle:
  - Created during build, per component/group.
  - Consumed by validators and judgment.
- Ownership:
  - Owned by `Constrqutor`.

### Validation Result Bundles
- Relationship:
  - Provide deterministic and executed evidence about the built output.
- Lifecycle:
  - Created during validation.
  - Consumed by `Inspeqtor`, audit, and continuation logic.
- Ownership:
  - Owned by system validators.

### Inspection Verdicts
- Relationship:
  - Express final completion judgment or targeted repair requirement.
- Lifecycle:
  - Created after validation.
  - Drives finish vs repair routing.
- Ownership:
  - Owned by `Inspeqtor`.

### Run Manifest
- Relationship:
  - Links all stage outputs, statuses, evidence, and lifecycle state into one authoritative per-run record.
- Lifecycle:
  - Created at run start.
  - Updated throughout the run.
  - Remains authoritative after completion for audit and continuation.
- Ownership:
  - Owned by orchestration / runtime authority.

### Continuation Metadata
- Relationship:
  - Encodes how a run may resume, repair, extend, or fork.
- Lifecycle:
  - Created when continuation becomes relevant.
  - Tracks source lineage and inherited artifacts.
- Ownership:
  - Owned by orchestration / runtime authority.

## State & Persistence Model

`.qonqrete/` is the canonical state root of the final system.

State model:
- repo code remains the source of truth for code
- `.qonqrete/` is the source of truth for:
  - task/run state
  - constraints
  - plans
  - evidence
  - verdicts
  - audit records
  - continuation metadata

Run-level structure is stable and keyed by run identity, not by recursive cycle sprawl. Each run stores:
- task intake artifacts
- clarified task artifacts
- guard artifacts
- planning artifacts
- build artifacts
- validation artifacts
- verdict artifacts
- audit artifacts
- continuation artifacts
- run manifest

Continuation model:
- all runs are continuable
- “finished” means verdict reached, not frozen forever
- continuation may mean:
  - inspect prior evidence
  - targeted repair
  - extend with new tasking
  - fork from prior run truth
- continuation always references explicit prior state; it is never inferred from undocumented side effects

## Run Manifest System

The run manifest is the central coordination record of the final system.

Its role:
- creates one authoritative linkage point per run
- ties task input, clarification, guard, planning, build, validation, verdict, audit, and continuation together
- provides stage status, artifact references, cost information, lifecycle state, and continuation lineage

It enables:
- audit traceability
- repair routing
- continuation integrity
- evidence traceability
- consistency checks between stage records
- reliable reconstruction of what the system believed, planned, changed, validated, and decided

Without the run manifest, QonQrete is not considered operationally complete. The final system does not rely on fragmented stage records as the sole source of runtime truth.

## Validation & Testing Model

QonQrete separates deterministic validation from AI judgment.

Deterministic validation:
- owned by system validators
- covers syntax, parseability, imports, schemas, interfaces, required artifact presence, grouped component coherence, and controlled test execution
- produces machine-readable evidence bundles plus human-readable summaries

AI validation:
- owned by `Inspeqtor`
- interprets evidence against:
  - `Qrystalized Task Spec`
  - `Guard Result`
  - `Execution Blueprint`
  - Component Contracts
  - Validation Plan
  - Completion Criteria
- never substitutes for mechanical proof

Optional execution engines:
- the final system supports capability modes
- Simulation Mode:
  - no real code execution
  - heuristic/non-executed validation
  - lower confidence, clearly disclosed
- Execution Mode:
  - real build/test execution through controlled execution systems
  - may use Codex-style execution workers inside constrained boundaries
  - richer evidence, higher confidence, same orchestration authority

Correctness is established by combining:
- deterministic validation evidence
- executed test evidence where available
- explicit comparison to planning and contract artifacts
- evidence-based final judgment from `Inspeqtor`

## Audit & Transparency Model

The final system exposes a dual-layer audit model.

Human-readable layer:
- optimized for rapid comprehension
- shows:
  - task intake
  - clarification outcome
  - effective constraints
  - planning decisions
  - cost estimate
  - build progress
  - validator outcomes
  - verdict
  - repair decisions
  - final lifecycle state

Machine-readable layer:
- optimized for debugging, tooling, and integrity checks
- contains:
  - prompts
  - raw model outputs
  - command logs
  - test outputs
  - validator bundles
  - cost actuals
  - assumption records
  - fallback records
  - manifest-linked event references

The final system makes traceable:
- decisions
- assumptions
- execution steps
- degraded modes
- evidence lineage
- continuation lineage

Nothing important is implicit if it can affect understanding, judgment, or continuation.

## CLI / UX Experience

QonQrete’s final UX is repo-native and one-command by default.

Core experience:
- one-command entry: `qonqrete [task-file?]`
- no required config beyond provider credentials and model choices
- no required `init` + `run` split in the happy path
- no required `sqrapyard` concepts
- no required fixed `tasq.md` filename

Task input modes:
- task file path
- inline or pasted task input
- richer selection/input modes may exist, but all resolve into the same task-input contract

Continuation UX:
- runs are naturally continuable
- prior runs can be resumed, repaired, extended, or inspected through explicit continuation state
- “resume” and “finished” are not separate mental models; continuation is part of one unified UX

Repo-native behavior:
- operates directly in existing repositories
- stores its runtime state under `.qonqrete/`
- does not require copying the repo into staging areas

## Developer Experience

Developers interact with QonQrete through explicit, inspectable artifacts rather than hidden agent behavior.

The final developer experience provides:
- predictable stage boundaries
- stable contracts between stages
- clear ownership of each artifact
- direct visibility into what the system believed and why
- direct visibility into what changed and what was validated
- clear debugging paths through audit plus manifest linkage

Extensibility expectations:
- new validators can be added without collapsing stage boundaries
- new execution backends can be added without taking over orchestration
- new model providers can be used without changing artifact contracts
- richer repo workflows can be added without changing the core clarify/guard/plan/build/validate/judge architecture

Debugging clarity:
- every important output is linked by the run manifest
- every stage has narrow responsibility
- degraded behavior is disclosed, not hidden

Predictability:
- same task and environment should yield materially similar structure, decisions, and outputs
- bounded heuristics and explicit contracts keep behavior controlled

## Repo / GitOps Interaction

QonQrete integrates with repositories as a repo-native execution layer, not as a detached external staging system.

Repo interaction model:
- repository is the execution context
- repository remains the source of truth for code
- `.qonqrete/` persists the run state, evidence, and verdicts
- task inputs are explicit artifacts
- outputs are trackable, attributable, and repo-local

Git compatibility:
- works inside normal Git workflows
- artifacts can be inspected alongside code changes
- change scope, validation evidence, and verdicts are attributable to a run identity
- later GitOps expansion is natural because:
  - scope is explicit
  - contracts are explicit
  - evidence is explicit
  - run lineage is explicit

QonQrete is GitOps-friendly in behavior without requiring CI/CD semantics to be its core identity.

## Performance Characteristics

The final system is optimized for controlled throughput, not uncontrolled autonomy.

Expected efficiency characteristics:
- ambiguity is resolved up front to reduce churn
- explicit planning reduces architectural drift
- component-group execution reduces context fragmentation
- targeted repair avoids expensive whole-run repetition
- support/context artifacts improve efficiency without becoming hidden authorities

Bounded execution behavior:
- fixed phase order
- bounded repair count
- bounded questioning
- explicit execution shape
- explicit capability mode

Cost awareness:
- estimated cost before major execution
- actual cost tracked during run
- cost visibility as part of run state and audit
- clear distinction between estimated and actual execution footprint

## System Qualities

### Determinism
- explicit contracts and bounded heuristics produce materially similar structure across equivalent runs
- hidden replanning and undocumented control flow are absent

### Reliability
- blocking conditions fail fast
- completion depends on evidence, not optimism
- degraded modes are explicit and safe

### Explainability
- artifacts and audit logs make system behavior reconstructable
- decisions, assumptions, and verdicts are linked to evidence

### Composability
- stages are separable by role and contract
- new validators, execution backends, and providers fit without collapsing authority boundaries

### Auditability
- one manifest-linked run truth
- human-readable and machine-readable audit layers
- explicit evidence lineage
- explicit continuation lineage

## Transition Compatibility Notes

This target state is the final condition reached after migration from the current qage/cycle-based runtime.

The following are explicitly not part of the final state:
- qage-local canonical state
- `sqrapyard` as primary user workflow
- `tasQleveler` as active canonical clarification stage
- `reqap -> next tasq` as canonical continuation mechanism
- fragmented, unlinked stage records as operational truth
- uncontrolled cycle reruns as core execution behavior

Transitional coexistence may exist while the system is being migrated, but those bridge behaviors are not part of the completed target state.
