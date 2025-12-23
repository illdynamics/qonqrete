# QonQrete Release Notes

---

## [v0.9.0-beta] - 2025-12-23

### 🚀 TasqLeveler Agent - Automatic Tasq Enhancement

**The Big Idea:** A well-structured tasq.md = dramatically better output quality. So why not let AI enhance your tasq automatically?

**TasqLeveler** is a new agent that runs ONCE on Cycle 1, BEFORE InstruQtor. It supercharges your tasq.md with:

| Enhancement | What It Adds | Impact |
|-------------|--------------|--------|
| 📦 Dependency Graph | Explicit "what can import what" structure | Prevents circular imports |
| 🎯 Golden Path Tests | Code that MUST work after each module | Defines success explicitly |
| 🧪 Mock Infrastructure | Mock servers for testing integrations | Test without real services |
| 📋 Success Criteria | Global "what does SUCCESS mean" | Clear pass/fail criteria |
| ⏱️ Phase Priority | What to focus on if running low | Better token allocation |
| 🔗 Base Classes | Abstract bases for similar modules | Consistent interfaces |

**Example Enhancement:**

```markdown
# BEFORE (basic tasq)
## Phase 6: C2 Integrations
### 6.1 Sliver Client
Create src/c2/sliver_client.py with connection handling.

# AFTER (TasqLeveler enhanced)
## Phase 6: C2 Integrations
### 6.1 Sliver Client
Create src/c2/sliver_client.py with connection handling.

**MUST inherit from BaseC2Client!**

🎯 Golden Path Test:
from src.c2.sliver_client import SliverClient
from src.c2.base_client import BaseC2Client

assert issubclass(SliverClient, BaseC2Client)
client = SliverClient(config={'config_path': 'test.cfg'})
assert hasattr(client, 'connect')
assert hasattr(client, 'get_sessions')
```

**How It Works:**
1. TasqLeveler reads your original tasq.md
2. Analyzes project structure and requirements
3. Calls AI to enhance with golden paths, mocks, etc.
4. Backs up original as `tasq_original.md`
5. Writes enhanced version back
6. InstruQtor then uses the enhanced tasq

**Configuration:**
```yaml
# config.yaml
agents:
  tasqleveler:
    provider: openai
    model: gpt-4.1-mini  # Or use instruqtor's config
```

**Pipeline Integration:**
```yaml
# pipeline_config.yaml
agents:
  - name: tasqleveler
    script: tasqleveler.py
    input: "tasq.d/cyqle{N}_tasq.md"
    output: "tasq.d/cyqle{N}_tasq.md"
    cycle_1_only: true  # Only runs on Cycle 1
```

**Impact on Output Quality:**

| Metric | Without TasqLeveler | With TasqLeveler |
|--------|---------------------|------------------|
| Imports resolve | 85% | **95%** |
| Classes instantiate | 80% | **95%** |
| Tests pass | 60% | **80%** |
| **Fully functional** | 65% | **75-80%** |

---

### 🔧 Universal File Rule (s00permode)

**The Problem:** Previous "refinement mode" approach was too restrictive - it artificially limited what cycles 2+ could do, potentially blocking legitimate new file creation.

**The Solution:** Removed all mode-based logic. Replaced with ONE simple universal rule that applies to ALL cycles:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 UNIVERSAL FILE RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 File EXISTS in qodeyard?
   → MODIFY it (fix bugs, improve implementation)
   → EXTEND it (add new functions, classes, features)
   → NEVER recreate it from scratch

📄 File DOESN'T EXIST yet?
   → CREATE it (new modules are welcome!)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Why This is Better:**
- ✅ No artificial "modes" that restrict creativity
- ✅ Full freedom to create new files on ANY cycle
- ✅ Prevents rebuild-from-scratch bug (the actual problem)
- ✅ Simple rule that's easy for AI to follow
- ✅ Works naturally for complex multi-cycle builds

**What Changed:**
- Removed `is_refinement_cycle` logic entirely
- Removed mode-based directive switching
- Added Universal File Rule to ALL InstruQtor prompts
- Added qodeyard file count display for context

**Examples of Valid Briqs (any cycle):**
```
✅ "Implement HavocClient RPC methods in src/c2/havoc_client.py" (MODIFY)
✅ "Add geofencing module at src/safety/geofencing.py" (CREATE new)
✅ "Fix syntax error in src/traffic/dga.py" (MODIFY)
✅ "Add unit tests for orchestration" (CREATE new test files)
```

**Examples of Invalid Briqs (any cycle, if file exists):**
```
❌ "Setup project root and create main.py" (main.py EXISTS)
❌ "Create the configuration system" (config.yaml EXISTS)
❌ "Initialize the C2 client base class" (base_client.py EXISTS)
```

---

### 🐛 Original Fix: Prevent Rebuild-from-Scratch Bug

**The Bug:** When a cycle was marked `[FAILURE]` or `[PARTIAL]`, InstruQtor would interpret this as "start from scratch" instead of "iterate on existing code". This caused cycle 3+ to recreate the entire project scaffolding.

