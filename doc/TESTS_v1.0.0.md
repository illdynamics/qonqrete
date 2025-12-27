# QonQrete v1.0.0 - Configuration A/B Testing Results

## Overview

This document contains the complete results of configuration A/B testing performed prior to the v1.0.0 release. These tests identified a critical briq sensitivity bug and validated the enforced briq range solution.

**Testing Period:** December 26-27, 2025  
**Total Runs:** 13  
**Test Task:** FastAPI boilerplate server with HTML page, /health endpoint, configuration, and Docker support

---

## Test Matrix

| Run | Sensitivity | Cycles | Briqs | Flow | Files | LOC | Grade | Notes |
|-----|-------------|--------|-------|------|-------|-----|-------|-------|
| 1 | 6 | 3 | 11 | ✅⚠️✅ | 10 | 578 | B+ (85%) | Rich but gaps |
| 2 | 6 | 4 | 22 | ⚠️⚠️✅✅ | 9 | 226 | B- (78%) | Wasteful |
| **3** | **8** | **4** | **7** | ✅✅✅✅ | **10** | **368** | **A- (92%)** | **Best run** |
| 4 | 9 | 2 | 6 | ✅✅ | 10 | 320 | C+ (72%) | Incomplete |
| 5 | 9 | 1 | 1 | ✅(fake) | 8 | 8 | F (0%) | Empty placeholders |
| 6 | 8 | 2 | 3 | ✅✅ | 7 | 285 | B (80%) | Missing extras |
| 7 | 2 | 4 | 52 | ⚠️⚠️⚠️❌ | 15 | 897 | D (50%) | Fragmentation death spiral |
| 8 | 6 | 4 | 23 | ⚠️⚠️⚠️⚠️ | 8 | 304 | C+ (75%) | Stuck in PARTIAL |
| 9 | 7 | 4 | 20 | ⚠️✅✅✅ | 7 | 297 | B (82%) | Good recovery |
| **10** | **8** | **4** | **7** | ✅✅✅✅ | **4** | **260** | **F (20%)** | **Polish loop!** |
| 11 | 8 | 4 | 16 | ⚠️⚠️✅✅ | 13 | 375 | B+ (87%) | Recovered |
| 12 | 8 | 2 | 5 | ✅✅ | 15 | 663 | B- (75%) | Duplicates |
| 13 | 8 | 2 | 5 | ⚠️✅ | 5 | ~300 | C+ (70%) | Missing /health |

---

## Critical Discovery: The sens=8 Variance Bug

### The Problem

With the same configuration (sens=8, cyc=4), we observed **wildly different briq counts**:

| Run | Config | Cycle 1 Briqs | Total Briqs | Grade |
|-----|--------|---------------|-------------|-------|
| Run 3 | sens=8, cyc=4 | ~2 | 7 | A- (92%) |
| Run 10 | sens=8, cyc=4 | **1** | 7 | **F (20%)** |
| Run 11 | sens=8, cyc=4 | **10** | 16 | B+ (87%) |

### Root Cause

`briq_sensitivity` was passed to the AI as a **hint**, not a constraint:

```
InstruQtor Console (Run 10):
"--- Architect Generating 1 Build Phases (Sens:8) ---"

InstruQtor Console (Run 11):
"--- Architect Generating 10 Build Phases (Sens:8) ---"
```

The AI model made its own interpretation of "sensitivity 8" each time.

### New Failure Mode Discovered: Polish Loop

Run 10 revealed a new failure mode where sens=8 produces a single briq for "utilities":

```
Cycle 1: AI creates 1 briq for "shared utilities"
         → Briq builds only config.py, logger.py, constants.py, exceptions.py
         
Cycle 2-4: AI sees utilities need polish
           → Creates briqs to improve type hints
           → Never realizes server is missing!
           
Result: Perfect utilities (260 LOC), ZERO functionality (F grade)
```

---

## sens=8 Distribution Analysis

| Grade | Count | Percentage |
|-------|-------|------------|
| A- (92%) | 1 | 20% |
| B+ (87%) | 1 | 20% |
| B (80%) | 1 | 20% |
| B- (75%) | 1 | 20% |
| F (20%) | 1 | **20%** |

**Average Grade:** C+ (71%)  
**Variance:** EXTREME (20% - 92%)  
**Failure Rate:** 20% complete failure

---

## Failure Modes Catalog

| Mode | Config | Symptom | Example | Solution |
|------|--------|---------|---------|----------|
| **Empty Placeholders** | sens=9, cyc≤2 | `pass` statements | Run 5 | More cycles |
| **Fragmentation** | sens=2 | 50+ briqs, circular deps | Run 7 | Higher sensitivity |
| **Polish Loop** 🆕 | sens=8, low C1 briqs | Utilities only, no server | Run 10 | Enforce min briqs |
| **Duplication** | sens=8, cyc=2 | app/ + src/app/ | Run 12 | Better prompts |
| **PARTIAL Stuck** | sens=6, cyc=4 | Never recovers | Run 8 | More cycles |

---

## Detailed Run Analysis

### Run 3: A- (92%) - The Winner

**Config:** sens=8, cyc=4  
**Why it worked:** Cycle 1 produced balanced 7 briqs covering all components

**Files Generated:**
```
qodeyard/
├── app/
│   ├── main.py (FastAPI + Uvicorn)
│   ├── routes.py
│   └── health.py
├── shared/
│   ├── config.py (Singleton pattern)
│   ├── logger.py
│   ├── constants.py
│   └── exceptions.py
├── tests/test_health.py
├── Dockerfile
└── README.md
```

