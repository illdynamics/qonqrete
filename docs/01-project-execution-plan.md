# QonQrete Execution Plan

## Core Principles
QonQrete should operate as a structured software realization system, not as a loose chain of prompts. The system must separate intent clarification, planning, construction, validation, realization, and judgment into distinct responsibilities with explicit artifacts between them.

The design should prioritize bounded execution over open-ended looping. The default path should be one clarified task, one planned build, one main construction pass, system-level validation, one realization pass, and bounded targeted repair passes only when evidence justifies them.

Every major claim must be evidence-backed. Planning artifacts describe intent, realization artifacts describe what actually happened, and inspection artifacts judge the gap between the two. These layers must remain separate.

Language-agnostic claims must be honest. Universal workflow support is acceptable; universal validation rigor is not. Capability strength must be disclosed per mode and per ecosystem.

Local verification is a system responsibility, not an AI responsibility. AI may request, interpret, or summarize validation, but deterministic checks and test execution must be treated as non-AI system functions.

## System Architecture
The target architecture should retain the current qage-centered, file-backed runtime model, but reorganize execution around cleaner contracts and stage boundaries. The intended runtime is a host CLI that creates and manages run state, an orchestrator that executes a bounded stage pipeline, AI agents that produce planning and judgment artifacts, and system-level validators and executors that touch the filesystem, run commands, and collect evidence.

The architecture should move from the current tasQleveler-first model to a Qrystallizer-first model. Qrystallizer becomes the only task-clarification stage and produces a structured execution-ready specification. instruQtor consumes that specification and produces the implementation plan and briq decomposition. construQtor performs the build against explicit scope. System validators execute deterministic checks and tests. A realization layer records what changed and what behavior was observed. inspeQtor then judges results against intent and evidence.

The system should preserve the existing strengths of qage-local state, resumability, artifact traceability, and containerized isolation, while correcting current weaknesses around partial writes, stale stage ordering, fragmented audit data, and Python-skewed validation claims.

Inconsistencies to carry forward explicitly:
- Current codebase has `tasqleveler`; the target architecture replaces it with `Qrystallizer`.
- No `Qualifier` agent exists and none should be required in this plan; validation remains system-level.
- Current runtime places realization-like artifacts inside construQtor and review inside inspeQtor; the target design separates realization from judgment.

## Agent Responsibilities
- `Qrystallizer (future)`: Replace tasQleveler as the only task-clarification stage. It should read the raw task, detect ambiguity, ask only a small number of high-impact clarification questions when needed, convert unresolved ambiguity into explicit assumptions, and emit a structured Qrystalized Task Spec with a readiness result such as ready versus not ready. It should not generate code, briqs, or judgments. It should not own testing. It should be allowed to stop execution when the task is too underspecified to build responsibly.

- `instruQtor`: Consume the Qrystalized Task Spec and produce the implementation blueprint. Its outputs should include system-level intent, proposed build scope, component decomposition, briqs or equivalent execution units, dependency ordering, validation intent, and any declared invariants or constraints that later stages must honor. It should not clarify the task interactively once Qrystallizer has finished. It should not inspect final quality.

- `construQtor`: Execute the build plan and apply scoped changes. Its responsibility is realization of intended modifications, not final judgment. It may use Codex or another execution-capable engine for file edits and command execution, but it must operate within explicit scope, record attempted actions, and write into controlled staging/persistence boundaries. It should emit build and action artifacts, not verdicts.

- `inspeQtor`: Judge outcomes after validation and realization artifacts exist. It should compare intended results against observed results, evaluate remaining gaps, classify success versus partial versus failure, and define repair targets when bounded repair is justified. It should consume evidence; it should not be the source of evidence. It should not be responsible for deterministic validation execution.

- `system-level validators (non-AI)`: Execute syntax checks, builds, tests, linters, static analysis, contract checks, and other deterministic environment-bound verification. These validators are not agents in the conversational sense. They should emit machine-readable and human-readable evidence bundles that other stages consume. They should remain the authority for local validation results.

## Execution Flow
The intended execution flow should be:

1. Intake the raw task and create a run manifest.
2. Run Qrystallizer to produce a Qrystalized Task Spec or stop with unresolved blockers.
3. Run instruQtor to produce the implementation plan, build scope, and execution units.
4. Run construQtor to apply changes within an explicit write boundary and produce construction artifacts.
5. Run system-level validation to execute deterministic checks and tests against the constructed result.
6. Run an explicit observe/realization step that records what actually happened before any judgment is allowed.
7. Run inspeQtor to judge intent versus evidence and either conclude or issue bounded repair targets.
8. If repair is justified, run only targeted repair passes with the same validation and realization requirements.
9. Finalize the run manifest, audit trail, and resumable state.

The observe/realization step must exist between validation and inspection. It should gather changed-file evidence, command outcomes, validation outputs, runtime behavior signals, generated artifacts, scope deltas, and impact summaries. inspeQtor must consume this material rather than inferring execution reality indirectly from prompts or partial logs.

