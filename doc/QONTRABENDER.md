# Qontrabender - The Cache Bender 🌀 (v0.8.0)

> Local sovereignty over remote RAM - Policy-driven Variable Fidelity

Qontrabender is QonQrete's sophisticated hybrid caching agent that manages context assembly with intelligent content classification. All behavior is controlled via `caching_policy.yaml`.

## Key Features

- **Policy-Driven Configuration**: All behavior controlled via `caching_policy.yaml`
- **Multiple Operational Modes**: 6 pre-configured modes for different use cases
- **Variable Fidelity**: Mixes MEAT (full code) + BONES (skeletons) intelligently
- **Schema Validation**: Bad YAML can't brick your flow
- **Improved Volatile Detection**: Multiple signals (cycle, diff, git, mtime)
- **Fidelity Rules Engine**: Configurable per-file treatment rules

## The "Compositor" Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DATA LAKE (Local)                                │
│                                                                         │
│   qodeyard/ (MEAT)           bloq.d/ (BONES)        qontext.d/ (SOUL)   │
│   ├── api.py (FULL)          ├── api.py (SKEL)      ├── api.q.yaml      │
│   ├── models.py (FULL)       ├── models.py (SKEL)   ├── models.q.yaml   │
│   └── legacy_lib.py (FULL)   └── legacy_lib.py(SKEL)└── legacy.q.yaml   │
│                                                                         │
│             │                        │                      │           │
│             └───────────┬────────────┴──────────────────────┘           │
│                         ▼                                               │
│              ┌───────────────────────┐                                  │
│              │    QONTRABENDER       │                                  │
│              │   "The Compositor"    │                                  │
│              ├───────────────────────┤                                  │
│              │  caching_policy.yaml  │ ← Policy-driven behavior         │
│              │                       │                                  │
│              │ 1. Validate Schema    │ ← Prevent bad config             │
│              │ 2. Load Mode Config   │ ← 6 operational modes            │
│              │ 3. Detect Volatile    │ ← Multi-signal detection         │
│              │ 4. Evaluate Rules     │ ← Fidelity rules engine          │
│              │ 5. Assemble & Hash    │ ← Content-addressed caching      │
│              └──────────┬────────────┘                                  │
│                         ▼                                               │
│                   qache.d/ (The Ledger)                                 │
│                   ├── manifest.json         (local truth)               │
│                   ├── ledger.db             (hash→cache_id)             │
│                   ├── .active_cache_id      (for lib_ai.py)             │
│                   ├── sync.log              (audit trail)               │
│                   ├── decisions.log         (debug_repro mode)          │
│                   └── payloads/v*.txt       (version history)           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                             │
                             │ (Optional: cyber_* modes)
                             ▼
                    [ Remote Cache API ]
```

## Operational Modes

Select mode in `config.yaml`:

```yaml
agents:
  qontrabender:
    policy_file: "./caching_policy.yaml"
    mode: "local_smart"  # ← Select your mode
```

| Mode | Description | Remote Cache | Use Case |
|------|-------------|:------------:|----------|
| `local_fast` | Ultra-fast, skeleton only | ❌ | Quick iterations |
| `local_smart` | Variable fidelity, balanced | ❌ | **Default - recommended** |
| `cyber_bedrock` | Stable bedrock in remote cache | ✅ | Long-running projects |
| `cyber_aggressive` | Aggressive caching | ✅ | Big refactors |
| `paranoid_mincloud` | Skeletons only to cloud | ✅ | Security-conscious |
| `debug_repro` | Maximum audit logging | ❌ | Debugging issues |

### Mode Details

#### `local_fast`
- No remote cache
- Mostly skeleton + tiny hotset
- Minimal disk I/O
- Best for rapid iteration

#### `local_smart` (Recommended)
- No remote cache dependency
- Variable fidelity based on core score
- Strong reproducibility
- Best balance of context and efficiency

#### `cyber_bedrock`
- Remote cache for stable files
- Full code for high-utility files
- TTL keepalive management
- Low churn, good reuse

#### `cyber_aggressive`
- More files in remote cache
- Higher token budgets
- More cache rebuilds
- For "big refactor week"

#### `paranoid_mincloud`
- Minimal cloud exposure
- Only docs/schemas + skeletons uploaded
- Secrets redaction enabled
- For security-conscious environments

#### `debug_repro`
- Maximum audit logging
- Writes full payload artifacts
- Detailed decision logs
- For debugging and reproducibility

## Configuration

### config.yaml

```yaml
agents:
  qontrabender:
    provider: local
    model: qontrabender
    policy_file: "./caching_policy.yaml"
    mode: local_smart