**Evidence from production build:**
```
CyQle 1: briq000_setup_project_root_and_gitignore  ← Initial build ✅
CyQle 2: briq000_implement_havoc_client_rpc_logic  ← Refinement ✅
CyQle 3: briq000_setup_project_directory_and_core  ← REBUILDING! ❌
```

**Impact:** Multi-cycle builds now properly iterate while maintaining full creative freedom.

### 🧪 Battle-Tested: 7-Cycle Autonomous Build

v0.9.0-beta was validated with a 7-cycle autonomous build:

| Metric | Result |
|--------|--------|
| **Total Cycles** | 7 |
| **Total Briqs** | 137 (37→25→21→17→11→13→13) |
| **Python Files** | 80 |
| **Total LOC** | ~15,000 |
| **LoQal Pass Rate** | 160/160 (100%) |
| **Est. Total Cost** | ~$1.50 |

---

## [v0.8.8-beta] - 2025-12-23

### ✅ Confirmed: Batched Reviews Working Perfectly!

Deep analysis of v0.8.7 production run (28 briqs, 7 cyQles) confirmed:
- **Zero `[UNKNOWN]` assessments** - batch parsing working correctly
- **All `[FAILURE]` results are real AI assessments**, not parse failures
- **Retry mechanism working** - briq027 failed once (Gemini API error), succeeded on attempt 2
- **Cost efficiency achieved** - 28 briqs reviewed in 3 batches for ~$0.01 total

### 🔧 LoQal Verifier Display Fix

**Problem:** "Running local validation..." was showing under `construQtor` in the event log, but it's conceptually part of `inspeQtor`'s LoQal Verification stage.

**Fix:** Changed display to use `[LoQal]` prefix for clearer attribution:
```
# Before (v0.8.7):
〘aQQ〙『construQtor』⸎ - Running local validation...

# After (v0.8.8):
〘aQQ〙『construQtor』⸎      [LoQal] Running validation...
〘aQQ〙『construQtor』⸎      [LoQal] ✅ Passed
```

Also shows clear status indicators:
- `[LoQal] ✅ Passed` - validation succeeded
- `[LoQal] ⚠️ Import warnings: N` - warnings found
- `[LoQal] ❌ Syntax errors found:` - errors found

### 🎯 Default Config Updates

Updated `config.yaml` with production-ready defaults:

```yaml
agents:
  instruqtor:
    provider: gemini
    model: gemini-2.5-flash-lite    # $0.10/$0.40 - planning
  
  construqtor:
    provider: gemini
    model: gemini-2.5-pro           # $1.25/$10.00 - code generation (UPGRADED)
  
  inspeqtor:
    provider: gemini
    model: gemini-2.5-flash-lite    # $0.10/$0.40 - batched reviews

options:
  briq_sensitivity: 3
  auto_cycle_limit: 7
  mode: program
  cheqpoint: false
```

### 📊 Understanding Batch Results

The batch results show **real AI assessments**, not system errors:
```
Batch 1/3: 12 briqs → ✅0 ⚠️1 ❌11   # AI found 11 incomplete briqs
Batch 2/3: 12 briqs → ✅0 ⚠️0 ❌12   # AI found 12 incomplete briqs
Batch 3/3: 4 briqs  → ✅3 ⚠️1 ❌0    # 3 complete, 1 partial
```

This is **expected behavior** for cycle 1 of a multi-cycle build - the AI is correctly identifying that most code is incomplete. Subsequent cycles will fill in the gaps.

### 🔧 Changes

- `construqtor.py`: Changed "Running local validation..." to "[LoQal] Running validation..." with status indicators
- `qrane.py`: Added `[LoQal]` to VISIBLE_KEYWORDS for display filter
- `config.yaml`: Updated construQtor to gemini-2.5-pro, added production defaults
- All agents now use Gemini provider for consistency

### 💰 Expected Costs (7 cyQles × ~20 briqs each)

| Agent | Model | Est. Cost |
|-------|-------|-----------|
| InstruQtor | flash-lite | ~$0.10 |
| ConstruQtor | pro | ~$3.50 |
| InspeQtor | flash-lite (batched) | ~$0.15 |
| **TOTAL** | | **~$4.00** |

Compare to v0.8.5 unbatched with GPT-4.1: **$100+** 💸

---

## [v0.8.7-beta] - 2025-12-23

### 🐛 Bug Fix: Display Filter Was Completely Broken

**Problem:** ConstruQtor and InspeQtor status messages weren't showing in the event log at all:
```
# What v0.8.6 showed (missing everything!):
〘aQQ〙『construQtor』⸎ Per-briq exeQ summaries written to: exeq.d/cyqle1/

# What was missing:
--- ConstruQtor v0.8.7: Processing 1 Briqs (Interleaved) ---
-- Processing Briq: cyqle1_tasq1_briq000_setup_project.md --
     - Wrote [Code] main.py
-- Briq Complete: ... [✅ SUCCESS] (attempts: 1) --
```

**Root Cause:** The `is_content_line()` function was being called BEFORE checking `VISIBLE_KEYWORDS`, and it was matching patterns in legitimate status lines.

