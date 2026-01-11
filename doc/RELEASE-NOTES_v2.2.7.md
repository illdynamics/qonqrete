# QonQrete v2.2.7-stable Release Notes

## 🧠 INTELLIGENT CODE GENERATION - NO MORE COPYPASTA! 🧠

**Release Date:** January 2025  
**Type:** Major Quality Fix

---

## The Problems Found

### 1. GARBAGE SEARCH QUERIES
v2.2.6 was sending nonsense queries:
```
"python 10_and_172_and_192 local 885 example code"  ← WTF?!
"python "  ← EMPTY!
```
**ROOT CAUSE:** BRIQ filenames like `cyqle1_tasq1_briq000_10_and_172_and_192.md` were parsed into garbage keywords.

### 2. COPYPASTA WINNING OVER WEB RESULTS
Even when web search worked, Franqenstein was picking generic copypasta because it "scored higher" on docstrings/type hints.
```
qodeyard/bloodhound_wrapper.py:
├── 16x class Repository  ← COPYPASTA!
├── 0x bloodhound code    ← NOTHING SPECIFIC!
```

### 3. TOOL NAMES NOT DETECTED
BRIQ description was `base_tool` but filename was `bloodhound_wrapper.py` - tool detection wasn't checking filenames!

### 4. bloq.d/ vs qodeyard/ CONFUSION
`bloq.d/` = SKELETONS (intentional for LLM context)
`qodeyard/` = REAL CODE
The real code was there but filled with generic patterns.

---

## The Fixes

### 1. `_clean_keywords()` - New Method in SQavenger
Filters garbage from briq filenames:
```python
GARBAGE_TOKENS = {'and', 'or', 'cyqle', 'tasq', 'briq', '000', '001'...}
TOOL_KEYWORDS = {'nmap', 'bloodhound', 'feroxbuster', 'masscan'...}

# BEFORE: ['10', 'and', '172', 'and', '192']
# AFTER:  ['bloodhound', 'wrapper']
```

### 2. Tool Extraction from Filename in `_parse_intent()`
Now extracts tool names from `intent.target_file`:
```python
# filename: bloodhound_wrapper.py
# keywords: ['bloodhound', 'wrapper', ...] ← PRIORITIZED!
```

### 3. TOOL_PATTERNS FIRST for Security Tools
When tool detected in filename, use TOOL_PATTERNS directly:
```python
if detected_tool:
    _log(f"[SQavenger] Tool '{detected_tool}' detected!")
    _log(f"[SQavenger] Trying TOOL_PATTERNS first...")
    tool_code = self._match_offline_pattern(combined_text, context)
    if tool_code:
        return tool_code  # Skip garbage web search!
```

### 4. Copypasta Penalties in Franqenstein
```python
# Generic names = HEAVY penalty
generic_names = {'repository', 'config', 'shared', 'error', 'entity'...}
if comp.name.lower() in generic_names:
    score -= 0.4  # -40%!

# Copypasta indicators = HEAVY penalty
copypasta_indicators = ['self._storage:', '"""repository."""'...]
if copypasta_count >= 2:
    score -= 0.5  # -50%!

# Tool-specific = BONUS
tool_indicators = ['subprocess.run', 'nmap', 'bloodhound'...]
if tool_count >= 2:
    score += 0.4  # +40%!
```

### 5. SQAVENGER Preference in combine_tier_results
When SQAVENGER has tool-specific code, USE IT DIRECTLY:
```python
if sqavenger_result.code:
    if tool_count >= 2 and copypasta_count == 0:
        return sqavenger_result.code, "Tool-specific SQAVENGER result"
```

### 6. Boilerplate Detection in triple_threat.py
Added Repository copypasta detection:
```python
boilerplate_indicators = [
    'class Repository:',      # Generic CRUD
    'class Shared:',          # Generic shared
    '"""Repository."""',      # Stub docstrings
    'self._storage: Dict',    # Generic storage
    ...
]
```

---

## Expected Results

### Search Queries (v2.2.7)
```
[SQavenger] Tool 'bloodhound' detected in task/filename!
[SQavenger] Trying TOOL_PATTERNS first...
[SQavenger] Using TOOL_PATTERN for 'bloodhound'!
```

### Code Output
```python
# BEFORE v2.2.6:
class Repository:
    def __init__(self):
        self._storage: Dict[str, Dict] = {}  # GENERIC!

# AFTER v2.2.7:
class BloodHoundWrapper:
    def __init__(self, sharphound_path: str = None):
        self._verify_sharphound()  # TOOL-SPECIFIC!
    
    def collect(self, domain: str, method: str = "all"):
        cmd = ["mono", self.sharphound_path, "-c", method]
        subprocess.run(cmd, ...)  # REAL IMPLEMENTATION!
```

---

## WoNQ Predictions

| Build Type | v2.2.6 Actual | v2.2.7 Expected | Improvement |
|------------|---------------|-----------------|-------------|
| Security tools | 140-280/666 | 450-550/666 | +70-200% |
| Generic code | 200-300/666 | 350-450/666 | +50-75% |

---

## Files Changed

| File | Changes |
|------|---------|
| `worqer/mindstaq/sqavenger.py` | `_clean_keywords()`, improved `_build_queries()`, tool detection in `generate()` |
| `worqer/mindstaq/__init__.py` | Tool extraction in `_parse_intent()` |
| `worqer/mindstaq/triple_threat.py` | Repository copypasta detection, SQAVENGER preference, tool bonuses |
| `worqer/mindstaq/franqenstein.py` | Copypasta penalties, tool bonuses in `score_component()` |

---

## Test It!

```bash
# Run with v2.2.7
./qonqrete.sh qonstruqt -t worqspace/tasq.md

# Look for in logs:
# [SQavenger] Tool 'bloodhound' detected in task/filename!
# [SQavenger] Using TOOL_PATTERN for 'bloodhound'!
# Or: Tool-specific SQAVENGER result (tools=3)
```

---

*QonQrete v2.2.7-stable - "Real Tools, Real Code, No More Copypasta!"* 🎯
