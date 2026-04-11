# llama.cpp Small-Task Live Proof

Date: 2026-04-11

## Goal

Run a real autonomous QonQrete task from `tasq-small.md` using:

- `provider: llamacpp`
- model path expanded to an absolute path
- `planning_context_limit_tokens: 16384`

No cloud fallback, no provider swap, no simulated proof.

## Exact Runtime Inputs

### Absolute model path used

`/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`

This exact absolute path existed on disk and was used in config and in live audit payloads.

### Endpoint used

Configured primary endpoint:

`http://localhost:8080/v1`

Configured fallback candidates in effective provider options:

- `http://localhost:8080/v1`
- `http://host.docker.internal:8080/v1`
- `http://host.containers.internal:8080/v1`

The successful live inference calls recorded in audit payloads resolved to:

`http://host.docker.internal:8080/v1`

### Server-side llama.cpp context

The actual running `llama-server` process was verified via `ps` and was started with:

`--ctx-size 16384`

So this environment had both:

- QonQrete-side `planning_context_limit_tokens: 16384`
- real server-side llama.cpp context size `16384`

## Config Changes Made For The Proof

Minimal proof-run tuning only:

- set active agents for the autonomous path to `provider: llamacpp`
- set their model to `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- set provider-level `planning_context_limit_tokens: 16384`
- set llama.cpp provider timeout high enough for slower local inference
- preserved boundedness and failure reporting
- did not disable chunking truthfulness
- did not switch to another provider or model

Important runtime fix discovered and implemented during proof prep:

- `ai_capabilities.py` was loading repo-root config instead of the active qage config
- this caused an initial proof attempt to run with an unintended planning ceiling of `32768`
- after fixing config-path precedence, the second proof run correctly used `16384`

## Preflight Evidence

Verified before or during the proof:

- absolute model path existed:
  - `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- llama.cpp `/v1/models` endpoint was reachable
- model reconciliation succeeded against server model list
- live llama.cpp integration tests passed in this environment

Evidence paths:

- invalid first proof attempt qage:
  - `.qonqrete/worqspace/qage_20260411_184517`
- corrected proof attempt qage:
  - `.qonqrete/worqspace/qage_20260411_184742`

## Planning-Ceiling Proof

### First attempt: invalid for acceptance

Artifact:

- `.qonqrete/worqspace/qage_20260411_184517/audit/ai_payloads/20260411T164542Z-instruqtor-bbb48b4598f9.json`

This showed:

- `provider: "llamacpp"`
- correct absolute model path
- but `planning_context_limit_tokens: 32768`

That run was not accepted as the mandatory proof because the intended 16384 ceiling was not actually active.

### Second attempt: valid planning ceiling

Artifact:

- `.qonqrete/worqspace/qage_20260411_184742/audit/ai_payloads/20260411T164811Z-instruqtor-bbb48b4598f9.json`

This showed:

- `provider: "llamacpp"`
- `model: "/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf"`
- `planning_context_limit_tokens: 16384`
- `capabilities.total_context_window: 16384`
- `conversation_budgeting.planning_context_limit_tokens: 16384`
- `provider_options.endpoint: "http://localhost:8080/v1"`
- actual `provider_response_metadata.endpoint: "http://host.docker.internal:8080/v1"`

Conclusion:

- the corrected live proof did respect the QonQrete-side 16384 planning/chunking ceiling
- the server also truthfully had `--ctx-size 16384`

## Autonomous Run Command

Real run command:

`env QONQ_NON_INTERACTIVE=1 ./.qonqrete/qonqrete.sh run -f /Users/wicked/x/test-run/tasq-small.md --auto`

This was executed for the proof.

## Outcome

### Final status

Fail

### Run manifest

Artifact:

- `.qonqrete/worqspace/qage_20260411_184742/run-manifest.v1.json`

Final recorded state:

- `lifecycle_state: "FAILED"`
- `run_status: "RUN_FAILED"`
- planning stage failed
- no build stage completed

Timeline artifact:

