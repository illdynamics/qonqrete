<proposed_plan>
# QonQrete Execution Plan

## Core Principles

- Replace `tasQleveler` with `Qrystallizer` as the single ambiguity-clearing front door.
- Treat local verification and test execution as system-level services, not AI agents.
- Keep orchestration explicit, bounded, and auditable; do not rely on hidden agent autonomy.
- Use one primary planning/build/inspect pass with at most 1-2 targeted repair passes, not open-ended full-cycle reruns.
- Make every stage produce a strict artifact contract so downstream stages consume structured outputs, not free-form prose.
- Keep user UX zero-config by default: API keys + model choices + one command; all other tuning is internal.
- Separate “thinking” from “doing”: reasoning/planning/judgment stay in QonQrete, execution/testing may be delegated later to Codex or equivalent.
- Ask questions only once, in `Qrystallizer`; all later ambiguity is resolved via logged assumptions, never mid-run prompts.

## System Architecture

- **Phase 1: Clarify**
  - `Qrystallizer` receives raw task input, extracts goal/constraints/inputs, detects only high-impact gaps, asks up to 3-5 questions, and emits a `Qrystalized Task Spec`.
  - Output includes `READY` / `NOT_READY`, locked assumptions, blocking gaps, and non-blocking unknowns.

- **Phase 2: Guard**
  - A pre-build policy/constraint validation stage checks the `Qrystalized Task Spec` against default sane QONTRACT rules and any user overrides.
  - It returns `pass | fail | review`, blocking issues, warnings, and effective constraints to inject into planning.

- **Phase 3: Plan**
  - `Instruqtor` classifies complexity, selects briq sense, decides execution profile, and generates the full planning package:
    - Architecture Foundation
    - Execution Plan
    - Dependency & Interaction Contract
    - Component Contracts
    - Validation Plan
    - Completion Criteria
  - Planning is explicit and stable before coding starts.

- **Phase 4: Estimate**
  - `Calqulator` computes estimated total cost, expected execution shape, and confidence level, then optionally gates execution once before build and once before any repair pass.

- **Phase 5: Build**
  - `Constrqutor` executes component-by-component.
  - Each component is internally decomposed into mini-briqs, but built with shared component context.
  - It emits build reports, changed-file manifests, assumptions used, and component-level execution summaries.

- **Phase 6: Validate**
  - System-level validators run first: syntax/parsing/import/schema checks, component coherence checks, and sandboxed tests.
  - `Inspeqtor` then evaluates outputs against the Architecture Foundation, Dependency Contract, Validation Plan, and Completion Criteria.

- **Phase 7: Finish or Repair**
  - If complete, mark the run finished.
  - If not, generate a targeted repair plan for affected components/groups only.
  - Rebuild and revalidate only those targets; hard-cap repair passes at 1-2.

## Agent Responsibilities

- **Qrystallizer (future)**
  - Replace `tasQleveler` completely.
  - Clarify intent, detect high-impact gaps, ask bounded questions, lock assumptions, and output a structured `Qrystalized Task Spec`.
  - Be model-agnostic and reasoning-first; copy Codex-style gap behavior explicitly rather than depending on Codex itself.
  - Never generate architecture or code.

- **Instruqtor**
  - Consume only `READY` tasks plus effective constraints.
  - Determine complexity, briq sense, execution profile, repair allowance, and planning artifacts.
  - Produce the system architecture, dependency wiring, component contracts, validation plan, and completion criteria.
  - Treat dependency relationships as a first-class contract, not side notes.

- **Constrqutor**
  - Build components, not isolated global briqs.
  - Internally decompose each component into briqs, generate in shared context, run immediate intra-component coherence checks, and emit structured build reports.
  - Never ask questions mid-run.
  - If using Codex later, Codex acts only as a constrained execution worker for scoped component tasks.

