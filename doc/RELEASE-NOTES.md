# QonQrete Release Notes

---

## [v1.0.4-stable] — Container Runtime Auto-Detect (Addition)

### 🐳 MULTI-ENGINE SUPPORT — Docker, Podman, and Cross-Platform

This addition extends `qonqrete.sh` with automatic container runtime detection for macOS, Windows, and Linux. No pipeline changes. Fully backward compatible.

---

#### 🆕 NEW FEATURES

**1. Container Engine Auto-Detection**
- Priority: `CONTAINER_ENGINE` env → `--podman`/`--docker` CLI → auto-detect
- Auto-detect: docker first, then podman, else clear error with install links
- New `-p`/`--podman` CLI flag alongside existing `-d`/`--docker`

**2. Engine-Aware Wrappers**
- `engine_build()` — docker build / docker buildx build / podman build / msb build
- `engine_run()` — docker run / podman run / msb run (with security flags)
- `engine_run_helper()` — lightweight helper for permission fix / delete operations
- All wrappers preserve: build args, security flags, volume mounts, env vars, logging style, QONQ_VERSION injection

**3. Build Backend Detection**
- Docker: auto-detects `buildx` availability, falls back to plain `docker build`
- Podman: uses `podman build` (no buildx requirement)
- Override via `BUILD_BACKEND=buildx|plain` env var

**4. macOS Podman Support**
- Idempotent `podman machine init` + `podman machine start` on Darwin
- Clear error messages if machine fails
- No action taken if machine already running

**5. Windows Support**
- WSL2: detected via `/proc/version`, treated as Linux (no special behavior)
- Git Bash / MSYS / MINGW: detected via `uname -s` and `OSTYPE`
- Automatic path normalization for Docker Desktop volume mounts
- Advisory printed: "Git Bash detected. WSL2 is recommended for best compatibility."

**6. Permission & Cleanup Helpers (Engine-Aware)**
- `fix_qage_permissions()` and `delete_qage()` now use whichever engine is available
- Graceful fallback chain: detected engine → docker → podman → warning with manual command

**7. Runtime Info Logging**
- Prints at startup: Container engine, Build backend, OS detected
- Uses existing QonQrete log format

#### ✅ TESTED SUCCESSFULLY ON
- Linux (Fedora 42 & 43) + docker and docker-desktop
- Windows 11 WSL 2 ubuntu and docker desktop
- Mac OS Sequoia 15.7.4 with podman and docker-desktop

#### 📁 CHANGED FILES
| File | Change |
|------|--------|
| `qonqrete.sh` | Full rewrite of container handling: OS detection, engine detection, build backend, engine wrappers, path normalization, Podman machine support |
| `README.md` | Updated System Requirements with multi-platform table and env overrides |
| `doc/RELEASE-NOTES.md` | Added this addition entry |

#### 🚫 NOT CHANGED (confirmation)
- Pipeline order: instruqtor → calqulator → construqtor → inspeqtor → qontextor → qompressor
- Agent logic: zero modifications
- Qontract / Qompressor / Qontextor / InspeQtor: untouched
- MSB mode: preserved
- All 110 tests: unaffected

---

## [v1.0.4-stable] - 2026-02-23

### 🔒 QONTRACT LOCKDOWN — Contract-Enforced Pipeline

This release implements **rocktight contract enforcement** across the entire pipeline. The QONTRACT (project constitution) is now a mandatory, fail-fast dependency with its own dedicated directory and deterministic AST-based verification.

---

#### 🆕 NEW FEATURES

**1. qontract.d/ Migration (Section A)**
- Contract files moved from `qontext.d/` to dedicated `qontract.d/` directory
- `qontract.md` (human-readable) + `qontract.json` (machine-parseable)
- All code paths updated: InstruQtor, ConstruQtor, InspeQtor, QontractGuard
- Zero stale references to old `qontext.d/qontract.*` paths

**2. Fail-Fast Contract Dependency (Section B)**
- New `worqer/runtime_checks.py` with `ensure_qontract_present()` helper
- ConstruQtor and InspeQtor call fail-fast check at startup (cycles > 1)
- QontractGuard NEVER silently skips — empty contract = FAIL with `CONTRACT_MISSING`
- Clear, actionable error messages on missing contract

**3. InspeQtor Context Wiring (Section C)**
- `qodeyard/*` is now the PRIMARY truth source for code review
- `bloq.d/*` and `qontext.d/*` are OPTIONAL with explicit staleness warnings
- Logs clearly state: "NOTE: bloq.d may be stale because qompressor runs after inspeqtor"
- Context log at `struqture/qonsole_inspeqtor.log` includes all paths + totals + staleness notes
- Pipeline order preserved: instruqtor → calqulator → construqtor → inspeqtor → qontextor → qompressor

**4. QontractGuard Enforcement (Section D)**
- Forbidden imports (uuid etc.) — robust AST-based detection
- Exact schema field enforcement for named Pydantic models
- Forbidden field names (e.g. "name") — class-level detection
- ID type rules (int vs str) — annotation checking
- **NEW: Monotonic ID strategy verification** — verifies `next_id=1` + increment or `max()+1` patterns exist
- Required endpoint detection (route decorators)
- JSON + markdown + text summary output formats
- Per-file guard for targeted briq-level checking

**5. Qompressor Indentation Fix (Section E)**
- Fixed hardcoded 4-space indentation that broke class method skeletons
- Summary comments and `pass` statements now use actual function body indentation
- Correct output for module-level functions, class methods, and nested defs
- All skeleton output guaranteed to `ast.parse()` successfully

**6. TasqLeveler (Section G)**
- Kept as implemented (commented in pipeline_config.yaml)
- Documentation updated on how to enable without breaking stage order

---

#### 📁 FILES CHANGED

- `worqer/runtime_checks.py` — **NEW** fail-fast contract dependency helper
- `worqer/qontract_guard.py` — CONTRACT_MISSING violation, monotonic ID strategy, never-skip
- `worqer/instruqtor.py` — Contract output to qontract.d/, fail-fast assertion
- `worqer/construqtor.py` — qontract.d/ paths, fail-fast check, updated context logging
- `worqer/inspeqtor.py` — qontract.d/ paths, fail-fast, qodeyard primary, staleness warnings
- `worqer/qompressor.py` — Indentation-aware summary/pass insertion
- `worqspace/pipeline_config.yaml` — Updated descriptions for v1.0.4-stable
- `tests/test_v1_0_4_stable_smoke.py` — **NEW** 52-test comprehensive smoke suite
- `doc/RELEASE-NOTES.md` — This entry

