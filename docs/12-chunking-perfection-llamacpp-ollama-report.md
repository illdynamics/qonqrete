# Chunking Perfection + llama.cpp + Ollama Report

## What was wrong before

- Chunk planning only verified the inline prompt, not the full final conversation footprint after preload user messages, assistant ACKs, system message, and final manifest message were all included.
- The no-loss audit trail stored hashes and metadata, but not enough exact payload data to reconstruct and prove the precise chunk transport payloads.
- ACK handling was single-shot and fragile.
- Chunk splitting was raw char slicing.
- Provider planning context overrides were not a shared authority and did not cleanly flow from provider defaults through agent overrides.
- `llamacpp` and `ollama` were not first-class providers across runtime, schema, docs, config, zero-cost logic, and IDE surfaces.

## What was fixed

### Aggregate context budgeting

- `worqer/ai_capabilities.py` now carries `planning_context_limit_tokens` as a first-class capability field.
- Planning context can be overridden from built-in defaults, `ai_budgeting.providers`, top-level `providers.<provider>`, and `agents.<agent>`.
- `worqer/lib_ai.py` now validates the full transport footprint:
  - every preload request
  - the accumulated preload history
  - expected ACK output budget
  - the final conversation plus final output budget
- If the no-loss preload history cannot fit inside the effective planning context limit, the call now fails loudly and truthfully.

### No-loss audit and replay

- Audit artifacts moved to schema `ai-call-metadata.v2`.
- Exact transport payloads are now persisted into sidecar files under `worqspace/audit/ai_payload_sidecars/...`.
- Sidecars include:
  - system message
  - inline prompt
  - final user/manifest message
  - exact chunk payload files
  - exact preload user messages
  - ACK files when real transport runs occur
- The JSON audit manifest references the sidecar directory and file hashes so the exact transmitted content can be reconstructed and verified.

### Deterministic ACK handling

- Preload ACK calls now use a dedicated deterministic request mode.
- ACK calls use minimal output budgets and stricter generation settings where the transport supports them.
- ACK matching remains exact.
- Bounded retries were added for transient mismatch or transport failure cases.
- Retry attempts and outcomes are written into audit metadata.

### Deterministic boundary-aware chunking

- Chunk splitting now prefers:
  1. section boundaries
  2. paragraph boundaries
  3. line boundaries
  4. sentence-ish boundaries
  5. hard fallback only when needed
- Splitting remains deterministic and hash-stable.

### New providers

- Added `worqer/lib_provider_config.py` as a shared local HTTP provider resolver.
- Added first-class `llamacpp` provider support.
- Added first-class `ollama` provider support.
- Both reuse shared endpoint normalization, fallback candidate generation, provider/agent option merges, timeout handling, and zero-cost classification.

## How aggregate context budgeting now works

1. Capabilities resolve an effective `planning_context_limit_tokens`.
2. Prompt sections are normalized and optional sections are dropped or summarized according to explicit loss policy.
3. Chunking only occurs when inline prompt safety requires it and provider capabilities support preload history.
4. The planner builds the exact chunk manifest and exact preload message texts.
5. The planner token-estimates:
   - every preload request with all prior history
   - final conversation history with manifest and final output budget
6. If any preload step or the final request exceeds the effective planning limit, planning aborts.

This fixes the old false-positive case where the inline prompt looked safe but the real multi-message preload conversation did not fit.

## How no-loss audit/replay now works

- The JSON audit stores structure, hashes, budgets, chunk manifest, retry metadata, and provider metadata.
- The sidecar directory stores the exact text artifacts required to replay or prove what was sent.
- Each stored sidecar file is hash-addressed in the audit manifest.

This means the audit trail now supports exact transport proof instead of only best-effort metadata.

## Config fields added

Canonical planning field:

- `planning_context_limit_tokens`

Supported for provider-level and agent-level overrides.

New top-level provider config blocks:

- `providers.llamacpp.*`
- `providers.ollama.*`

`llamacpp` options:

- `endpoint`
- `timeout`
- `max_tokens`
- `temperature`
- `top_p`
- `top_k`
- `min_p`
- `seed`
- `repeat_penalty`
- `presence_penalty`
- `frequency_penalty`
- `stop`
- `mirostat`
- `mirostat_tau`
- `mirostat_eta`
- `planning_context_limit_tokens`

`ollama` options:

- `endpoint`
- `native_endpoint`
- `timeout`
- `max_tokens`
- `temperature`
- `top_p`
- `seed`
- `presence_penalty`
- `frequency_penalty`
- `stop`
- `use_native_discovery`
- `use_native_metadata`
- `use_native_transport`
- `enable_responses_api`
- `keep_alive`
- `think`
- `reasoning_effort`
- `api_key`
- `planning_context_limit_tokens`

## llama.cpp integration summary

- Distinct provider identity: `llamacpp`
- OpenAI-compatible `/v1/chat/completions` transport
- Endpoint normalization and fallback chain
- Optional `LLAMACPP_API_KEY`
- `/models` preflight with configured model reconciliation across path, basename, alias, root, and parent hints
- Zero-cost billing behavior preserved
- Provider and agent option merge rules added

## Ollama integration summary

- Distinct provider identity: `ollama`
- OpenAI-compatible `/v1/chat/completions` transport as the default path
- `/v1/models` validation support
- Native discovery helpers for:
  - `/api/version`
  - `/api/tags`
  - `/api/show`
  - `/api/ps`
- Better missing-model diagnostics
- Runtime metadata enrichment including observed `context_length` when available from `/api/ps`
- Zero-cost billing behavior preserved

## Truthfulness note about Ollama context limits

`planning_context_limit_tokens` is a QonQrete-side safety ceiling for budgeting and chunking.

It does not change Ollama server-side `num_ctx` when using the OpenAI-compatible `/v1` API. Native Ollama diagnostics may expose observed `context_length`, and that value is surfaced for visibility, but request-time enforcement remains honest about this distinction.

## Tests added and results

Added and updated tests cover:

- oversized dry-run request chunking and audit sidecars
- loud failure when full aggregate preload history cannot fit
- reconstructable audit sidecar output
- ACK retry behavior
- capability override precedence for planning context limits
- schema acceptance for `llamacpp` and `ollama`
- endpoint normalization and fallback ordering
- llama.cpp model reconciliation
- Ollama model discovery, native metadata ingestion, and missing-model diagnostics
- API-key checks skipping the local HTTP providers

Result from the focused test run:

```text
./.venv/bin/python -m unittest tests.test_ai_budgeting_dryrun tests.test_local_provider_integration
Ran 12 tests in 0.223s
OK
```

## Remaining caveats

- The OpenAI-compatible local-provider transport is the shipped default. Optional Ollama native generation transport was left disabled by default to avoid destabilizing the main request path.
- The Gemini SDK in this repo still emits the upstream deprecation warning for `google.generativeai`; that warning is unrelated to this provider/chunking pass.
- The new provider tests are transport-helper and planner tests, not live network integration tests against a running `llama-server` or Ollama daemon.
