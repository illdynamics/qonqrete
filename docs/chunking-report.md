# Provider Token Budget and Chunking Fix Report

## What Was Wrong Before

QonQrete previously planned most AI requests with character caps instead of provider-aware token budgets. The central path in `worqer/lib_ai.py` could truncate context files by characters, drop architectural context opportunistically, and even truncate the base prompt as a last resort. That meant required instructions were not structurally protected.

Provider handling was also inconsistent. Anthropic had a hardcoded output cap while other providers mostly relied on provider defaults. There was no central capability registry for safe input budget, output budget, context window, or chat/session chunk-preload support.

Prompt assembly was flat and opaque. Large inline prompt sections and `context_files` were merged into one big string, so there was no way to distinguish required content from optional context, no auditable omission policy, and no deterministic no-loss preload strategy for oversized requests.

`construqtor.py` especially sent too much payload per briq. It embedded QONTRACT, cycle-1 task context, structure tree, grouped context, repair context, and then still attached broad context files. `inspeqtor.py` also converted token roofs back into chars with `batch_token_roof * 4`, which kept token safety approximate rather than provider-aware.

## What Changed

### Central capability and budgeting layer

Added `worqer/ai_capabilities.py` as the single source of truth for conservative provider/model capability defaults. It resolves:

- safe input tokens
- safe output tokens
- total context window
- chars-per-token estimate
- multi-message support
- chunk preload support
- system message support

It also reads overrides from `worqspace/config.yaml` under `ai_budgeting.providers`.

### Structured prompt sections and loss policy

Replaced the old flat prompt builder in `worqer/lib_ai.py` with structured `PromptSection` planning. Each section now has:

- `label`
- `section_type`
- `required`
- `loss_policy`
- token estimate
- source file references
- omission/summarization/chunking status for audit

Supported policies are:

- `preserve`
- `droppable`
- `summarizable`
- `chunkable`

Required sections are no longer silently truncated away. If they do not fit inline, the system either chunks them with multi-message preload or raises a loud error.

### No-loss chunking

`run_ai_completion(...)` now plans requests against provider-safe input/output budgets and switches to deterministic preload chunking when needed. The preload path:

1. splits chunkable content into deterministic fixed-order chunks
2. sends one preload message per chunk with section label, section hash, chunk hash, and exact chunk content
3. requires the model to return a strict ACK format
4. aborts if any ACK is missing or inconsistent
5. sends the final generation request with a chunk manifest referencing every preloaded chunk

This preserves exact content without character truncation and produces a machine-readable chunk manifest in the audit artifact.

### Unified output budgeting

Output token budgeting is now resolved centrally from capabilities plus config overrides. `run_ai_messages(...)` dispatches provider calls with explicit output budgets for OpenAI, DeepSeek, Qwen, OpenRouter, Gemini, and Anthropic. Response truncation signals are captured into audit metadata instead of being silent.

### Prompt payload optimization

Before chunking, `lib_ai.py` now:

- estimates tokens per section using provider-aware chars/token
- drops low-value optional sections first
- summarizes summarizable sections before chunking
- uses Qompressor when it can reduce code-context payload safely
- keeps previous-log injection optional and budget-aware instead of always-on

`construqtor.py` now sends:

- required core instructions
- required briq plan
- required grouped build context
- required repair context when present
- required QONTRACT as its own chunkable section
- optional cycle-1 task anchor as summarizable context
- optional structure tree as droppable context

It also narrows attached context files per briq with `filter_context_by_relevance(...)` instead of blindly attaching the heaviest available payload to every build request.

`inspeqtor.py` no longer uses `batch_token_roof * 4` as the main enforcement path. Batched review, per-briq review, and meta-review now rely on structured planning through `run_ai_completion(...)`, with output budgets passed explicitly.

`instruqtor.py` and `qontextor.py` were updated to use the new structured entrypoint so their requests also inherit provider-aware budgeting and audit metadata.

## How Provider Limits Are Now Resolved

Resolution order is:

1. built-in conservative capability defaults in `worqer/ai_capabilities.py`
2. provider defaults from `worqspace/config.yaml -> ai_budgeting.providers`
3. model-pattern overrides from the same config subtree
4. per-agent or per-task output token overrides from `ai_budgeting.agent_output_tokens` and `ai_budgeting.task_output_tokens`

For dry validation, `ai_budgeting.dry_run_provider` selects which capability profile to use for planning without calling an external API.

## How No-Loss Chunking Works

The planner computes the safe inline input budget from resolved capabilities. If active sections exceed that budget:

- droppable sections are omitted first
- summarizable sections are reduced next
- remaining oversized chunkable sections are split into deterministic chunks

Each chunk records:

- chunk index / total
- section label
- section hash
- chunk hash
- estimated tokens

The final request only proceeds if all preload ACKs match the expected format exactly. Because chunk boundaries are deterministic and hashes are recorded, the original chunked content can be reconstructed from the audit manifest.

## What Prompt Bloat Was Removed or Downgraded

- `construqtor.py` no longer blindly inlines all constitutional material into one monolithic prompt string.
- Cycle-1 task context is no longer hard-truncated in `construqtor.py`; it is now optional summarizable context handled by the planner.
- Project structure tree is now optional droppable context.
- Previous log fallback is governed by `ai_budgeting.include_previous_log` and is dropped first under pressure.
- Context files are converted into explicit optional sections, summarized with Qompressor where useful, and can be omitted with audit disclosure.
- `inspeqtor.py` now estimates per-context-file review cost using token estimation rather than `chars // 4`.

## Audit Artifacts

Every AI request now writes JSON metadata under:

`worqspace/audit/ai_payloads/`

Each artifact includes:

- provider and model
- agent name
- resolved capability profile
- input token estimate
- output token budget
- safe budgets
- chunking usage and chunk count
- per-section breakdown
- dropped optional sections
- summarized sections
- source files included
- fallback hard-limit disclosure
- response truncation detection
- chunk manifest and preload ACKs when chunking is used

## Risks and Follow-Ups

- Gemini import currently emits an upstream deprecation warning for `google.generativeai`; the new budgeting layer preserves behavior but does not migrate the SDK.
- The current chunking strategy assumes chat-history retention inside one request session. That is valid for the supported chat providers but should still be validated against live provider-specific edge behavior in integration runs.
- `filter_context_by_relevance(...)` is now used more aggressively by ConstruQtor, but further signal improvement is still possible by incorporating build-group and component-contract awareness into context ranking itself.
- Existing pricing utilities still use heuristic token estimation. They now consult the capability registry for chars/token when available, but they are still estimates, not tokenizer-accurate counts.
