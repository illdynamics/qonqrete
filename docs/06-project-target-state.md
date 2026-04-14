# QonQrete Target State

## System Overview
QonQrete is a deterministic AI-driven system for structured software construction. It transforms user intent into validated, auditable, reproducible software outcomes through explicit clarification, explicit planning, scoped construction, deterministic validation, explicit realization, and evidence-based judgment.

Core philosophy:
- clarify first
- plan explicitly
- build deterministically
- observe reality explicitly
- validate mechanically
- verify explicitly

QonQrete is not a prompt wrapper, not an opaque autonomous loop, and not a code generator that treats written files as proof of success. It is a structured software realization system whose authority is distributed across explicit stages, explicit artifacts, explicit contracts, and explicit runtime control.

The final system is fully aligned with:
- execution intent defined by the execution plan
- constraints defined by the hard ruleset
- feasible transition boundaries defined by the migration compound
- contract and schema boundaries defined by Qonscience
- explicit observed-outcome authority defined by the Results / Realization layer

Current-state inconsistencies that remain true about the present repository but are not part of final target state:
- the current codebase still contains `tasqleveler` and no implemented `Qrystallizer`
- the current runtime is qage/cycle-based and still uses `reqap -> next tasq` continuation
- the current codebase has fragmented audit artifacts and no canonical run manifest
- the current validation depth is materially stronger for Python than for several other ecosystems

## Architecture
QonQrete has a modular agent-based architecture governed by strict contracts, canonical enums, manifest-linked artifacts, and explicit stage sequencing.

Architectural properties:
- modular agent-based architecture governed by strict contracts
- clear separation between:
  - AI reasoning layers
  - deterministic validation layers
  - orchestration/runtime control
- manifest-centered execution model
- `.qonqrete/` acts as canonical system state root
- no implicit or hidden execution paths
- no undocumented stage or status drift
- no artifact authority outside the manifest-linked contract system

The final architecture has four top-level system strata:
1. reasoning stratum
   - Qrystallizer
   - instruQtor
   - inspeQtor
2. execution stratum
   - construQtor
   - controlled execution engines where enabled
3. deterministic system stratum
   - Guard / policy validation
   - syntax/build/test validators
   - scoped mechanical and contract validators
   - Results / Realization composition
4. control stratum
   - Runtime / Orchestrator
   - Run Manifest
   - continuation and repair routing
   - artifact persistence and lifecycle integrity

The architecture is manifest-centered rather than log-centered. No stage is authoritative merely because it emitted output. Authority exists only where contracts assign it and where the manifest links and contextualizes the produced artifacts.

The final architecture is repo-native. `.qonqrete/` is the canonical runtime state root. Repository code remains the user’s software source tree; it is not the canonical QonQrete state carrier.

The final architecture is finite-state and evidence-gated. Later stages cannot proceed without required artifacts from prior stages. No hidden cycle promotion, hidden replanning, or hidden continuation path exists.

## Agent Ecosystem
### Qrystallizer
Qrystallizer is the intake authority.

Responsibilities:
- accepts raw user intent
- performs structured gap detection
- asks a bounded number of high-impact clarification questions when needed
- captures assumptions explicitly
- produces the Qrystalized Task Spec
- enforces readiness gating

Authority:
- clarification authority only

Must not:
- perform planning
- perform execution
- perform judgment
- defer unresolved blocking ambiguity into hidden downstream interpretation
- ask questions after execution begins

Canonical outputs:
- Qrystalized Task Spec
- clarification summary
- assumption log
- readiness result

### instruQtor
instruQtor is the planning authority.

Responsibilities:
- consumes Qrystalized Task Spec and Guard Result
- produces Execution Blueprint
- defines architecture and component breakdown
- defines dependency and interaction contracts
- defines build groups and component contracts
- defines validation plan
- defines completion criteria

Authority:
- planning authority only

Must not:
- generate code
- mutate clarified intent silently
- perform deterministic validation execution
- perform final judgment

Canonical outputs:
- Execution Blueprint
- architecture foundation
- dependency and interaction contract
- Component Contracts
- Validation Plan
- Completion Criteria

### construQtor
construQtor is the build authority.

Responsibilities:
- implements Component Contracts
- executes build groups within explicit scope
- produces Build Reports
- produces changed-file manifests
- produces build logs and scope application records
- operates within scoped build boundaries only

Authority:
- scoped build authority only

Must not:
- change architecture
- silently expand scope
- skip required validator handoffs
- issue final correctness claims
- ask the user questions mid-run

Canonical outputs:
- Build Reports
- changed-file manifests
- scoped build evidence
- build-group outputs

### inspeQtor
inspeQtor is the AI-level judgment authority.

Responsibilities:
- consumes Result / Realization evidence
- determines completion and correctness
- determines confidence level
- determines unresolved unknowns
- produces Inspection Verdict
- produces Repair Plan when needed

