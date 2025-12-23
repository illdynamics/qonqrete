# Multi-Stage Inspeqtion System (v0.8.3)

## Overview

The Multi-Stage Inspeqtion system with **Interleaved Pipeline** provides:
1. **Build → Review → Build → Review** per briq (interleaved orchestration)
2. **Local validation** after each briq (syntax, imports) - no AI needed
3. **Optional AI quick review** per briq for quality assurance
4. **Retry on failure** with configurable attempts
5. **Fail-fast or fail-tolerant** modes

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     INSTRUQTOR (Once per cycle)                  │
├─────────────────────────────────────────────────────────────────┤
│   tasq.md ──► Break into briqs ──► briq.d/cyqle{N}_*.md         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│            CONSTRUQTOR v0.8.3 (Interleaved Pipeline)             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   FOR EACH briq:                                                 │
│   ┌───────────────────────────────────────────────────────────┐ │
│   │                                                            │ │
│   │   ┌──────────────┐                                         │ │
│   │   │  1. BUILD    │  AI generates code for this briq        │ │
│   │   │  (ConstruQtor)│  Write files to qodeyard/              │ │
│   │   └──────────────┘                                         │ │
│   │          │                                                  │ │
│   │          ▼                                                  │ │
│   │   ┌──────────────┐                                         │ │
│   │   │ 2. VALIDATE  │  Local syntax check (compile())         │ │
│   │   │ (No AI)      │  Import resolution check                │ │
│   │   └──────────────┘                                         │ │
│   │          │                                                  │ │
│   │    ┌─────┴─────┐                                           │ │
│   │    ▼           ▼                                           │ │
│   │   ✅ OK      ❌ FAIL ──► retry (up to max_attempts)        │ │
│   │    │                                                        │ │
│   │    ▼                                                        │ │
│   │   ┌──────────────┐                                         │ │
│   │   │ 3. REVIEW    │  Optional AI quick review               │ │
│   │   │ (if enabled) │  (ai_quick_review: true)                │ │
│   │   └──────────────┘                                         │ │
│   │          │                                                  │ │
│   │    ┌─────┴─────┐                                           │ │
│   │    ▼           ▼                                           │ │
│   │   ✅ PASS    ❌ FAIL ──► retry (if retry_on_review_fail)   │ │
│   │    │                                                        │ │
│   │    ▼                                                        │ │
│   │   Write reqap.d/cyqle{N}/briq{XXX}_reqap.md                │ │
│   │                                                            │ │
│   └────────────────────────────────────────────────────────────┘ │
│          │                                                       │
│          ├── stop_on_briq_fail=true  ──► HALT                   │
│          └── stop_on_briq_fail=false ──► Continue to next briq  │
│                                                                  │
│   Output: exeq.d/cyqle{N}_summary.md (with all briq results)    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│          INSPEQTOR (Final Review & Verification)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   STAGE 1: Aggregate Per-Briq Results                           │
│   • Read all briq reqaps from construqtor                       │
│   • Detect cross-briq integration warnings                      │
│                                                                  │
│   STAGE 2: Meta-Review (AI)                                     │
│   • Synthesize patterns across briqs                            │
│   • Consolidated suggestions                                    │
│                                                                  │
│   STAGE 3: LoQal Verification (No AI)                           │
│   • Final syntax validation                                     │
│   • Import resolution                                           │
│   • Results appended to reqap                                   │
│                                                                  │
│   Output: reqap.d/cyqle{N}_reqap.md                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  QRANE: promote_reqap()                          │
├─────────────────────────────────────────────────────────────────┤
│   reqap.d/cyqle{N}_reqap.md ──► tasq.d/cyqle{N+1}_tasq.md       │
│   Self-healing loop!                                             │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### config.yaml

```yaml
# Retry Configuration
retry:
  enabled: true
  max_attempts: 3              # Total attempts per briq
  stop_on_briq_fail: false     # Continue to other briqs on failure
  retry_delay: 2               # Seconds between retries

# Interleaved Pipeline (NEW in v0.8.3)
interleaved:
  enabled: true                # Enable build→review per briq
  local_validation: true       # Syntax/import checks (no AI)
  ai_quick_review: false       # Set true for AI review per briq
  retry_on_review_fail: true   # Retry if AI review fails

# Local Verification (final stage)
verification:
  enabled: true
  checks:
    syntax: true               # Python compile() validation
    imports: true              # Import resolution
    skeleton_match: true       # Signature comparison

agents:
  inspeqtor:
    provider: openai
    model: gpt-4.1
    max_prompt_chars_per_briq: 500000
    max_context_files_per_briq: 40
    max_chars_per_context_file: 80000
    use_filtered_context: true
    include_neighbor_depth: 1
```

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `retry.max_attempts` | 3 | How many times to retry a failed briq |
| `retry.stop_on_briq_fail` | false | Halt cycle on failure (true) or continue (false) |
| `interleaved.local_validation` | true | Run syntax/import checks per briq |
| `interleaved.ai_quick_review` | false | Run AI review per briq (costs tokens) |

