<proposed_plan>
# QonQrete Hard Ruleset

## Summary

QonQrete must operate as a deterministic, auditable, repo-local orchestration system with explicit stage boundaries, structured artifacts, and bounded autonomy. It must not rely on hidden agent behavior, open-ended rerun loops, or AI-based claims of validation where deterministic system validation is required. `tasQleveler` is replaced by `Qrystallizer`; no `Qualifier` agent exists; syntax/tests/mechanical validation belong to system-owned validators, not AI agents.

## Core Guardrails

- QonQrete is the authority. Models and agents are subordinate execution or reasoning components only.
- All stages must consume and emit explicit artifact contracts; no downstream stage may depend on free-form prose alone.
- Ambiguity may be surfaced only once, in `Qrystallizer`, before execution starts.
- After the task is marked `READY`, the run proceeds without further user interaction unless a configured user gate is reached.
- Internal adaptation must be bounded, visible, and logged; no hidden autonomy or silent scope drift.
- One primary plan/build/validate pass is the default architecture.
- Repair is allowed only as targeted repair passes, capped at 1-2. Full open-ended cycle reruns are disallowed.
- User-facing operation must stay zero-config by default except for model/provider credentials and explicit model choices.
- The system must prefer repo-local, in-place execution and `.qonqrete/` state over copy-into-`sqrapyard` workflows.

## Agent Contracts

- `Qrystallizer` (future)
  - Replaces `tasQleveler` completely; no hybrid long-term coexistence.
  - Sole phase allowed to ask questions.
  - Extracts goal, known inputs, constraints, assumptions, and high-impact gaps.
  - May ask at most 3-5 targeted questions; must not turn into a form-filling interview.
  - Must output a structured `Qrystalized Task Spec` with `READY` or `NOT_READY`, locked assumptions, blocking gaps, and non-blocking unknowns.
  - Must never generate architecture, code, or execution actions.

- `Instruqtor`
  - Consumes only `READY` tasks plus effective constraints from guard validation.
  - Determines complexity, briq sense/execution profile, repair allowance, and planning structure.
  - Must produce explicit planning artifacts:
    - Architecture Foundation
    - Execution Plan
    - Dependency & Interaction Contract
    - Component Contracts where needed
    - Validation Plan
    - Completion Criteria
  - Must define completion criteria before coding starts.
  - Must not ask questions mid-run.

- `Constrqutor`
  - Builds against the planning artifacts and constraints; it must not redesign architecture or rewrite contracts.
  - Must execute by component group, using internal mini-briqs within shared component context.
  - Must not generate all briqs independently first, and must not treat giant undifferentiated batches as the working unit.
  - Must perform immediate intra-component coherence checks before moving to the next group.
  - Must emit structured build reports, changed-file manifests, execution summaries, and logged assumptions.
  - Must not ask questions mid-run. Any ambiguity is resolved via logged assumptions.
  - If Codex or similar is used, it acts only as a constrained execution worker.

- `Inspeqtor`
  - Judges against explicit artifacts, not intuition.
  - Consumes build reports, validator bundles, test results, Architecture Foundation, Dependency & Interaction Contract, Validation Plan, and Completion Criteria.
  - Must decide only:
    - `done`
    - `repair required`
  - If repair is required, it must emit explicit repair targets and rationale.
  - Must remain separate from test execution and mechanical validation.
  - Must not ask questions mid-run.

- `system-level validators`
  - Own syntax, parseability, import/schema/interface checks, required file presence, grouped component validation, and sandboxed test execution.
  - Produce machine-readable bundles and concise human-readable summaries.
  - Are deterministic system services, not AI agents.
  - Replace the concept of a `Qualifier` agent completely.

## Validation Rules

- AI validation and system validation must remain separate.
- AI may judge alignment, completeness, and repair targeting; AI must not be treated as proof that code executes correctly.
- Deterministic/system validation owns:
  - syntax/parsing/import checks
  - contract/policy/mechanical checks
  - grouped component coherence checks
  - sandboxed test execution
  - required artifact/file presence checks
- `QontractGuard`-style policy enforcement belongs in guardrails/system validation, not subjective AI review.
- Validation must be evidence-based:
  - validator bundles
  - test outputs
  - build reports
  - explicit contract comparisons