#### 🧪 TEST RESULTS

- `test_v1_0_4_stable_smoke.py`: 52 passed, 0 failed
- `test_v1_0_4.py`: 58 passed, 0 failed
- Total: 110 tests passing

---


## [v1.0.3-stable] - 2026-02-06

### 🚀 BATCHED BRIQ GENERATION - Bypass Token Limits!

This release introduces **batched briq generation** for high-sensitivity builds, enabling you to generate 50-250+ briqs without hitting LLM token output limits. Perfect for enterprise-scale projects!

---

#### 🆕 NEW FEATURES

**1. Batched Briq Generation (Blueprint → Fabrication Pipeline)**

High-sensitivity builds (sensitivity >= 8) now use a revolutionary 2-phase approach:

- **Phase 1: Blueprint (JSON)** - Generates a JSON list of briq titles and objectives
  - Low-token, guaranteed complete list
  - No risk of truncation at 50+ briqs
  - Clear architectural overview

- **Phase 2: Fabrication (Batched XML)** - Generates full briq content in chunks
  - Processes briqs in batches of 5 (configurable)
  - Each batch fits comfortably within token limits
  - Progressive cost tracking per batch
  - Automatic retry on batch failures

**Benefits:**
- ✅ **Actually get 50-75+ briqs** for sensitivity 10 (previously capped ~30-40)
- ✅ **100-200+ briqs** for sensitivity 14-16 (enterprise mega-projects)
- ✅ **Cost transparency** with per-phase and per-batch cost reporting
- ✅ **Fault tolerance** - Failed batches don't kill entire generation
- ✅ **Automatic fallback** to single-shot if batching fails

**2. Configurable Batching**

New config options in `config.yaml` under `agents.instruqtor`:

```yaml
instruqtor:
  provider: openai
  model: gpt-4.1-nano
  
  # BATCHED GENERATION MODE (v1.0.3+)
  batch_mode: true         # Enable batched generation
  batch_size: 5            # Briqs per batch (default: 5)
```

**When batching activates:**
- `batch_mode: true` AND `sensitivity >= 8` → Batched generation
- `batch_mode: false` OR `sensitivity <= 7` → Traditional single-shot
- Fallback to single-shot if batching fails

---

#### 💡 USAGE EXAMPLES

**Generate 60 briqs for an enterprise project:**
```bash
./qonqrete.sh run -b 10 -c 4 -a  # Sensitivity 10 = 50-75 briqs
```

**Output:**
```
  [CONFIG] Sensitivity: 10 → Target: 60 briqs (range: 50-75)
  [CONFIG] Strategy: Batched (batch_size: 5, batch_mode: true)

🚀 [BATCHED GENERATION] Phase 1: Blueprint (Target: 60 briqs)
  ✅ [BLUEPRINT] Generated 60 briq specifications
  💰 [BLUEPRINT] Cost: $0.02 (8,234 tokens)

🔨 [FABRICATION] Phase 2: Generating 60 briqs in 12 batches (size: 5)
  📦 [Batch 1/12] Fabricating briqs 1-5...
  ✅ [Batch 1] Generated 5 briqs | Cost: $0.03 (12,456 toks)
  ...
  📦 [Batch 12/12] Fabricating briqs 56-60...
  ✅ [Batch 12] Generated 5 briqs | Cost: $0.03 (11,892 toks)

  💰 [FABRICATION] Total Cost: $0.38
  ✅ [COMPLETE] Generated 60 briqs across 12 batches
```

**Generate 150+ briqs for maximum granularity:**
```bash
./qonqrete.sh run -b 15 -c 5 -a  # Sensitivity 15 = 130-200 briqs
```

---

#### 🔍 TECHNICAL CHANGES

| Component | Change | Purpose |
|-----------|--------|---------|
| `instruqtor.py` | Added `generate_briqs_paginated()` | 2-phase briq generation |
| `instruqtor.py` | Phase 1: Blueprint (JSON) | Token-efficient list generation |
| `instruqtor.py` | Phase 2: Fabrication (batched) | Chunked XML generation |
| `instruqtor.py` | Automatic fallback logic | Reliability guarantee |
| `instruqtor.py` | Per-batch cost tracking | Budget transparency |
| `config.yaml` | `batch_mode` config option | Enable/disable batching |
| `config.yaml` | `batch_size` config option | Tune batch granularity |
| Main pipeline | Auto-activates for sens >= 8 | Smart strategy selection |

---

#### 📊 BENCHMARKS

Real-world results from testing:

| Sensitivity | Target Briqs | Old (Single-shot) | New (Batched) | Success Rate |
|-------------|--------------|-------------------|---------------|--------------|
| 8 (Very High) | 35 | 28-32 briqs (truncated) | 35 briqs ✅ | 100% |
| 10 (Ultra) | 60 | 38-45 briqs (truncated) | 60 briqs ✅ | 100% |
| 12 (Hyper) | 90 | FAIL (token limit) | 90 briqs ✅ | 100% |
| 14 (Maximum) | 135 | FAIL (token limit) | 135 briqs ✅ | 98% |
| 16 (QONQRETE MAX) | 200 | FAIL (token limit) | 198 briqs ✅ | 95% |

**Cost comparison** (using gpt-4.1-nano):
- Sensitivity 10 (60 briqs): ~$0.40 total
- Sensitivity 14 (135 briqs): ~$1.20 total
- Still dramatically cheaper than manual development!

---

#### 🎯 RECOMMENDATIONS

**When to use batched generation:**
- ✅ Enterprise projects requiring 50+ briqs
- ✅ Complex multi-layer architectures (sensitivity 10-16)
- ✅ Projects with extensive feature sets
- ✅ When you need guaranteed briq count accuracy

**When to stick with single-shot:**
- ✅ Simple projects (sensitivity 0-7)
- ✅ Quick prototypes (10-30 briqs)
- ✅ When speed > precision
- ✅ Low-token models with large output windows

---

#### 🔄 BREAKING CHANGES

**None!** This is a fully backward-compatible release.
- Default behavior unchanged for sensitivity <= 7
- Batching is opt-in (controlled by `batch_mode: true`)
- Automatic fallback ensures reliability

---

#### 🐛 BUG FIXES

- Fixed: InstruQtor now reliably generates target briq counts for high sensitivity levels
- Fixed: No more truncated briq lists due to token limits
- Fixed: Better error handling for JSON parsing in blueprint phase

---

## [v1.0.2-stable] - 2026-01-20

### 🔄 INVERTED BRIQ SENSITIVITY SCALE & NON-INTERACTIVE RUNS

