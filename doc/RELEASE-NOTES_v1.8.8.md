# QonQrete v1.8.8-stable Release Notes

**Release Date:** 2026-01-07  
**Codename:** SQavenger Resurrection Edition

---

## 🔥 CRITICAL BUG FIX

### SQavenger AttributeError - THE REAL CULPRIT!

**File:** `worqer/mindstaq/sqavenger.py` (lines 480, 483)

**Bug #1:** `intent.entities` - attribute doesn't exist!
```python
# WAS (broken):
'entities': intent.entities,  # ❌ AttributeError!

# NOW (fixed):
'entities': intent.keywords,  # ✅ Correct attribute
```

**Bug #2:** `intent.raw_task` - attribute doesn't exist!
```python
# WAS (broken):
task = intent.raw_task  # ❌ AttributeError!

# NOW (fixed):
task = intent.raw_text  # ✅ Correct attribute
```

**Impact:** This was the REAL reason all code generation fell back to the generic `AsyncWorkerPool` template! The v1.8.7 sqavanger→sqavenger typo fix was correct, but SQavenger itself was crashing on every invocation with:

```
'CrystallizedIntent' object has no attribute 'entities'
```

**Root Cause Analysis:**
1. Qomputator scores task at 499/666 → routes to QOMBINATOR
2. Qombinator returns None → falls back to SQavenger
3. SQavenger crashes accessing `intent.entities` and `intent.raw_task`
4. MindstaQ catches exception → falls through to Qrystallizer fallback
5. Qrystallizer uses generic `fallback` template → AsyncWorkerPool

**Fix:** Updated SQavenger to use the correct `CrystallizedIntent` attribute names:
- `intent.entities` → `intent.keywords`
- `intent.raw_task` → `intent.raw_text`

---

## 📊 test187 Analysis (v1.8.7 Run)

### Run Statistics
| Metric | Value |
|--------|-------|
| Cycles Completed | 8 |
| Briqs Processed | 193 |
| Files Generated | 7 |
| LocalInspeQtor Score | 100/100 (all cycles) |
| Assessment | SUCCESS (all cycles) |

### The Problem
Despite showing SUCCESS across all 8 cycles, **every generated file is IDENTICAL**:
```
MD5: 50ac553e794e864d6cf74de978134329
```

All 7 files contain the exact same generic `AsyncWorkerPool` code - completely unrelated to the AutoWonQNet specification!

### WoNQ Score: **85/666** (12.8%)

**Breakdown:**
| Component | Score | Notes |
|-----------|-------|-------|
| Pipeline Orchestration | 550/666 | Cycles ran correctly |
| Briq Splitting | 480/666 | 193 briqs from complex spec |
| LocalInspeQtor | 520/666 | Reviews completed properly |
| Code Generation Quality | **0/666** | ALL FALLBACK TEMPLATES |
| Functional Output | **0/666** | Zero AutoWonQNet code |

**Weighted Average:** 85/666

The system RUNS correctly, but produces GARBAGE output due to the SQavenger crash.

---

## 🛠️ Files Modified (v1.8.7 → v1.8.8)

```
VERSION                              # 1.8.8-stable
worqer/mindstaq/sqavenger.py        # Fixed entities/raw_task attributes
worqer/mindstaq/__init__.py         # Version header update
worqer/mindstaq/local_inspeqtor.py  # Version bump
doc/RELEASE-NOTES_v1.8.8.md         # This file
```

---

## 🔮 Expected Improvement with v1.8.8

With SQavenger now properly accessing intent attributes:

1. **Tier 2 (Qombinator)** can now successfully fall back to **Tier 1 (SQavenger)**
2. SQavenger will attempt web search code harvesting (if Qrawler enabled)
3. If Qrawler disabled, SQavenger uses `OFFLINE_PATTERNS` dictionary
4. More relevant code generation based on actual task keywords

### Recommended Test
```bash
./qonqrete.sh -a -b 5 -c 3 -n "test-v188"
```

Expected: Generated code should now be MORE task-specific, not generic fallback.

---

## ⚠️ Known Limitations (Still Present)

1. **Qrawler Disabled** - Web search code harvesting requires SearXNG setup
2. **Z3 Solver Disabled** - Qombinator constraint solving not active
3. **Complex Specs** - AutoWonQNet-level complexity may still exceed local capabilities

---

## 📈 Version History

| Version | Critical Fix |
|---------|--------------|
| v1.8.5 | Initial release |
| v1.8.7 | sqavanger→sqavenger typo, hardcoded paths, -n flag |
| **v1.8.8** | **SQavenger .entities/.raw_task AttributeError** |

---

*QonQrete v1.8.8-stable - Zero-Cost Local Code Generation*  
*"SQavenger lives again!"*