```

### caching_policy.yaml Structure

```yaml
version: 1

defaults:
  qache_dir: "qache.d"
  
  volatile_detection:
    use_changed_files_manifest: true
    changed_files_pattern: "exeq.d/*_changed.md"
    use_git_diff_if_available: true
    git_diff_base: "HEAD"
    use_mtime_fallback: true
    mtime_minutes: 15
    use_briq_targets: true
    briq_pattern: "briq.d/*.md"
  
  budgets:
    cached_max_chars: 1800000
    cached_target_chars: 1200000
    hotset_max_chars: 350000
    hotset_target_chars: 220000
  
  classification:
    signals:
      dependency_rank_weight: 0.50
      symbol_count_weight: 0.20
      inbound_refs_weight: 0.20
      doc_presence_weight: 0.10
    thresholds:
      core_score_min: 0.65
      massive_chars_min: 220000
  
  paths:
    exclude_globs:
      - "**/.git/**"
      - "**/node_modules/**"
      - "**/__pycache__/**"
  
  logging:
    verbose_decisions: false

modes:
  local_smart:
    description: "Default - variable fidelity, local only"
    remote_cache:
      enabled: false
    fidelity:
      rules:
        - name: "stable_core_full"
          when:
            tier: "stable"
            core_score_gte: 0.65
            file_chars_lte: 200000
          use: "full"
        - name: "massive_skeleton"
          when:
            file_chars_gte: 220000
          use: "skeleton"
        - name: "default"
          when: {}
          use: "skeleton"

qontext_schema:
  file_path_key: "file_path"
  symbols_key: "symbols"
  deps_key: "dependencies"
```

## Fidelity Rules Engine

Rules are evaluated in order. First matching rule wins.

### Rule Structure

```yaml
fidelity:
  rules:
    - name: "rule_name"
      when:
        tier: "stable"           # stable | volatile
        volatile: false          # true | false
        core_score_gte: 0.65     # >= comparison
        core_score_lte: 0.90     # <= comparison
        file_chars_gte: 100000   # >= comparison
        file_chars_lte: 500000   # <= comparison
        dependency_count_gte: 5  # >= comparison
      use: "full"                # full | skeleton | diff | omit