Planning intent and observed execution reality must remain distinct. Qrystallizer and instruQtor define what should happen. construQtor and validators produce what did happen. Realization records the difference without judging it. inspeQtor judges that difference afterward.

Artifacts that must exist before judgment is allowed:
- Qrystalized Task Spec
- implementation blueprint and execution units
- construction action report
- system validation result bundle
- realization bundle with changed files, scope evidence, and observed outcomes

This resolves a key design contradiction in the conversation: the system should not treat iterative replanning as the default execution model. The intended model is one planned pass plus bounded evidence-driven repair.

## Codex Integration Strategy
Codex should be integrated where touching reality matters most: code edits, command execution, and system-level testing workflows. It should not be the core decision-maker for task clarification or execution governance.

Qrystallizer, instruQtor, and inspeQtor should remain model-agnostic AI roles that can run on general reasoning models. construQtor should support an execution-capable backend, with Codex as the preferred strong mode when available. System-level validation remains outside AI ownership, though Codex may invoke it or react to its outputs.

The system should expose capability modes honestly. A Codex-backed execution mode may support stronger scoped edits, richer repair loops, and tighter command/test integration. A non-Codex mode may still support planning and limited construction, but must be labeled as weaker where execution fidelity or validation integration is reduced.

Codex should be positioned as the engine that executes within scope, while QonQrete remains the system that decides scope, stage boundaries, artifact contracts, and judgment rules.

## Validation Strategy
Local validation must be system-level and deterministic. It should cover syntax, parseability, buildability, test execution, contract checks, static analysis, and environment-bound verification where available. The validation layer should run as commands or tools in the execution environment and emit structured evidence. It should be capable of being stronger for some languages than others, but it must always report exactly what was and was not checked.

AI validation should be judgmental and interpretive, not authoritative over deterministic facts. AI may reason about architectural coherence, missing edge cases, risk concentration, scope mismatch, or likely defects not covered by tests. AI may request further validation or recommend repairs. AI should not override failing deterministic evidence.

Validation outputs should be grouped by level:
- universal checks that apply regardless of language or stack
- language-specific deterministic checks
- project-specific checks declared by the task or repository
- AI review findings that interpret residual risk

This resolves another conversation-level contradiction: there is no separate Qualifier agent in the intended architecture. Deterministic validation remains a system function, and AI review remains inspection.

## Result / Realization Layer
The realization layer should be a first-class stage whose job is to describe outcomes without passing judgment.

It should capture structural outcomes such as created files, modified files, deleted files, write scope, generated artifacts, unresolved partial outputs, and whether changes stayed within declared boundaries.

It should capture behavioral outcomes such as test results, command exit states, runtime observations, build success or failure, service startup behavior, and any observed deviations from expected operation.

It should capture system impact outcomes such as dependency changes, configuration changes, schema changes, interface changes, persistence changes, migration implications, and operational side effects.

It should capture changed files and scope evidence in a machine-readable form and a compressed human-readable summary. The evidence should make it clear what was intended to change, what actually changed, and what fell outside scope.

It should explicitly distinguish intended outcomes from actual outcomes. If the plan targeted three components and five files changed outside that intended scope, realization must record that before inspection evaluates whether it is acceptable.

Realization must feed judgment without merging with it. inspeQtor should consume realization artifacts as evidence, not overwrite or collapse them into a verdict-only summary.

## CLI / UX Improvements
The CLI should move toward a simpler task-first experience. The system should support direct task input without forcing a specific `tasq.md` ritual as the long-term primary interface, while still supporting file-based workflows.

User-facing flow should reduce configuration burden. The preferred mode is minimal setup: choose models or execution backends, provide the task, review any Qrystallizer questions, then run. Complexity estimation, briq sensitivity, and repair-budget decisions should default to automatic bounded policies and be surfaced as explicit run decisions rather than hidden internals.

The CLI should make stage progress legible at the level of intent, build, validation, realization, and judgment. Users should be able to see what the system is doing, what artifacts exist, what confidence level applies, and whether the system is in initial pass or targeted repair.

The `sqrapyard` concept should be de-emphasized or renamed in user-facing UX. Seeded workspace behavior may remain technically useful, but it should not define the mental model of the product.

Resume should be natural and evidence-based. Users should be able to resume a failed or partial run with clear visibility into prior artifacts, repair targets, and remaining scope.

## State & Persistence
The qage should remain the primary persistence boundary. Each run should keep all task, plan, build, validation, realization, inspection, and audit artifacts together in a resumable directory.

State should be organized around stable artifact domains rather than stage-specific ad hoc files. The minimum persistent domains are task specification, implementation plan, build actions, validation results, realization evidence, inspection verdicts, logs, and run manifest metadata.

The system should preserve resumability by snapshotting or versioning state at meaningful boundaries rather than only copying the entire qage after the fact. Resume should understand stage completion, pending repair targets, and prior evidence.

Manifest-driven persistence should become the source of truth for run state. The manifest should record stage entries, stage exits, artifact locations, scope declarations, validation coverage, capability mode, and final disposition without requiring users to reconstruct state from scattered logs.