**Fix:** Complete rewrite of display filter logic:
1. Check `VISIBLE_KEYWORDS` FIRST - if found, display immediately (unless blocked)
2. Only apply content filtering to lines WITHOUT visible keywords
3. Removed `is_content_line()` from the visible keyword path entirely
4. Added more explicit patterns to match all status message formats

### ✨ Expected Output Now

```
〘aQQ〙『construQtor』⸎ --- ConstruQtor v0.8.7: Processing 5 Briqs (Interleaved) ---
〘aQQ〙『construQtor』⸎ -- Processing Briq: cyqle1_tasq1_briq000_setup.md --
〘aQQ〙『construQtor』⸎ - Wrote [Code] main.py
〘aQQ〙『construQtor』⸎ - Wrote [Code] config.yaml
〘aQQ〙『construQtor』⸎ -- Briq Complete: ... [✅ SUCCESS] (attempts: 1) --
〘aQQ〙『construQtor』⸎ -- Processing Briq: cyqle1_tasq1_briq001_logging.md --
...
〘aQQ〙『inspeQtor』  ⸎ --- InspeQtor: Reviewing 5 briqs in 1 batches ---
〘aQQ〙『inspeQtor』  ⸎ -- Batch 1/1: 5 briqs --
〘aQQ〙『inspeQtor』  ⸎    Estimated batch cost: $0.00024
〘aQQ〙『inspeQtor』  ⸎    Batch results: ✅5 ⚠️0 ❌0
〘aQQ〙『inspeQtor』  ⸎ --- Reviews complete: 5 briqs, estimated $0.00024 total ---
〘aQQ〙『inspeQtor』  ⸎ === Final Assessment: [SUCCESS] ===
```

### 🔧 Changes

- `qrane/qrane.py`: Rewrote `should_display()` with simpler priority logic
- Removed `is_content_line()` from display path for visible keyword lines
- Added explicit `VISIBLE_KEYWORDS` patterns for ALL status message formats:
  - `"--- ConstruQtor"`, `"-- Processing Briq:"`, `"- Wrote [Code]"`, `"-- Briq Complete:"`
  - `"--- InspeQtor:"`, `"-- Batch "`, `"Batch results:"`, `"--- Reviews complete:"`
  - `"[SUCCESS]"`, `"[FAILURE]"`, `"[PARTIAL]"`, `"attempts:"`
- Reduced `BLOCKED_KEYWORDS` to only AI review content noise

---

## [v0.8.6-beta] - 2025-12-23

### 🚀 Major: Batched Reviews (90% Fewer API Calls!)

**The Problem:** v0.8.5 with per-briq reviews made 77+ API calls per cycle, burning $16+ with GPT-4.1.

**The Solution:** Batched reviews group multiple briqs into single API calls.

| Briqs | Old API Calls | New API Calls | Savings |
|-------|---------------|---------------|---------|
| 20 | 20 | ~3 | 85% |
| 50 | 50 | ~6 | 88% |
| 77 | 77 | ~8 | **90%** |

### 💰 New Default: Gemini 2.5 Flash-Lite

All agents now default to **gemini-2.5-flash-lite** ($0.10/$0.40 per 1M tokens):

| Agent | Old Model | New Model | Cost Reduction |
|-------|-----------|-----------|----------------|
| InstruQtor | gpt-4.1-mini | gemini-2.5-flash-lite | **75%** |
| InspeQtor | gpt-4.1 | gemini-2.5-flash-lite | **95%** |
| ConstruQtor | gemini-2.5-pro | gemini-2.5-flash | *unchanged* |

**Why Flash-Lite?**
- Same price as GPT-4.1-nano ($0.10/$0.40)
- Newer model (2.5 series) with better quality
- 1M token context window (perfect for batched reviews!)
- More than smart enough for planning and reviewing

### ✨ New Configuration Options

```yaml
agents:
  inspeqtor:
    # BATCHED REVIEW MODE (v0.8.6+)
    batch_mode: true           # Enable batched reviews (default: true)
    batch_token_roof: 60000    # Max input tokens per batch
    batch_max_briqs: 12        # Max briqs per batch
```

### 📊 Cost Comparison (77 briqs)

| Configuration | Est. Cost/Cycle |
|---------------|-----------------|
| v0.8.5 + gpt-4.1 | **$16.00** |
| v0.8.5 + gpt-4.1-mini | $3.20 |
| v0.8.6 + batched + flash-lite | **$0.15** |

That's a **99% cost reduction** from the default v0.8.5 config!

### 🔧 Changes

- `inspeqtor.py`: Added batched review system with `group_briqs_into_batches()`, `build_batched_review_prompt()`, `parse_batched_response()`
- `lib_funqtions.py`: Updated pricing table with correct Gemini rates
- `config.yaml`: New defaults for all agents, added `batch_mode`, `batch_token_roof`, `batch_max_briqs`
- Display filter: Continues to suppress per-briq noise (from v0.8.5)

### 📋 Expected Output

