# QonQrete Hard Ruleset

## Summary

QonQrete must operate as a deterministic, auditable, repo-native orchestration system with explicit stage boundaries, structured artifacts, bounded autonomy, and one authoritative run record per run. It must not rely on hidden agent behavior, open-ended rerun loops, undocumented state transitions, or AI-based claims of validation where deterministic system validation is required. `tasQleveler` is transitional residue only; `Qrystallizer` is the canonical clarification stage; no standalone `Qualifier` agent exists; syntax/tests/mechanical validation belong to system-owned validators, not AI agents.

## Core Guardrails

- QonQrete is the authority. Models, workers, and support helpers are subordinate reasoning or execution components only.
- All stages must consume and emit explicit artifact contracts; no downstream stage may depend on free-form prose alone when a structured contract is required.
- Ambiguity may be surfaced only once, in `Qrystallizer`, before execution starts.
- After the task is marked `READY`, the run proceeds without further user questioning unless an explicit user gate outside agent control is configured.
- Internal adaptation must be bounded, visible, and logged; no hidden autonomy, silent scope drift, or silent contract mutation is allowed.
- One primary clarify/guard/plan/build/validate/judge pass is the canonical architecture.
- Repair is allowed only as targeted repair passes, capped at 1-2. Full open-ended cycle reruns are disallowed as the target architecture.
- User-facing operation must converge on repo-native `.qonqrete/` state and one-command entry over qage/sqrapyard-centric workflows.
- Support helpers such as `qontextor`, `qompressor`, and `qontrabender` may provide context/cache support, but they must never become hidden planning, validation, or verdict authorities.
- Repo code is the source of truth for code. QonQrete state is the source of truth for run reasoning, constraints, evidence, verdicts, and continuation metadata.

## Agent Contracts

- `Qrystallizer`
  - Replaces `tasQleveler` as the canonical front door. No hybrid long-term coexistence is allowed.
  - Is the sole phase allowed to ask questions.
  - Must output a structured `Qrystalized Task Spec` with `READY` or `NOT_READY`, locked assumptions, blocking gaps, and non-blocking unknowns.
  - Must never generate architecture, code, validation results, or execution actions.

- `Instruqtor`
  - Consumes only `READY` tasks plus effective constraints from guard validation.
  - Must produce explicit planning artifacts:
    - Architecture Foundation
    - Execution Plan
    - Dependency & Interaction Contract
    - Component Contracts
    - Validation Plan
    - Completion Criteria
  - Must define completion criteria before coding starts.
  - Must not ask questions mid-run.

- `Constrqutor`
  - Builds against locked planning artifacts and constraints; it must not redesign architecture or rewrite contracts.
  - Must execute by component group, using internal mini-briqs within shared component context.
  - Must not generate all briqs independently first, and must not treat giant undifferentiated batches as the working unit.
  - Must emit structured build reports, changed-file manifests, execution summaries, and logged assumptions.
  - Must not ask questions mid-run. Remaining ambiguity must be resolved via logged assumptions.
  - If external execution engines are used, they act only as constrained workers.

- `Inspeqtor`
  - Judges against explicit plans, contracts, validator bundles, test results, and completion criteria.
  - Must decide only:
    - `done`
    - `repair required`
  - If repair is required, it must emit explicit repair targets and rationale.
  - Must remain separate from test execution and mechanical validation.
  - Must not ask questions mid-run.

- `system-level validators`
  - Own syntax, parseability, import/schema/interface checks, required artifact presence, grouped component validation, deterministic contract checks where implemented, and sandboxed test execution.
  - Produce machine-readable bundles and concise human-readable summaries.
  - Are deterministic system services, not AI agents.
  - Replace the concept of a `Qualifier` agent completely.

- `Guard / Policy Validation Stage`
  - Must run after clarification and before planning.
  - Must output `pass | fail | review`, blocking issues, warnings, and effective constraints.
  - Must block planning on `fail`.
  - Must not be reduced to vague AI review or hidden policy checks.

- `Orchestrator / Runtime Authority`
  - Owns stage order, sequencing, gates, manifest lifecycle, persistence linkage, continuation routing, repair caps, and final runtime control.
  - Must fail fast on missing required artifacts or invalid stage preconditions.
  - Must not delegate orchestration authority to AI agents.