**Requirements Coverage:**
- ✅ HTTP Server (FastAPI + Uvicorn)
- ✅ HTML Page (Tailwind CSS)
- ✅ /health endpoint (returns {"status": "ok"})
- ✅ README
- ✅ Dockerfile
- ✅ Config from env
- ✅ Logging
- ⚠️ Tests (minor issues)

---

### Run 7: D (50%) - Fragmentation Death Spiral

**Config:** sens=2, cyc=4

**The Problem:**
```
Cycle 1: 36 briqs → Too granular, creates fragmented code
Cycle 2: +8 briqs → Tries to fix, adds more fragments
Cycle 3: +4 briqs → Still broken, circular dependencies
Cycle 4: +4 briqs → Never converges, gives up (52 total briqs)
```

**Result:** 897 LOC across 15 files, but nothing works together

**Lesson:** sens=2 is too granular for simple projects

---

### Run 10: F (20%) - Polish Loop Disaster

**Config:** sens=8, cyc=4

**What was built:**
```
qodeyard/
└── shared/
    ├── config.py (84 LOC)
    ├── constants.py (42 LOC)
    ├── exceptions.py (99 LOC)
    └── logger.py (35 LOC)
```

**What was missing:**
- ❌ HTTP server
- ❌ HTML page
- ❌ /health endpoint
- ❌ README
- ❌ Dockerfile
- ❌ Tests
- ❌ **ANY application code!**

**Cycle Breakdown:**
| Cycle | Briqs | What Happened |
|-------|-------|---------------|
| 1 | 1 | "create_shared_utility_modules" |
| 2 | 2 | "modify constants for better type hints" |
| 3 | 2 | "modify constants for improved type hints" |
| 4 | 2 | "extend exceptions with domain-specific" |

**InspeQtor marked all cycles SUCCESS** because utilities were well-built!

---

### Run 11: B+ (87%) - Same Config, Different Result

**Config:** sens=8, cyc=4 (identical to Run 10)

**What was built:** Full application with 13 files, 375 LOC

**Why it succeeded:** Cycle 1 produced **10 briqs** instead of 1:
1. Create project directory structure
2. Implement shared/logger.py
3. Implement shared/config.py
4. Implement app/main.py
5. Implement app/routes.py
6. Implement app/handlers.py
7. Create requirements.txt
8. Write Dockerfile
9. Create README.md
10. Create test file

**Lesson:** The variance between Run 10 (1 briq) and Run 11 (10 briqs) is the bug!

---

## Sensitivity Comparison Summary

| Sensitivity | Runs | Avg Grade | Variance | Reliability | Cost Efficiency |
|-------------|------|-----------|----------|-------------|-----------------|
| sens=2 | 1 | D (50%) | N/A | ❌ Poor | ❌ Poor (52 briqs) |
| sens=6 | 3 | B- (79%) | Medium | ⚠️ 67% | OK (11-23 briqs) |
| sens=7 | 1 | B (82%) | N/A | ✅ Good | Good (20 briqs) |
| **sens=8** | **5** | **C+ (71%)** | **HIGH** | **⚠️ 60%** | **✅ Best (3-16 briqs)** |
| sens=9 | 2 | D (36%) | High | ❌ Poor | ✅ Best (1-6 briqs) |

---

## Recommended Configuration (Post v1.0.0)

### For Simple Projects
```yaml
briq_sensitivity: 7  # ENFORCED: 3-5 briqs
auto_cycle_limit: 4
```

### For Medium Projects
```yaml
briq_sensitivity: 6  # ENFORCED: 5-8 briqs
auto_cycle_limit: 5
```

### For Complex Projects
```yaml
briq_sensitivity: 5  # ENFORCED: 8-12 briqs
auto_cycle_limit: 6
```

---

## v1.0.0 Solution: Enforced Briq Ranges

The v1.0.0 release implements **hard enforcement** of briq counts:

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

### Enforcement Logic

```
AI generates briqs
       ↓
Check: min ≤ count ≤ max?
       ↓
   YES → ✅ Accept
   NO (too few) → 🔄 Retry with stronger prompt (up to 2x)
   NO (too many) → 🔗 Auto-merge consecutive briqs
```

### Expected Results Post-Fix

| Old Behavior | New Behavior |
|--------------|--------------|
| sens=8 → 1-16 briqs (random) | sens=8 → 2-3 briqs (enforced) |
| 20% failure rate | ~0% failure rate |
| Polish loop possible | Polish loop prevented |

---

## Test Environment

- **QonQrete Version:** v0.9.9-beta (pre-fix testing)
- **InstruQtor Model:** gpt-4.1-nano
- **ConstruQtor Model:** gemini-2.5-flash
- **InspeQtor Model:** gpt-4.1-mini
- **Host:** Docker container with security hardening

---

## Conclusion

The A/B testing revealed a critical bug in how `briq_sensitivity` was implemented. The v1.0.0 release fixes this by:

1. **Enforcing hard min/max ranges** for each sensitivity level
2. **Auto-retry** when AI produces too few briqs
3. **Auto-merge** when AI produces too many briqs
4. **Better defaults:** sens=7, cyc=4 (was sens=8, cyc=2)

Expected improvement: **From 60% reliability to ~99% reliability** for simple projects.

---

*Document generated: 2025-12-27*  
*QonQrete v1.0.0-stable*