- `.qonqrete/worqspace/qage_20260411_184742/audit/timeline.md`

Timeline summary:

- `PLANNING` started at `2026-04-11T16:47:58Z`
- `PLANNING` failed at `2026-04-11T16:50:28Z`
- run finalized as failed

### Failure classification

Primary classification:

- local-model quality/output issue

Contributing runtime condition:

- endpoint fallback from in-container `localhost` to `host.docker.internal` was needed, but it worked

Not a provider wiring failure:

- provider was `llamacpp`
- endpoint fallback succeeded
- `/models` discovery succeeded
- model reconciliation succeeded
- real completions were returned by llama.cpp

Not a chunking/budgeting failure:

- corrected run used `planning_context_limit_tokens: 16384`
- no silent truncation occurred
- no fallback char-based clipping occurred

Observed planning log evidence:

- `[WARN] llamacpp endpoint failed http://localhost:8080/v1: Connection error.`
- fallback continued to the reachable host endpoint
- repeated `No valid briqs parsed` warnings
- planning ultimately failed to produce the required briq set

Console log artifact:

- `.qonqrete/worqspace/qage_20260411_184742/struqture/qonsole_instruqtor.log`

## Scoreboard

- pass/fail: fail
- repairs needed: not reached
- provider used: `llamacpp`
- model used: `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- effective serving endpoint: `http://host.docker.internal:8080/v1`
- configured planning ceiling: `16384`
- actual server context flag: `--ctx-size 16384`
- autonomous completion: no
- build artifacts produced by the run: no trustworthy generated build output
- final contract compliance: fail, because the autonomous run did not complete planning/build

## Contract Evaluation Against `tasq-small.md`

The run did not complete the task autonomously, so the task contract is a fail overall.

Important truthfulness note:

- `qodeyard/main.py`
- `qodeyard/requirements.txt`
- `qodeyard/run.sh`

were present in the qage, but they matched the already-existing repo-root files and were part of seeded workspace state. They are not evidence that the autonomous run completed the small task contract.

Because planning failed before build completion, the proof cannot claim that QonQrete successfully produced or validated a compliant FastAPI app for this task.

## Artifacts Preserved

Primary proof artifacts:

- `.qonqrete/worqspace/qage_20260411_184742/run-manifest.v1.json`
- `.qonqrete/worqspace/qage_20260411_184742/audit/timeline.md`
- `.qonqrete/worqspace/qage_20260411_184742/audit/ai_payloads/20260411T164811Z-instruqtor-bbb48b4598f9.json`
- `.qonqrete/worqspace/qage_20260411_184742/audit/ai_payloads/20260411T164831Z-instruqtor-db055c8b24c1.json`
- `.qonqrete/worqspace/qage_20260411_184742/audit/ai_payloads/20260411T164850Z-instruqtor-9a90d91b5031.json`
- `.qonqrete/worqspace/qage_20260411_184742/struqture/qonsole_instruqtor.log`
- `.qonqrete/worqspace/qage_20260411_184742/qontract.d/qontract.md`

Supporting first-attempt evidence showing the pre-fix config-path bug:

- `.qonqrete/worqspace/qage_20260411_184517/audit/ai_payloads/20260411T164542Z-instruqtor-bbb48b4598f9.json`

## Speed / Patience Notes

Local-model patience was tuned upward with bounded timeouts so the proof would be fair to llama.cpp.

What was changed:

- longer provider timeout values
- no premature worker termination during normal slow local inference

What was not changed:

- no removal of bounded safety timeouts
- no suppression of retries or failure reporting
- no provider or model substitution

## Bottom Line

This proof establishes that QonQrete can truthfully operate with:

- `provider: llamacpp`
- the required absolute model path
- a real 16384 QonQrete planning ceiling
- a real 16384 llama.cpp server context size
- real endpoint fallback and model reconciliation

It does not establish successful autonomous completion of `tasq-small.md` with this local model, because the run failed in planning after repeated invalid briq outputs from the model.
