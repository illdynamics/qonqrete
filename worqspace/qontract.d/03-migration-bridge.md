# 03 — Migration Bridge

## When this runs
Once, after current-state, execution-plan, and hard-ruleset are written.

## Dependencies
Load and read ALL before producing output:
1. `{{OUTPUT_DIR}}/00-current-state.md`
2. `{{OUTPUT_DIR}}/01-execution-plan.md`
3. `{{OUTPUT_DIR}}/02-hard-ruleset.md`
4. The task description at `{{TASK_FILE}}`

## Inputs
- Project root: `{{PROJECT_ROOT}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary.

---

## Greenfield fast path

If the current-state document declares `project kind: greenfield`, produce
a minimal document:

```
# Migration Bridge

## Nature
Greenfield construction. No prior code to migrate.

## Forward Construction Order
<ordered list of implementation phases from the execution plan, one line each>

## Risk Notes
<any forward-construction risks identified in the execution plan>
```

Do NOT pad. Do NOT invent a current state that does not exist.
STOP after writing this.

---

## Existing-project path

If the current-state document declares `project kind: existing` or
`partially-seeded`, produce the full document below.

### Source-of-truth rule

- Current-state document is the primary source of truth about the codebase.
- Execution-plan document is the primary source of truth about intent.
- Hard-ruleset is the primary source of truth about constraints.
- Do NOT re-analyze the codebase from scratch.
- Do NOT contradict earlier docs unless a clear inconsistency exists.
- Inconsistencies must be listed explicitly.

### Rule: bridge, not rewrite

This document maps CURRENT → TARGET for every meaningful component, file,
or subsystem. It does NOT redefine either end.

### Rule: actionable transition verbs

Every row of the migration truth table uses exactly one of:

- **KEEP** — unchanged in target state
- **ADAPT** — same role, modified behavior or interface
- **REPLACE** — different implementation serving the same role
- **RETIRE** — removed entirely
- **SPLIT** — one component becomes multiple
- **MERGE** — multiple components collapse into one

Mixed or ambiguous verbs are not allowed.

---

## Required Sections (existing-project path)

```
# Migration Bridge

## Purpose
One paragraph. What this document is and why it exists separately from the
execution plan.

## Migration Summary
Concise paragraph describing the architecture transition from current to
target.

## Current-to-Target Transition Overview
- current operating model (derived from doc 00)
- target operating model (derived from doc 01)
- biggest deltas (3-7 bullets)
- highest-risk transitions (3-7 bullets)

## Migration Truth Table
Structured table with one row per significant module / component / artifact
/ flow. Every row includes:

| Current Component | Current Role | Target Role | Action | Prerequisite | Notes | Done Criteria |
|---|---|---|---|---|---|---|

Cover every significant item from the current-state inventory. Leave
nothing unaddressed.

## Transition Lifecycle
The explicit step-by-step order in which the migration proceeds. Each
step states:
- what is changed
- what is preserved
- what MUST be validated before moving to the next step

## State Migration Design
- where runtime state lives today
- where runtime state lives in the target
- how existing data is migrated, backfilled, or discarded
- what remains source-of-truth during transition
- compatibility / precedence rules when old and new coexist temporarily

## Interface / API Migration
- which interfaces break
- which are preserved
- which are versioned side-by-side
- deprecation notices required

## Transaction / Rollback Strategy
- how partial failures are detected
- what is rolled back on failure
- what is preserved for diagnosis
- how the target ends up recoverable

## Migration Phases
Ordered phases. For each phase:
- goal
- scope
- why this order
- dependencies
- success criteria
- what NOT to change yet

## Transition Risks
Specific risks of this migration. Includes data loss, downtime,
compatibility breaks, semantic drift.

## Non-Goals During Migration
Things that will NOT be attempted during this run. Derived from execution
plan's out-of-scope list, extended with migration-specific non-goals.

## Readiness Criteria
How we know the migration is sufficiently complete for this run. Concrete
checks, not vibes.

## Inconsistencies Detected
Every inconsistency between current-state, execution-plan, ruleset, and
this bridge. List — do not reconcile.
```

---

## Forbidden in this document

- redefining current state
- redefining target state
- introducing new architecture not in the execution plan
- inventing migrations the task does not require
- optimistic "it will all be fine" language
- meta commentary