This release brings a more intuitive briq sensitivity scale, non-interactive qonstruction saving, and Gemini-only Qontrabender activation.

---

#### 🆕 NEW FEATURES

**1. Inverted Briq Sensitivity Scale (0-16)**

The briq sensitivity scale has been INVERTED and EXTENDED for a more intuitive experience:
- **Higher number = MORE briqs** (no more confusion!)
- **Extended range: 0-16** (was 0-9)
- New enterprise-level granularity options (10-16)

| Level | Name | Briq Count | Use Case |
|-------|------|------------|----------|
| 0 | Monolithic | 1 | Single file scripts |
| 1 | Very Broad | 2-3 | Tiny projects |
| 2 | Broad | 3-5 | Small projects |
| 3 | Feature-level | 5-8 | Basic apps |
| 4 | Component-level | 8-12 | Standard apps |
| **5** | **Balanced** | **10-15** | **← RECOMMENDED DEFAULT** |
| 6 | Standard | 15-20 | Most files separate |
| 7 | High | 20-30 | Detailed split |
| 8 | Very High | 30-40 | Fine-grained |
| 9 | Atomic | 40-60 | Maximum detail |
| 10 | Ultra | 50-75 | Enterprise projects |
| 11 | Mega | 60-90 | Large enterprise |
| 12 | Hyper | 75-110 | Complex architectures |
| 13 | Extreme | 90-130 | Multi-layer systems |
| 14 | Maximum | 110-160 | Critical systems |
| 15 | Insane | 130-200 | Mega specifications |
| 16 | QONQRETE MAX | 160-250 | Enterprise mega-tasqs! |

**2. Non-Interactive Qonstruction Save (-n flag)**

Run fully automated pipelines with auto-saving:
```bash
./qonqrete.sh run -a -b 6 -c 3 -n myproject
```

- The `-n/--qonstruction-name` flag enables non-interactive qonstruction saving
- Automatically saves to `worqspace/qonstructions/<name>`
- Auto-deletes the original qage after saving (no more clutter!)
- Perfect for CI/CD pipelines and automated testing

**3. Gemini-Only Qontrabender**

Qontrabender is now automatically skipped when NOT using Gemini as the construqtor provider:
- Qontrabender is specifically designed for Gemini's context caching feature
- Using it with other providers has no benefit
- This reduces unnecessary processing for non-Gemini builds
- Calqulator is also skipped for local construqtor (no API costs to calculate)

---

#### 📋 MIGRATION GUIDE

**If upgrading from v1.0.1-stable or earlier:**

1. **Update your briq sensitivity values!**
   - OLD: sens=7 (3-5 briqs) → NEW: sens=2 (3-5 briqs)
   - OLD: sens=5 (8-12 briqs) → NEW: sens=4 (8-12 briqs)
   - Or use the new recommended default: **sens=5 or 6**

2. **Update your scripts if using -b flag:**
   ```bash
   # OLD (v1.0.1): 7 = Broad (3-5 briqs)
   ./qonqrete.sh run -b 7 -c 4
   
   # NEW (v1.0.2): 6 = Standard (15-20 briqs), 3 cycles
   ./qonqrete.sh run -b 6 -c 3
   ```

3. **New defaults:**
   - Default briq sensitivity: **6** (Standard: 15-20 briqs)
   - Default cycles: **3**
   - Default mode: **program**

---

#### 🔍 TECHNICAL CHANGES

| Component | Change | Purpose |
|-----------|--------|---------|
| `instruqtor.py` | Inverted BRIQ_RANGES (0-16) | Higher = more briqs |
| `instruqtor.py` | Extended scale (10-16) | Enterprise granularity |
| `instruqtor.py` | Default sensitivity: 5 | Balanced default |
| `qonqrete.sh` | `-n/--qonstruction-name` flag | Non-interactive saves |
| `qonqrete.sh` | `save_qonstruction_non_interactive()` | Auto-save function |
| `qrane/qrane.py` | Gemini-only Qontrabender check | Skip for non-Gemini |
| `qrane/qrane.py` | Local construqtor calqulator skip | No cost calc for local |
| `config.yaml` | New scale documentation | Clear guidance |
| `config.yaml` | Default: briq_sens=6, cycles=3 | New defaults |

---

#### 🎯 FILES CHANGED

- `worqer/instruqtor.py` - Inverted briq sensitivity scale
- `qonqrete.sh` - Added -n flag and non-interactive save
- `qrane/qrane.py` - Gemini-only Qontrabender check
- `worqspace/config.yaml` - Updated defaults and documentation
- `VERSION` - Bumped to 1.0.2
- `doc/RELEASE-NOTES.md` - This file

---

#### 🏷️ QUICK REFERENCE

```bash
# Simple project (web server, API)
./qonqrete.sh run -a -b 5 -c 3

# Medium project (full-stack app)
./qonqrete.sh run -a -b 6 -c 4

# Complex project (multi-service)
./qonqrete.sh run -a -b 7 -c 5

# CI/CD pipeline (auto-save)
./qonqrete.sh run -a -b 6 -c 3 -n myproject
```

---

## [v1.0.1-stable] - 2026-01-02

### 🔧 HOTFIX: HuggingFace Cache Permissions in Docker Hardened Environment

This hotfix resolves the critical permission error when using Qontextor's `complex` mode (semantic embeddings) in the Docker hardened container.

---

#### 🚨 THE PROBLEM (v1.0.0-stable)

When running Qontextor with `local_mode: complex`, users would see errors like:

```yaml
error: 'AST Parse Error: PermissionError at /home/qrane/.cache/huggingface when downloading
  sentence-transformers/all-MiniLM-L6-v2. Check cache directory permissions.'
```

**Root Cause:**
The Docker security hardening in v0.9.9+ includes a tmpfs mount over `/home/qrane/.cache`:
```bash
--tmpfs /home/qrane/.cache:rw,size=500m
```

This ephemeral mount **wipes out** any pre-cached models from the Docker build, forcing the sentence-transformers library to re-download the model at runtime. The download then fails due to lock file conflicts or permission issues.

---

#### ✅ THE FIX (v1.0.1-stable)

**1. Pre-downloaded Model in `/opt/hf_cache`**

The Dockerfile now pre-downloads the `all-MiniLM-L6-v2` model during build time to a separate location (`/opt/hf_cache`) that is NOT affected by the tmpfs mount:

```dockerfile
# Pre-download the sentence-transformers model during build
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"
```

**2. Environment Variables in Entrypoint**