## Validation Rules

- AI validation and system validation must remain separate.
- AI may judge alignment, completeness, and repair targeting; AI must not be treated as proof that code executes correctly.
- Deterministic/system validation owns:
  - syntax/parsing/import checks
  - interface/schema checks
  - contract/policy/mechanical checks where implemented
  - grouped component coherence checks
  - sandboxed test execution
  - required artifact/file presence checks
- `QontractGuard`-style policy enforcement belongs in guardrails/system validation, not subjective AI review.
- Validation must be evidence-based:
  - validator bundles
  - test outputs
  - build reports
  - explicit contract comparisons
- Validation bundles must distinguish executed validation from simulated or non-executed validation.
- If execution mode is unavailable, the system must degrade honestly to simulation mode and state that tests were not actually executed.
- `Inspeqtor` must not issue a final verdict without validator evidence.
- Deterministic failures must not be silently downgraded by AI judgment.

## Execution Constraints

- Canonical flow:
  - Input
  - `Qrystallizer`
  - Guard/policy validation
  - `Instruqtor`
  - `Calqulator`
  - optional user gate
  - `Constrqutor`
  - system-level validators
  - `Inspeqtor`
  - finish or targeted repair
- No stage after `Qrystallizer` may ask the user anything.
- No model may pause the run waiting for confirmation once execution has started.
- If a model emits a question during execution, that is a failure condition; the system must retry once with stricter no-question constraints or convert the question into a logged assumption under orchestrator policy.
- Repair passes must be scoped to affected groups/components only.
- Full rerun loops as the default execution model are forbidden.
- Execution shape, repair allowance, capability mode, and degraded mode must be visible in the audit trail and run manifest.
- User-facing CLI must converge toward one mental model: `qonqrete [task-file?]`.
- Current qage-based cycle behavior may exist during transition, but it must not silently substitute for the target execution model when target behavior is expected.

## Security Rules

- The system must remain deterministic, controlled, and auditable over “smart” but hidden behavior.
- Policy/constraint validation must occur before planning/building.
- Safe defaults must be built in; user overrides may relax or tighten rules only through explicit, auditable configuration.
- Execution/testing must run in controlled sandboxes with:
  - no-network-by-default
  - scoped filesystem access
  - resource/time limits
  - approved-command boundaries
  - auditable logs
- No agent may bypass QonQrete’s contracts, policies, or execution boundaries.
- External execution engines must never become the orchestrator, hidden planner, or hidden policy authority.
- Security claims must match actual enforcement; do not claim broad security coverage where integration is partial.
- No hidden shadow state may be used to store security-relevant run decisions, constraints, or verdict inputs outside manifest-linked state.

## Audit & Logging Rules

- Every run must produce a two-layer audit trail:
  - high-level timeline for default viewing
  - deep technical trace for debugging
- Every major event must record:
  - what happened
  - why it happened
  - what changed
- Required high-level entries:
  - input received
  - `Qrystallizer` decisions/questions
  - locked assumptions
  - guard result and effective constraints
  - complexity/briq sense/execution profile selection
  - cost estimate and gates
  - component build progress
  - validator outcomes
  - `Inspeqtor` verdict
  - repair decisions
  - final status
- Required deep entries:
  - prompts
  - raw model outputs
  - command/test logs
  - validator bundles
  - token/cost actuals
  - assumption details
  - fallbacks and degraded modes
- All fallbacks must be explicit:
  - assumption chosen
  - simulation mode used
  - repair cap hit
  - validation bypass/degradation
  - compatibility-mode usage
- The run manifest must be the authoritative linkage record for auditability.
- Fragmented logs, markdown artifacts, IDE markers, or raw stage logs alone are insufficient audit basis if they are not linked by the run manifest.

## Failure & Retry Rules

- Fail fast on blocking preconditions:
  - task not `READY`
  - policy/guard failure
  - missing required planning artifacts
  - missing required manifest
  - missing required validator outputs before judgment
