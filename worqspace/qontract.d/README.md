# Run-start scaffolding prompts

Six generalized prompts that a planner/instructor agent runs **once per run at run start**
to produce authoritative guidance docs for every subsequent agent in the pipeline
(builder / deterministic validator / inspector / repair planner).

All QonQrete-specific terminology has been stripped. These work for any system / any
task, greenfield or existing project.

## The six docs

| # | Doc | Purpose | Greenfield path |
|---|---|---|---|
| 00 | Current Project State | Deep inspection of whatever is in the project root right now | Declares greenfield, lists any existing config/README |
| 01 | Execution Plan | Structured plan converting task → ordered work | Forward-construction plan |
| 02 | Hard Ruleset | MUST / MUST NOT / REQUIRED / FORBIDDEN rules | Unchanged — rules apply regardless |
| 03 | Migration Bridge | Current→target transition map | **Fast-path mini doc** — no migration needed |
| 04 | Contracts | Schemas, interfaces, component contracts | Unchanged |
| 05 | Target State | Final "when done" spec | Unchanged |

## Dependency chain

Each doc reads all prior docs before producing output. The chain is strict:

```
00 ── 01 ── 02 ── 03 ── 04 ── 05
              └── task file ──┘ (every doc also reads the task)
```

## Template variables

Every prompt expects these placeholders to be replaced before the prompt is sent
to the model:

- `{{PROJECT_ROOT}}` — absolute path to the project root being built
- `{{TASK_FILE}}` — absolute path to the task description file
- `{{OUTPUT_DIR}}` — directory where the docs are written (e.g. `struqture/`)
- `{{OUTPUT_PATH}}` — absolute path to this specific doc's output file

## Recommended scale-gating

Do not run all six for every task. Rough guide:

| Task complexity | Docs generated |
|---|---|
| Small (single file, <200 LoC, no contracts) | Skip entirely — direct build |
| Medium (multi-file, single domain, contracts implicit) | 00 + 01 + 05 (3 docs) |
| Big (multi-file, strict contracts, forbidden fields, multiple components) | All 6 |

For QonQrete specifically: gate on `briq-sensitivity` level — e.g. >=4 → run the
medium set, >=11 → run the full set.

## Once per run, not per cycle

These docs are written once at run start and persisted in the run workspace.
Every subsequent cycle, briq, and repair pass reads them rather than regenerating.

Cost posture:
- small task: 0 extra AI calls
- medium task: +3 AI calls at run start, amortized across all briqs
- big task: +6 AI calls at run start, amortized across all briqs

## Format contract every prompt follows

1. Single-stage — each prompt produces its doc directly, no "plan mode / execution mode" split.
2. Output is the full document content only. No preamble. No surrounding markdown fences.
3. Required sections are listed verbatim in each prompt. The model reproduces those
   headings exactly, in order.
4. Forbidden content is listed in each prompt. Anything in that list must not appear
   in the output.
5. Explicit handling for greenfield vs existing projects, so doc 00 is honest on
   day-one runs.

## What this solves (specific bugs addressed)

From the v1.3.13 big-tasq post-mortem:

- **B2 import hallucination** — doc 00 declares that the project root IS the working
  dir; doc 02 names a Naming / Path Rule; doc 05 fixes the interface surface. Model
  can no longer infer `from <workdir-name> import …` — the three layers rule it out.
- **Field-level contract violations** (adding forbidden `created_at` / `timestamp`) — doc 02
  lists Data Model Rules verbatim from the task; doc 04 pins exact schemas with forbidden fields.
- **Target-file extraction gaps** — doc 02 Required Files / Forbidden Files sections are
  authoritative; the builder can compare its output set against them directly.

What this does NOT solve:

- **B1 retry budget** — that's a config.yaml value, not a prompt issue.
- **Qonfirmer feedback fidelity** — that's runtime wiring.
- **Planning-call bloat for small tasks** — that's why the scale-gating above exists.

## Generalization notes

- Terminology replaced:
  - Qrystallizer / InstruQtor / ConstruQtor / InspeQtor → planner / builder / inspector (or whatever the host system's agent names are)
  - tasQleveler → (removed — legacy concept)
  - `.qonqrete/` → output dir (templatized)
  - `qage` → run workspace
  - `briq` → work unit
  - `struqture` → output dir (templatized)
- The realization-layer doc from the original 7-prompt set was dropped. Realization
  is a runtime concern (how does the system track what actually happened) — it is
  not a per-task guidance artifact the instructor writes at run start. Keep it in
  the runtime, not in this bundle.
- The "PLAN MODE / EXECUTION MODE" two-stage framing was dropped. Single-stage
  prompts that produce their final output directly.

## File list

```
prompts/
  00-current-state.md
  01-execution-plan.md
  02-hard-ruleset.md
  03-migration-bridge.md
  04-contracts.md
  05-target-state.md
README.md
```