The entrypoint.sh now exports HuggingFace environment variables to point to the pre-cached model:

```bash
export HF_HOME=/opt/hf_cache
export SENTENCE_TRANSFORMERS_HOME=/opt/hf_cache
export TRANSFORMERS_CACHE=/opt/hf_cache
```

**3. Improved Error Handling in Qontextor**

The qontextor.py now:
- Sets HF environment variables before importing sentence_transformers
- Catches `PermissionError` explicitly and falls back to AST-only analysis
- Distinguishes between actual AST parse errors and model loading failures
- Continues analysis gracefully even if semantic embeddings fail

---

#### 📋 MIGRATION GUIDE

**If upgrading from v1.0.0-stable:**

1. **Rebuild the Docker image** (required to download the model):
   ```bash
   ./qonqrete.sh init
   ```

2. That's it! The fix is fully backward compatible.

**Alternative: Use `fast` mode (no semantic embeddings)**

If you prefer to skip semantic embeddings entirely, set in `config.yaml`:
```yaml
agents:
  qontextor:
    provider: local
    local_mode: fast  # AST-only, no embeddings
```

---

#### 🔍 TECHNICAL DETAILS

| Component | Change | Purpose |
|-----------|--------|---------|
| `Dockerfile` | Pre-download model to `/opt/hf_cache` | Model survives tmpfs mount |
| `Dockerfile` | Set `HF_HOME`, `SENTENCE_TRANSFORMERS_HOME` | Point to pre-cached location |
| `entrypoint.sh` | Export HF environment variables | Persist settings for runtime |
| `qontextor.py` | Set env vars before imports | Ensure correct cache path |
| `qontextor.py` | Catch `PermissionError` explicitly | Graceful fallback |
| `qontextor.py` | Better error type distinction | Clear error messages |

---

#### 🎯 FILES CHANGED

- `Dockerfile` - Pre-download model, set environment variables
- `entrypoint.sh` - Export HF cache environment variables
- `worqer/qontextor.py` - Improved error handling, env var setup
- `VERSION` - Bumped to 1.0.1-stable
- `doc/RELEASE-NOTES.md` - This release note
- `doc/CONTEXT.md` - Updated with v1.0.1 cache handling note
- `doc/QUICKSTART.md` - Updated version reference

---

## [v1.0.0-stable] - 2025-12-29

### 🎉 PRODUCTION RELEASE - BULLETPROOF LANGUAGE DETECTION

The definitive stable production release of QonQrete! This release fixes the critical "py file bug" and introduces the ULTIMATE language detection system that works with ALL AI providers.

---

#### 🔥 CRITICAL FIX: No More "py" or "js" File Creation

**The Problem (v0.9.x):**
When using OpenAI as the AI provider, code blocks like ` ```py ` would create files named "py" instead of being skipped:

```
# AI output:                  # Result (WRONG):
```py                         → File "py" created
print("hello")                  (should have been skipped!)
```
```

This happened because OpenAI uses shorthand language identifiers (`py`, `js`, `ts`) instead of full names with paths (`python:src/main.py`).

**The Fix (v1.0.0-stable):**
The `language_keywords` set has been MASSIVELY expanded from **23 entries** to **400+ entries**, covering:

| Category | Examples | Count |
|----------|----------|-------|
| Python variants | `py`, `py3`, `pyw`, `pyi`, `pyc`, `pyx`, `cython`, `jython`, `pypy` | 25+ |
| JavaScript/TypeScript | `js`, `jsx`, `mjs`, `cjs`, `ts`, `tsx`, `es6`, `node`, `deno` | 40+ |
| Infrastructure-as-Code | `tf`, `tfvars`, `hcl`, `ansible`, `puppet`, `k8s`, `helm` | 30+ |
| All GitHub Linguist IDs | Every language identifier from Linguist v4.5.2+ | 300+ |
| Generic markers | `code`, `snippet`, `output`, `console`, `terminal`, `result` | 20+ |

**NEW: Smart Filename Validation**

Added `_is_valid_filename()` function that distinguishes real files from language keywords:
- ✅ `src/main.py` → Real file (has path + extension)
- ✅ `Dockerfile` → Real file (known extensionless filename)
- ❌ `py` → Language keyword (single word, no extension)
- ❌ `typescript` → Language keyword (in comprehensive set)

**Tested With:**
- ✅ OpenAI GPT-4/GPT-4o (uses `py`, `js` shorthand)
- ✅ Google Gemini (uses full names)
- ✅ Anthropic Claude (uses full names + paths)
- ✅ DeepSeek Coder (uses language-specific IDs)
- ✅ Qwen/Qwen2.5-Coder (mixed behavior)

---

## [v1.0.0] - 2025-12-27

### 🎉 PRODUCTION RELEASE - ENFORCED BRIQ SENSITIVITY

The first stable production release of QonQrete! This release fixes the critical briq sensitivity inconsistency bug and introduces enforced briq count ranges.

---

#### 🆕 NEW: Cycle Override Flag (-c/--cyqles)

Now you can override the auto_cycle_limit directly from the command line!

```bash
# Default: 4 cycles
./qonqrete.sh run

# Override to 6 cycles for complex projects
./qonqrete.sh run -c 6

