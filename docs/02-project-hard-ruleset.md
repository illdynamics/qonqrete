# QonQrete Hard Ruleset

## Summary
This ruleset defines the non-negotiable behavioral foundation for QonQrete. It exists to prevent drift between planning, execution, validation, realization, judgment, state, and audit.

These rules apply independently of future migration details, future Qonscience or contract systems, future canonical stage registries, and future repair-plan schemas. Missing future systems do not suspend these rules.

Current inconsistencies that must remain explicit until corrected:
- The current codebase still contains `tasqleveler` and does not yet contain `Qrystallizer`.
- No `Qualifier` agent exists today; deterministic validation is currently system-level and partially implemented in runtime code.
- Current docs, comments, and runtime stage ordering are not fully aligned.
- Current runtime still allows incremental partial writes without full transactional protection.
- Current validation depth is materially stronger for Python than for several other ecosystems.

## Core Guardrails
- Every run must have a single explicit task intake point.
- Only the task-clarification phase may ask the user questions.
- No execution phase may block on new clarification after execution begins.
- Every stage must have a defined responsibility boundary.
- Planning, execution, validation, realization, and judgment must remain separate concerns.
- A later stage must not silently replace the responsibility of an earlier stage.
- A stage must not claim evidence it did not produce or consume.
- A run must not be declared complete without explicit validation and realization evidence.
- Missing evidence must lower confidence and must be disclosed.
- Capability limits must be disclosed whenever they affect outcome confidence, validation depth, or execution fidelity.
- Auditability is required even when execution is partial, failed, or degraded.

## Determinism Rules
- Deterministic checks must be preferred over heuristic checks whenever a deterministic method is available.
- Deterministic results must not be overridden by AI judgment.
- If a result is inferred rather than directly validated, that must be disclosed.
- The same declared mode, same declared scope, and same same-stage inputs must produce traceably comparable execution behavior.
- Hidden runtime branching that changes behavior without disclosure is forbidden.
- Automatic adaptation must be bounded, explainable, and visible in artifacts.
- Open-ended recursive replanning is forbidden as a default execution model.
- Default execution must be one bounded main pass with bounded targeted repair only when justified by evidence.
- Hard caps must exist for repair attempts, time, and execution budget.
- Cost or complexity auto-tuning must not be treated as magical or opaque; the decision basis must be surfaced.

## Validation Rules
- Validation is required before final judgment.
- Deterministic local or system-level validation must be executed when available for the relevant ecosystem and mode.
- AI review may supplement validation but must not replace available deterministic validation.
- Validation output must distinguish what was actually checked from what was not checked.
- Validation coverage must be explicit by language, ecosystem, and capability mode.
- Simulated validation must be labeled as simulated.
- Executed validation must be labeled as executed.
- Validation must not be summarized in a way that hides failures, skipped checks, or unavailable checks.
- Completion claims must not exceed validation coverage.
- Validation planning must exist before build execution begins.
- Validation results must remain linkable to the build scope they evaluate.

## Execution Constraints
- Execution must not begin until task clarification is declared ready or equivalent.
- Execution must operate within an explicit scope boundary.
- Mid-run user questioning is forbidden outside the task-clarification phase.
- If execution encounters ambiguity after start, it must use logged assumptions or fail explicitly; it must not hang waiting for input.
- Execution must not silently redesign the task, architecture, or completion criteria during build.
- Planning artifacts must define completion criteria before construction begins.
- Build execution must produce explicit outputs and run evidence, not only generated files.
- Group-level or component-level coherence must be evaluated where the build scope crosses multiple sub-units.
- Whole-system judgment must not rely only on per-unit success.
- Repair must be targeted, bounded, and evidence-driven.
- Full rerun loops as the default response to failure are forbidden.

## Security Rules
- Scope boundaries for reads, writes, and execution must be explicit.
- Execution environments must have defined limits for filesystem scope, time, and allowed commands where execution is enabled.
- Unsafe or prohibited actions must be blocked or explicitly surfaced before build execution.
- Security policy evaluation must occur before build execution when such policies exist.
- Security-sensitive limitations or missing enforcement must be disclosed.
- Hidden privilege escalation is forbidden.
- Hidden external side effects are forbidden.
- Capability disclosures must state when execution is sandboxed, simulated, or unrestricted.
- Security claims must not exceed implemented enforcement.

