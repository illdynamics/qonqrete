Implemented:
- Added task-file-first CLI entry so `./qonqrete.sh <task-file.md>` and `./qonqrete.sh run -f <task-file.md>` now work as the canonical demo path.
- Added `status` and `audit` commands for latest-run discovery, manifest path visibility, audit timeline visibility, and artifact path surfacing.
- Added latest-run pointers under `.qonqrete` state (`runs/latest`, per-run links, latest-run marker) while preserving legacy qage compatibility.
- Added auto-image bootstrap before `run`/`resume` if the runtime image is missing.
- Added repo-native import behavior when the runtime is deployed in `.qonqrete/`: the current repo is seeded into `qodeyard` by default.
- Updated CLI help and quick docs to present task-file-first usage as the primary path.

CLI / UX / sqrapyard changes:
- `sqrapyard` is no longer presented as the primary UX path; `--sqrapyard` is now documented as a legacy compatibility overlay.
- `resume` now uses the canonical task input path flow and updates latest-run pointers.
- Interactive qage selection now shows manifest-derived stage/status context when available.
- `status`/`audit` do not require container-engine detection.
- README and `doc/QUICKSTART.md` now show `qonqrete.sh <task-file>` / `run -f <task-file>` instead of `worqspace/tasq.md` as the main story.

Validation commands run:
- `bash -n qonqrete.sh`
- `./qonqrete.sh --help | sed -n '1,80p'`
- Repo-native smoke path in a temp repo with runtime under `.qonqrete`, task file outside runtime, and a stubbed `docker`:
- `QONQ_NON_INTERACTIVE=1 PATH="<fakebin>:$PATH" ./.qonqrete/qonqrete.sh demo-task.md`
- `PATH="<fakebin>:$PATH" ./.qonqrete/qonqrete.sh status`
- `PATH="<fakebin>:$PATH" ./.qonqrete/qonqrete.sh audit | sed -n '1,40p'`

Validation results:
- Shell syntax check passed.
- Help output shows task-file-first invocation, new `status`/`audit`, and downgraded `sqrapyard` wording.
- Temp repo smoke test passed for:
- task-file-first invocation
- repo-native `.qonqrete` mode detection
- repo seeding into `qodeyard`
- latest-run pointer creation
- manifest-linked `status`
- audit timeline discovery via `audit`
- Smoke test used a stubbed container engine to validate startup and manifest linkage without requiring live model execution.

Remaining blockers / intentionally deferred:
- Full live end-to-end run with real agents/models was not executed in this pass; the smoke test validated CLI/task/manifest startup, not model-backed realization.
- Legacy qage/cycle runtime remains underneath; this pass improves the front door and visibility, not full qage removal.
- Full GitOps/CI rollout, distributed execution, deep validator expansion, and complete qage/qage-compat retirement are deferred.
- IDE/plugin wording and config surfaces still contain older `tasq.md` / `sqrapyard` references outside this focused CLI/demo-ready pass.