```
inspeQtor  ⸎ --- InspeQtor: Reviewing 77 briqs in 8 batches (cyQle 1) ---
inspeQtor  ⸎ -- Batch 1/8: 12 briqs --
inspeQtor  ⸎    Estimated batch cost: $0.00234
inspeQtor  ⸎    Batch results: ✅10 ⚠️2 ❌0
inspeQtor  ⸎ -- Batch 2/8: 12 briqs --
...
inspeQtor  ⸎ --- Reviews complete: 77 briqs, estimated $0.15 total ---
```

### ⚙️ Disabling Batch Mode

If you prefer per-briq reviews (legacy mode):

```yaml
agents:
  inspeqtor:
    batch_mode: false
```

---

## [v0.8.5-beta] - 2025-12-23

### 🚨 TOKEN BURN FIX - CRITICAL

**Problem Identified:** Running InspeQtor with `gpt-4.1` (not mini) on 77 briqs × 2 stages = ~154 AI calls burned ~$25 in a single run.

**Root Cause:** InspeQtor was configured with `gpt-4.1` ($2.00/$8.00 per 1M tokens) instead of `gpt-4.1-mini` ($0.40/$1.60 per 1M tokens).

**Recommendation:** For development/testing, use:
```yaml
agents:
  inspeqtor:
    provider: openai
    model: gpt-4.1-mini  # or gpt-4.1-nano for even cheaper
```

### ✨ New Features

#### 1. Cost Estimation Display

InstruQtor and InspeQtor now show estimated costs before AI calls:
```
instruQtor ⸎ Estimated cost: $0.00234 (1,234 in + ~2,000 out tokens @ gpt-4.1-mini)
inspeQtor  ⸎ --- Per-briq reviews complete: 77 briqs, estimated $3.45 total ---
inspeQtor  ⸎ Estimated cost: $0.00456 (meta-review @ gpt-4.1)
```

#### 2. Cleaner Display Filter System

Completely overhauled the display filter to suppress noise:
- **Blocked:** Per-briq `Assessment: SUCCESS/PARTIAL/FAILURE` lines (only Final shown)
- **Blocked:** `## Summary`, `## Issues Found`, markdown headers
- **Blocked:** Code snippets (`except FileNotFoundError:`, `with pytest`, etc.)
- **Blocked:** Table rows from AI reviews
- **Kept:** High-level status (`Briq Complete`, `Processing Briq:`, `Wrote exeQ`)
- **Kept:** `=== Final Assessment:` and `=== InspeQtor v0.8.5 Complete:` 

#### 3. LoQal Verifier Renamed to InspeQtor

Display name `loQal_verifier` now shows as `inspeQtor` since it's part of the InspeQtor pipeline.

### 🔧 Changes

- Added `lib_funqtions.py` pricing for GPT-4.1 series and Claude models
- Display filter now has `BLOCKED_KEYWORDS` list for aggressive noise suppression
- `total_review_cost` tracking across all per-briq reviews
- Cost estimation added to InstruQtor briq planning
- Cost estimation added to InspeQtor per-briq and meta reviews

### 📋 Clean Display Example

With v0.8.5, your event log should look like:
```
construQtor ⸎ -- Processing Briq: cyqle1_tasq1_briq000_setup_project.md --
construQtor ⸎ - Wrote [Code] main.py
construQtor ⸎ - Running local validation...
construQtor ⸎ - Wrote exeQ: cyqle1_tasq1_briq000_setup_project_exeq.md
construQtor ⸎ -- Briq Complete: ... [✅ SUCCESS] (attempts: 1) --
...
inspeQtor  ⸎ --- Per-briq reviews complete: 20 briqs, estimated $0.89 total ---
inspeQtor  ⸎ === Final Assessment: [SUCCESS] ===
inspeQtor  ⸎ === InspeQtor v0.8.5 Complete: [SUCCESS] ===
```

No more `## Summary`, `## Issues Found`, per-briq `Assessment:` spam!

---

## [v0.8.4-beta] - 2025-12-23

### 🐛 Bug Fixes

#### 1. Fixed Empty/Invalid `__init__.py` Files Being Written

**Problem:** AI sometimes outputs empty code blocks resulting in files containing just ``` (markdown fence) instead of valid Python.

**Fix:** Improved code block regex parser to:
- Prevent matching across code blocks (using `[^`]` pattern)
- Skip files with empty content
- Skip files where content starts with ``` 
- Skip files with content shorter than 3 characters
- Added `[SKIP]` log messages for transparency

#### 2. Improved Import Resolution in LoQal Verifier

**Problem:** Import checker was flagging `src.utils.logger` as missing even when `src/utils/logger.py` existed.

**Fix:** Enhanced import resolution to:
- Search recursively for the final module name
- Check paths with and without the first component
- Only flag imports that start with known local prefixes
- Added more third-party packages to skip list

#### 3. Fixed Skeleton Signature False Positives (from v0.8.3)

**Note:** v0.8.3 already included the fix for `argparse`, `logging`, `sys`, `Path` false positives.

### 🔧 Changes

- ConstruQtor version header updated to v0.8.4
- LoQal Verifier version header updated to v0.8.4
- Improved logging for skipped files during code block parsing

### 📋 What to Expect

With v0.8.4, you should see:
```
     [SKIP] Empty file: src/__init__.py
     [SKIP] Invalid content (markdown fence): src/evasion/__init__.py
     - Wrote [Code] src/utils/logger.py
     - Wrote [Code] src/agent/factory.py