Authority:
- judgment authority only

Must not:
- perform execution
- replace deterministic validator truth
- mutate build outputs
- hallucinate closure when realization shows blind spots

Canonical outputs:
- Inspection Verdict
- Repair Plan
- issue list
- confidence classification

### Guard / Policy Validation Stage
Guard is the pre-plan constraint authority.

Responsibilities:
- enforces constraints and policy compliance before planning
- validates intent against policy
- blocks disallowed tasks
- emits effective constraints for downstream planning

Authority:
- pre-plan constraint authority

Must not:
- perform planning
- perform code execution
- silently downgrade policy failures into warnings

Canonical outputs:
- Guard Result
- effective constraints
- blocking issues
- warnings

### System Validators (Non-AI)
System Validators are the deterministic authority.

Responsibilities:
- validate syntax
- validate builds/compilation where implemented
- validate executed tests where implemented
- validate deterministic mechanical checks
- validate grouped component coherence checks where implemented

Authority:
- final truth for deterministic correctness within implemented coverage

Must not:
- make business completion judgments
- pretend missing validators ran
- replace inspection judgment
- imply ecosystem parity that does not exist

Canonical outputs:
- Validation Result Bundles
- test result bundles
- deterministic issue records
- capability coverage disclosures

### Runtime / Orchestrator
Runtime / Orchestrator is the lifecycle control authority.

Responsibilities:
- governs execution lifecycle
- enforces stage transitions
- maintains manifest integrity
- routes repair and continuation
- enforces repair caps
- enforces no-question execution after clarification
- enforces stage ordering and artifact prerequisites

Authority:
- runtime control authority

Must not:
- invent undocumented transition paths
- change capability mode silently
- bypass required artifacts
- allow hidden enum drift

Canonical outputs:
- manifest updates
- lifecycle transitions
- gating decisions
- continuation metadata

## Execution Model
Canonical flow:
- `intake -> Qrystallizer -> Guard -> instruQtor -> construQtor -> Validators -> Result / Realization -> inspeQtor -> repair if needed -> completion`

The final execution model is strictly single-pass with bounded repair loops.

The final execution model forbids:
- uncontrolled recursion
- open-ended cycle reruns
- `reqap -> next tasq` as canonical continuation
- mid-run questioning
- hidden replanning
- hidden scope expansion

Completion is determined only through:
- validation success within declared coverage
- inspection verdict
- manifest completeness
- explicit terminal-state transition

Build completion alone is not completion.

Plan conformance alone is not completion.

Validator success alone is not completion.

Completion requires:
- complete required artifact set
- realization evidence
- inspection verdict
- manifest-linked terminal state

## Execution Lifecycle Summary
The final system lifecycle states and stage progression align with the canonical stage/status/mode registry defined in the migration compound.

Canonical stage IDs:
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

Canonical lifecycle states:
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

Canonical run statuses:
- `RUN_CREATED`
- `RUN_ACTIVE`
- `RUN_WAITING_FOR_INPUT`
- `RUN_WAITING_FOR_GATE`
- `RUN_REPAIR_PENDING`
- `RUN_COMPLETED`
- `RUN_PARTIAL`
- `RUN_FAILED`
- `RUN_ABORTED`

Lifecycle properties:
- explicit
- finite
- manifest-tracked
- free of undocumented transition paths
- repair transitions are explicit and bounded
- terminal states are explicit
- invalid transitions are prevented by the runtime

Terminal states:
- `COMPLETED`
- `PARTIAL`
- `FAILED`
- `ABORTED`

Repair is not a hidden cycle. It is an explicit lifecycle path entered only from inspection or other policy-approved failure handling.

## Data & Artifact Model
Canonical artifacts include:
- Qrystalized Task Spec
- Guard Result
- Execution Blueprint
- Component Contracts
- Build Reports
- Validation Result Bundles
- Result / Realization Bundles
- Inspection Verdicts
- Repair Plans
- Run Manifest
- Continuation Metadata

Artifact properties:
- all canonical artifacts are structured and schema-versioned
- all canonical artifacts are manifest-linked
- ownership is explicit per agent or system stage
- no orphan artifacts are allowed
- lifecycle is:
  - creation
  - usage
  - validation
  - persistence
  - optional supersession through versioned replacement
- human-readable companions may exist, but machine-readable schema-versioned artifacts are canonical

Artifact ownership:
- Qrystallizer owns Qrystalized Task Spec
- Guard owns Guard Result
- instruQtor owns Execution Blueprint and Component Contracts
- construQtor owns Build Reports and changed-file manifests
- System Validators own Validation Result Bundles
- Results / Realization layer owns Result / Realization Bundles
- inspeQtor owns Inspection Verdicts and Repair Plans
- Runtime / Orchestrator owns Run Manifest and Continuation Metadata

