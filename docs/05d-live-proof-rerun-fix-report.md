# 05d Live Proof Rerun Fix Report

- Date: 2026-04-10
- Target repo: `/Users/wicked/x/test-run`
- Engine repo/runtime: `/Users/wicked/x/test-run/.qonqrete`
- Task file: `tasq-live-prove-run.md`

## Summary

This pass fixed the live proof blockers in `/.qonqrete/worqer/inspeqtor.py`, reran QonQrete against the target repo, and achieved one real live model-backed bounded completion with coherent manifest and audit artifacts. The prior `all_changed` crash is resolved, inspection no longer falsely treats generated files as missing, and the built proof-task output is now synced into the target repo root.

## What Was Fixed

- Fixed the `NameError: all_changed is not defined` path in `.qonqrete/worqer/inspeqtor.py`.
- Corrected changed-file evidence loading so inspection can truthfully see grouped build outputs from `build/groups/*/changed-files.v1.json` in addition to legacy changed manifests.
- Preserved deterministic changed-file ordering and deduplication so generated files such as `run.sh` are not falsely judged missing when they exist in `qage/qodeyard`.
- Confirmed the existing finalize sync path in `.qonqrete/qonqrete.sh` propagates qage `qodeyard` outputs into the target repo root once the run reaches `RUN_COMPLETED`.

## Live Rerun Attempts

1. Attempt 1:
   - Real live run launched from the target repo with `.qonqrete/qonqrete.sh run -f /Users/wicked/x/test-run/tasq-live-prove-run.md --auto`
   - Provider/model path: OpenAI configured path
   - Result: failed during planning due a new provider blocker, `429 insufficient_quota`
   - Classification: provider/config blocker, new and external to the prior inspection bug

2. Attempt 2:
   - Real live run launched from the target repo with the same task file
   - Provider/model path: fallback `deepseek` / `deepseek-chat`
   - Result: successful bounded completion

Total live rerun attempts in this pass: `2`

## Provider / Config Truth

- OpenAI was used first as required.
- A new real OpenAI blocker appeared on 2026-04-10: `429 insufficient_quota`.
- Because that blocker was provider-specific and new, config was switched to `deepseek` / `deepseek-chat` for the rerun.
- Provider/config changes were required for the successful rerun.

## Successful Rerun Truth

- Successful qage: `.qonqrete/worqspace/qage_20260410_182545`
- Manifest result: `RUN_COMPLETED`
- Lifecycle state: `COMPLETED`
- Final audit outcome: `run_finalized` with `completed`
- Bounded-stop behavior: worked
- Implicit next-cycle continuation: not created by default
- Audit note: `Run ended after bounded clarified bridge pass without implicit legacy continuation.`

Stages actually reached in the successful rerun:

- Qrystallizer/front-door clarification
- Guard before planning
- Planning
- Estimation
- Build
- Validation
- Realization
- Inspection
- Finalize

Inspection truth in the successful rerun:

- No crash
- `deterministic_gate: PASS`
- `status: PARTIAL`
- The run still completed successfully and finalized truthfully

## Key Artifacts Produced

- `run-manifest.v1.json`
- `audit/events.ndjson`
- `audit/timeline.md`
- `task/task-intake-bridge.v1.json`
- `task/task-spec.v1.json`
- `guard/guard-result.v1.json`
- `planning/planning-bridge.v1.json`
- `estimation/estimation-bridge.v1.json`
- `build/build-output-bridge.v1.json`
- `validation/validation-bundle.v1.json`
- `realization/realization-bundle.v1.json`
- `verdict/inspection-input.v1.json`
- `verdict/inspection-verdict.v1.json`

Manifest / audit coherence check:

- Manifest linked the produced stage artifacts coherently.
- Audit recorded stage start/completion events through `FINALIZE`.

## Target Repo Root Output

The proof-task output now exists in the target repo root, not only inside qage `qodeyard`:

- `main.py`
- `requirements.txt`
- `run.sh`

## Validation Commands Run

```bash
python3 -m py_compile .qonqrete/worqer/inspeqtor.py
python3 - <<'PY'
import yaml
from pathlib import Path
cfg=yaml.safe_load(Path('.qonqrete/worqspace/config.yaml').read_text())
for name in ('tasqleveler','instruqtor','construqtor','inspeqtor'):
    print(name, cfg['ai'][name]['provider'], cfg['ai'][name]['model'])
PY
python3 - <<'PY'
from pathlib import Path
import json
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location('inspeqtor', '.qonqrete/worqer/inspeqtor.py')
mod = module_from_spec(spec)
spec.loader.exec_module(mod)
qage = Path('.qonqrete/worqspace/qage_20260410_163837')
items = mod.load_changed_code_artifacts(qage)
print([item['file'] for item in items])
print(any(item['file']=='run.sh' for item in items))
print(all((qage/'qodeyard'/item['file']).exists() for item in items))
PY
env QONQ_NON_INTERACTIVE=1 ./.qonqrete/qonqrete.sh run -f /Users/wicked/x/test-run/tasq-live-prove-run.md --auto
ls -l main.py requirements.txt run.sh
python3 -m py_compile main.py
sh -n run.sh
```

Validation results:

- `inspeqtor.py` compiled successfully.
- DeepSeek fallback config parsed correctly after the OpenAI quota blocker.
- Changed-file loading now includes `main.py`, `requirements.txt`, and `run.sh`, and all were confirmed present in qage `qodeyard`.
- Successful live rerun completed and synced repo-native export.
- Root `main.py` compiles.
- Root `run.sh` passes shell syntax check.

## Remaining Blockers / Residuals

No remaining blocker prevents a real successful bounded live proof run.

Residual non-blocking issues still reported by inspection:

- Legacy ConstruQtor still writes directly into `qodeyard` without transactional staging.
- System impact telemetry is still not collected.
- Inspection reported one briq-level partial review because the supporting-files briq also touched `main.py`.

## Final Truth

Post-05 QonQrete is now demo-proven by a successful real live bounded run on this target repo.