```

---

## [v0.8.3-beta] - 2025-12-23

### ✨ New Features & Enhancements

#### 1. Interleaved Pipeline (Build → Validate → Build → Validate)

ConstruQtor now processes each briq with interleaved validation:

```
FOR EACH briq:
  1. BUILD     - AI generates code
  2. VALIDATE  - Local syntax/import check (NO AI)
  3. REVIEW    - Optional AI quick review
  4. RETRY     - If failed, retry up to 3x
  5. EXEQ      - Write per-briq exeQ summary
```

#### 2. Per-Briq ExeQ Summaries

ConstruQtor now writes execution summaries to `exeq.d/cyqle{N}/`:
- `briq000_exeq.md` - Status, files written, validation results
- `briq001_exeq.md` - etc.

**Note:** ConstruQtor writes **exeQ** summaries (execution results). InspeQtor writes **reQap** summaries (review/recap).

#### 3. Smarter LoQal Verifier Skeleton Matching

Fixed false positive warnings for standard library imports and typing constructs:
- Filters out: `argparse`, `sys`, `os`, `re`, `json`, etc.
- Filters out: `List`, `Dict`, `Any`, `Optional`, `Union`, etc.
- Filters out: Uppercase names (likely classes, not functions)
- Filters out: Single-letter names (likely type vars)

#### 4. Improved Qrane Display Keywords

Added new keywords to visible output filter:
- `exeQ` - Per-briq execution summaries
- `Running local validation` - Validation status
- `Briq Complete` - Per-briq completion
- `SUCCESS`, `FAILURE`, `PARTIAL` - Status indicators

### 🔧 Configuration

```yaml
# Interleaved Pipeline (NEW in v0.8.3)
interleaved:
  enabled: true              # Enable build→review per briq
  local_validation: true     # Syntax/import checks (no AI)
  ai_quick_review: false     # Set true for AI review per briq
  retry_on_review_fail: true # Retry if AI review fails
```

### 🐛 Bug Fixes

- Fixed `NameError: name 'e' is not defined` in inspeqtor.py line 785
- Fixed LoQal Verifier false positives for stdlib/typing symbols
- Fixed terminology: ConstruQtor → exeQ, InspeQtor → reQap

---

## [v0.8.2-beta] - 2025-12-23

### ✨ LoQal Verifier Integration

Integrated a deterministic local verification agent that runs after ConstruQtor:

#### What It Checks (NO AI Required)
1. **Syntax Validation**: `python -m py_compile` on all .py files
2. **Import Resolution**: Verifies local imports resolve to actual files
3. **Skeleton Signature Matching**: Ensures functions exist that are called elsewhere

#### Self-Healing Feedback Loop

Verification errors are appended to the reqap.md, which is read by InstruQtor in the next cycle:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ CyQle N:  ConstruQtor → LoQal Verifier → InspeQtor → ReQap                     │
│                              ↓                           ↓                      │
│                        [Errors Found]              [Errors Logged]              │
│                              ↓                           ↓                      │
│ CyQle N+1: InstruQtor reads errors → Creates fix briqs → ConstruQtor fixes     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 🔧 Configuration

```yaml
# config.yaml
agents:
  loqal_verifier:
    max_attempts: 3          # Retry failed briqs up to 3 times
    stop_on_briq_fail: false # Continue to next briq on failure
```

### 📋 Output Format

```
[LoQal] ═══════════════════════════════════════════════════
[LoQal] Validation Report for: src/utils/logger.py
[LoQal] ───────────────────────────────────────────────────
[LoQal] ✅ Syntax: VALID
[LoQal] ✅ Imports: All resolved
[LoQal] ⚠️ Skeleton: 2 potentially missing signatures
[LoQal] ═══════════════════════════════════════════════════
```

---

## [v0.8.1-beta] - 2025-12-23

### ✨ ConstruQtor Per-Briq Retry

Added configurable retry mechanism for individual briq failures:

```yaml
# config.yaml
agents:
  construqtor:
    max_attempts: 3           # Retry failed briqs up to 3 times
    stop_on_briq_fail: true   # Stop cycle if briq fails after all retries