## Audit Trail Design
The audit trail should become a coherent run narrative rather than a pile of unrelated files. Every stage should emit a concise structured event stream plus any rich artifacts it produces.

The top-level audit should show a compressed timeline: task intake, task clarification, plan creation, construction start and finish, validation start and finish, realization recorded, inspection verdict, repair passes if any, and final completion state.

Each stage should have a stable event schema with timestamps, stage identity, capability mode, inputs consumed, outputs produced, commands executed, scope touched, and status. Rich artifacts such as test bundles or review reports should be linked from the audit trail rather than duplicated into it.

The audit design should explicitly support diagnosis of partial writes, validation gaps, and capability-mode limitations. If deterministic validation was unavailable for a language or stack, that disclosure should be present in the audit trail, not buried in a comment.

Existing fragmented logs, exeQ summaries, reqaps, and cache metadata provide useful precedent, but they should be consolidated under a manifest-linked audit system.

## Stage / Lifecycle Direction
The intended phase model should be:
1. intake
2. task clarification
3. planning
4. construction
5. validation
6. realization
7. inspection
8. bounded repair when needed
9. finalize

The intended stage progression direction should be forward-moving and evidence-gated. A later stage should not proceed without the required artifacts from the prior stage. Repair should re-enter at the smallest justified point rather than restarting the whole flow by default.

The intended final lifecycle shape, before a canonical registry is formalized, should distinguish at least these concepts: created, clarifying, ready, blocked, planning, building, validating, realizing, inspecting, repairing, completed, partial, failed, and aborted. These are directionally correct lifecycle concepts, not a final canonical enum set.

The intended run trace and manifest direction should encode stage order, stage status, evidence presence, capability mode, repair count, scope declaration, and final disposition. The manifest should reflect actual execution, not only intended configuration.

Explicit inconsistency to preserve:
- Current runtime and docs disagree about stage ordering. The intended direction is not to normalize those mismatches silently, but to move to an evidence-gated sequence where realization exists before inspection judgment.

## Transaction Safety Direction
Safe writes should become an explicit design requirement. construQtor should write through scoped staging or atomic file replacement rather than directly mutating persistent state without recovery boundaries.

Partial failures should be treated as first-class outcomes. If a construction or repair pass fails mid-scope, the system should preserve evidence of attempted writes, identify committed versus uncommitted changes, and avoid pretending the workspace is clean.

Rollback does not need to mean global magic undo, but the system should support at least one of these reliable recovery behaviors: staged commit on success, per-scope rollback on failure, or durable snapshotting before mutation with explicit resume/recover semantics. The current no-rollback state should not remain the target.

Build scope and persisted evidence must stay aligned. If a stage was authorized to touch a defined scope, realization and audit artifacts should prove what was touched, what was withheld, what failed, and what remained pending. Persisted evidence must make partial state diagnosable without guesswork.

## Language / Ecosystem Capability Direction
The system should describe itself honestly as workflow-universal but validation-strength-variable. QonQrete can provide a common architecture across ecosystems without claiming equal deterministic depth everywhere on day one.

Universal validation should include scope enforcement, artifact completeness, command/result capture, changed-file evidence, manifest integrity, and explicit disclosure of validation coverage. These are cross-language responsibilities.

Language-specific validation may remain stronger initially for ecosystems with mature deterministic tooling integration. Python is the current strongest example in the existing system, and similar strength should be added incrementally for other ecosystems rather than implied prematurely.

Weaker capability modes must be disclosed plainly. If a stack lacks deterministic compile/test integration, the system should say that validation was limited, identify which checks were not performed, and reduce implied confidence accordingly. AI review may supplement weak deterministic coverage, but it must not be presented as equivalent.

Explicit inconsistency to preserve:
- The current implementation has materially stronger deterministic support for Python than for other ecosystems. The future plan should improve this, but it must not describe the current or near-term system as uniformly validated across languages.

## Implementation Phases
Phase 1 should establish the new execution contract without requiring a full engine rewrite. Replace tasQleveler conceptually with Qrystallizer, define the Qrystalized Task Spec, define implementation-plan, validation-bundle, realization-bundle, and inspection-verdict artifacts, and enforce the new stage order at the orchestration level.

Phase 2 should separate realization from inspection in the runtime. construQtor should emit construction reports only, system validators should emit deterministic evidence bundles, and a dedicated realization step should assemble structural, behavioral, and impact evidence before inspeQtor runs.

Phase 3 should harden transaction and audit behavior. Introduce scoped safe-write strategy, manifest-linked stage events, partial-failure traceability, resume-aware recovery metadata, and clearer final lifecycle reporting.

Phase 4 should integrate stronger execution backends and broader validation coverage. Codex-backed construction and repair should become the preferred strong mode, while additional deterministic validators for non-Python ecosystems are added incrementally with explicit capability disclosure.

Phase 5 should simplify user experience. Reduce required configuration, surface automatic bounded decisions clearly, improve resume flows, and converge the CLI on a task-first experience with clear stage visibility and honest capability reporting.
