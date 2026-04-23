# 04 — Contracts

## When this runs
Once, after current-state, execution-plan, hard-ruleset, and migration-bridge
are written.

## Dependencies
Load and read ALL before producing output:
1. `{{OUTPUT_DIR}}/00-current-state.md`
2. `{{OUTPUT_DIR}}/01-execution-plan.md`
3. `{{OUTPUT_DIR}}/02-hard-ruleset.md`
4. `{{OUTPUT_DIR}}/03-migration-bridge.md`
5. The task description at `{{TASK_FILE}}`

## Inputs
- Project root: `{{PROJECT_ROOT}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary.

---

## Instructions

Produce ONE document defining the concrete contracts every component in
the target system must satisfy.

This document is the authoritative structural / behavioral glue. It
unifies what earlier docs imply but do not specify at the schema level.

### Source-of-truth rule

- Earlier docs (00-03) are authoritative. This doc refines, never
  contradicts.
- Where earlier docs are vague, this doc makes the shape concrete.
- Where earlier docs conflict, this doc lists the conflict — it does
  not silently reconcile.

### Rule: every contract is enforceable

A contract is enforceable if:
- a schema validator can check it, OR
- a type checker can check it, OR
- a test can assert it, OR
- an inspector can verify it after the fact from artifacts alone.

Anything looser than this is a guideline, not a contract, and belongs
elsewhere.

### Rule: schema versioning is mandatory

Every machine-readable artifact schema you specify MUST include a
`schema_version` field. Contracts that omit this are rejected.

### Rule: exact names from the task

Where the task specifies exact field names, exact endpoint paths, exact
file paths, exact status strings, copy them VERBATIM. Do not paraphrase.
Do not soft-normalize. Do not expand with synonyms.

---

## Required Sections

Produce the document using exactly these top-level sections, in this order.

```
# Contracts

## Purpose
One paragraph. Why this document exists separately from the ruleset and
the execution plan.

## System Relationship Model
Describe how components interact at the contract level. For each pair of
components that exchange data or control:
- what flows between them
- in what format
- under what invariants

## Component Contracts
For every significant component in the target system:

### <component-id>
- Input: exact shape, exact source
- Output: exact shape, exact sink
- Responsibilities: exact list
- MUST NOT: exact list
- Authority: what this component may decide / not decide
- Errors: how errors are represented and propagated

Repeat for every component. Do not skip any that appears in the execution
plan.

## Data Contracts
For every data model / DTO / persisted record / message payload in scope,
produce a concrete schema with `schema_version`.

Use JSON schema style where machine-readable. Use inline field-table style
where the format is not JSON.

Example format:
```json
{
  "schema_version": "1.0",
  "<model_name>": {
    "<required-field>": "<type>",
    "<optional-field>": "<type | null>"
  }
}
```

Copy field names and types verbatim from the task when provided.

## Interface Contracts
For every external interface (HTTP / CLI / library / WebSocket / message
queue):
- exact path / command / signature
- request shape (with schema_version when machine-readable)
- response shape (with schema_version when machine-readable)
- error responses and status codes
- side effects

## Artifact Contracts
For every persisted artifact this run produces or consumes:
- purpose
- required fields
- where it lives
- who writes it
- who reads it
- schema_version

## Validation Ownership Matrix
For each check the system runs, state which layer owns it:

| Check | Owner | Mechanism | Where evidence lands |
|---|---|---|---|

Checks include: syntax, tests, type, schema, policy, completion judgment.

## Responsibility Separation
Explicit boundaries:
- what the planner does / does not do
- what the builder does / does not do
- what the deterministic validator does / does not do
- what the inspector does / does not do
- what runtime orchestration does / does not do

No hidden decision-making. No cross-boundary shortcuts.

## Execution Boundaries
- what each component may do
- what each component may never do
- what no component is allowed to do (system-wide invariants)

## Inconsistencies Detected
Every inconsistency between earlier docs and the contracts you are
specifying. Do not reconcile — list.

## Open Structural Risks
Where a contract CANNOT be made fully enforceable today. Explicitly
disclose, do not paper over.
```

---

## Forbidden in this document

- rewriting the execution plan or ruleset
- defining what is to be built step by step (that's the plan)
- defining how to migrate (that's the bridge)
- aspirational contract wishes a validator cannot check
- paraphrased task requirements — copy verbatim or not at all
- meta commentary