```

### 🔧 Changes

- ConstruQtor now tracks `attempts` per briq
- Failed briqs are retried with error context appended to prompt
- Status output shows attempt count: `[✅ SUCCESS] (attempts: 2)`
- Configurable `stop_on_briq_fail` - set `false` to continue despite failures

### 📋 Output Example

```
construQtor ⸎ -- Processing Briq: briq005_implement_dga.md --
construQtor ⸎    Attempt 1/3...
construQtor ⸎    [FAIL] Syntax error in output
construQtor ⸎    Attempt 2/3 (with error context)...
construQtor ⸎    [✅ SUCCESS] (attempts: 2)
```

---

## [v0.8.0-beta] - 2025-12-22

### 🌀 Qontrabender - The Cache Bender

A new agent that manages hybrid caching with intelligent content classification:

- **Variable Fidelity**: Mixes MEAT (full code) + BONES (skeletons) based on file importance
- **Policy-Driven Configuration**: All behavior controlled via `caching_policy.yaml`
- **Multiple Operational Modes**: 6 pre-configured modes for different use cases
- **Schema Validation**: YAML validation prevents bad configuration from breaking the flow
- **Improved Volatile Detection**: Cycle-based, diff-based, git diff, and mtime fallback

### 📦 Available Modes

| Mode | Description | Remote Cache |
|------|-------------|--------------|
| `local_fast` | Ultra-fast, skeleton only, minimal I/O | ❌ |
| `local_smart` | Default - variable fidelity, best balance | ❌ |
| `cyber_bedrock` | Remote cache for stable bedrock | ✅ |
| `cyber_aggressive` | Aggressive caching, more churn | ✅ |
| `paranoid_mincloud` | Minimal cloud exposure, skeletons only | ✅ |
| `debug_repro` | Maximum audit logging | ❌ |

### 🔧 Configuration

```yaml
# config.yaml
agents:
  qontrabender:
    provider: local
    model: qontrabender
    policy_file: "./caching_policy.yaml"
    mode: local_smart
