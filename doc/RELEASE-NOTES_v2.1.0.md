# QonQrete v2.1.0-stable Release Notes

**Release Date:** January 8, 2026  
**Codename:** "LOCAL BY DEFAULT" 🆓

## 🔧 Critical Fix: ConstruQtor Now Defaults to Local/MindstaQ!

### The Problem
v2.0.x had construqtor.py defaulting to Gemini:
```python
ai_provider = agent_cfg.get('provider', 'gemini')     # ← WRONG!
ai_model = agent_cfg.get('model', 'gemini-1.5-pro')   # ← WRONG!
```

This caused cloud API calls even when config said `provider: local`!

### The Fix (v2.1.0)
```python
ai_provider = agent_cfg.get('provider', 'local')      # ← FIXED!
ai_model = agent_cfg.get('model', 'mindstaq')         # ← FIXED!
```

### Added Diagnostic Logging
Now shows what provider is being used:
```
    Provider: local | Model: mindstaq | Mode: LOCAL MINDSTAQ
```

## 📊 Full Component Audit - ALL PRESENT!

### Main Agents (13)
✅ construqtor, instruqtor, inspeqtor, calqulator, qompressor
✅ qontextor, qontrabender, qombinator, qrystallizer, sqavenger
✅ qomputator, qoncentrator, tasqleveler

### MindstaQ Components (24)
✅ __init__.py (1094 lines) - Main MindstaQEngine
✅ z3_solver.py (689 lines) - Z3 constraint solver
✅ qalibrator.py (766 lines) - AST mutations
✅ qualifier.py (880 lines) - Fitness scoring
✅ franqenstein.py (623 lines) - Code combinator
✅ triple_threat.py (239 lines) - Parallel tier execution
✅ local_instruqtor.py (841 lines)
✅ local_inspeqtor.py (1228 lines)
✅ local_tasqleveler.py (377 lines)
✅ pattern_db.py (1072 lines)
✅ template_breeder.py (723 lines)
✅ semantic_matcher.py (605 lines)
✅ code_normalizer.py (516 lines)
✅ type_synthesis.py (880 lines)
✅ decision_table.py (740 lines)
✅ qrawler.py (682 lines) - With POST fix for SearXNG!
✅ sqavenger.py (964 lines)
✅ deep_qrawler.py (1079 lines)
✅ parallel_harvester.py (565 lines)
✅ language_adapters.py (630 lines)
✅ allowlist_security.py (908 lines)
✅ smart_qomputator.py (571 lines)
✅ timewalqer.py (873 lines)
✅ wonq_index.py (618 lines)
✅ mindstaq_logger.py (234 lines)

### lib_ai Routing
✅ Supports: openai, gemini, anthropic, deepseek, local
✅ Local routing: `provider='local' + model='mindstaq' → _run_mindstaq()`

## 🎯 MindstaQ Pipeline (15 Steps)

1. Parse intent
2. SmartQomputator scoring (0-666)
3. DecisionTable routing
4. Tier execution (Qrystallizer/SQavenger/Qombinator)
5. ParallelHarvester (multi-source search)
6. SemanticMatcher (find similar code)
7. Franqenstein (combine best parts)
8. **[Qalibrator ⟷ Qualifier LOOP]** (evolve code)
9. TypeSynthesis (generate glue code)
10. CodeNormalizer (clean up)
11. Qoncentrator (AST processing)
12. AllowlistSecurity (validate)
13. Qonscience (final verification)
14. WonqIndex (cache successful pattern)
15. TimeWalQer (track history)

## 📁 SearXNG Integration
- Qrawler uses POST method ✅
- Bot detection disabled via limiter.toml ✅
- Config in `searxng/` folder ✅

## 🚀 Quick Start
```bash
# Extract
unzip qonqrete_v2.1.0-stable.zip
cd qonqrete_v2.1.0-stable

# Start SearXNG (optional but recommended)
docker compose -f docker-compose.searxng.yml up -d

# Run (will use LOCAL MindstaQ by default!)
./qonqrete.sh -a -b 2 -c 12 -n "myproject"

# Expected output:
#     Provider: local | Model: mindstaq | Mode: LOCAL MINDSTAQ
```

---

**QonQrete v2.1.0: Zero LLM, Zero Cost, FULL LOCAL! 🆓🔥**