- Mid-run questions are failures, not acceptable interactive behavior.
- Model failures may trigger bounded retries with stronger constraints; silent uncontrolled retries are disallowed.
- Partial build output is not success; validator and inspection evidence determine status.
- Repair retries must be targeted and capped at 1-2 passes.
- Hitting the repair cap must result in a final explicit non-success verdict, not silent continuation.
- Degraded capability modes must lower confidence and be surfaced to the user, audit trail, and run manifest.
- Resume/continuation must fail if state lineage, artifact linkage, or manifest integrity is broken.

## Assumption Handling Rules

- Questions are allowed only in `Qrystallizer`.
- Once a task is `READY`, remaining ambiguity is resolved via assumptions, never via new prompts to the user.
- Assumptions must be:
  - explicit
  - minimally invasive
  - logged with rationale
  - attached to relevant artifacts/build reports/audit records
- Assumptions must not override explicit user requirements, contract rules, guard constraints, or security policies.
- High-impact unknowns must block readiness; low-impact unknowns may become logged assumptions.
- Assumption handling must be deterministic enough to be explainable and auditable.
- Assumptions that materially influence code or verdicts must be reachable from the run manifest.

## Determinism & Control Rules

- Same input and environment should yield materially similar structure, execution path, and decisions, even if model wording varies.
- Hardcoded caps and rule-based heuristics must bound model discretion for complexity, briq sense, repair allowance, execution profile, and retry behavior.
- Capability differences must be explicit:
  - Simulation Mode: heuristic/non-executed validation
  - Execution Mode: real build/test execution with higher confidence
- The system must never pretend simulated validation is equivalent to executed validation.
- Hidden agent autonomy, silent replanning, and undocumented contract changes are forbidden.
- QonQrete decides scope, contracts, repair targets, lifecycle state, and verdict routing. External builders only execute within that frame.
- Support helpers, caches, and warmup outputs must not silently influence planning or verdicts outside documented contract paths.

## State Persistence & Migration Rules

- Repo-native `.qonqrete/` state is the canonical target persistence model.
- During transition, coexistence with current qage-based reality is allowed only through explicit bridge logic.
- State authority boundaries must be enforced:
  - repo code is the source of truth for code
  - `.qonqrete/` is the source of truth for run reasoning, constraints, evidence, verdicts, and continuation metadata
  - qage-era artifacts are compatibility artifacts unless explicitly bridged into canonical state
- No hidden shadow state is allowed. Any state required to explain, continue, validate, or judge a run must be stored in or linked from canonical QonQrete state.
- Continuation/resume integrity is mandatory:
  - continuation must have explicit source-run linkage
  - inherited artifacts must be identifiable
  - planning reuse vs refresh must be explicit
  - repair-pass counts must remain accurate
- Migration honesty is required:
  - the system must disclose when it is using compatibility behavior
  - the system must disclose when canonical `.qonqrete/` state is incomplete or bridged from qage-era artifacts
  - the system must not claim migration-complete behavior while relying on undocumented legacy state semantics
- Compatibility constraints during transition:
  - qage and `.qonqrete/` semantics may coexist only when the bridge logic is explicit
  - cycle-promotion artifacts may persist as readable compatibility records, but they must not silently remain canonical continuation truth where target continuation metadata is required
  - support/cache artifacts may persist across models only if their ownership and linkage are explicit

## Authoritative Run Manifest Rules

- Every run must have one authoritative run manifest.
- The run manifest must be created before clarification starts, immediately after run identity is allocated.
- The run manifest must link, at minimum:
  - task input artifact
  - clarified task artifact
  - guard result
  - planning package
  - cost estimate/current actuals
  - build reports
  - validation bundles
  - inspection verdict
  - audit timeline
  - deep trace
  - continuation metadata
- The orchestrator must update the manifest at each major stage boundary.
- At minimum, these stages must update or trigger manifest updates:
  - run intake
  - `Qrystallizer`
  - Guard / Policy Validation Stage
  - `Instruqtor`
  - `Calqulator`
  - each build group in `Constrqutor`
  - each validator bundle completion
  - `Inspeqtor`
  - each repair pass start/end
  - final lifecycle closure
  - continuation creation
- Manifest consistency guarantees:
  - referenced artifacts must exist or be explicitly marked unavailable/degraded
  - stage status in the manifest must match artifact reality
  - current lifecycle state must be singular and unambiguous
  - continuation lineage must be traceable