- **Inspeqtor**
  - Judge outputs against explicit plans/contracts, not intuition.
  - Aggregate system-level evidence from build reports, validator results, and tests.
  - Decide `done` vs targeted repair, and emit repair targets plus rationale.
  - Remain separate from execution and test-running responsibilities.

- **System-level validators (non-AI)**
  - Own syntax/mechanical validation, schema/import/interface checks, grouped component validation, and sandboxed test execution.
  - Produce machine-readable result bundles and human-readable summaries for `Inspeqtor` and the audit trail.
  - Replace the idea of a `Qualifier` agent; no standalone AI tester exists.

## Execution Flow

1. User runs QonQrete in an existing repo and points to a task file or selects one interactively.
2. `Qrystallizer` clarifies the task, asks bounded questions, and emits a `READY` or `NOT_READY` spec.
3. Guard stage validates the spec against default constraints and enriches it with effective rules.
4. `Instruqtor` creates the planning package and selects internal execution settings.
5. `Calqulator` presents estimated total cost, current confidence, and optional gate.
6. `Constrqutor` builds component groups sequentially, each with internal mini-briqs and immediate component coherence checks.
7. System-level validators run local checks and sandboxed tests as defined by the Validation Plan.
8. `Inspeqtor` evaluates the results against the planning artifacts and completion criteria.
9. If needed, `Inspeqtor` emits a targeted repair plan; only affected groups are rebuilt and revalidated.
10. QonQrete finishes with a final verdict, clean audit timeline, and resumable continuation state.

## Codex Integration Strategy

- Use Codex later only as an execution engine, never as QonQrete’s planner or orchestrator.
- Authority stays with QonQrete:
  - QonQrete decides scope, contracts, repair targets, and success criteria.
  - Codex builds scoped components and runs tests within those constraints.
- Preferred split:
  - `Qrystallizer`: general reasoning model
  - `Instruqtor`: general reasoning/planning model
  - `Constrqutor`: Codex-preferred, fallback general LLM possible
  - system test execution: Codex-preferred later, system-owned wrapper
  - `Inspeqtor`: general reasoning/judgment model
- Expose explicit execution modes:
  - Simulation Mode: any model, no real execution, heuristic validation only
  - Execution Mode: Codex-enabled, real build/test execution, higher confidence
- Never allow Codex to redesign architecture, alter contracts, or ask mid-run questions.
- Capture Codex command logs and test outputs into the audit trail when integration is added.

## Validation Strategy

- **Local validation**
  - Syntax, parseability, import/schema/interface checks, required file presence, grouped component validation, and sandboxed tests.
  - Run as system services, not AI agents.
  - Produce both machine-readable bundles and condensed summaries.
  - Treat execution/testing as constrained sandbox operations with no-network-by-default, scoped filesystem access, resource caps, and auditable logs.

- **AI validation**
  - `Inspeqtor` performs judgment and alignment, not raw test execution.
  - Compare implementation against:
    - Qrystalized Task Spec
    - Architecture Foundation
    - Dependency & Interaction Contract
    - Component Contracts
    - Validation Plan
    - Completion Criteria
  - Output `done` / `repair required` with explicit repair targets and reasons.

## CLI / UX Improvements

- Flatten the CLI to one mental model: `qonqrete [task-file?]`.
- Remove user-facing `sqrapyard` concepts and `-s` dependency from the main flow.
- Operate in-place on existing git repos; do not require copying projects into a staging area manually.
- Do not require `tasq.md` naming; accept an arbitrary task file path first, richer input modes later.
- Auto-detect repo context and initialize runtime automatically; no manual `init` + `run` split in the happy path.
- Auto-detect resumable/continuable runs and prompt naturally instead of forcing separate conceptual flows for “resume” vs “finished”.
- Keep install UX dual-path:
  - fast one-liner
  - reviewable download-then-run path
- Pre-demo scope for UX:
  - one-command entry
  - task file selection
  - auto-init
  - Qrystallizer questions
  - run
  - name/result capture
