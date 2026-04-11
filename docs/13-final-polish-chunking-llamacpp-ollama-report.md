# Final Polish Report: Chunking + llama.cpp + Ollama

Date: 2026-04-11

## Scope

This pass was intentionally narrow. It preserved:

- structured prompt planning
- no-loss chunking and truthful preload-fit failure
- provider-aware `planning_context_limit_tokens`
- sidecar-backed AI transport audit artifacts
- first-class `provider: llamacpp`
- first-class `provider: ollama`

It did not reintroduce silent truncation, flat char-based fallback, or any weakening of aggregate preload history fit checks.

## What Was Fixed

### 1. Ollama flag truthfulness

The exposed Ollama flags now match reality exactly.

Still supported and now wired end-to-end:

- `use_native_discovery`
  - Controls whether native Ollama `/api/*` discovery is used at runtime.
  - When `false`, native discovery and native metadata fetches are skipped.
- `use_native_metadata`
  - Controls whether extra native metadata enrichment is fetched from `/api/show` and `/api/ps`.
  - Requires `use_native_discovery=true`.

Removed from active supported config because they were cosmetic, not real:

- `use_native_transport`
- `enable_responses_api`

Validation now fails loudly if either unsupported flag still appears in provider or agent config, rather than leaving a lying user-facing knob in place.

### 2. Native endpoint pairing during fallback

Ollama fallback now keeps native discovery and metadata paired with the currently attempted OpenAI-compatible endpoint host.

Before this polish, a fallback attempt could hit OpenAI endpoint candidate `N` while still using an unrelated native endpoint candidate from a different host.

Now:

- matching is host-paired via provider-config normalization helpers
- native `/api/*` calls follow the same host as the active `/v1` candidate
- aggregated errors include both the attempted `/v1` endpoint and paired native endpoint where relevant

### 3. Failure-path audit completeness for chunk transport

Chunk transport failures now preserve partial evidence instead of collapsing to a generic failure.

The audit payload now retains:

- partial preload ACK history
- ACK retry log entries
- transmitted chunk metadata
- sidecar references and hashes for transmitted payloads
- the exact failure boundary stage

This applies to both:

- preload failures mid-stream
- final generation failures after successful preload

### 4. Provider config validation tightened

Provider validation is now stricter and provider-specific.

It now rejects, with clear messages:

- malformed `endpoint` and `native_endpoint` values
- bad option types
- invalid timeout values
- invalid `planning_context_limit_tokens`
- unsupported Ollama option combinations
- host-mismatched Ollama `endpoint` / `native_endpoint`
- `use_native_metadata=true` with `use_native_discovery=false`

The validation still intentionally allows local HTTP endpoints and normalized shorthand forms where supported.

### 5. Runtime config resolution for live qage runs

`ai_capabilities.py` now prefers the active qage/runtime config path before falling back to repo-root config.

This fixed a real live-run defect where a proof-run qage config set `planning_context_limit_tokens: 16384`, but the runtime incorrectly loaded broader repo-root defaults and silently operated at `32768`.

### 6. Documentation truth pass

Docs and config examples were updated so they now say, explicitly:

- `planning_context_limit_tokens` is a QonQrete-side planning/chunking safety ceiling
- it does not reconfigure the real provider server context window
- Ollama `/v1` context must still be configured outside QonQrete
- llama.cpp server context must still be configured on `llama-server`
- `provider: local` is not `provider: llamacpp`
- `provider: ollama` is distinct from `provider: llamacpp`
- unsupported Ollama native transport / Responses API flags are not exposed as supported config

## Files Changed

- `.qonqrete/worqer/lib_provider_config.py`
- `.qonqrete/worqer/lib_security.py`
- `.qonqrete/worqer/lib_ai.py`
- `.qonqrete/worqer/ai_capabilities.py`
- `.qonqrete/tests/test_local_provider_integration.py`
- `.qonqrete/tests/test_ai_budgeting_dryrun.py`
- `.qonqrete/tests/test_live_local_provider_integration.py`
- `.qonqrete/worqspace/config.yaml`
- `.qonqrete/README.md`

## Ollama Flags: Final Truth Table

### Truly active

- `use_native_discovery`
- `use_native_metadata`

### Removed from supported config surface

- `use_native_transport`
- `enable_responses_api`

## Failure-Path Audit Behavior After This Patch

On chunk preload failure, audit evidence now includes:

- which chunk payloads were attempted
- which preload ACKs succeeded before failure
- which retry attempt failed or mismatched
- hashes and sidecar file references for payloads already transmitted
- exact failure boundary details

On final generation failure after successful preload, audit evidence now still preserves:

- the completed preload history
- transmitted chunk metadata
- the final failure boundary at post-preload generation

## Tests Added / Updated

Offline regression:

- Ollama discovery flags change runtime behavior
- Ollama native endpoint fallback stays host-paired
- invalid provider config is rejected clearly
- active qage config is preferred by capability loading
- preload failure preserves partial transport audit
- final-generation failure preserves preload audit evidence

Optional live integration tests were added and remain opt-in only:

- llama.cpp live tests gated by `QONQ_LIVE_LLAMACPP_TESTS=1`
- Ollama live tests gated by `QONQ_LIVE_OLLAMA_TESTS=1`

Live test coverage:

- llama.cpp:
  - endpoint reachability
  - `/models` preflight
  - model reconciliation
  - simple chat completion
  - chunked path with a small planning ceiling
- Ollama:
  - `/v1/models`
  - `/api/version`
  - `/api/tags`
  - `/api/show`
  - `/api/ps`
  - simple chat completion
  - chunked path with a small planning ceiling

These live tests do not run in default CI and do not make the default suite slower or network-dependent.

## Verification Run

Executed:

- `python -m py_compile` on all touched Python files
- `python -m unittest tests.test_local_provider_integration tests.test_ai_budgeting_dryrun`
- live llama.cpp integration tests

Environment-gated and not executed because the service was unavailable:

- live Ollama integration tests

Observed live environment facts:

- llama.cpp server reachable
- `/v1/models` reachable
- model reconciliation succeeded
- Ollama daemon was not reachable at `http://127.0.0.1:11434`

## Remaining Honest Caveats

- The optional live Ollama suite is implemented and gated, but was not runnable in this environment because no local Ollama daemon was reachable.
- The mandatory real llama.cpp proof proved provider wiring, endpoint fallback, model reconciliation, and planning-ceiling enforcement, but the actual autonomous small-task run still failed during planning because the local model did not produce valid briqs. Details are captured in `14-llamacpp-small-task-live-proof.md`.