# Combine with sensitivity for full control
./qonqrete.sh run -b 5 -c 6  # Complex project config
./qonqrete.sh run -b 7 -c 4  # Simple project config (default)
```

**CLI Reference:**
| Flag | Long Form | Description |
|------|-----------|-------------|
| `-c` | `--cyqles <N>` | Override max cycles (1-10) |
| `-b` | `--briq-sensitivity <N>` | Override sensitivity (0-9) |

---

#### 🚨 CRITICAL FIX: Briq Sensitivity Now ENFORCED

**The Problem (v0.9.x and earlier):**
Previously, `briq_sensitivity` was just a "hint" to the AI, resulting in wildly inconsistent outputs. The same sensitivity setting could produce anywhere from 1 to 10+ briqs depending on AI mood:

| Run | Sensitivity | Expected Briqs | Actual Briqs | Result |
|-----|-------------|----------------|--------------|--------|
| A | 8 | ~2-3 | **1** | Polish loop failure |
| B | 8 | ~2-3 | **10** | Worked but inefficient |
| C | 8 | ~2-3 | **7** | Unpredictable |

**The Fix (v1.0.0):**
Briq counts are now **ENFORCED** with hard min/max ranges:
- If AI produces too few briqs → System retries with stronger prompt
- If AI produces too many briqs → System merges briqs automatically

---

#### 📊 NEW BRIQ SENSITIVITY SCALE

| Level | Name | Briq Range | Target | Use Case |
|-------|------|------------|--------|----------|
| **9** | Monolithic | 1 | 1 | Single-file scripts |
| **8** | Very Broad | 2-3 | 2 | Backend/Frontend split |
| **7** | Broad | 3-5 | 4 | **RECOMMENDED DEFAULT** |
| **6** | Feature | 5-8 | 6 | Feature-level decomposition |
| **5** | Component | 8-12 | 10 | Component-level |
| **4** | Balanced | 10-15 | 12 | Medium complexity |
| **3** | Standard | 15-20 | 18 | Standard granularity |
| **2** | High Gran. | 20-30 | 25 | High granularity |
| **1** | Very High | 30-40 | 35 | Very fine-grained |
| **0** | Atomic | 40-60 | 50 | Maximum decomposition |

---

#### 🎯 RECOMMENDED CONFIGURATIONS

| Project Type | Sensitivity | Cycles | Expected Result |
|--------------|-------------|--------|-----------------|
| **Simple** (API, web server) | 7 | 4 | B+ to A- grade |
| **Medium** (full-stack app) | 6 | 5 | B to B+ grade |
| **Complex** (multi-service) | 5 | 6 | Comprehensive coverage |

---

#### 🆕 New Features

| Feature | Description |
|---------|-------------|
| **Enforced Briq Ranges** | System guarantees briq count within specified range |
| **Auto-Retry** | Retries with stronger prompt if AI doesn't comply |
| **Auto-Merge** | Automatically merges excess briqs to meet max limit |
| **Range Logging** | Console shows `[CONFIG] Sensitivity: 7 → Target: 4 briqs (range: 3-5)` |
| **Compliance Check** | `[OK] Briq count 4 is within range [3-5]` confirmation |

---

#### ⚙️ Configuration Changes

| Setting | Old Default | New Default | Reason |
|---------|-------------|-------------|--------|
| `briq_sensitivity` | 8 | **7** | More consistent results |
| `auto_cycle_limit` | 2 | **4** | Enough iterations for polish |

---

#### 📝 Technical Implementation

**instruqtor.py - Enforced Ranges:**
```python
BRIQ_RANGES = {
    9: (1, 1, 1),      # Monolithic: exactly 1 briq
    8: (2, 3, 2),      # Very Broad: 2-3 briqs
    7: (3, 5, 4),      # Broad: 3-5 briqs (RECOMMENDED)
    6: (5, 8, 6),      # Feature-level: 5-8 briqs
    5: (8, 12, 10),    # Component-level: 8-12 briqs
    4: (10, 15, 12),   # Balanced: 10-15 briqs
    3: (15, 20, 18),   # Standard: 15-20 briqs
    2: (20, 30, 25),   # High Granularity: 20-30 briqs
    1: (30, 40, 35),   # Very High: 30-40 briqs
    0: (40, 60, 50),   # Atomic: 40-60 briqs
}
```

**Enforcement Logic:**
1. AI generates briqs with MANDATORY count prompt
2. System checks if count is within range
3. If too few → Retry with stronger prompt (up to 2 retries)
4. If too many → Merge consecutive briqs to meet max
5. Log compliance status

---

#### 📋 Migration from v0.9.x

1. Update `config.yaml`:
   ```yaml
   briq_sensitivity: 7  # was 8
   auto_cycle_limit: 4  # was 2
   ```

2. No container rebuild required - just replace `worqer/instruqtor.py`

---

#### 🧪 A/B Testing Results (Pre-Release)

Extensive testing with 13 runs revealed the inconsistency bug and validated the fix:

| Config | Runs | Briq Variance | Avg Grade | Notes |
|--------|------|---------------|-----------|-------|
| sens=8 (old) | 5 | 1-16 briqs | C+ (71%) | HIGH variance |
| sens=7 (old) | 2 | 20 briqs | B (82%) | Better but expensive |
| sens=8 (new) | TBD | 2-3 briqs | TBD | **ENFORCED** |

---

#### 📝 Files Changed

- `worqer/instruqtor.py` - Complete rewrite with enforcement logic
- `worqspace/config.yaml` - Updated defaults and documentation
- `VERSION` - Bumped to 1.0.0
- `doc/RELEASE-NOTES.md` - This document

---

## [v0.9.9-beta] - 2025-12-26

### 🎨 OUTPUT CLEANUP & UX IMPROVEMENTS

Cleaner console output with less noise.

---

#### 🔇 Console Output Changes

| Component | Change |
|-----------|--------|
| **TasqLeveler** | Only shows `[TasqLeveler]` status lines, not verbose headers |
| **InspeQtor** | Only shows `=== InspeQtor` and `=== Final Assessment:` |
| **Table dividers** | `|----` lines are now hidden |
| **Batch details** | Per-batch progress hidden, only final assessment shown |

---

#### 🔧 pycg Removal

| Issue | Resolution |
|-------|------------|
| **pycg package broken** | Module name mismatch on PyPI (PyCG vs pycg) |
| **Dependency analysis** | Now relies on jedi (already integrated) |
| **Warning spam** | Removed - silent fallback to empty call graph |

---

#### 📋 Verified Features

| Feature | Status |
|---------|--------|
| **Universal File Rule** | ✅ InstruQtor enforces modify/extend for existing files |
| **Skeleton Protection** | ✅ ConstruQtor skips files with Qompressor markers |
| **Cycle Continuity** | ✅ PARTIAL → promotes reqap → next cycle fixes |
| **LoQal Verification** | ✅ Internal to InspeQtor, no exit code issues |

---

#### 📝 Files Changed

- `qrane/qrane.py` - Updated VISIBLE_KEYWORDS and BLOCKED_KEYWORDS
- `worqer/qontextor.py` - Removed broken pycg, uses jedi only
- `requirements.txt` - Removed pycg dependency

---

## [v0.9.8-beta] - 2025-12-26

### 🐛 CRITICAL BUG FIXES

Two critical bugs discovered during multi-cycle builds that caused pipeline failures.

---

#### 🐛 Bug Fixes

| Issue | Root Cause | Fix |
|-------|------------|-----|
| **Skeleton overwrites code** | AI copies bloq.d skeletons from context back to qodeyard | Detect and skip files containing Qompressor markers |
| **Exit code 1 after inspeqtor** | loqal_verifier runs twice (in inspeqtor + standalone) | Remove standalone loqal_verifier from pipeline_config.yaml |

---

#### 📝 Technical Details

**construqtor.py - Skeleton Detection:**
```python
# Skip files containing Qompressor skeleton markers
skeleton_markers = [
    "# ... (body stripped by Qompressor) ...",
    "// ... (body stripped by Qompressor) ...",
    "/* ... (body stripped by Qompressor) ... */",
    "(body stripped by Qompressor)"
]
if any(marker in code_content for marker in skeleton_markers):
    print(f"     [SKIP] Skeleton detected (not overwriting): {filename}")
    continue
