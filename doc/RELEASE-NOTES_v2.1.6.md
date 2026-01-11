# QonQrete v2.1.6-stable Release Notes

**Release Date:** January 2026  
**Codename:** "Anti-Copypasta Edition"

---

## 🎯 CRITICAL BUG FIX: Template Copypasta Prevention

### The Problem (v2.1.5 and earlier)

When building tool wrappers (e.g., `nmap_wrapper.py`, `sqlmap_wrapper.py`), the system was generating **identical boilerplate code** in every file instead of **actual tool-specific implementations**.

**Root Cause Analysis:**

1. **Qrystallizer Over-Matching** (`qrystallizer.py` line 1078-1081):
   ```python
   # OLD (v2.1.5) - TOO BROAD!
   'base_tool': [r'tool.*wrapper', r'base.*tool', r'nmap', r'masscan', r'nuclei', r'scanner']
   ```
   When user asked for "nmap wrapper", this matched the `base_tool` template pattern, returning a generic SafetyGovernor/EventBus boilerplate instead of searching for real nmap code.

2. **Triple Threat Combination Bug** (`triple_threat.py`):
   ```python
   # OLD (v2.1.5) - PICKS LONGEST, NOT BEST!
   best = max(successful, key=lambda r: len(r.code) if r.code else 0)
   ```
   The boilerplate templates were **longer** than web search snippets, so templates always won!

### The Fix (v2.1.6)

#### Fix 1: Qrystallizer Matcher Restrictions

Removed specific tool names from template matchers. Now only matches when user **explicitly** asks for generic/base/template versions:

```python
# NEW (v2.1.6) - SPECIFIC ONLY!
'base_tool': [r'generic.*tool.*wrapper', r'base.*tool.*template', r'tool.*skeleton']
'safety_governor': [r'generic.*safety', r'base.*governor', r'template.*safety']
```

#### Fix 2: Web Search Priority Weighting

Added priority scoring that **favors web search results** over templates:

```python
# NEW (v2.1.6) - PRIORITIZE WEB SEARCH!
tier_weights = {
    'SQAVENGER': 2.0,      # Web search - HIGHEST PRIORITY
    'QOMBINATOR': 1.5,     # Synthesis - medium priority  
    'QRYSTALLIZER': 1.0,   # Templates - lowest priority (fallback)
}
```

#### Fix 3: Boilerplate Detection Penalty

Added automatic detection and penalty for copypasta indicators:

```python
# v2.1.6: Penalty for boilerplate indicators
boilerplate_indicators = ['class SafetyGovernor', 'class EventBus', 'class SafetyConfig']
if boilerplate_count >= 2:
    weight *= 0.3  # 70% penalty for obvious copypasta
```

---

## 📊 Expected Improvements

| Metric | v2.1.5 | v2.1.6 (Expected) |
|--------|--------|-------------------|
| Boilerplate Ratio | 85.7% | <30% |
| Unique Implementations | ~234 classes | ~1200+ classes |
| Tool-Specific Code | 0% | >70% |
| Web Search Priority | 0 (longest wins) | 2x weight |

---

## 🔧 Configuration

The web priority weight is configurable in `triple_threat.py`:

```python
combine_tier_results(results, web_priority_weight=2.0)  # Default: 2x for web
```

Higher values = stronger preference for web search results.

---

## 📋 Upgrade Path

1. Replace `worqer/qrystallizer.py`
2. Replace `worqer/mindstaq/triple_threat.py`
3. Update `VERSION` to `2.1.6`
4. Clear any cached pattern matches

No config changes required - fixes are automatic!

---

## 🧪 Validation

To verify the fix is working, run a test build and check:

```bash
# Count boilerplate occurrences
grep -r 'class SafetyGovernor' qodeyard/ | wc -l

# Should be LOW (1-5) not HIGH (300+)
```

---

## 🎵 WoNQ Rating

- **Pre-Fix (v2.1.5):** 312/666 (INTERMEDIATE) - Template copypasta everywhere
- **Post-Fix (v2.1.6):** 480/666 (ADVANCED) - Real implementations expected!

---

## 🙏 Credits

Bug discovered via WoNQ Matrix deep analysis of AutoWonQNet v2.15 builds B12C3 vs B16C6.

*"The templates were winning because they were longer, not better."*

---

**Next Steps:**
- Run new builds with v2.1.6
- Compare boilerplate ratios
- Tune `web_priority_weight` if needed
