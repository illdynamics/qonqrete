# QonQrete v2.0.0-stable Release Notes

**Release Date:** January 7, 2026  
**Codename:** "Pattern Master"

## 🎯 Major Focus: CODE VARIETY & ONLINE SEARCH

v1.9.9 fixed SPEED but all files had identical code. v2.0.0 fixes this with:
1. FILE-FIRST pattern matching (filename determines code pattern)
2. Markdown code block extraction (```python:path/file.py)
3. Online Qrawler with 10s timeout (graceful fallback)
4. TripleThreat parallel execution enabled

## 🔥 Key Fixes

### 1. FILE-FIRST Pattern Matching
Qombinator now prioritizes FILENAME over prompt content:
```
src/shared/constants.py  → constants_module pattern
shared/config_loader.py  → config_loader pattern
intel/target_profile.py  → target_profile pattern
ai/base_capability.py    → capability_base pattern
```

### 2. Markdown Code Block Extraction (NEW!)
When briq contains ```python:qodeyard/path/file.py, we now extract the path directly:
```python
# Old: Had to guess from prompt text
# New: Extracts directly from markdown header
markdown_path = re.search(r'```[a-z]+:([\w/.-]+\.(?:py|sh|...))', text)
```

### 3. Online Qrawler with Timeout
```yaml
sqavenger:
  offline_mode: false     # v2.0.0: Online mode enabled!
  timeout: 10             # 10s per query with graceful fallback
```

If any query times out, we use the snippets collected so far + OFFLINE_PATTERNS.

### 4. TripleThreat Mode Enabled
```yaml
mindstaq:
  triple_threat:
    enabled: true         # Run all tiers in parallel
    timeout_per_tier: 30  # Pick best result
```

## 📊 Expected Results

| Metric | v1.9.9 | v2.0.0 |
|--------|--------|--------|
| Unique Python files | 3/10 | 10/10 |
| Unique Shell scripts | 1-2/8 | 8/8 |
| Pattern matches | Hash-based | File-based |
| Search mode | Offline | Online + timeout |

## 🎯 WoNQ Prediction for -b 2 -c 12

**Prediction: 480-540/666 @ 78% confidence**

| Component | Score |
|-----------|-------|
| Speed | 666/666 ✅ (all briqs < 100ms) |
| Variety | 500/666 ✅ (file-specific patterns) |
| Completeness | 400/666 ⚠️ (limited by pattern library) |
| Correctness | 100/100 ✅ (InspeQtor passes) |

### Why Not Higher?
- mindstaQ is pattern-based, not truly generative
- Complex business logic still won't match patterns
- But now each file gets APPROPRIATE code!

## 🚀 Run Command

```bash
./qonqrete.sh -a -b 2 -c 12 -n "autowonqnet_v200"
```

## 📁 Files Changed

- `worqer/mindstaq/__init__.py` - Markdown code block extraction
- `worqer/mindstaq/sqavenger.py` - Qrawler timeout with fallback
- `worqer/qombinator.py` - 15+ patterns, FILE-FIRST matching
- `worqer/mindstaq/language_adapters.py` - Context-aware shell scripts
- `worqer/mindstaq/mindstaq_logger.py` - Agent event logging
- `worqspace/config.yaml` - Online mode, TripleThreat enabled

---
**Zero LLM. Zero Cost. MAXIMUM VARIETY!** 🔥