```

**pipeline_config.yaml:**
- Removed standalone `loqal_verifier` agent
- LoQal verification still runs as Stage 3 inside inspeqtor

---

#### 🔍 Issue Analysis

**Skeleton Overwrite Bug:**
1. `use_qompressor: true` sends bloq.d skeletons as context
2. AI sees skeleton in prompt, copies it to output
3. ConstruQtor writes skeleton to qodeyard
4. Working code replaced with broken `# ... (body stripped by Qompressor) ...`

**Duplicate Verifier Bug:**
1. InspeQtor runs LoQal verification internally (Stage 3)
2. Pipeline also runs loqal_verifier.py as standalone agent
3. Standalone exits with code 1 on errors
4. Pipeline aborts even though inspeqtor handled it

---

#### 📋 Migration

No container rebuild required. Just update:
- `worqer/construqtor.py`
- `worqspace/pipeline_config.yaml`

---

## [v0.9.7-beta] - 2025-12-26

### 🔧 RELIABILITY & COMPATIBILITY FIXES

Fixes issues discovered during real-world testing with tasq builds.

---

#### 🐛 Bug Fixes

| Issue | Fix |
|-------|-----|
| **pycg not found** | Now uses `sys.executable -m pycg` for reliable module invocation |
| **sentence-transformers cache errors** | Added `--tmpfs /home/qrane/.cache:rw,size=500m` for writable cache |
| **PATH issues in container** | Added `ENV PATH="/usr/local/bin:${PATH}"` to Dockerfile |

---

#### 🆕 New Features

| Feature | Description |
|---------|-------------|
| **Writable cache tmpfs** | 500MB tmpfs mount for model caching during runs |
| **Robust pycg detection** | Multi-method detection: module first, then direct executable |

---

#### ⚙️ Configuration Changes

| Setting | New Default | Previous | Reason |
|---------|-------------|----------|--------|
| `briq_sensitivity` | 6 | 3 | Finer-grained task decomposition |
| `auto_cycle_limit` | 3 | 7 | More controlled autonomous runs |

---

#### 🗂️ Ignore File Updates

| File | Change |
|------|--------|
| `.gitignore` | Added `worqspace/qonstructions/*` (keeps `.gitkeep`) |
| `.dockerignore` | Added `worqspace/qonstructions/*` |

Qonstructions are now excluded from version control as they are user-specific outputs.

---

#### 📝 Technical Changes

**Dockerfile:**
```dockerfile
# Added explicit PATH for pip scripts
ENV PATH="/usr/local/bin:${PATH}"

# Created cache directory for sentence-transformers
RUN mkdir -p /home/qrane/.cache/huggingface && \
    chown -R qrane:qrew /home/qrane/.cache
```

**qonqrete.sh:**
```bash
# Added tmpfs for cache directory
--tmpfs /home/qrane/.cache:rw,size=500m
```

**qontextor.py:**
```python
# Now uses sys.executable for reliable pycg invocation
subprocess.run([sys.executable, "-m", "pycg", ...])
```

---

#### 📋 Migration

Requires container rebuild (`./qonqrete.sh init`) for Dockerfile changes.

---

## [v0.9.6-beta] - 2025-12-26

### 🔧 BUGFIX & POLISH RELEASE

Fixes several issues discovered during security hardening testing.

---

#### 🐛 Bug Fixes

| Issue | Fix |
|-------|-----|
| **pycg not found** | Use `shutil.which()` to find pycg, fallback to common pip locations |
| **Permission denied on qage files** | Changed `chmod a+rX` to `a+rwX` for full host access |
| **Cannot save Qonstruction** | Added `fix_qage_permissions()` helper that runs docker to chmod files |
| **Cannot delete Qage** | Added `delete_qage()` helper that uses docker when host rm fails |
| **TasqLeveler KeyError** | Escaped `{{` in prompt template (Python .format() was interpreting dicts) |

---

#### 🆕 New Features

| Feature | Description |
|---------|-------------|
| **Delete Qage prompt** | When declining to save Qonstruction, now asks if you want to delete the Qage |
| **Permission fix helper** | `fix_qage_permissions()` ensures host user can read/write container-created files |
| **Docker-based delete** | `delete_qage()` uses docker to delete when host permissions fail |

---

#### 🔒 Security Capability Additions

Required capabilities for full functionality:

| Capability | Purpose |
|------------|---------|
| `SETUID` | gosu user switch |
| `SETGID` | gosu group switch |
| `CHOWN` | Fix mounted volume ownership |
| `FOWNER` | chmod on files |
| `DAC_OVERRIDE` | Access host-mounted directories |

---

#### 📝 Technical Changes

**entrypoint.sh:**
```bash
# Changed from 2770 to 2775 for host user read access
chmod -R 2775 /qonq

# Added umask for world-readable new files
umask 0002
```

**qontextor.py:**
```python
# Use shutil.which to find pycg, with fallbacks
import shutil
pycg_cmd = shutil.which("pycg")
if not pycg_cmd:
    for candidate in ["/usr/local/bin/pycg", "/usr/bin/pycg"]:
        if os.path.isfile(candidate):
            pycg_cmd = candidate
            break
subprocess.run([pycg_cmd, "--output", ...])
```

**tasqleveler.py:**
```python
# Escaped literal braces in prompt template
config={{'test': True}}  # Double braces escape .format()
```

**qonqrete.sh:**
```bash
# Permission fix now makes files writable (not just readable)
fix_qage_permissions() {
    docker run --rm -v "${qage_path}:/fix" \
        --entrypoint /bin/bash "$IMAGE_NAME" \
        -c "chmod -R a+rwX /fix"  # Changed from a+rX to a+rwX
}

# New delete helper uses docker when host can't delete
delete_qage() {
    rm -rf "$qage_path" 2>/dev/null || \
    docker run --rm -v "${qage_path}:/delete" \
        --entrypoint /bin/bash "$IMAGE_NAME" \
        -c "rm -rf /delete/*"
}
```

---

#### 📋 Migration

No breaking changes. Just update files from zip.

---

## [v0.9.5-beta] - 2025-12-26

### 🔐 SECURITY HARDENING RELEASE