- Fragmented, unlinked stage records are forbidden as the sole audit basis.
- A run is not audit-complete if its critical artifacts exist only as unlinked markdown, logs, or sidecar files without manifest linkage.

## Required Public Interfaces / Artifacts

- `Qrystalized Task Spec`
  - must include goal, known inputs, constraints, locked assumptions, confirmed decisions, gaps/unknowns, and `READY`/`NOT_READY`
- `Guard Result`
  - must include `pass | fail | review`, blocking issues, warnings, and effective constraints
- `Execution Blueprint`
  - must include Architecture Foundation, Execution Plan, Dependency & Interaction Contract, Component Contracts, Validation Plan, Completion Criteria, and execution-shape metadata
- `Component Contract`
  - must include component identity, interfaces, dependencies, constraints, and acceptance conditions
- `Build Report`
  - must include changed-file manifest, assumptions used, execution summary, touched interfaces/dependencies, capability mode, and scoped build identity
- `Validation Result Bundle`
  - must include machine-readable results, scope checked, execution/simulation disclosure, and condensed summary
- `Inspection Verdict`
  - must include `done` or `repair required`, explicit repair targets, reasons, evidence refs, and confidence conditioned by capability mode
- `Run Manifest`
  - must include per-run linkage of stage statuses, artifacts, audit refs, validation refs, verdict refs, and continuation refs
- `Continuation Metadata`
  - must include source run, continuation type, inherited artifacts, target scope, planning reuse mode, repair-pass count, and next action

## Absolute Non-Requirements (CRITICAL)

- Do not build or preserve `tasQleveler` as a long-term active canonical stage.
- Do not introduce a standalone `Qualifier` AI agent.
- Do not let AI own syntax checking, test execution, or mechanical validation claims.
- Do not allow open-ended autonomous cycles or recursive whole-system reruns as the core architecture.
- Do not allow mid-run clarifying questions from `Instruqtor`, `Constrqutor`, `Inspeqtor`, validators, or any execution worker.
- Do not embed black-box CLI agents as the system brain/orchestrator.
- Do not let Codex or any execution engine redefine architecture, contracts, state authority, or success criteria.
- Do not require users to copy repos into `sqrapyard` or rely on `-s` as the primary flow.
- Do not require `tasq.md` as the only valid task-file name.
- Do not require manual `init` + `run` in the happy path.
- Do not hide degraded capability modes or imply all model backends provide real execution/testing.
- Do not claim deterministic security or state integrity coverage beyond what the system actually enforces.
- Do not rely on free-form prose artifacts where machine-readable contracts/results are required.
- Do not treat qage-era compatibility artifacts as canonical state after migration-complete behavior is claimed.

## Anti-Patterns to Avoid

- Pipeline-order drift between code, docs, and operator mental model
- “Another document” sprawl without first-class contract semantics
- Generating all briqs independently and hoping coherence emerges later
- Using `Inspeqtor` as a cleanup firefighter for upstream architectural chaos
- Mixing planning authority with execution authority
- Confusing AI judgment with proof of correctness
- Silent fallbacks, silent assumption changes, or silent capability downgrades
- Over-tuning cycles and briq sense as moving targets during execution
- Double-brain orchestration by stacking QonQrete on top of autonomous CLI agents
- Audit dumps without a readable timeline or explicit decision rationale
- Fragmented logs without manifest linkage
- Shadow state outside canonical persistence roots
- Claiming repo-native target behavior while silently depending on qage-only semantics

## Transition-Specific Prohibitions

- Do not silently half-migrate state models.
- Do not mix qage and `.qonqrete/` semantics without explicit bridge logic.
- Do not leave manifest gaps undocumented during transitional coexistence.
- Do not silently fall back to old cycle behavior when target behavior is expected.
- Do not pretend migration-complete status before required canonical artifacts exist.
- Do not let `reqap -> next tasq` remain implicit continuation truth when continuation metadata is required.
- Do not treat qage-local artifacts as canonical without explicit manifest linkage into the bridged run truth.
- Do not silently preserve old path semantics, including `qache` placement, when canonical state placement is expected.
- Do not declare audit completeness if critical stage records are still fragmented and unlinked.
- Do not declare repo-native state authority while hidden operational truth still lives only in legacy runtime paths.
