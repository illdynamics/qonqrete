# 05 — Target State

## When this runs
Once, after all prior docs are written. This is the final run-start doc.

## Dependencies
Load and read ALL before producing output:
1. `{{OUTPUT_DIR}}/00-current-state.md`
2. `{{OUTPUT_DIR}}/01-execution-plan.md`
3. `{{OUTPUT_DIR}}/02-hard-ruleset.md`
4. `{{OUTPUT_DIR}}/03-migration-bridge.md`
5. `{{OUTPUT_DIR}}/04-contracts.md`
6. The task description at `{{TASK_FILE}}`

## Inputs
- Project root: `{{PROJECT_ROOT}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary.

---

## Instructions

Produce ONE document describing the system **when the task is fully and
correctly completed**. This is the reference the inspector and any
completion gate compares reality against.

### Source-of-truth rule

- Earlier docs (00-04) are authoritative. This doc is their integrated
  endpoint view.
- Where earlier docs conflict, list the conflict — do not reconcile.
- Do not introduce architecture, components, or contracts that aren't
  in earlier docs.

### Rule: describe the DONE state, not the journey

Describe the system as if it is already fully built and running. Not
"we will add ...", not "next we need to ...". Just: how the system is.

### Rule: completion is falsifiable

Every claim in this document must be something an inspector can either
confirm or refute from artifacts. If a claim is not checkable, it is a
marketing statement — rewrite it or remove it.

### Rule: transitional behaviors do not belong here

Anything that exists only during migration, bootstrapping, or the build
process itself does NOT belong in the target state. Target state is the
steady-state system, not the construction scaffolding.

---

## Required Sections

Produce the document using exactly these top-level sections, in this order.

```
# Target State

## System Overview
- what the system does, in one paragraph
- who uses it / what invokes it
- core philosophy (3-7 principles, derived from the execution plan)

## Architecture
- component-level picture of the final system
- how control flows
- how data flows
- where boundaries sit

## Components
For each significant component, one subsection with:
- id / name
- role in the final system
- interfaces it exposes
- interfaces it depends on
- runtime characteristics

## Execution Model
- canonical flow from input to output
- where work is sequential vs parallel
- where retries happen
- what is bounded vs unbounded
- terminal states

## Data & Artifact Model
- data models in use (reference doc 04 by name)
- persistence locations
- retention / lifecycle of each artifact
- schema versioning posture

## State & Persistence Model
- where runtime state lives
- how state transitions happen
- continuation / resume model, if relevant
- transaction / consistency model

## Validation & Testing Model
- deterministic checks in place
- test layers in place
- what evidence a completed run produces
- what the bar for "done" is

## Observability Model
- logging
- metrics
- tracing
- audit artifacts
- what a human operator sees when things go wrong

## Interface Surface
Every externally-visible surface of the system:
- HTTP endpoints
- CLI commands
- library entry points
- events / messages
- with exact shapes (reference doc 04 for schemas)

## Developer / Operator Experience
- how the system is deployed / run
- how a developer extends it safely
- what the feedback loop looks like
- predictable vs surprising behaviors

## Security Model
- trust boundaries
- secret handling
- input validation posture
- known-unknown threats that are out of scope

## Performance Characteristics
- expected throughput / latency / cost envelopes
- known bottlenecks
- scaling posture

## System Qualities
Concrete claims about: determinism, reliability, explainability,
composability, auditability, extensibility. Each claim must be
checkable — no vibes.

## Explicit Non-Goals
Things the system deliberately does NOT do. Copy from execution plan's
out-of-scope + any non-goals surfaced in the ruleset.

## Completion Criteria
Enumerated, checkable conditions that together mean this run is done.
The inspector evaluates exactly these.

## Inconsistencies Detected
Every inconsistency between earlier docs and this target-state
integration. List — do not reconcile.
```

---

## Forbidden in this document

- "we plan to ...", "next step ...", "in a future release ..."
- migration-era compatibility scaffolding
- aspirational marketing ("highly scalable", "robust", "enterprise-grade")
  without a checkable definition
- architecture not derived from earlier docs
- completion criteria a validator or inspector cannot check
- meta commentary
