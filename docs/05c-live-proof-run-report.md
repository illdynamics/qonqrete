# 05c Live Proof Run Report

- Date: 2026-04-10
- Target repo: `/Users/wicked/x/test-run`
- Engine repo: `/Users/wicked/x/test-run/.qonqrete`
- Task file consumed: `/Users/wicked/x/test-run/tasq-live-prove-run.md`
- Qage: `qage_20260410_163837`

## Outcome

A real live model-backed QonQrete run did occur from this target repo using the repo-local engine under `.qonqrete/`.

The run used the existing OpenAI configuration as-is. No provider switch was needed. The first launch attempt was blocked by container sandbox access, and the second launch attempt exposed a non-provider runtime issue: forced `-it` container allocation in a non-TTY proof environment. I made one small direct run-enabling fix in `.qonqrete/qonqrete.sh` so TTY flags are only used when a real terminal is attached, then retried once.

The retried run reached:

- INTAKE
- CLARIFICATION / Qrystallizer
- GUARD
- PLANNING
- ESTIMATION
- BUILD
- support-service updates (`qontextor`, `qompressor`, `qontrabender`)
- INSPECTION start
- FINALIZE as failed

The run did not reach a successful bounded clarified-pass stop. It failed in `inspeqtor` with:

- `NameError: name 'all_changed' is not defined`
- file: `.qonqrete/worqer/inspeqtor.py`

This is a runtime/code-path blocker, not a provider/config blocker.

## Provider Path

- Provider path used: OpenAI
- Models observed in artifacts/logs:
  - `gpt-4.1-mini` for planning
  - `gpt-4.1-mini` for build/review path
- DeepSeek fallback: not needed
- Provider/config fixes: none

## Mandatory Checks

- Real live model-backed run occurred: yes
- Run launched from this target repo using `.qonqrete/`: yes
- Root task file was consumed: yes
- Qrystallizer/front-door behavior exercised: yes
- Guard ran before planning: yes
- Planning/build path executed: yes
- Validation/realization/inspection artifacts produced if reached: partially
- `run-manifest.v1.json` produced: yes
- Audit artifacts produced: yes
- Implicit next-cycle task created by default: no
- Bounded-stop clarified-pass behavior completed: no, blocked by inspection failure
- Target repo contains requested built result at repo root: no
- Built result exists inside preserved qage `qodeyard/`: yes

## Key Artifacts Produced

- `.qonqrete/worqspace/qage_20260410_163837/run-manifest.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/audit/timeline.md`
- `.qonqrete/worqspace/qage_20260410_163837/audit/events.ndjson`
- `.qonqrete/worqspace/qage_20260410_163837/task/task-spec.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/task/clarification-log.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/guard/guard-result.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/planning/execution-blueprint.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/planning/validation-plan.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/estimation/estimate.v1.json`
- `.qonqrete/worqspace/qage_20260410_163837/exeq.d/cyqle1_summary.md`
- `.qonqrete/worqspace/qage_20260410_163837/exeq.d/cyqle1_changed.md`
- `.qonqrete/worqspace/qage_20260410_163837/reqap.d/cyqle1_qontract_guard.md`
- `.qonqrete/worqspace/qage_20260410_163837/reqap.d/cyqle1/cyqle1_verification.md`

Missing due inspection failure:

- successful inspection verdict bridge completion
- successful bounded-stop completion state
- propagation of built output back into the target repo root

## What Changed

In the target repo root itself:

- no `main.py`
- no `requirements.txt`
- no `run.sh`

In the engine/runtime area:

- `.qonqrete/qonqrete.sh` updated to avoid forcing TTY allocation for non-TTY runs
- preserved proof-run artifacts under `.qonqrete/worqspace/qage_20260410_163837/`

Built output inside the qage:

- `.qonqrete/worqspace/qage_20260410_163837/qodeyard/main.py`
- `.qonqrete/worqspace/qage_20260410_163837/qodeyard/requirements.txt`
- `.qonqrete/worqspace/qage_20260410_163837/qodeyard/run.sh`

## Validation Commands

- `bash -n .qonqrete/qonqrete.sh`
- `python3 -m py_compile .qonqrete/worqspace/qage_20260410_163837/qodeyard/main.py`
- `sh -n .qonqrete/worqspace/qage_20260410_163837/qodeyard/run.sh`
- requirements exactness check against `fastapi` + `uvicorn`
- manifest status check from `run-manifest.v1.json`
- next-cycle existence check under `tasq.d/`
- repo-root existence check for `main.py`, `requirements.txt`, `run.sh`

Results:

- shell syntax for `.qonqrete/qonqrete.sh`: pass
- generated `main.py` syntax: pass
- generated `run.sh` shell syntax: pass
- generated `requirements.txt` exact content: pass
- manifest finalized as `RUN_FAILED / FINALIZE / FAILED`
- no `cyqle2_*` task artifacts created
- repo root does not contain generated app files

## Blockers

- Runtime blocker: `inspeqtor.py` crashes with `NameError: all_changed not defined`
- Inspection quality issue: `inspeqtor` claimed `run.sh` was missing even though it existed in qage `qodeyard/`
- Because inspection failed, bounded-stop success was not exercised and the live run cannot be claimed as fully successful

## Verdict

Post-05 QonQrete is not yet fully demo-proven by this proof run.

What is proven:

- repo-local front door and guard-before-plan bridge work in a real live run
- OpenAI provider wiring works as configured
- planning and build execute for a real external task
- manifest and audit artifact generation are real and coherent

What is not yet proven:

- a complete successful bounded clarified-pass run through inspection/finalization
- propagation of built result into the target repo root

