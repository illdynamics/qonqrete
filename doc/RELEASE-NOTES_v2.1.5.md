# QonQrete v2.1.5-stable Release Notes

**Release Date:** January 8, 2026

## 🐛 CRITICAL BUG FIX: Briq Inversion Now Works!

### The Bug (v2.1.3):
- `local_instruqtor.py` still had OLD BRIQ_RANGES (not inverted)
- Sensitivity was clamped to 0-9 instead of 0-16
- Short-circuit logic triggered at sens >= 8 (should be <= 1)
- Result: `-b 12` gave 1 briq instead of 75-110!

### The Fix (v2.1.5):
- ✅ BRIQ_RANGES inverted in BOTH `instruqtor.py` AND `local_instruqtor.py`
- ✅ Sensitivity clamp extended to 0-16
- ✅ Short-circuit logic inverted: sens <= 1 = monolithic (not >= 8)
- Result: `-b 12` now gives 75-110 briqs as expected!

## 🆕 QONVERGER: The Convergence Agent

### What It Is:
A new LOCAL agent that runs after InspeQtor to ensure convergence toward complete implementation.

### What It Does:
1. **Compares** original tasq.md requirements vs qodeyard output
2. **Finds** missing files/modules that weren't created in Cycle 1
3. **Generates** CREATE briqs for Cycle 2+ to fill the gaps
4. **Converges** implementation toward 100% specification coverage!

### Pipeline Position:
```
Cycle N: InstruQtor → ConstruQtor → InspeQtor → Qonverger → Cycle N+1
```

### Console Output:
```
[QONVERGER] Cycle 2 - Checking for missing files from previous cycle...
[QONVERGER] Found 47 missing files! Adding CREATE briqs...
[QONVERGER] Added 47 CREATE briqs (total: 96 briqs)
```

## 📊 WoNQ PREDICTIONS

### With v2.1.5 Fixes:

| Config | Expected Briqs | Expected Coverage | WoNQ Prediction |
|--------|----------------|-------------------|-----------------|
| `-b 9 -c 3` | 40-60 per cycle | 60-70% | 450-500/666 (68-75%) |
| `-b 12 -c 3` | 75-110 per cycle | 75-85% | 520-560/666 (78-84%) |
| `-b 12 -c 6` | 75-110 per cycle | 85-92% | 580-620/666 (87-93%) |

### With Qonverger Active (Cycle 2+):

| Config | Without Qonverger | With Qonverger | Improvement |
|--------|-------------------|----------------|-------------|
| `-b 12 -c 3` | 520/666 (78%) | **580-610/666 (87-92%)** | **+9-14%** |
| `-b 12 -c 6` | 580/666 (87%) | **620-650/666 (93-98%)** | **+6-11%** |

## 🔄 INVERTED BRIQ SENSITIVITY SCALE

### The Big Change: Higher Number = More Briqs!

The briq sensitivity scale has been **inverted** to be more intuitive:
- **Before:** 0 = Atomic (many briqs), 9 = Monolithic (1 briq) ❌ Counter-intuitive
- **After:** 0 = Monolithic (1 briq), 16 = Max (160-250 briqs) ✅ Intuitive

### New Scale (0-16):

| Level | Name | Briqs | Use Case |
|-------|------|-------|----------|
| 0 | Monolithic | 1 | Single simple task |
| 1 | Very Broad | 2-3 | Basic split |
| 2 | Broad | 3-5 | Major components |
| 3 | Feature-level | 5-8 | Per-feature |
| 4 | Component-level | 8-12 | Per-component |
| **5** | **Balanced** | **10-15** | **← NEW DEFAULT** |
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
| 16 | QONQRETE MAX | 160-250 | Enterprise mega-tasqs |

### Migration Guide:

If you were using the OLD scale, here's the mapping:

| Old `-b` | Old Meaning | New `-b` | New Meaning |
|----------|-------------|----------|-------------|
| `-b 9` | 1 briq | `-b 0` | 1 briq |
| `-b 7` | 3-5 briqs | `-b 2` | 3-5 briqs |
| `-b 5` | 8-12 briqs | `-b 4` | 8-12 briqs |
| `-b 3` | 15-20 briqs | `-b 6` | 15-20 briqs |
| `-b 0` | 40-60 briqs | `-b 9` | 40-60 briqs |

### Extended Range (NEW!):

For mega-projects that need even more granularity:
```bash
# For AutoWonQNet-scale projects (1000+ requirements)
./qonqrete.sh run -b 12 -c 6   # 75-110 briqs per cycle

# For enterprise mega-tasqs
./qonqrete.sh run -b 16 -c 10  # 160-250 briqs per cycle
```

## 📦 Files Changed

- `worqer/instruqtor.py` - Inverted BRIQ_RANGES, added levels 10-16
- `worqer/mindstaq/local_instruqtor.py` - Updated defaults
- `qrane/qrane.py` - Updated argparse and defaults
- `qonqrete.sh` - Updated help text and examples
- `worqspace/config.yaml` - Updated comments and default
- `README.md` - Updated documentation
- `doc/QUICKSTART.md` - Updated quick reference

## 🎯 Recommendations

| Project Size | Recommended `-b` |
|--------------|------------------|
| Simple script | 0-2 |
| Small module | 3-4 |
| Medium project | 5-6 (default) |
| Large application | 7-9 |
| Enterprise system | 10-12 |
| Mega specification | 13-16 |

## ✅ Compatibility

- **Drop-in replacement** for v2.1.2
- All other functionality unchanged
- SearXNG localhost:8888 config preserved
- MindstaQ templates preserved

---

*QonQrete v2.1.3-stable - Now with intuitive briq scaling!*
