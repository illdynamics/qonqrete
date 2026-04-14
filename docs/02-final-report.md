- Implemented:
  - Added canonical intake via [`worqer/qrystallizer.py`](/Users/wicked/x/qonqrete/worqer/qrystallizer.py) and wired it through the legacy `tasqleveler` stage as a compatibility wrapper in [`worqer/tasqleveler.py`](/Users/wicked/x/qonqrete/worqer/tasqleveler.py).
  - Added canonical pre-plan Guard stage in [`worqer/guard.py`](/Users/wicked/x/qonqrete/worqer/guard.py) and inserted it before planning in [`worqspace/pipeline_config.yaml`](/Users/wicked/x/qonqrete/worqspace/pipeline_config.yaml).
  - Adapted [`worqer/instruqtor.py`](/Users/wicked/x/qonqrete/worqer/instruqtor.py) to consume `task/task-spec.v1.json` plus `guard/guard-result.v1.json` as the real planning handoff instead of raw tasq text alone.
  - Updated [`qrane/qrane.py`](/Users/wicked/x/qonqrete/qrane/qrane.py) to enforce no mid-run questions after readiness acceptance by bypassing later gates/prompts and ending user-gated flow without prompting.
  - Updated [`qrane/manifest_bridge.py`](/Users/wicked/x/qonqrete/qrane/manifest_bridge.py) to link the new intake and guard artifacts into the canonical run manifest.

- Task Spec / Guard artifacts added:
  - `task/task-spec.v1.json`
  - `task/clarification-log.v1.json`
  - `task/clarification-summary.md`
  - `guard/guard-result.v1.json`
  - `guard/guard-result.v1.md`
  - `guard/guard-bridge.v1.json`

- `tasqleveler` adaptation:
  - `tasqleveler` is no longer canonical intake authority and no longer mutates `tasq.md` in place.
  - It now delegates to `Qrystallizer` and exists only as a legacy pipeline alias for compatibility.

- Validation commands run:
  - `python3 -m py_compile worqer/qrystallizer.py worqer/guard.py worqer/tasqleveler.py worqer/instruqtor.py qrane/manifest_bridge.py qrane/qrane.py`
  - Temp-workspace deterministic validation script covering:
    - READY Task Spec generation
    - NOT_READY Task Spec generation
    - Guard PASS/REVIEW vs FAIL behavior
    - assumption/clarification artifact emission
    - manifest linkage for Task Spec and Guard Result
    - no-mid-run-question `handle_cheqpoint(..., no_midrun_questions=True)` enforcement
  - Source-level deterministic assertion for planning handoff markers in `worqer/instruqtor.py`

- Validation results:
  - `py_compile`: passed
  - READY flow: passed, Task Spec emitted as `READY`, Guard emitted `REVIEW`, manifest linked artifacts
  - NOT_READY flow: passed, Task Spec emitted as `NOT_READY`, Guard failed with `TASK_SPEC_NOT_READY`
  - no-mid-run-question enforcement: passed, user-gated checkpoint returned `QUIT` without prompting
  - planning handoff markers: passed

- Remaining blockers / intentionally deferred:
  - Full end-to-end planning/build run was not executed because `instruqtor` still depends on the existing AI runtime stack.
  - Full planning/build-group redesign is deferred.
  - realization separation is still bridge-based, not a standalone runtime stage.
  - repair-plan migration, repo-native CLI overhaul, deep Codex integration, and transaction hardening remain deferred to later phases.
