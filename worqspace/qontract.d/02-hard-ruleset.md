# 02 — Hard Ruleset

## When this runs
Once, after current-state and execution-plan are written.

## Dependencies
Load and read ALL before producing output:
1. `{{OUTPUT_DIR}}/00-current-state.md`
2. `{{OUTPUT_DIR}}/01-execution-plan.md`
3. The task description at `{{TASK_FILE}}`

## Inputs
- Project root: `{{PROJECT_ROOT}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary.

---

## Instructions

Produce ONE ruleset defining what MUST happen, what MUST NOT happen, what
is REQUIRED, and what is FORBIDDEN for this run.

### Source-of-truth rule

- Current-state document is the primary source of truth about the codebase.
- MAY inspect the repository to verify specific details.
- MUST NOT contradict the documented current state unless a clear
  inconsistency is found. List such inconsistencies explicitly.

### Rule: rules come from the task, not from generic AI hygiene

Most rules must be derivable from:
- explicit task constraints ("do not add authentication", "no timestamps")
- explicit task forbidden-field lists
- explicit task required-file lists
- explicit task out-of-scope clauses
- current-state constraints that must be preserved

Include generic hygiene rules only when they materially improve this
specific run.

### Rule: every rule is enforceable

A rule a deterministic validator cannot check, and a human cannot audit
after the fact, is a wish — not a rule. Rewrite it or drop it.

### Rule: explicit scope, no silent expansion

A rule that introduces a new concept not present in the task must
explicitly note this and state why.

---

## Required Sections

Produce the document using exactly these top-level sections, in this order.

```
# Hard Ruleset

## Summary
One paragraph stating what this ruleset governs. Does not restate
the task.

## Core Guardrails
Non-negotiable invariants the build MUST respect. Each is a single
declarative sentence.

## Determinism Rules
Rules that ensure the same task gives the same shape of output. Includes
rules about seeding, ordering, idempotent writes, side-effect isolation.

## Validation Rules
What deterministic validation the build MUST pass before it can be
considered complete. Includes syntax, typing, linting, tests, schema
checks, required-file existence.

## Execution Constraints
Rules about how the work is executed. Includes:
- work-unit atomicity
- no partial commits
- no silent scope expansion
- no stashed or hidden work

## Security Rules
- no hardcoded credentials
- no unsanitized user input paths
- no path traversal
- no injection vectors
- no plaintext secrets
Adapt these to the actual task. Drop those that do not apply.

## Audit & Logging Rules
- what MUST be logged
- what MUST be persisted as artifact
- what MUST NOT be logged (e.g. secrets, PII when applicable)

## Failure & Retry Rules
- how retries are counted
- when a failure is terminal
- what partial state MUST be preserved for diagnosis on failure
- what partial state MUST be cleaned up on failure

## Assumption Handling Rules
- no silent assumptions
- every chosen interpretation of an ambiguous requirement MUST be
  recorded as a written rule here with justification

## State Persistence Rules
- where runtime state MAY live
- where it MUST NOT live
- schema versioning expectations
- no hidden shadow state

## Required Files / Artifacts
Enumerate every file or artifact the completed work MUST produce.
Reference the task's "required files" section verbatim where the task
provides one. Do not invent extras.

## Forbidden Files / Artifacts
Enumerate every file or pattern that MUST NOT be produced. Includes:
- files outside the declared scope
- files violating the task's explicit forbidden list
- scratchpad, TODO-only, or placeholder files as final output
- generated artifacts accidentally committed to source

## Data Model Rules
For each data model in scope:
- required fields (exact names and types)
- forbidden fields (exact names)
- allowed value ranges / enums
Derive from the task verbatim where specified.

## Interface / API Rules
For each interface (HTTP / CLI / library):
- required endpoints / commands / functions (with exact names and shapes)
- forbidden extensions
- error-response conventions

## Naming / Path Rules
- output files live at `{{PROJECT_ROOT}}` unless task specifies otherwise
- no package prefixes that reflect the build tool's own directory layout
- imports reference files as they would be at the project root
- exact path conventions derived from the task

## Absolute Non-Requirements
Features, concepts, or behaviors explicitly OUT of scope. Derive from
the task's "do not add" section verbatim.

## Anti-Patterns
Patterns that are seductive but forbidden here. Includes:
- treating syntactically-valid trivial content as a valid implementation
- treating plan conformance as evidence of behavior
- silently reconciling contradictions instead of surfacing them
- inventing required functionality not in the task
```

---

## Forbidden in this document

- rewriting the execution plan
- introducing target-state architecture
- introducing data contracts beyond rule form (those belong to doc 04)
- recommendations, aspirations, "we should"
- rules that cannot be checked
- rules that contradict the task