## Audit & Logging Rules
- Every run must produce a traceable audit trail.
- Every major stage must emit a stable, linkable record of entry, exit, status, and produced artifacts.
- Audit records must distinguish high-level summaries from detailed evidence.
- Decision points must record what happened, why it happened, and what changed because of it.
- Failures, fallbacks, assumption use, and capability downgrades must be logged explicitly.
- Logs must not be the only place where critical execution state can be reconstructed.
- Markdown summaries alone are not sufficient audit basis.
- Fragmented artifacts are allowed temporarily, but they must still be linked through one authoritative run-level record concept.
- Audit output must support diagnosis of partial writes, missing validation, and degraded modes.
- A run must not require tribal knowledge to reconstruct what happened.

## Failure & Retry Rules
- Failure must be explicit, not inferred from silence.
- A failed stage must record why it failed, what scope it touched, and what artifacts remain valid.
- Retry behavior must be explicit and bounded.
- Repair or retry must not erase evidence of the failed attempt.
- Repair must consume prior validation and realization evidence rather than ignoring it.
- A repair pass must define what it is trying to correct before it runs.
- Repair must not silently expand scope beyond the declared repair target.
- Failure states must remain distinguishable from success states in both artifacts and lifecycle status.
- Partial success must not be represented as full success.
- If recovery or rollback is not available, that absence must be disclosed.

## Assumption Handling Rules
- Assumptions are allowed only when they do not replace required clarification on high-impact blockers.
- High-impact ambiguity must be resolved during task clarification or cause a not-ready outcome.
- Only the task-clarification phase may ask the user questions.
- After execution starts, ambiguity must be handled through explicit assumptions or explicit failure.
- Every material assumption must be logged with what was unclear, what was assumed, and why.
- Assumptions must be distinguishable from user-provided facts.
- Assumptions must remain traceable through planning, execution, validation, realization, and judgment.
- Hidden assumptions are forbidden.
- Mid-run invented requirements are forbidden.
- Assumptions must not be used to overstate completion or validation quality.

## Determinism & Control Rules
- Stage identity must be explicit.
- Stage order must be explicit.
- Lifecycle status must be explicit.
- Capability mode must be explicit where it affects execution or validation depth.
- No hidden enum drift is allowed across code, config, docs, runtime outputs, or audit artifacts.
- If divergence exists between implementation and documentation, that divergence must be disclosed.
- Status-bearing artifacts must not invent undocumented meanings.
- Control logic must not depend on undocumented side channels.
- Automatic decisions must be bounded, attributable, and reviewable.
- The system must not present heuristic behavior as guaranteed control.

## State Persistence Rules (PRE-MIGRATION SAFE)
- State must be explicit.
- No hidden state is allowed.
- No implicit continuation is allowed.
- State transitions must be traceable.
- Future `.qonqrete` persistence may be assumed directionally but must not be falsely represented as already canonical.
- Current-state persistence and any transition toward canonical state must remain honest and auditable.
- No hidden shadow state may become required to explain, continue, validate, or judge a run.
- A run must be resumable only through explicit persisted state, not through untracked memory or conversational context.
- Persisted state must distinguish task input, planning output, build output, validation output, realization output, judgment output, and audit output.
- If state is copied, resumed, or continued, the lineage must remain visible.

## Manifest Rules (FOUNDATIONAL)
- Every run must produce a traceable execution record.
- Execution trace must be reconstructable.
- Artifact linkage must exist.
- No orphan outputs are allowed.
- There must be one authoritative run-level record concept, even before the final manifest design is formalized later.
- Stage results, major artifacts, and lifecycle status must be linkable through that authoritative record concept.
- Fragmented unlinked logs or markdown alone must not be sufficient audit basis.
- The authoritative run-level record must distinguish intended flow from observed execution.
- The authoritative run-level record must expose capability mode, validation coverage, and final disposition.
- The authoritative run-level record must survive partial failure.

## Observation / Realization Rules
- Every execution stage that can change code, artifacts, behavior, or state must produce explicit realization evidence.
- Realization must describe what actually happened, not what was intended.
- Realization must remain separate from planning, judgment, and marketing-style summaries.
- Realization evidence must include touched scope and changed-file truth where applicable.
- Realization must distinguish structural change, behavioral change, and system impact when evidence exists.
- Judgment, completion, or repair decisions must not rely on plan text alone when realization evidence is available.
- Missing realization evidence must lower confidence and be disclosed.
- Realization must be produced before final inspection judgment.
- Realization must remain linkable to the specific execution attempt that produced it.
- Realization must not be overwritten by later verdict summaries.