No artifact may claim authority outside its contract domain.

No artifact may silently override another artifact’s domain authority.

## State & Persistence Model
`.qonqrete/` is the canonical system state root.

Canonical run-scoped structure includes:
- artifacts
- manifest
- logs
- continuation metadata
- audit records
- scoped build and validation outputs
- realization outputs
- verdict outputs

Repository code is not execution state.

Repository code is the user’s working software tree.

Continuation is explicit via Continuation Metadata.

No implicit resume logic exists in the final system.

State transitions are explicit and auditable.

Canonical persistence rules:
- each run has a stable run root under `.qonqrete/runs/<run_id>/`
- run-scoped artifacts are grouped by function, not by legacy ad hoc stage names
- support artifacts and cache artifacts are explicitly categorized and must not be confused with authoritative artifacts
- lineage across runs is explicit and manifest-linked
- continuation never depends on untracked conversational memory or implicit hidden state

The final system does not depend on qage as hidden canonical state. Any coexistence with qage belongs only to migration compatibility and is not part of the final state model.

## Safe Write / Transaction Model
The final system must not rely on untracked incremental partial writes as normal behavior.

Build application is:
- scoped
- auditable
- attributable
- recoverable

Changed-file manifests are first-class artifacts.

Rollback or recovery behavior is explicit and runtime-governed.

A failed scoped build application must remain diagnosable and must not be indistinguishable from success.

Final write-model properties:
- every build group has declared scope before application
- write strategy is explicit in artifacts and manifest
- applied changes are attributable to build attempt and scope
- partial or failed application is surfaced in realization and audit
- repair plans use changed-scope truth for targeting
- success claims cannot be made if committed outcome cannot be distinguished from residue

The final system may implement staged commit, atomic replacement, or snapshot-based recovery, but whichever model exists must be explicit, auditable, and enforced.

## Run Manifest System
The Run Manifest is the central execution authority for traceability.

It is created at run initialization.

It is updated after every stage transition.

It links:
- all artifacts
- all stages
- all timestamps
- all decisions
- capability modes
- validation execution modes
- lineage and continuation relationships

It is used for:
- audit
- continuation
- validation traceability
- completion determination
- repair routing
- lifecycle integrity

Manifest properties:
- one authoritative run-level record concept
- explicit stage and lifecycle status tracking
- explicit artifact linkage
- explicit evidence status linkage
- explicit compatibility linkage where legacy artifacts exist
- survival through partial failure
- no confusion with cache manifests or helper manifests

The final system does not treat logs, markdown summaries, or helper manifests as substitutes for the canonical Run Manifest.

## Validation & Testing Model
The final system enforces strict separation:
- AI -> reasoning, planning, and judgment
- system -> deterministic validation and execution evidence

Validators include:
- syntax validation
- execution validation
- test validation
- mechanical contract or policy checks where implemented
- grouped component coherence checks where implemented

Optional controlled execution engines may exist, including strong execution backends such as Codex-style execution engines, but:
- they are execution tools, not orchestration authorities
- they do not replace QonQrete’s planning, realization, or judgment structure
- they operate within QonQrete’s scoped contracts and manifest system

Correctness is established only through deterministic validation plus inspection.

Inspection cannot overrule deterministic failure.

Reasoning-based review may supplement missing coverage, but must remain explicitly weaker than direct deterministic or execution evidence.

Validation planning must exist before build begins.

Validation coverage must be explicit in artifacts.

## Language / Ecosystem Capability Model
The final system discloses validation strength honestly across languages and ecosystems.

Universal validation capabilities and language-specific strengths are distinguishable.

Weaker ecosystem support affects:
- confidence
- capability disclosure
- repair targeting precision
- verdict strength

The system must not pretend equal deterministic coverage where it does not exist.

Universal capabilities include:
- manifest linkage
- changed-file truth
- build scope declaration
- capability disclosure
- artifact completeness checks
- lifecycle integrity
- direct versus inferred versus unknown evidence classification

Language-specific capabilities may include:
- AST-based checks
- compile/build checks
- executed tests
- runtime startup validation
- ecosystem-native contract enforcement

The final system must preserve honesty if one ecosystem has stronger deterministic support than another. Broader support may expand over time, but parity cannot be claimed ahead of implementation.

## Results / Realization Model
The final system includes a first-class Results / Realization layer as the authoritative observed-outcome membrane between validation and inspection.

Realization records:
- what actually changed
- what actually happened
- what behavior actually occurred
- what impact was actually observed
- what evidence exists
- what remains inferred or unknown

Realization is separate from:
- planning intent
- build action reports
- validator raw output
- inspection verdicts
- repair plans

Realization provides:
- structural reality
- behavioral reality
- system impact reality
- confidence and evidence reality

Realization is required before canonical inspection verdicts.

