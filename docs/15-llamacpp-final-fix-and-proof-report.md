# 15 llama.cpp final fix and proof report

Date: 2026-04-11

## Scope

Final bounded repair/proof pass for the real llama.cpp provider on the autonomous `tasq-small.md` task using:

- provider: `llamacpp`
- model: `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- planning/chunking ceiling: `16384`

## What the prior proof actually failed on

The prior accepted small-task proof did not mainly fail because llama.cpp was merely slow.

The evidence in the previous qage artifacts showed:

- provider wiring worked
- endpoint fallback worked
- model reconciliation worked
- `planning_context_limit_tokens: 16384` was active
- the actual failure was planning output quality / parseability

The key artifact was the repeated `No valid briqs parsed` result even when the provider call itself succeeded.

## Slowness vs brokenness

Truthful classification:

- slowness was a partial contributor only
- the dominant prior failure was malformed planning output, not a false timeout diagnosis

Evidence:

- local generations routinely took tens of seconds
- the local model also returned unusable planning output such as a leading `<think>...` block ending in a dangling `<`
- stronger live tests now fail on exactness and chunk ACK correctness instead of passing on arbitrary non-empty text

## Code changes made

### 1. Planning robustness

Updated `.qonqrete/worqer/instruqtor.py` to:

- salvage briqs from JSON-like and markdown list shapes, not just strict XML
- normalize escaped newline output before parsing
- use a compact local-model retry prompt for tiny local planning retries
- fail truthfully when bounded retries still produce no valid briqs
- increase local planning/review output budgets to reduce truncation pressure

### 2. Local provider handling

Updated `.qonqrete/worqer/lib_ai.py` to:

- add endpoint preflight for local providers
- record endpoint preflight and resolved timeout in audit payloads
- instruct local models not to emit `<think>` / chain-of-thought
- strip recoverable complete `<think>...</think>` prefixes while preserving raw text in metadata
- increase bounded patience for local planning/review

### 3. Endpoint selection fix

Updated `.qonqrete/worqer/lib_ai.py` and `.qonqrete/worqer/lib_provider_config.py` so that:

- endpoint candidates are preflighted before the live run
- the chosen reachable endpoint is moved to the front for the active run
- dead `/models` probes are no longer treated as reachable

### 4. ConstruQtor context fallback fix

Updated `.qonqrete/worqer/construqtor.py` so that when a briq does not explicitly mention target files:

- fallback context prefers real implementation files such as `main.py`, `requirements.txt`, and `run.sh`
- giant markdown design reports and `.q.yaml` relationship blobs are no longer used as the default fallback context

This specifically repaired the earlier build-stage failure where no-loss chunking became impossible under the real `16384` ceiling because the fallback context included large report files and a very large `main.py.q.yaml`.

## Patience settings used

Active local patience during this pass:

- provider timeout for llama.cpp: `600` seconds from active config
- local-provider timeout cap in code: up to `900` seconds
- planning/review local output floor: `4000` tokens
- runtime heartbeat evidence: `Instruqtor: splitting briqs (waiting 30s)` was emitted during the live proof run

I did not disable bounded protections.

## Endpoint preflight result

The final live proof run `qage_20260411_191856` proves the endpoint-selection fix worked.

Artifact:

- `.qonqrete/worqspace/qage_20260411_191856/audit/ai_payloads/20260411T172001Z-instruqtor-768d4e5323ff.json`

Preflight result:

- `http://localhost:8080/v1` rejected with `Connection refused`
- `http://host.docker.internal:8080/v1` selected before the request

This removed the earlier noisy first-call miss.

## Iterations performed

After initial inspection, I completed 3 focused repair/proof iterations.

### Iteration 1

Planning robustness patch.

Outcome:

- planning recovered far enough to produce briqs and a structured plan
- build artifact was produced
- contract was still not an exact pass
- inspection/runtime state progression remained inconsistent

Notable artifact:

- `qage_20260411_190702`

### Iteration 2

Additional budgeting / review-output repair.

Outcome:

- planning succeeded
- both build groups failed before dispatch with:
  `No-loss chunking plan exceeds the effective planning context limit when full preload history, ACKs, and final request are counted.`