## Stage / Status / Mode Control Rules
- Stage names, stage order, lifecycle statuses, and capability modes must be explicit.
- No hidden enum drift is allowed across code, config, docs, or runtime outputs.
- Current implementations must disclose divergence until one canonical registry exists later.
- Status-bearing artifacts must not invent ad hoc meanings without documentation.
- Capability mode disclosures must not be omitted when they affect confidence or validation depth.
- A mode that lacks real execution must disclose that limitation.
- A mode that lacks deterministic validation for a relevant ecosystem must disclose that limitation.
- A stage must not imply canonical status naming that does not yet exist.
- Foundational rules must be enforceable without inventing the future appendix registry.

## Transaction & Partial Write Safety Rules
- Partial untracked writes are forbidden in the target architecture.
- Until a formal rollback strategy exists, current partial-write behavior must be explicitly disclosed and auditable.
- Every build operation must produce enough evidence to identify touched scope and changed files.
- Failure must not silently leave the system in a state that is indistinguishable from success.
- Rollback, recovery, or cleanup behavior must be explicit, not implied.
- Writes must be attributable to a specific execution attempt.
- A failed attempt must not erase the evidence of files it touched.
- A success claim must not be issued if the system cannot distinguish committed outcome from partial residue.
- Retrying after partial writes without disclosure is forbidden.
- If atomic or staged writes are unavailable, the system must say so.

## Language / Ecosystem Capability Disclosure Rules
- Validation coverage must be disclosed honestly by language and ecosystem.
- No false language-agnostic parity claims are allowed.
- Where deterministic validation is stronger for one language or ecosystem than another, that asymmetry must be made explicit.
- Weaker capability modes or weaker ecosystem support must lower confidence and be disclosed to the user and audit trail.
- Universal workflow support must not be described as universal deterministic verification.
- AI-dependent review must not be presented as equivalent to executed validation.
- Missing validators for a stack must be disclosed before or during execution, not hidden after the fact.
- Language-specific enforcement must not be described as ecosystem-neutral enforcement.
- Marketing language must not outrun implementation reality.

## Required Artifacts (MINIMUM SET)
- Task Spec (structured)
- Execution Plan (structured)
- Build Output
- Validation Output
- Result / Realization Output
- Execution Trace
- Repair Intent or Repair Target artifact when repair is required
- Explicit capability-mode disclosure where validation or execution depth differs materially

Additional minimum artifact rules:
- Each required artifact must be attributable to a run and stage.
- Each required artifact must be linkable from the authoritative run-level record.
- A required artifact may be incomplete only if that incompleteness is explicit.
- Required artifacts must not be replaced by conversational summaries alone.

## Absolute Non-Requirements
- A future migration model is not required to define these rules.
- Qonscience is not required to define these rules.
- A future canonical contract appendix is not required to define these rules.
- A final stage and status registry is not required to define these rules.
- An exact final repair-plan schema is not required to define these rules.
- A specific vendor model is not required to define these rules.
- Codex is not required for every phase.
- Full language parity is not required immediately.
- Full transactional rollback is not required immediately.
- A complete GitOps platform is not required immediately.
- A polished UI is not required to satisfy these rules.
- A hidden internal mechanism is never required to explain a run.

## Anti-Patterns
- Asking the user new questions after execution has started
- Treating iterative whole-system reruns as the default execution strategy
- Claiming validation that was never executed
- Claiming ecosystem parity that does not exist
- Using AI judgment to overrule deterministic failures
- Allowing undocumented stage or status drift
- Declaring completion from planning text without realization evidence
- Letting logs exist without authoritative linkage
- Leaving partial writes without explicit disclosure
- Allowing repair to expand scope silently
- Hiding assumptions in prompts or internal state
- Requiring hidden runtime memory to resume or explain a run
- Treating fragmented markdown as a sufficient audit system
- Letting capability downgrades go undisclosed
- Letting security claims exceed enforcement reality
- Treating simulated testing as real execution
- Allowing unbounded auto-tuning, retry, or repair behavior
- Collapsing realization and judgment into one opaque summary
- Using future architecture ideas as excuses for present ambiguity
- Silently correcting known inconsistencies instead of disclosing them
