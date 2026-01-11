# Release Notes v2.1.7

**Release Date:** January 2026  
**Codename:** "WONQ EVOLUTION"

---

## 🎯 Overview

v2.1.7 is a MAJOR feature release that introduces three powerful new code generation techniques and expands the anti-copypasta detection system. This release directly addresses the tool-specific code generation weakness identified in v2.1.6 builds.

---

## 🆕 New Features

### 1. Darwinian Evolution (Genetic Programming) 🧬

**File:** `worqer/mindstaq/darwinian.py`  
**WoNQ Impact:** +45-60 points for novel algorithm generation

A genetic programming engine that EVOLVES code through:
- **Population-based evolution** - Multiple code candidates compete
- **AST-level mutations** - Safe transformations that preserve syntax
- **Crossover operations** - Combine successful code from multiple parents
- **Test-driven fitness** - Code is scored by passing test cases
- **Novelty search** - Encourages exploration to avoid local optima

```python
from worqer.mindstaq.darwinian import evolve_from_tests

tests = [
    {'inputs': {'x': 5}, 'expected': 10},
    {'inputs': {'x': 3}, 'expected': 6},
]
code, fitness = evolve_from_tests(tests, function_name='double')
```

**Key Classes:**
- `DarwinianEvolver` - Main evolution engine
- `ASTMutator` - Safe AST mutation operations
- `Crossover` - Code combination strategies
- `FitnessEvaluator` - Test-based fitness scoring
- `NoveltySearch` - Diversity maintenance

---

### 2. Wisdom Pits (Domain Expert Knowledge Banks) 📚

**File:** `worqer/mindstaq/wisdom_pits.py`  
**WoNQ Impact:** +25-35 points for domain-specific code

Pre-built knowledge banks with REAL tool-specific implementations:

**Supported Tools (Initial Release):**
- `nmap` - Full-featured port scanner wrapper with async support
- `bloodhound` - Active Directory collector and analyzer
- `feroxbuster` - Web content discovery scanner
- `masscan` - High-speed port scanner

```python
from worqer.mindstaq.wisdom_pits import get_tool_code, search_wisdom

# Get implementation for a specific tool
nmap_code = get_tool_code("nmap")

# Search for relevant entries
results = search_wisdom("port scanner network")
```

**Key Features:**
- Tool-specific code templates (NOT generic boilerplate!)
- Security best practices built-in
- Actual API knowledge for real tools
- Extensible pit system for new domains

**Domains Supported:**
- Security Tools
- Network Scanning
- Web Pentesting
- Post-Exploitation
- C2 Frameworks

---

### 3. Dependency Graph Scaffold 🏗️

**File:** `worqer/mindstaq/dependency_graph.py`  
**WoNQ Impact:** +25-35 points for multi-file architecture

Analyzes and understands project structure:

```python
from worqer.mindstaq.dependency_graph import analyze_project, suggest_file_placement

# Analyze entire project
analysis = analyze_project("/path/to/project")
print(f"Pattern: {analysis.pattern}")
print(f"Circular deps: {len(analysis.circular_deps)}")

# Get placement suggestion for new code
suggestion = suggest_file_placement(
    "/path/to/project",
    code_type="class",
    dependencies=["BaseClass", "utils"]
)
```

**Key Features:**
- AST-based import analysis
- Dependency graph construction
- Circular dependency detection
- Architecture pattern recognition (Layered, MVC, Domain-Driven, etc.)
- Smart file placement suggestions
- Mermaid diagram export

---

## 🔧 Improvements

### Expanded Anti-Copypasta Detection

**File:** `worqer/mindstaq/triple_threat.py`

v2.1.7 adds detection for NEW boilerplate patterns discovered in v2.1.6 builds:

**New Patterns Detected:**
- `class ValidationResult` (was in 9 files in b3c3 build!)
- `class Validator`
- `class ConfigLoader` (when misplaced)
- `EMAIL_RE = re.compile`
- `IP_RE = re.compile`
- `class BaseHandler`
- `class GenericWrapper`
- `class AbstractFactory`

**New Detection Logic:**
- Duplicate class definition detection (50% penalty)
- Graduated penalties: 30% (1 pattern), 70% (2 patterns), 80% (3+ patterns)
- Web search results now get 2x priority over templates

---

## 📊 Expected WoNQ Improvements

| Metric | v2.1.6 | v2.1.7 (Expected) | Improvement |
|--------|--------|-------------------|-------------|
| AutoWonQNet b3c3 | ~380 | ~520-560 | +140-180 |
| AutoWonQNet b16c6 | ~495 | ~580-620 | +85-125 |
| Boilerplate Ratio | ~48% | ~20-30% | -18-28% |
| Tool-Specific Code | ~15% | ~60-75% | +45-60% |
| Novel Algorithm Gen | ~10% | ~40-50% | +30-40% |

---

## 🧠 Technical Details

### New Module Dependencies

```
darwinian.py      → ast, random, copy, hashlib, dataclasses
wisdom_pits.py    → re, json, pathlib, dataclasses
dependency_graph.py → ast, os, pathlib, collections, json
```

### Integration Points

The new modules integrate with existing mindstaQ components:

```
triple_threat.py
├── Uses wisdom_pits for tool-specific code
├── Uses darwinian for novel algorithm synthesis
└── Uses dependency_graph for file placement

qrystallizer.py
└── Falls back to wisdom_pits when templates fail

sqavenger.py
└── Web search enhanced by wisdom_pits keywords
```

---

## 🚀 Upgrade Guide

### From v2.1.6

1. Replace entire `worqer/mindstaq/` directory
2. No configuration changes needed
3. New features are opt-in (enabled by default in triple_threat)

### Testing the Upgrade

```bash
# Verify new modules
python3 -c "from worqer.mindstaq.darwinian import DarwinianEvolver; print('✅ Darwinian')"
python3 -c "from worqer.mindstaq.wisdom_pits import WisdomPitsManager; print('✅ Wisdom Pits')"
python3 -c "from worqer.mindstaq.dependency_graph import DependencyGraph; print('✅ Dependency Graph')"

# Run a test build
./qonqrete.sh -b 3 -c 3 -P tasq.md
```

---

## 🔮 Roadmap

### v2.2.0 (Planned)

- Monte Carlo Tree Search for Code (+35-50 WoNQ)
- Expanded Wisdom Pits (20+ tools)
- Symbolic Execution integration

### v2.3.0 (Planned)

- Full Z3 constraint solving
- Taint analysis for security
- Neural-symbolic hybrid (tiny models)

---

## 📝 Known Issues

1. **Darwinian Evolution** may take 30-60 seconds for complex functions
2. **Wisdom Pits** currently only supports Python tools
3. **Dependency Graph** may miss dynamic imports

---

## 🙏 Credits

- Genetic Programming concepts from DEAP library
- BloodHound integration based on bloodhound-python
- Architecture patterns from Clean Architecture principles

---

**Full Changelog:** [v2.1.6...v2.1.7](https://github.com/qonqrete/qonqrete/compare/v2.1.6...v2.1.7)