This release focuses on comprehensive security hardening across all layers of QonQrete.

---

#### 🐳 Docker Container Hardening

| Feature | Description |
|---------|-------------|
| **Read-only Filesystem** | Container root is read-only, only `/qonq` is writable |
| **Drop All Capabilities** | `--cap-drop=ALL` removes all Linux capabilities |
| **Memory Limits** | `--memory=4g --memory-swap=4g` prevents OOM attacks |
| **PID Limits** | `--pids-limit=100` prevents fork bombs |
| **CPU Limits** | `--cpus=2` ensures fair resource allocation |
| **Secure tmpfs** | `--tmpfs /tmp:rw,noexec,nosuid,size=100m` for ephemeral /tmp |
| **HEALTHCHECK** | Container health monitoring with Dockerfile directive |

> **Note:** `--security-opt=no-new-privileges` intentionally omitted as it conflicts with `gosu` privilege dropping.

**Docker Security Flags (in qonqrete.sh):**
```bash
DOCKER_SECURITY_FLAGS="--read-only \
    --cap-drop=ALL \
    --memory=4g --memory-swap=4g \
    --cpus=2 --pids-limit=100 \
    --tmpfs /tmp:rw,noexec,nosuid,size=100m"
```

> **Note:** `--security-opt=no-new-privileges:true` intentionally omitted - it conflicts with `gosu` privilege dropping. The gosu pattern provides equivalent security by dropping from root to `qrane` user.

---

#### 📦 Dependency Security

| Feature | Description |
|---------|-------------|
| **Pinned Base Image** | `ubuntu:22.04@sha256:...` with digest for reproducibility |
| **requirements.txt** | All Python packages pinned to specific versions |
| **Minimal Install** | `--no-install-recommends` reduces attack surface |

**New file: `requirements.txt`**
```
PyYAML==6.0.2
openai==2.14.0
anthropic==0.75.0
google-generativeai==0.8.6
jedi==0.19.2
docstring-parser==0.16
pycg==0.0.8
numpy==2.2.1
sentence-transformers==3.3.1
jsonschema==4.23.0
```

> **Note:** `sentence-transformers` includes PyTorch - container image is ~3GB but enables full semantic search in Qontextor complex mode.

---

#### 🔑 Secrets Management

| Feature | Description |
|---------|-------------|
| **.env.example** | Template file with placeholder API keys |
| **No secrets in repo** | `.env` remains in `.gitignore` and `.dockerignore` |

**New file: `.env.example`** - Copy to `.env` and add your keys.

---

#### ⏱️ API Timeouts & Retry Limits

| Feature | Description |
|---------|-------------|
| **Default Timeout** | 300 seconds (5 minutes) for all AI API calls |
| **Hard Retry Limit** | Maximum 10 retries enforced in code |
| **Timeout Exceptions** | Proper `TimeoutError` raised instead of hanging |

All providers (OpenAI, Anthropic, Gemini, DeepSeek) now have explicit timeout handling.

---

#### 🛡️ New Security Library: `lib_security.py`

New module providing:

| Function | Purpose |
|----------|---------|
| `validate_path()` | Jail enforcement - paths must stay within `/qonq` |
| `safe_write_file()` | Atomic writes with size limits |
| `safe_read_file()` | Size-limited reads with jail check |
| `is_path_within_jail()` | Symlink-aware path validation |
| `validate_config()` | JSON Schema validation for config.yaml |
| `validate_tasq_file()` | Size limit check (100KB max) |
| `setup_signal_handlers()` | SIGTERM/SIGINT graceful shutdown |
| `sanitize_traceback()` | Redact API keys from error logs |
| `SecurityLogger` | JSON-formatted structured logging |

**Constants:**
```python
MAX_TASQ_SIZE = 100 * 1024           # 100KB
MAX_GENERATED_FILE_SIZE = 1024 * 1024  # 1MB
MAX_CONFIG_SIZE = 50 * 1024          # 50KB
MAX_RETRIES_HARD_LIMIT = 10
MAX_TIMEOUT_SECONDS = 300
```

---

#### 🪵 Structured Logging

| Feature | Description |
|---------|-------------|
| **JSON Format** | Machine-parseable log entries |
| **Audit Trail** | Security events logged separately |
| **Sanitized Tracebacks** | API keys redacted from error messages |

Example JSON log entry:
```json
{
  "timestamp": "2025-12-26T16:00:00.000Z",
  "level": "INFO",
  "event_type": "audit",
  "message": "path_traversal_blocked",
  "details": {"attempted_path": "../../../etc/passwd"}
}
```

---

#### 📁 File System Security

| Feature | Description |
|---------|-------------|
| **Jail Enforcement** | All file operations validated against `/qonq` |
| **Symlink Protection** | `os.path.realpath()` resolves symlinks before validation |
| **Size Limits** | Generated files capped at 1MB, tasq.md at 100KB |
| **Atomic Writes** | Write to temp file, then rename (prevents corruption) |

---

#### ⚡ Signal Handling

| Feature | Description |
|---------|-------------|
| **SIGTERM Handler** | Graceful shutdown on container stop |
| **SIGINT Handler** | Clean exit on Ctrl+C |
| **Handler Registration** | Plugins can register cleanup callbacks |

---

#### 📋 Config Validation

| Feature | Description |
|---------|-------------|
| **JSON Schema** | Config.yaml validated against schema |
| **Retry Limits** | max_retries enforced 0-10 |
| **Timeout Limits** | timeout enforced 1-300 seconds |
| **Provider Validation** | Only known providers accepted |

---

### Migration Guide

**No breaking changes.** All security features are transparent.

1. Extract new zip
2. Copy your `.env` from backup (or create from `.env.example`)
3. Run `./qonqrete.sh init` to rebuild with hardened Dockerfile
4. Run normally - all security features are automatic

---

### Files Added/Changed

| File | Change |
|------|--------|
| `Dockerfile` | Pinned image, HEALTHCHECK, requirements.txt |
| `requirements.txt` | NEW - Pinned Python dependencies |
| `.env.example` | NEW - API key template |
| `qonqrete.sh` | Docker security flags added |
| `worqer/lib_security.py` | NEW - Security utilities |
| `worqer/lib_ai.py` | Timeouts, proper exception handling |

---

## [v0.9.3-beta] - 2025-12-26

### 🛡️ Security Hardening - gosu Entrypoint (Fixed)

**The Fix:** Proper non-root execution now works on both Docker Desktop AND native Linux Docker.

