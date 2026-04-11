# Remaining-Issues Analysis

## Overall status estimate

QonQrete is `mostly complete in code, not yet truthfully final-state aligned in runtime reality`.

Roughly:
- architecture migration: `~80%`
- truth/audit alignment: `~65%`
- finish-on-harder-task continuation proof: `not yet proven`

The strongest real progress is live on `2026-04-10`: Qrystallizer aliasing, guard-before-planning, manifest-linked repair routing, and staged build attempts are real.

The biggest remaining gap is that final-state claims still outrun runtime truth in four places:
- canonical state root
- stage authority
- evidence semantics
- beefier-task completion quality

## Top remaining blockers

### Truth-critical

- `.qonqrete` is still mostly a compatibility shell over `worqspace/qage_*`, not a truly independent canonical run-root.
  - Evidence: `.qonqrete/runs/*` are symlinks into `.qonqrete/worqspace/qage_*`; manifests and artifacts still live in qage roots.

- Qrystallizer is real, but canonical intake still flows through the `tasqleveler` alias and qage-era task files.
  - This is compatibility-mediated authority, not clean final-state authority.

- Validation and realization are not first-class runtime stages.
  - In proof qage `qage_20260410_235023`, manifest stage records are `INTAKE, CLARIFICATION, GUARD, PLANNING, ESTIMATION, BUILD, INSPECTION, ...`, with no separate `VALIDATION` or `REALIZATION` stage records.
  - Those bundles are still produced inside `inspeqtor.py`.

- Evidence semantics are still too optimistic.
  - The `2026-04-10` repair-continuation proof run marked `validation_execution_mode: STATIC_ONLY` and `evidence_status: EVIDENCE_COMPLETE` even though:
    - no executed test runner exists
    - non-Python deterministic validation was effectively near-zero
    - the resulting app was still broken
  - That is not final-state truthful evidence accounting.

- Run lineage metadata is wrong inside canonical artifacts.
  - In the latest proof artifacts, `run_id` / `source_run_id` are `"qonq"` instead of the actual run id `qage_20260410_235023`.
  - That weakens manifest, repair-plan, and continuation truth.

### Completion-critical

- The beefier-task failure is mainly not a routing failure; it is a build-quality plus targeting failure.
  - For `tasq-live-prove-run-04.md`, bounded repair routing worked, but the app still ended `RUN_PARTIAL` because:
    - planning split the task into only 2 coarse briqs
    - non-Python validation did not prove behavior
    - inspection/repair targeting stayed broad
    - HTML/JS contract mismatches remained unfixed (`recipe-ingredients` / `recipe-steps` / `recipe-category` expected by `app.js`, but `index.html` used `ingredients` / `steps` / `category`)

### Proof-critical

- `docs/10-live-repair-continuation-proof-report.md` overstates repo-root proof.
  - Current `qonqrete.sh` syncs qage outputs back to repo root only for `RUN_COMPLETED`.
  - The final partial proof run `qage_20260410_235023` was `RUN_PARTIAL`, and the current root files do not match that qage; they match earlier `qage_20260410_193035`.
  - Repo-root file presence is therefore not valid proof of the latest partial run’s export path.

- `docs/05d-live-proof-rerun-fix-report.md` is not final-state proof.
  - Its “successful bounded completion” qage `qage_20260410_182545` finalized `RUN_COMPLETED`, but its inspection verdict is still `PARTIAL` with `repair_required: true` and no repair-plan artifact.
  - That historical proof cannot be treated as final-state-aligned evidence.

## What is not a major blocker

- Guard-before-planning is real in runtime order.
- Scoped staged attempts and recovery metadata are real in current code and in the `2026-04-10` repair proof qage.
- Legacy `reqap -> next tasq` is no longer the default canonical continuation path; it is mostly compatibility-only now.

## Cleanup-only / drift

- README, docs, VS Code, and IntelliJ surfaces still carry substantial `tasq.md`, `worqspace/tasq.md`, and `sqrapyard` language.
- Some docs still present qage paths as the normal visible runtime shape.
- `docs/02-final-report.md` contains links to another workspace path.
- `docs/00-project-current-state.md` is materially stale relative to the live repo.

These are mostly cleanup, but they still create false confidence.

## What is still stopping “continue until finished” from being fully proven

- The engine can continue in bounded repair mode.
- It has not yet shown that it can finish a reasonable medium-complexity real task once the first pass is insufficient.

Current limiting causes are primarily:
- inspection / repair targeting weakness
- construQtor quality / contract precision weakness
- validation coverage weakness for non-Python frontend tasks

They are not mainly:
- repair routing defects
- manifest creation defects
- scoped-write lineage defects

The target task is still reasonable; the failure is not “task too hard”, it is “signal and repair precision still too weak”.

## Smallest coherent final-fix scope

- Make canonical truth actually canonical:
  - real `.qonqrete` run-root truth
  - correct run IDs and lineage
  - explicit validation and realization stage recording
  - honest evidence-status rules

- Tighten finishability on beefier tasks:
  - stronger non-Python/frontend validation
  - sharper completion-criteria evaluation
  - sharper repair targeting from inspection into concrete missing wiring issues

- Remove remaining false-confidence paths:
  - stop implying repo-root export for partial runs
  - finish demoting qage, `tasqleveler`, and legacy naming to compatibility-only truth

## Feasibility of a final execution pass

Yes, a final execution pass still looks feasible.

But it is only worth doing after the truth-critical fixes above, otherwise the next run can still produce a coherent manifest while overstating completion, evidence quality, or canonical state alignment.