- If execution mode is unavailable, the system must degrade honestly to simulation mode and state that tests were not actually executed.

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
- If a model emits a question during execution, that is a failure condition; the system must retry once with stricter no-question constraints or convert the question into a logged assumption.
- Repair passes must be scoped to affected groups/components only.
- Full rerun loops as the default execution model are disallowed.
- Execution shape, repair allowance, and capability mode must be visible in the audit trail.
- User-facing CLI must converge toward one mental model: `qonqrete [task-file?]`, with auto-detection of repo context and continuable runs.

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
- External execution engines must never become the orchestrator or hidden planner.
- Security claims must match actual enforcement; do not claim broad security coverage where integration is partial.

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
- There must be one authoritative per-run record tying stage outcomes together; fragmented logs alone are insufficient.

## Failure & Retry Rules

- Fail fast on blocking preconditions:
  - task not `READY`
  - policy/guard failure
  - missing required planning artifacts
  - missing required validator outputs
- Mid-run questions are failures, not acceptable interactive behavior.
- Model failures may trigger bounded retries with stronger constraints; silent uncontrolled retries are disallowed.
- Partial build output is not success; validator and inspection evidence determine status.
- Repair retries must be targeted and capped at 1-2 passes.
- Hitting the repair cap must result in a final explicit non-success verdict, not silent continuation.
- Degraded capability modes must lower confidence and be surfaced to the user and audit trail.

## Assumption Handling Rules

- Questions are allowed only in `Qrystallizer`.
- Once a task is `READY`, remaining ambiguity is resolved via assumptions, never via new prompts to the user.
- Assumptions must be:
  - explicit
  - minimally invasive
  - logged with rationale
  - attached to relevant artifacts/build reports
- Assumptions must not override explicit user requirements, contract rules, or security policies.
- High-impact unknowns must block readiness; low-impact unknowns may become logged assumptions.
- Assumption handling must be deterministic enough to be explainable and auditable.

## Determinism & Control Rules

- Same input and environment should yield materially similar structure, execution path, and decisions, even if model wording varies.
- Hardcoded caps and rule-based heuristics must bound model discretion for complexity, briq sense, repair allowance, and execution profile.
- Capability differences must be explicit:
  - Simulation Mode: heuristic/non-executed validation
  - Execution Mode: real build/test execution with higher confidence
- The system must never pretend simulated validation is equivalent to executed validation.
- Hidden agent autonomy, silent replanning, and undocumented contract changes are forbidden.
- QonQrete decides scope, contracts, repair targets, and verdicts. External builders only execute within that frame.

## Important Public Interfaces / Artifacts

- `Qrystalized Task Spec`
  - must include goal, known inputs, constraints, assumptions, decisions, unknowns, and `READY`/`NOT_READY`
- `Guard Result`
  - must include `pass | fail | review`, blocking issues, warnings, and effective constraints
- `Execution Blueprint`
  - must include Architecture Foundation, Execution Plan, Dependency & Interaction Contract, Validation Plan, and Completion Criteria
- `Build Report`
  - must include changed-file manifest, assumptions used, execution summary, and component/group scope
- `Validator Result Bundle`
  - must include machine-readable results plus condensed summary
- `Inspection Verdict`
  - must include `done` or `repair required`, with explicit repair targets and reasons

## Absolute Non-Requirements (CRITICAL)

- Do not build or preserve `tasQleveler` as a long-term active stage.
- Do not introduce a standalone `Qualifier` AI agent.
- Do not let AI own syntax checking, test execution, or mechanical validation claims.
- Do not allow open-ended autonomous cycles or recursive whole-system reruns as the core architecture.
- Do not allow mid-run clarifying questions from `Instruqtor`, `Constrqutor`, `Inspeqtor`, or any execution worker.
- Do not embed black-box CLI agents as the system brain/orchestrator.
- Do not let Codex or any execution engine redefine architecture, contracts, or success criteria.
- Do not require users to copy repos into `sqrapyard` or rely on `-s` as the primary flow.
- Do not require `tasq.md` as the only valid task-file name.
- Do not require manual `init` + `run` in the happy path.
- Do not hide degraded capability modes or imply all model backends provide real execution/testing.
- Do not claim deterministic security coverage beyond what the system actually enforces.
- Do not rely on free-form prose artifacts where machine-readable contracts/results are required.

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
- Rebuild-before-demo thinking instead of surgical upgrades to clarification, audit, validation boundaries, and entry UX

## Assumptions

- Current reality still includes `tasqleveler` in the repo and pipeline, but the intended hard ruleset treats it as deprecated and to be replaced by `Qrystallizer`.
- Current deterministic validators are strongest for Python-centric flows; the ruleset still requires system-owned validation generally.
- Codex-backed execution/testing is a future or capability-tiered mode, not a mandatory universal backend.
- The system remains file-contract-driven and repo-local, with state persisted under `.qonqrete/` in the intended target model.
</proposed_plan>