Realization is manifest-linked.

Realization is the evidence substrate for:
- inspection
- repair targeting
- continuation safety
- future learning or adaptation loops

## Audit & Transparency Model
The final system has dual-layer audit:
- human-readable audit outputs
- machine-readable artifacts and event records

Full traceability exists for:
- decisions
- assumptions
- execution steps
- changed scope
- validation coverage
- realized outcomes
- judgments
- repair decisions
- continuation lineage

No hidden or implicit behavior is allowed.

Audit properties:
- skimmable high-level timeline
- drillable deep evidence
- explicit capability disclosures
- explicit unknowns
- explicit failure and fallback visibility
- explicit stage identity and timestamps
- no reliance on tribal knowledge to reconstruct what happened

The audit model is manifest-centered, not log-centered.

## CLI / UX Experience
The final system provides:
- one-command execution
- zero required configuration by default
- repo-native operation
- input modes:
  - file-based
  - inline
- seamless continuation support
- no manual orchestration required
- no primary user-facing dependency on `sqrapyard`
- no forced `tasq.md` naming convention

Canonical UX properties:
- task-first interaction
- explicit stage progress
- explicit capability-mode disclosure
- explicit continuation and repair visibility
- no hidden multi-command ritual required to begin normal operation

User experience remains subordinate to correctness, auditability, and state integrity. Convenience does not justify hidden execution paths.

## Developer Experience
The final system provides:
- predictable and deterministic system behavior
- clear artifact structure
- easy debugging via manifest and artifacts
- extensible agent architecture
- no hidden system behavior
- explicit stage and contract boundaries
- stable machine-readable outputs for automation and tooling
- explicit lifecycle and continuation model
- clear separation between reasoning, execution, realization, and judgment

Developers can understand a run by inspecting:
- Run Manifest
- canonical artifacts
- audit outputs
- scoped build and validation records
- realization and verdict artifacts

They do not need to infer behavior from scattered logs or implicit runtime conventions.

## Repo / GitOps Interaction
The final system is fully compatible with Git workflows.

Outputs persist within repo-local structure via `.qonqrete/`.

`.qonqrete/` is excluded or managed appropriately according to project policy.

The system supports CI/CD integration by exposing:
- manifest-linked machine-readable artifacts
- explicit capability modes
- explicit validation outputs
- explicit realization outputs
- explicit verdicts
- explicit continuation metadata

The final system does not require repo copying into a separate staging concept as the primary UX.

Repo-native execution is canonical.

## Performance Characteristics
The final system has:
- bounded execution model
- predictable cost behavior
- efficient artifact reuse where applicable
- no uncontrolled compute expansion
- bounded repair loops
- explicit gating where configured
- explicit capability-mode constraints

Performance and cost behavior are observable and auditable through artifacts and manifest-linked records, not implied by opaque orchestration.

## System Qualities
The final system exhibits:
- determinism
- reliability
- explainability
- composability
- auditability
- extensibility
- bounded autonomy
- contract discipline
- state traceability
- evidence-based correctness

These qualities are not branding claims. They are enforced by:
- canonical stage and status registries
- manifest-linked artifacts
- contract-separated responsibilities
- realization before judgment
- explicit repair flow
- honest capability disclosure

## Qonscience Alignment
The final system fully conforms to Qonscience.

That means:
- every major interaction is governed by explicit contracts
- every major artifact is schema-versioned and owned
- every authority boundary is explicit
- every dependency and interaction path is declared
- every stage may claim only what its contract permits
- builders do not redesign architecture
- validators do not replace judgment
- inspection does not invent evidence
- runtime does not invent hidden state or hidden stage transitions

Qonscience is not an optional documentation layer in the final system. It is the structural contract substrate of the system.

## Results / Repair / Continuation Alignment
The final system fully aligns Results / Realization, Repair Plans, and Continuation Metadata.

That means:
- realization exists before judgment
- repair plans reference realization artifacts
- continuation metadata references prior run lineage and reuse mode
- repair is bounded and scoped
- continuation is explicit and manifest-linked
- no canonical follow-up path depends on legacy cycle promotion

The final system does not treat repair as hidden replanning or continuation as implicit resume.

## Transition Compatibility Notes
This target state is achieved through defined migration.

Transitional behaviors such as qage and cycle models are not part of the final system.

The final system must not expose migration artifacts or legacy behaviors as hidden dependencies.

Current-state realities may coexist only during migration, never as hidden final-state dependencies.

Specifically not part of final state:
- qage as canonical state root
- `tasqleveler` as intake authority
- `reqap -> next tasq` as canonical continuation
- fragmented logs as sufficient audit basis
- undocumented stage aliases as canonical IDs
- implicit cycle recursion as default execution model

The final system is the post-migration architecture in which the migration bridge has been completed and hidden reliance on legacy mechanisms has been removed.