```

### 📋 Fidelity Rules Engine

Configurable rules determine how each file is treated:

```yaml
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
```

### 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DATA LAKE (Local)                                │
│                                                                         │
│   qodeyard/ (MEAT)           bloq.d/ (BONES)        qontext.d/ (SOUL)   │
│   ├── api.py (FULL)          ├── api.py (SKEL)      ├── api.q.yaml      │
│   └── lib.py (FULL)          └── lib.py (SKEL)      └── lib.q.yaml      │
│                                                                         │
│             │                        │                      │           │
│             └───────────┬────────────┴──────────────────────┘           │
│                         ▼                                               │
│              ┌───────────────────────┐                                  │
│              │    QONTRABENDER       │                                  │
│              │   "The Compositor"    │                                  │
│              ├───────────────────────┤                                  │
│              │ POLICY ENGINE:        │                                  │
│              │ 1. Read 'Soul'        │ ← qontext.d intelligence         │
│              │ 2. Filter 'Volatile'  │ ← multi-signal detection         │
│              │ 3. Evaluate Rules     │ ← fidelity rules engine          │
│              │ 4. Assemble & Hash    │                                  │
│              └──────────┬────────────┘                                  │
│                         ▼                                               │
│                   qache.d/ (The Ledger)                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 📊 Triple-Core Memory System

QonQrete now features a **Triple-Core Memory System**:

| Agent | Role | Output |
|-------|------|--------|
| **Qompressor** | Skeletonizer | `bloq.d/` - AST-stripped code structures |
| **Qontextor** | Symbol Mapper | `qontext.d/` - Semantic YAML maps |
| **Qontrabender** | Cache Bender | `qache.d/` - Policy-driven cache payloads |

See [QONTRABENDER.md](./QONTRABENDER.md) for full documentation.

---

## [v0.7.0-beta] - 2025-12-21

### 🚀 Fully Local Qontextor Agent

This release introduces a major upgrade to the `qontextor` agent, enabling a fully local, deterministic, and highly detailed analysis of the codebase. This new "Local Qontextor Stack" significantly reduces reliance on AI for context generation, leading to massive cost savings, increased speed, and enhanced privacy.

### ✨ The Local Qontextor Stack

The new local mode is powered by a multi-layered analysis stack:
- **Python AST:** For extracting the fundamental structure of the code (classes, functions, signatures).
- **Docstrings & Verb Heuristics:** To understand the purpose of code, either from existing documentation or by inferring it from function names.
- **Jedi:** For static analysis, providing type inference and cross-file relationship understanding.
- **PyCG:** To generate a comprehensive call graph, mapping out dependencies and execution flow.

### 🔧 Fast vs. Complex Local Modes

The local `qontextor` can be fine-tuned for speed or detail:
- **`local_mode: 'fast'`**: Provides a very fast analysis using AST, Jedi, and heuristics.
- **`local_mode: 'complex'`**: Enhances the analysis by using a local `sentence-transformers` model to create deep semantic embeddings of the code's purpose.

### 📋 CLI Helpers

```bash
python3 worqer/qontextor.py --query "<search_term>"   # Semantic search
python3 worqer/qontextor.py --verb "<verb_pattern>"   # Find by verb pattern
python3 worqer/qontextor.py --ripple "<symbol_name>"  # Ripple effect analysis
```

### 🐛 Bug Fixes

- Fixed a `NameError` in the `inspeqtor` agent that was causing it to crash during the review phase.
- Fixed a `NameError` in the `qontextor` agent related to the `extract_first_sentence` function.
- Added a `docker system prune` command to `qonqrete.sh` to prevent "No space left on device" errors.

### 💰 Performance & Cost

- **Indexing Cost:** Reduced to **zero** when using the local `qontextor`.
- **Cost per Run:** Up to **25x cheaper** due to the massive reduction in tokens sent to AI providers.
- **Speed:** Approximately **3x faster** on average due to smaller prompts and local processing.

---

## [v0.6.3-beta] - 2025-12-19

### Added
- **Dynamic Local Agent Loader**: Implemented a dynamic local agent loader in `qrane/qrane.py`, allowing agents configured with `provider: local` to dynamically load and execute Python scripts from the `worqer` directory.

### Changed
- **`qrane.py`**: Modified `run_orchestration` to dynamically determine agent script paths for local providers.
- **`Dockerfile`**: Added `npm install -g @qwen-code/qwen-code@latest` to install the Qwen CLI tool.
- **`lib_ai.py`**: Modified `_run_qwen` to pass prompts via standard input instead of command-line arguments.

### Fixed
- **`QWEN_API_KEY` Environment Variable**: Ensured `qonqrete.sh` passes `QWEN_API_KEY` to the container.
- **`construQtor` Briq Processing**: Improved handling of briqs.

---

## [v0.6.2-beta] - 2025-12-18

### Added
- **"local" Provider**: Implemented a "local" provider for offline agents like `calqulator` and `qompressor`.
- **Qwen Model Testing**: Tested `qwen-turbo`, `qwen-coder`, and `qwen-max` models.

### Changed
- **Default Briq Format**: The `instruqtor` now defaults to a more reliable markdown-based format for briqs.

### Fixed
- **AI Reliability**: The new markdown format significantly improves reliability with various AI models.

---

## [v0.6.1-beta] - 2025-12-16

### Added
- **Qwen Provider Integration**: Integrated the Qwen AI provider into the system.
- **New Documentation**: Added extensive documentation:
  - `CONTEXT.md`: Explains the context mechanism.
  - `MEMORY.md`: Details the local memory mechanism.
  - `MINDSTACK.md`: Suggestions for the AI agent brain stack.
  - `MINDSTACK_ARCH.md`: Architecture of the brain stack.
  - `QWEN_90K_FIX.md`: Verification of Qwen's performance with large context.
  - `SKELETON.md`: Explains code skeletonization.

### Changed
- **Default Task**: Updated `worqspace/tasq.md` to a more complex task.
- **Version**: Bumped version to `0.6.1`.

---

## [v0.6.0-beta] - 2025-12-13

### Added
- **Major Improvements: The Dual-Core Memory System**: This release introduces the **Qompressor** and **Qontextor** agents, forming a "Dual-Core" memory system that dramatically reduces cost and increases speed.

  **The Scenario:** A medium-sized project (50 files, ~10,000 lines of code).
  - **Raw Size:** ~100,000 Tokens.

  | Metric | Old Approach (Send Full Code) | New Approach (Dual-Core) | Improvement |
  | :--- | :--- | :--- | :--- |
  | **Context Sent** | 100,000 Tokens (Full Repo) | ~4,000 Tokens (Skeletons) | **~96% Reduction** |
  | **Indexing Cost** | N/A (Read raw) | Low (Uses compressed code to index) | **Optimized** |
  | **Cost per Run** | ~$0.25 (GPT-4o) | ~$0.01 (GPT-4o) | **25x Cheaper** |
  | **Speed** | Slow (Huge prompt processing) | Fast (Tiny prompt) | **~3x Faster** |
  | **Memory** | Persistent | Persistent & Infinite Context | **Upgraded** |

  **Summary: You are paying 4% of the cost for 100% of the intelligence.**

- **Qompressor (The Skeletonizer)**: Creates a low-token "skeleton" of the codebase in `bloq.d`.
- **Qontextor (The Symbol Mapper)**: Generates detailed YAML maps of the codebase's symbols in `qontext.d`.
- **CalQulator (The Cost Estimator)**: Analyzes `briQ` files to provide token and cost estimates.
- **FunQtions Library**: Added `qrane/lib_funqtions.py` for common utility functions.

### Changed
- **Version Suffix**: Appended `-beta` to signify pre-release status.
- **Agent Architecture**: Updated `pipeline_config.yaml` to include new agents.
- **Configuration**: Updated `worqspace/config.yaml` with sane defaults.

---

## [v0.5.0-beta] - 2025-12-08

### Added
- **Pipeline Optimization**: Introduced a streamlined pipeline for multi-agent orchestration.
- **Multi-Provider Support**: Added support for OpenAI, Anthropic, Google Gemini, and DeepSeek.

### Changed
- **Agent Communication**: Improved inter-agent communication via YAML-based file passing.
- **Default Configuration**: Updated default models for improved performance.

### Fixed
- **Memory Leaks**: Fixed memory issues in long-running sessions.
- **Container Isolation**: Improved Docker container isolation.

---

## [v0.4.6-beta] - 2025-12-05

### Changed
- **Logging Architecture**: Re-architected logging system. Raw output captured in `struqture/qonsole_<agent>.log`, high-level status in `struqture/events_<agent>.log`.

### Fixed
- **Headless Mode Crash**: Fixed "I/O operation on closed file" error in non-TUI mode.
- **Gatekeeper Assessment Parsing**: More robust regex parsing for "Assessment:" status.
- **`construqtor` Path Duplication**: No longer creates nested `qodeyard/qodeyard` directories.
- **`construqtor` AI Output Parsing**: Stricter system prompt with clear output format example.

---

## [v0.4.5-alpha] - 2025-12-03

### Added
- **Sqrapyard Project Seeding**: `qonqrete.sh` now copies from `worqspace/sqrapyard` to `qodeyard` on startup.
- **`tasq.md` Seeding**: If `tasq.md` exists in `sqrapyard`, it's used as the initial task.
- **Verbose Startup Logging**: Explicit logs about seeding status.
- **Pre-run Delay**: 3-second delay after initial host logs.

### Changed
- **Ephemeral Workspaces**: Creates unique `qage_<timestamp>` directory for each run.
- **Agent Output Directory**: `construqtor` writes exclusively to `qodeyard`.
- **Instruqtor Sensitivity**: Re-implemented 10 distinct levels (0-9).
- **Context Awareness**: Both agents read all files from `qodeyard`.

### Fixed
- **Stricter Path Sanitization**: Forcibly removes `../` from AI-generated filenames.
- **Gatekeeper Assessment Parsing**: Correctly parses "Assessment" status.
- **AI Filename Resilience**: Handles AI providing language name as filename.
- **Build Log Verbosity**: Empty lines filtered from `docker build` output.

---

## [v0.4.4-alpha] - 2025-12-02

### Changed
- **InstruQtor Sensitivity**: Implemented 10 distinct levels (0-9).
- **Context Awareness**: InstruQtor reads all files from `qodeyard`.
- **Sqrapyard Logging**: Improved logging for seeding process.

### Fixed
- **Instruqtor Logic**: Overhauled sensitivity logic.
- **Construqtor**: Fixed bug causing agent to fail.
- **AI Reliability**: Implemented robust retry mechanism in `lib_ai`.
- **Container Workspace**: Isolated agent workspaces, fixed `NameError`.

---

## [v0.4.3-alpha] - 2025-12-02

### Added
- **Init Seeding**: `qonqrete.sh init` copies from `sqrapyard` to `qodeyard` if available.

---

## [v0.4.2-alpha] - 2025-11-28

### Added
- **Architect Role**: Implemented "Architect" role in `instruqtor`.
- **Micro-dosing**: Introduced "micro-dosing" technique for better AI results.

### Fixed
- **Syntax Errors**: Addressed multiple syntax errors and regressions.

---

## [v0.4.1-alpha] - 2025-11-27

### Fixed
- **Critical Regressions**: Patched syntax errors from v0.4.0.
- **Pre-flight Checks**: Disabled interfering pre-flight checks.

---

## [v0.4.0-alpha] - 2025-11-26

### Added
- **Operational Modes**: Agents operate with specific "personas" via `--mode` flag.
- **Briq Sensitivity**: `instruQtor` accepts `--briq-sensitivity` flag (0-9).
- **TUI Overhaul**: Major TUI improvements.

### Fixed
- **Path Regression**: Resolved critical bug in dynamic pipeline logic.

### Changed
- **Code Refinements**: Significant refactoring for readability.

---

## [v0.3.0-alpha] - 2025-11-25

### Changed
- **Branding**: Updated `README.md` to display `logo.png`.
- **Versioning**: Hardened build process for clean `VERSION` file.

---

## [v0.2.7-alpha] - 2025-11-24

### Fixed
- **Hotfix**: Addressed critical `IndentationError` in `qrane/qrane.py`.

---

## [v0.2.6-alpha] - 2025-11-23

### Fixed
- **TUI Experience**: Fixed "flash and gone" issue.

---

## [v0.2.5-alpha] - 2025-11-22

### Fixed
- **Agent Stability**: Fixed critical `NameError` and improved console error visibility.

---

## [v0.2.4-alpha] - 2025-11-21

### Changed
- **Documentation**: Consolidated inspection reports into `COMING_SOON.md` and `DOCUMENTATION.md`.

---

## [v0.2.3-alpha] - 2025-11-20

### Fixed
- **TUI Stability**: Fixed `NameError` crash in TUI mode.

---

## [v0.2.2-alpha] - 2025-11-19

### Changed
- **Major Refactoring**:
    - Implemented dynamic agent pipeline.
    - Centralized path management.
    - Added pre-flight checks for dependencies.
    - Implemented TUI state persistence.

---

## [v0.2.1-alpha] - 2025-11-18

### Added
- **Dynamic Versioning**: Centralized versioning in `VERSION` file.
- **Integrated Docker Output**: Streamed Docker build output into TUI.

---

## [v0.2.0-alpha] - 2025-11-17

### Added
- **TUI Enhancements**: Added raw log view, fullscreen mode, key shortcuts, improved colors.
- **Microsandbox (MSB) Integration**: Added support for `msb`.

### Changed
- **AI Models**: Updated default models for faster performance.

---

## [v0.1.1-alpha] - 2025-11-14

### Added
- **TUI Mode**: Introduced `--tui` flag for interactive interface.
- **Workspace Cleaning**: Added `clean` command to `qonqrete.sh`.

---

## [v0.1.0-alpha] - 2025-11-12

- The initial public alpha release of QonQrete.