The v0.9.1/v0.9.2 security hardening caused `PermissionError` on Linux because Docker bind mounts inherit host permissions. This is now fixed with the `gosu` entrypoint pattern.

#### How It Works

| Step | User | What Happens |
|------|------|--------------|
| 1 | root | Container starts, runs `entrypoint.sh` |
| 2 | root | `chown -R qrane:qrew /qonq` fixes mounted volume |
| 3 | root→qrane | `gosu qrane` drops privileges |
| 4 | qrane | Your actual command runs as **non-root** |

#### Files Added/Changed

| File | Purpose |
|------|---------|
| `entrypoint.sh` | Fixes permissions, drops to qrane user |
| `Dockerfile` | Installs `gosu`, sets ENTRYPOINT |

---

## [v0.9.2-beta] - 2025-12-26

### 🧹 Code Cleanup - DeepSeek Provider Consolidation

**The Change:** The `sqeleton/` directory has been removed. The `DeepSeekProvider` class is now built directly into `worqer/lib_ai.py`.

#### What Changed

| Before | After |
|--------|-------|
| `sqeleton/deepseek_provider.py` | Built into `worqer/lib_ai.py` |
| Separate import dependency | Self-contained lib_ai.py |
| Non-streaming DeepSeek output | Full streaming support |

**Benefits:**
- 🧹 Cleaner directory structure (one less folder)
- 📦 Simpler deployment (no separate provider scripts)
- 🚀 DeepSeek now uses streaming output like other providers
- 🔧 Easier maintenance (all AI providers in one file)

#### Technical Details

The `DeepSeekProvider` class is now defined in `lib_ai.py` with two methods:
- `query(prompt)` - Original non-streaming method
- `query_streaming(prompt)` - New generator for streaming responses

The `_run_deepseek()` function now uses streaming, matching the behavior of OpenAI, Gemini, and Anthropic providers.

#### Migration

**No action required.** This is a transparent refactor. If you had custom code importing from `sqeleton.deepseek_provider`, update to:

```python
# Old (no longer works)
from sqeleton.deepseek_provider import DeepSeekProvider

# New
from worqer.lib_ai import DeepSeekProvider
```

---

## [v0.9.1-beta] - 2025-12-26

### 🔄 Resume & Qonstructions - Persistent Project Workflow

**The Big Idea:** No more losing your work! QonQrete now supports resuming from previous runs and saving projects permanently.

#### New Commands

| Command | Description |
|---------|-------------|
| `./qonqrete.sh resume` | Interactive kubectx-style picker for previous Qages |
| `./qonqrete.sh resume -q <n>` | Resume from specific Qage directory |
| `./qonqrete.sh clean` | Interactive picker for Qage deletion |
| `./qonqrete.sh clean -q <n>` | Delete specific Qage |
| `./qonqrete.sh clean -A` | Delete ALL Qages (original behavior) |

#### Qonstructions

After each run completes, QonQrete prompts to save your work:

```
┌─────────────────────────────────────────────────┐
│           QonQrete Session Complete            │
└─────────────────────────────────────────────────┘

Save this run as a Qonstruction? [y/N] y
Enter project name [project_20251226_115701]: my-api
Saving Qonstruction to: qonstructions/my-api
Qonstruction saved successfully!
```

Qonstructions are saved to `worqspace/qonstructions/<name>/` with:
- Complete qodeyard (your generated code)
- All context directories (tasq.d, exeq.d, reqap.d, etc.)
- Meta information (meta.yaml)

---

### 🛡️ Security Hardening - Drop Root Privileges

**The Big Idea:** Defense in depth inside the container. Even if a rogue prompt injection tries to overwrite core logic, it fails.

#### User/Group Model

| User | Role | Permissions |
|------|------|-------------|
| `qrane` | Orchestrator | Owns `/qonq`, runs `qrane.py` |
| `worqer` | Agent Runner | Runs agents, writes to workspace |
| `qrew` | Shared Group | Enables collaboration between users |

#### Permissions

- `/qonqrete` (code): Owned by `qrane:qrew`, mode 750
- `/qonq` (workspace): Owned by `worqer:qrew`, mode 2770 (setgid)
- Container runs as `qrane` user (non-root)

**Impact:** Agents are jailed to `/qonq` and cannot modify orchestrator code or escape the sandbox.

---

### 🚀 Explicit Sqrapyard Control

**The Change:** Sqrapyard seeding is now **opt-in** to prevent accidental imports of leftover code.

```bash
# Fresh start (default) - ignores sqrapyard
./qonqrete.sh run

# Seed from sqrapyard (must be explicit)
./qonqrete.sh run -s
./qonqrete.sh run --sqrapyard
```

**Rationale:** Many users were accidentally importing old sqrapyard contents into new projects. This prevents that confusion.

---

### ✏️ Interactive TasQ Editor

**The Feature:** No `tasq.md`? No problem!

When you run `./qonqrete.sh run` without a `tasq.md`, QonQrete:
1. Opens your `$EDITOR` (default: vim) with a helpful template
2. Waits for you to write your task and save
3. Continues with the run

**Template includes:**
- Tips for writing good tasks
- Example task format
- Comments explaining TasqLeveler enhancement

---

### 🏷️ Flag Changes

| Old Flag | New Flag | Purpose |
|----------|----------|---------|
| `-s/--msb` | `-M/--msb` | Microsandbox mode [EXPERIMENTAL] |
| (none) | `-s/--sqrapyard` | Seed from sqrapyard |

**TUI and MSB marked EXPERIMENTAL:**
- `-t/--tui`: TUI mode now shows [EXPERIMENTAL] warning
- `-M/--msb`: Microsandbox mode now shows [EXPERIMENTAL] warning

---

### 📁 Directory Structure Update

New `qonstructions/` directory in worqspace:

```
worqspace/
├── config.yaml
├── pipeline_config.yaml
├── caching_policy.yaml
├── tasq.md
├── sqrapyard/           # Input seed code
├── qonstructions/       # NEW: Saved project outputs
│   ├── my-api/
│   │   ├── qodeyard/
│   │   ├── tasq.d/
│   │   ├── exeq.d/
│   │   ├── meta.yaml
│   │   └── ...
│   └── another-project/
└── qage_20251226_*/     # Ephemeral run directories
```

---

### 🔧 Technical Changes

1. **qonqrete.sh**: Complete rewrite with new CLI parser
2. **Dockerfile**: Security hardening with user/group model
3. **Documentation**: Updated all docs with new features
4. **VERSION**: Bumped to 0.9.1

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

v0.9.5-beta was validated with a 7-cycle autonomous build:

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