Root cause for this iteration:

- ConstruQtor fallback context was far too large for a tiny task under the enforced `16384` ceiling

Notable artifact:

- `qage_20260411_191110`

### Iteration 3

ConstruQtor fallback-context fix plus strict endpoint preflight fix.

Outcome:

- endpoint preflight truthfully selected `host.docker.internal`
- the final autonomous proof still did not complete truthfully
- latest run remained stuck in planning after the first malformed planning response

Notable artifact:

- `qage_20260411_191856`

## Tests run

### py_compile

Ran successfully on touched Python files:

- `.qonqrete/worqer/lib_ai.py`
- `.qonqrete/worqer/construqtor.py`
- `.qonqrete/worqer/instruqtor.py`
- `.qonqrete/worqer/ai_capabilities.py`
- `.qonqrete/worqer/lib_provider_config.py`
- `.qonqrete/qrane/qrane.py`
- updated test files

### Offline unit tests

Command:

```bash
./.venv/bin/python -m unittest tests.test_ai_budgeting_dryrun tests.test_local_provider_integration
```

Result:

- `Ran 23 tests`
- `OK`

### Updated live llama.cpp tests

Command:

```bash
env QONQ_LIVE_LLAMACPP_TESTS=1 \
QONQ_LLAMACPP_LIVE_MODEL=/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf \
LLAMACPP_ENDPOINT=http://127.0.0.1:8080/v1 \
./.venv/bin/python -m unittest tests.test_live_local_provider_integration.LiveLlamacppIntegrationTest
```

Truthful outcome:

- still failing

Observed failure evidence during this pass:

- exact constrained response tests still exposed model-output problems
- chunked live path still produced bounded ACK mismatch:
  `Chunk preload ACK mismatch after bounded retries`

This means the strengthened live tests are now proving real local-model misbehavior instead of accepting arbitrary text.

## Final autonomous small-task proof outcome

Truthful result: **FAILURE**

The final bounded proof run did not complete successfully.

Latest proof run:

- run id: `qage_20260411_191856`
- provider: `llamacpp`
- model: `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- selected endpoint: `http://host.docker.internal:8080/v1`
- planning ceiling: `16384`

Evidence from the latest planning payload:

- planning ceiling remained `16384`
- endpoint preflight selected the reachable endpoint correctly
- the first planning response again returned malformed local-model output ending in a dangling `<`

Artifact:

- `.qonqrete/worqspace/qage_20260411_191856/audit/ai_payloads/20260411T172001Z-instruqtor-768d4e5323ff.json`

At the bounded stop point:

- the run manifest still showed `current_stage: PLANNING`
- only the first malformed planning payload had been persisted
- the autonomous proof had not reached a truthful contract-verification success state

Because the run never completed, the required task contract could not be truthfully claimed as passed.

## Contract verification status

Final proof status:

- no truthfully successful autonomous contract pass was achieved

Earlier intermediate build evidence showed partial progress, but it is not the final proof and must not be counted as success.

## Exact provider / model / endpoint / ceiling used

From the latest proof artifacts:

- provider: `llamacpp`
- model: `/Users/wicked/Qoding/ai/OmniCoder-Claude-uncensored-V2-Q4_K_M.gguf`
- endpoint: `http://host.docker.internal:8080/v1`
- planning_context_limit_tokens: `16384`

Separate environment verification during this pass also confirmed the running llama-server used:

- `--ctx-size 16384`

## Remaining caveats

- endpoint selection is now fixed for the active run
- ConstruQtor fallback context inflation under `16384` was repaired
- planning remains unstable on malformed llama.cpp output for this model
- strengthened live tests still show exactness / ACK failures with the real provider

## Final root-cause classification

**mixed cause**

Primary causes:

- local-model capability / quality issue
- planning prompt complexity issue

Secondary contributing cause:

- orchestration/runtime issue

Why this classification is the most accurate:

- the real model still emits malformed planning output and unreliable ACKs
- the parser/planner is more robust than before, but not enough to make this model reliably complete the autonomous proof
- the latest final run remained active in planning after the first malformed response instead of converging to a completed truthful outcome
