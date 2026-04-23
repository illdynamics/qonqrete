# 00 — Current Project State

## When this runs
Once, at the very start of a run, before any planning or construction.

## Dependencies
None. This is the first document of the run.

## Inputs
- Project root: `{{PROJECT_ROOT}}`
- Task description file: `{{TASK_FILE}}`

## Output
Write this document to `{{OUTPUT_PATH}}`.

Write the full document content only. No preamble. No meta commentary. No
surrounding markdown fences. The runtime persists your output verbatim.

---

## Instructions

Produce ONE authoritative document describing the **current observed state**
of the project root, before any changes are made.

### Rule: describe what IS, not what SHOULD BE

- Never silently correct contradictions. Record them explicitly.
- Never invent architecture that isn't there.
- Never assume the documented description and the code agree — check both.
- If `README.md` / comments / docstrings disagree with the code, record the
  divergence. Do not average them into a flattering narrative.

### Rule: handle greenfield and existing projects both

**If the project root contains no source files (or only the task
description and a handful of config files):**
- State clearly: "Greenfield project — no prior code."
- List any files that DO exist (config, `README.md`, `.gitignore`, lockfiles, etc.) — do not skip them.
- Remaining sections may be short, but produce every required section.
- Do not fabricate missing architecture.

**If the project root contains non-trivial prior code:**
- Deep-inspect. Sample representative files across every significant
  directory. Do not rely on filenames alone.
- Identify languages, frameworks, build systems, entry points, test tooling.
- Map module structure and the responsibilities of each module.
- Describe observed execution / data / control flow as OBSERVED, not as
  intended.
- Note all inconsistencies explicitly.

### Rule: do not plan, judge, or rewrite

This document is analysis only. No recommendations. No "should be". No
patch suggestions. That belongs to later documents.

---

## Required Sections

Produce the document using exactly these top-level sections, in this order.
Keep them in the document even when short or empty — use "None observed"
or an equivalent honest phrase.

```
# Current Project State

## Snapshot
- project kind: greenfield | existing | partially-seeded
- primary language(s)
- primary framework(s) / runtime(s)
- top-level entry point(s)
- top-level test command(s), if observable
- top-level build command(s), if observable
- package / dependency manifest file(s), if present

## File / Module Inventory
For each significant directory and top-level file:
- path
- apparent responsibility
- lines / size if relevant
- anything explicitly marked deprecated, TODO, or WIP

## Execution Flow (as observed)
- how the project runs today
- observed control flow between modules
- observed data flow between modules
- for services: entry point → route / handler → storage → response path

## State & Persistence
- where runtime state lives (memory, disk, database, external service)
- observed schema versioning, if any
- observed migration tooling, if any

## Validation & Guardrails (existing)
- linters, formatters, type checkers currently wired in
- test layers present (unit / integration / e2e / snapshot / property)
- pre-commit hooks, CI workflows, or equivalent
- deterministic checks vs AI-based checks, if distinguishable

## Dependencies
- third-party runtime dependencies declared
- third-party dev dependencies declared
- dependencies used but not declared, if observable
- pinning strategy (exact / range / none), if observable
- licensing concerns noted, if surfaced

## Interfaces / Contracts Observed
- HTTP endpoints, if any
- CLI commands and flags, if any
- library public surface, if any
- data schemas / DTOs in use
- contract versioning, if any

## Inconsistencies & Divergence
- code vs README divergence
- code vs tests divergence
- code vs declared dependencies divergence
- module-to-module contract mismatches
- explicit contradictions between files or sections

## Gaps Observed
- areas with no test coverage
- entry points with no validation
- undocumented public interfaces
- dead code or orphan files, if visible

## Strengths
What the current state gets right. Be concrete — no vague praise.

## Weaknesses
What the current state gets wrong or where it is weak. Be concrete.

## Risks
Specific risks a downstream planner must know about before building on this
system. Include migration risk, data-loss risk, breaking-change risk,
dependency risk, architectural coupling risk.

## Observations
Anything else that does not fit above but a downstream agent must know.
```

---

## Forbidden in this document

- recommendations, "should", "we need to"
- migration plans, patch plans, fix plans
- target-state descriptions
- judgment on whether the current state is acceptable
- optimistic or marketing-style summaries
- assumption sections
- meta commentary about the analysis itself
