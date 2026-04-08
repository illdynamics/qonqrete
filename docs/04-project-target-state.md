<proposed_plan>
# QonQrete Target State

## System Overview

QonQrete is a repo-native AI software execution system that turns a task file and a target repository into a controlled, auditable build-and-validation run. It operates as the authority over planning, constraints, validation, repair scope, and final verdicts, while models act only within bounded roles. The system is zero-config by default apart from provider credentials and model selection, runs directly against an existing repository, and produces explicit artifacts that make every major decision, assumption, and outcome inspectable.

Its fully realized form is not a loose multi-agent experiment and not a generic chat wrapper. It is a structured orchestration system for clarifying work, planning architecture, building scoped changes, validating them mechanically, and judging completion against explicit criteria. It is designed to feel autonomous to the user while remaining deterministic, explainable, and operationally controlled.

## Architecture

The finished architecture is organized into explicit phases with stable artifact handoffs:

1. Clarify
`Qrystallizer` converts raw user input into a structured `Qrystalized Task Spec` that captures the objective, inputs, constraints, locked assumptions, blocking gaps, and readiness state.

2. Guard
A system guard stage validates the clarified task against default sane QONTRACT rules, security policies, and allowed operational boundaries, producing a `Guard Result` with effective constraints.

3. Plan
`Instruqtor` transforms the ready task and effective constraints into a stable planning package: Architecture Foundation, Execution Plan, Dependency & Interaction Contract, Component Contracts, Validation Plan, and Completion Criteria.

4. Estimate
`Calqulator` produces estimated cost, expected execution shape, and confidence, with optional gating before build and before any repair pass.

5. Build
`Constrqutor` builds component groups sequentially, using internal mini-briqs inside shared component context rather than independent global briqs.

6. Validate
System-owned validators perform syntax, parseability, import/schema/interface, grouped component coherence, required artifact checks, and sandboxed test execution.

7. Judge
`Inspeqtor` evaluates the full evidence set against the planning package and determines `done` or `repair required`.

8. Repair if needed
Only targeted affected components or groups are rebuilt and revalidated. The system never reverts into uncontrolled whole-run cycling.

This architecture remains file-contract-driven and artifact-centric. The system’s intelligence is expressed through explicit contracts and bounded phase responsibilities, not through hidden agent improvisation.

## Agent Ecosystem

- Qrystallizer (replacing tasQleveler)
  - Qrystallizer is the front door of the system and the only phase that interacts with ambiguity directly.
  - It behaves like a structured gap engine: it identifies high-impact missing information, asks a small number of targeted questions, locks assumptions, and decides whether the task is ready.
  - It is reasoning-first and model-agnostic. Its output is a stable specification artifact, not prose advice.
  - It does not plan architecture, write code, run tests, or redefine scope once execution starts.

- Instruqtor
  - Instruqtor is the planning authority.
  - It determines task complexity, internal execution profile, batch shape, repair allowance, dependency structure, validation expectations, and what counts as completion.
  - It produces a system-level design that downstream phases treat as the source of truth.
  - It makes dependency wiring and component interaction explicit rather than leaving them implicit inside generated code.

- Constrqutor
  - Constrqutor is the scoped implementation engine.
  - It works component by component, with each component decomposed into internal briqs that share context and are validated for coherence before the system moves on.
  - It produces code changes, changed-file manifests, execution summaries, and explicit assumption records.
  - It is execution-focused and does not own architecture or completion judgment.

- Inspeqtor
  - Inspeqtor is the judgment layer.
  - It compares what was built and validated against what was planned and required.
  - It consumes validator bundles, build reports, test outputs, contracts, and completion criteria to determine whether the run is complete or which exact repair targets remain.
  - It does not run tests itself and does not rescue vague upstream design with subjective interpretation.

- system validators
  - System validators are deterministic services, not AI agents.
  - They own mechanical validation: syntax, parsing, imports, schemas, interface conformance, required artifact presence, grouped component validation, and sandboxed test execution.
  - They produce machine-readable result bundles and condensed summaries for audit and inspection.
  - There is no standalone Qualifier agent in the final ecosystem.

## Execution Model

- single-pass execution + targeted repair
  - The normal execution shape is one clarified task, one stable planning package, one primary build, one full validation pass, and one inspection verdict.
  - If the verdict is not complete, the system produces a targeted repair plan and rebuilds only the affected groups.
  - Repair is bounded and explicit. The system allows at most a small fixed number of repair passes.
  - Completion is judged against explicit criteria defined before coding starts, not against vague “good enough” impressions.

- no uncontrolled cycles
  - The final system does not rely on recursive cycle-to-cycle document promotion or whole-system reruns as its core operating model.
  - Briq sense, execution profile, and repair allowance are decided up front for the run and remain visible in the audit trail.
  - The system may adapt within bounded rules, but it never shifts into opaque open-ended looping.

## CLI / UX Experience

- zero-config
  - The user experience requires only provider credentials, model choices, and a task input.
  - Sensitivity tuning, cycle tuning, staging flags, and manual artifact choreography are not part of the normal UX.