### How It Works

1. **ConstruQtor** processes each briq with interleaved validation:
   - Build code → Validate locally → (Optional AI review) → Next briq
   - Writes per-briq reqaps: `reqap.d/cyqle{N}/briq{XXX}_reqap.md`

2. **InspeQtor** does final review:
   - Aggregates per-briq results
   - Meta-review for patterns
   - LoQal verification (final syntax check)

3. **promote_reqap()** carries everything to next cycle

### caching_policy.yaml

The `inspeqtor` section controls detailed policy:

```yaml
inspeqtor:
  per_briq:
    max_prompt_chars: 500000
    max_context_files: 40
    context_filter:
      enabled: true
      neighbor_depth: 1
      
  meta_review:
    max_prompt_chars: 100000
    exclude:
      - raw_code
      - full_architectural_context
```

## Output Structure

After running InspeQtor on cyQle 2:

```
reqap.d/
├── cyqle2/                          # Per-briq reqaps
│   ├── cyqle2_tasq1_briq000_reqap.md
│   ├── cyqle2_tasq1_briq001_reqap.md
│   ├── cyqle2_tasq1_briq002_reqap.md
│   └── ...
└── cyqle2_reqap.md                  # Final aggregated reqap
```

## How Context Filtering Works

Instead of passing ALL `.q.yaml` files, we filter based on relevance:

1. **Identify Changed Files**: Extract files modified by the briq
2. **Find Direct Context**: Include `.q.yaml` for each changed file
3. **Expand Neighbors**: Include `.q.yaml` for dependencies (imports, calls)
4. **Apply Budget**: Stop if budget exhausted

Example:
- Briq modifies: `src/agent/factory.py`
- Direct context: `factory.py.q.yaml`
- Neighbors: `base_agent.py.q.yaml`, `config.py.q.yaml` (imported by factory)
- Result: 3 context files instead of 117!

## Budget Enforcement

Multiple layers of protection in `lib_ai.py`:

1. **Max Files**: Limit number of context files
2. **Per-File Cap**: Truncate individual large files
3. **Total Budget**: Stop adding context when budget exhausted
4. **Hard Limit**: Nuclear option - drop ALL context if > 9.5MB
5. **Logging**: Always logs final prompt size for debugging

## Running a Full Cycle

No changes to your workflow! Just run as normal:

```bash
./qonqrete.sh --mode program
```

InspeQtor automatically:
1. Runs per-briq reviews
2. Aggregates into meta-review
3. Outputs single `cyqle{N}_reqap.md`

## Troubleshooting

### Still hitting limits?

Reduce budgets in `config.yaml`:
```yaml
agents:
  inspeqtor:
    max_prompt_chars_per_briq: 300000    # Lower from 500K
    max_context_files_per_briq: 20       # Fewer files
```

### Want more context per briq?

Increase depth:
```yaml
agents:
  inspeqtor:
    include_neighbor_depth: 2            # 2-hop neighbors
    max_context_files_per_briq: 60       # More files allowed
```

### Debug mode

Check prompt sizes in stderr:
```
[PROMPT] Final size: 347,291 chars | Context files: 23
```

## Version History

- **v0.8.3**: Interleaved Pipeline (Build → Review → Build → Review)
  - ConstruQtor now validates each briq immediately after building
  - Local validation (syntax, imports) runs per-briq with no AI
  - Optional AI quick review per briq (`ai_quick_review: true`)
  - Per-briq reqaps generated during construction
  - InspeQtor aggregates and does final meta-review
  - Fixed various bugs from v0.8.2

- **v0.8.2**: Multi-Stage Inspeqtion with Retry + Local Verification
  - Per-briq retry mechanism (configurable max_attempts)
  - `stop_on_briq_fail` option for fail-fast or fail-tolerant modes
  - LoQal Verifier for deterministic syntax/import checking
  - Verification results appended to reqap (uses existing promote_reqap flow)
  
- **v0.9.0**: Two-Stage Inspeqtion system (internal)
  - Per-briq tactical reviews
  - Meta-review aggregation
  - Budget enforcement in lib_ai.py
  - Context filtering by relevance