```

### Comparison Operators

| Suffix | Meaning |
|--------|---------|
| `_gte` | Greater than or equal |
| `_lte` | Less than or equal |
| `_gt` | Greater than |
| `_lt` | Less than |
| (none) | Exact match |

## Volatile Detection

Files detected as "volatile" are excluded from cache and sent fresh via stdin.

### Detection Signals (in priority order)

1. **Changed Files Manifest**: Files in `exeq.d/*_changed.md`
2. **Briq Targets**: Files targeted by current briq
3. **Git Diff**: `git diff --name-only HEAD`
4. **Mtime Fallback**: Files modified within `mtime_minutes`

```yaml
volatile_detection:
  use_changed_files_manifest: true
  changed_files_pattern: "exeq.d/*_changed.md"
  use_git_diff_if_available: true
  git_diff_base: "HEAD"
  use_mtime_fallback: true
  mtime_minutes: 15
  use_briq_targets: true
  briq_pattern: "briq.d/*.md"
```

## Core Score Calculation

Files are scored based on configurable weights:

```yaml
classification:
  signals:
    dependency_rank_weight: 0.50   # How many deps this file has
    symbol_count_weight: 0.20      # Number of symbols defined
    inbound_refs_weight: 0.20      # How many files reference this
    doc_presence_weight: 0.10      # Has docstrings/comments
```

**Score = (dep × 0.50) + (sym × 0.20) + (ref × 0.20) + (doc × 0.10)**

Files with `core_score >= 0.65` are typically considered "core logic".

## CLI Usage

```bash
# Check if sync needed (default mode from config)
python worqer/qontrabender.py

# Use specific mode
python worqer/qontrabender.py --mode cyber_bedrock

# Show current status
python worqer/qontrabender.py --status

# Analyze file fidelity decisions
python worqer/qontrabender.py --analyze

# Validate policy file
python worqer/qontrabender.py --validate

# List available modes
python worqer/qontrabender.py --modes

# Prepare payload for sync
python worqer/qontrabender.py --sync

# Mark as synced with cache ID
python worqer/qontrabender.py --mark-synced caches/xxxxx

# Get active cache ID (for scripts)
python worqer/qontrabender.py --get-cache-id
```

## Example Output

### --analyze
```
═══════════════════════════════════════════════════════════════════════════
  QONTRABENDER FILE ANALYSIS (Mode: local_smart)
═══════════════════════════════════════════════════════════════════════════

  🥩 FULL FIDELITY (8 files):
    models.py                               score=0.85 deps=12  ~4,500 tok
    api.py                                  score=0.78 deps=9   ~3,200 tok
    auth.py                                 score=0.71 deps=7   ~2,100 tok
    utils.py                                score=0.65 deps=5   ~1,800 tok

  🦴 SKELETON FIDELITY (3 files):
    legacy_vendor_lib.py                    Massive file (120,000 chars)
    generated_proto.py                      Massive file (85,000 chars)

  ⚡ VOLATILE (2 files - excluded):
    main.py                                 In changed files manifest
    test_api.py                             Modified within last 15 minutes
═══════════════════════════════════════════════════════════════════════════
```

### --status
```
═══════════════════════════════════════════════════════════════════════════
  QONTRABENDER STATUS: my-project (v0.8.0)
═══════════════════════════════════════════════════════════════════════════
  Policy Version     : 1
  Active Mode        : local_smart
  Mode Description   : Best default. Variable fidelity locally...
  Remote Cache       : DISABLED
  Version            : 5
  Available Modes    : local_fast, local_smart, cyber_bedrock, ...

  FIDELITY STATS:
    🥩 Full files      : 8
    🦴 Skeleton files  : 3
    ⚡ Volatile files  : 2
    📊 Total tokens   : 45,000

  ACTIVE CACHE:
    ID      : caches/abc123
    Version : v5
    Tokens  : 45,000
    Mode    : local_smart
    Expires : 2025-01-15T16:32:00
═══════════════════════════════════════════════════════════════════════════
```

## Schema Validation

Qontrabender validates your policy file on load:

```bash
python worqer/qontrabender.py --validate
```

### Validation Checks

- Required fields present (`version`, `defaults`, `modes`)
- Correct types (int, str, bool, dict, list)
- Valid fidelity values (`full`, `skeleton`, `diff`, `omit`)
- Valid truncation strategies (`head`, `tail`, `middle`)
- Valid render formats (`xml`, `markdown`)
- At least one mode defined

### Error Example

```
  Validating: ./caching_policy.yaml

  Warnings:
    ⚠️  Mode 'custom_mode' is missing 'description'

  ❌ Policy file has errors:
    - 'version' must be an integer, got str
    - Mode 'broken'.fidelity.rules[2].use must be one of: ['full', 'skeleton', ...]
```

## Integration with ConstruQtor

Read active cache ID for API calls:

```python
from qontrabender import Qontrabender
from pathlib import Path

qb = Qontrabender(Path.cwd())
cache_id = qb.get_active_cache_id()

if cache_id:
    # Use in Gemini API call
    config['cachedContent'] = cache_id
```

Or via file:
```bash
CACHE_ID=$(cat qache.d/.active_cache_id)
```

## File Locations

```
worqspace/
├── caching_policy.yaml    # Policy configuration
├── config.yaml            # Mode selection
├── qodeyard/              # MEAT - full code
├── bloq.d/                # BONES - skeletons
├── qontext.d/             # SOUL - semantic intelligence
└── qache.d/               # The Ledger (at qage root)
    ├── manifest.json
    ├── ledger.db
    ├── .active_cache_id
    ├── sync.log
    ├── decisions.log      # (debug_repro mode)
    └── payloads/
        └── payload_v*.txt
```

## Why Variable Fidelity Matters

| Scenario | Skeleton Only | Variable Fidelity |
|----------|---------------|-------------------|
| Refactor using internal logic | ❌ Hallucinations | ✅ Full implementation visible |
| Large vendor libs | ❌ Token budget blown | ✅ Skeleton saves tokens |
| Active edits | ❌ Stale cache | ✅ Volatile detection excludes |
| Core utilities | ❌ Missing context | ✅ High score = full fidelity |

---

*"Don't serve the AI a dinner of only bones"* 🥩🦴