- one-command entry
  - The mental model is `qonqrete [task-file?]`.
  - A user can enter a repository, point at a task file, answer a few clarification questions if needed, and let the system run.
  - Install flow offers both a fast path and a reviewable path.

- repo-native operation
  - QonQrete runs directly inside an existing git repository.
  - It does not require users to copy the project into a staging directory or think in terms like `sqrapyard`.
  - Task input is not bound to a hardcoded filename like `tasq.md`.
  - Resuming or continuing work feels natural and is part of the same UX, not a separate mental model.

## Developer Experience

The finished system is predictable for engineers to understand and inspect. Each stage has a narrow responsibility, stable inputs, and a well-defined output artifact. Developers can see what the system believed, what it planned, what it changed, what it tested, and why it decided it was finished or not.

Working with QonQrete does not require trusting hidden model behavior. The developer experience centers on readable artifacts, structured contracts, audit clarity, and strong failure visibility. When the system degrades, uses assumptions, or lacks execution capability, that state is made explicit rather than buried.

For advanced users, capability tiers are visible. A simulation-only run is clearly labeled as such; an execution-enabled run exposes higher confidence because code was actually built and tested inside controlled boundaries.

## Validation & Testing

- system-level validation (syntax/tests)
  - Mechanical correctness is owned by the system.
  - The final system validates syntax, parsing, imports, interfaces, schemas, grouped component coherence, required outputs, and test execution through deterministic services.
  - Test execution happens in controlled sandboxes with bounded resources, restricted filesystem access, no-network-by-default behavior, and logged outputs.
  - Validation results are produced as structured bundles that are both machine-consumable and human-readable.

- optional Codex execution integration
  - QonQrete supports two explicit capability modes.
  - In Simulation Mode, the system uses reasoning and heuristic validation without real code execution.
  - In Execution Mode, a constrained execution engine such as Codex can be used by `Constrqutor` and system test wrappers to build components and run tests.
  - Even in Execution Mode, external execution engines are workers only. They do not plan architecture, alter contracts, ask questions mid-run, or define success.
  - Confidence, evidence quality, and audit detail are richer in Execution Mode, but the governing authority remains QonQrete.

## Audit & Transparency

The final system exposes a dual-layer audit model.

The high-level timeline is optimized for rapid comprehension. It shows the task intake, clarification outcome, effective constraints, planning decisions, cost estimate, build progress, validator results, inspection verdict, repair decisions, and final status.

The deep technical trace is optimized for debugging and trust. It contains prompts, raw model outputs, command logs, test outputs, validator bundles, actual cost usage, assumptions, and fallback details.

Every major entry answers three questions: what happened, why it happened, and what changed because of it. Assumptions, degraded modes, repair caps, and fallbacks are never implicit. The system’s intelligence is therefore visible as an evidence trail rather than a black box.

## State & Persistence Model

All persistent runtime state lives under `.qonqrete/` in the target repository. Runs are organized as stable artifact hierarchies keyed by run identity and component group rather than by recursive cycle sprawl.

The persisted model includes:
- original task input and clarified task spec
- guard result and effective constraints
- planning package
- build reports and changed-file manifests
- validator result bundles and test outputs
- inspection verdicts and repair plans
- audit timeline and deep trace
- continuation metadata

A completed run is still continuable. “Finished” means the run reached a verdict, not that its state becomes frozen or detached from future work.

## Repo / GitOps Interaction

QonQrete is repo-native and GitOps-friendly in behavior without turning into a CI/CD system by default. The repository is the execution context and source of truth for code, while QonQrete-managed state remains organized under `.qonqrete/`.

The system can be introduced into an existing repo with minimal ceremony, works against the repo in place, and keeps its artifacts trackable and inspectable. Task files are explicit inputs. Runs are resumable and attributable. The model is suitable for later GitOps expansion because scope, contracts, changes, validation evidence, and verdicts are already structured and repo-local.

## Performance Characteristics

The fully realized system is optimized for controlled throughput rather than uncontrolled autonomy. It front-loads ambiguity resolution to avoid downstream churn, uses explicit planning to reduce architectural drift, builds in component groups to keep context coherent, and limits repair to affected areas to avoid expensive whole-run repetition.

It supports cost estimation before major execution and before repair, distinguishes estimated from actual cost, and makes execution shape visible. Performance is also operational: repeated runs are meant to behave consistently, fail clearly, and avoid hidden expansion in scope, token usage, or execution time.

## System Qualities

- reliability
  - The system behaves consistently across runs, fails fast on blocking conditions, and exposes degraded states honestly.
  - Completion depends on explicit evidence rather than optimistic interpretation.

- determinism
  - The same task, repo, and environment lead to materially similar execution shape, artifacts, and decisions.
  - Adaptation exists, but it is bounded by explicit heuristics, caps, and contracts.

- explainability
  - Every important decision is represented in artifacts and audit logs.
  - The system’s behavior can be reconstructed from its outputs without guessing what the models “must have meant.”

- extensibility
  - New validators, execution backends, model providers, and richer repo workflows can be added without collapsing stage boundaries.
  - The architecture separates thinking, execution, validation, and judgment cleanly enough that capabilities can grow without turning the system into opaque agent soup.
</proposed_plan>