- Defer deeper GitOps/CI integrations until after the demo.

## State & Persistence

- Persist all run state under `.qonqrete/` inside the target repo.
- Store:
  - task input and Qrystalized Task Spec
  - guard result and effective constraints
  - planning package
  - build reports and changed-file manifests
  - validator bundles and test results
  - Inspeqtor verdicts and repair plans
  - audit timeline and deep logs
  - resumable continuation metadata
- Treat all runs as continuable; “finished” means completed, not frozen.
- Use a stable artifact hierarchy keyed by run and component group to avoid document sprawl and recursive cycle confusion.
- Keep dependency/interactions and completion criteria stable within a run unless a repair plan explicitly updates them.

## Audit Trail Design

- Build a two-layer audit system:
  - High-level timeline for default viewing
  - Deep technical trace for debugging
- Every major event should answer:
  - what happened
  - why it happened
  - what changed
- Required high-level entries:
  - input received
  - Qrystallizer decisions and questions
  - locked assumptions
  - guard result and effective constraints
  - complexity/briq sense/execution profile selection
  - cost estimate and gates
  - component build progress
  - validator outcomes
  - Inspeqtor verdict
  - targeted repair decisions
  - final status
- Required deep-level entries:
  - prompts
  - raw model outputs
  - command/test logs
  - token/cost actuals
  - validator bundles
  - assumption details
- Make briq sense and execution-shape decisions visible in the audit trail.
- Log all fallbacks explicitly:
  - ambiguity resolved via assumption
  - simulation mode used
  - repair cap hit
  - validation bypasses or degraded capability modes

## Implementation Phases

- **Phase 1: Pre-demo critical upgrades**
  - Implement `Qrystallizer` as the new clarify/gap engine with bounded questioning and structured output.
  - Restructure the audit trail into a readable timeline plus deep trace.
  - Stabilize `Constrqutor` around component-group execution and internal mini-briqs.
  - Flatten the CLI happy path to one-command repo-local entry with task-file selection.
  - Keep execution/testing integration minimal and honest; expose simulation mode explicitly if real execution is not ready.

- **Phase 2: Planning/contract hardening**
  - Extend `Instruqtor` outputs to include Dependency & Interaction Contract, Component Contracts, Validation Plan, and Completion Criteria.
  - Add pre-build guard enrichment so effective constraints flow cleanly into planning.
  - Replace open-ended cycle semantics with bounded repair-pass semantics.

- **Phase 3: Validator architecture**
  - Expand system-level validators from syntax-only into grouped component validation and sandboxed test execution.
  - Define machine-readable validator result bundles for `Inspeqtor`.
  - Ensure no standalone Qualifier agent is introduced.

- **Phase 4: Codex-backed execution mode**
  - Add explicit Execution Mode with Codex-backed component build and test-running wrappers.
  - Keep QonQrete as the authority for scope, contracts, repair targets, and verdicts.
  - Capture Codex logs/results into the audit trail and degrade cleanly when unavailable.

- **Phase 5: Post-demo UX and GitOps expansion**
  - Improve repo bootstrap/install flow further.
  - Add richer continuation/resume UX.
  - Extend toward GitOps-ready workflows, but only after the core clarify-plan-build-validate-repair pipeline is stable.

## Assumptions

- `tasQleveler` is fully replaced by `Qrystallizer`; no hybrid long-term coexistence is planned.
- No `Qualifier` AI agent will exist; testing and local validation remain system-level.
- Local verification and test execution are allowed in controlled sandboxes even if arbitrary container execution is otherwise restricted.
- Pre-demo priority is a surgical upgrade, not a full rebuild: tighten clarify, audit, `Constrqutor`, and CLI first.
- Model support is capability-tiered rather than uniform; Simulation Mode and Execution Mode are explicit product concepts.
</proposed_plan>
