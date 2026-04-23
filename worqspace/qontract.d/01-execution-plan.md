# 01 — Execution Plan

## When this runs
Once, after the current-state document is written, before any ruleset /
contract / construction work.

## Dependencies
Load and read BOTH before producing output:
1. `{{OUTPUT_DIR}}/00-current-state.md`
2. The task description at `{{TASK_FILE}}`

## Inputs
- Project root: `{{PROJECT_ROOT}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary.

---

## Instructions

Produce ONE structured execution plan that converts the raw task into an
explicit sequence of work the construction agent can follow.

### Source-of-truth rule

- Treat the current-state document as the PRIMARY source of truth about
  the codebase.
- MAY inspect the repository to verify specific details.
- MUST NOT re-analyze or redefine the codebase from scratch.
- MUST NOT contradict the documented current state unless a clear
  inconsistency is found. If found, list it explicitly — do not silently
  correct it.

### Rule: extract signal from noise

User task input is often messy: mixed ideas, contradictions, hedges,
aspirational extras. Your job is to:
- Extract all relevant requirements.
- Remove noise that isn't a requirement.
- Resolve contradictions explicitly (state which interpretation you
  chose and why).
- Convert everything into ONE structured plan — not a discussion.

### Rule: plan covers transition, not just endpoint

The plan must describe **how we get from the current state to the task's
target outcome**, not just what the end result looks like.

- For greenfield: the plan is mostly forward-construction.
- For existing projects: the plan MUST explicitly address what to keep,
  adapt, replace, or retire.

### Rule: executable, not philosophical

Every plan item must be actionable. If you cannot describe the concrete
output of a step, the step is too vague — break it down or remove it.

---

## Required Sections

Produce the document using exactly these top-level sections, in this order.

```
# Execution Plan

## Goal
A single paragraph stating what this plan exists to accomplish. Derived
from the task. No hedging.

## Scope
- in scope (explicit list)
- out of scope (explicit list)
- deferred to later runs, if any

## Core Principles
Non-negotiable principles that govern ALL plan items. Derived from the
task and from constraints implied by the current state.

## System Architecture
The intended architecture at the end of this run. Component-level, not
code-level. Name every significant component and state its role in a
sentence or two.

## Component Responsibilities
For each significant component:
- id / name
- input
- output
- responsibilities
- what it MUST NOT do
- dependencies on other components

## Execution Flow (intended)
- the control flow of the target system
- the data flow of the target system
- where validation / guardrails are placed
- where observability is placed

## Build Strategy
- how the work is ordered (dependency-first, risk-first, skeleton-first, etc.)
- what is built in what order
- what is deliberately deferred
- where the work can be parallelized vs must be sequential

## Validation Strategy
- deterministic checks the construction agent MUST pass (syntax, tests,
  lints, type checks, schema validation)
- AI-based checks, if any
- what is checked per work unit vs per run

## State & Persistence Strategy
- where state lives at runtime
- schema versioning rules (if applicable)
- migration / backfill strategy (if applicable)

## CLI / UX / API Surface
- exact commands / endpoints / library entry points the user will interact with
- input format
- output format
- error behavior

## Audit & Logging Strategy
- what is logged
- what is persisted as artifact
- what remains ephemeral

## Implementation Phases
Ordered, bounded phases. For each phase:
- goal
- scope
- dependencies (including which prior phase must be green)
- success criteria
- what is deliberately NOT changed yet

## Open Questions
Questions the plan cannot answer with the inputs given. Mark each one as
- BLOCKING (plan cannot be executed safely without resolution), or
- NON-BLOCKING (plan proceeds, resolution improves outcome)

## Inconsistencies Detected
Every inconsistency between task, current state, and plan. Do not silently
reconcile — list them here.
```

---

## Forbidden in this document

- file-level code diffs
- actual code
- the full target-state description (that belongs to doc 05)
- the full ruleset (that belongs to doc 02)
- the full data contracts (that belongs to doc 04)
- rewriting of the current state
- meta commentary, planning about planning
- "assumptions:" sections (assumptions that affect the plan belong in
  Open Questions with a chosen interpretation stated)
