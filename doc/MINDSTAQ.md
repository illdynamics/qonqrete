# mindstaQ: Zero-Cost Local Code Generation Engine

**Version:** 1.2.1  
**QonQrete:** v1.2.3-stable  
**Status:** Production Ready ✅

---

## 🎯 Overview

**mindstaQ** is QonQrete's revolutionary noLLM code generation provider that replaces cloud AI with fully deterministic, symbolic intelligence at **zero cost**.

### Cost Comparison

| System | Cost per 1000 Requests | Quality | Latency |
|--------|------------------------|---------|---------|
| Cloud AI (Gemini/GPT-4) | $1-10 | Excellent | 2-5s |
| **mindstaQ** | **$0.00** | Very Good (~85-90%) | 100ms-3s |

---

## 🚀 Quick Start

Enable the complete zero-cost stack in your `config.yaml`:

```yaml
agents:
  tasqleveler:
    provider: local
    model: tasqleveler     # ← FREE task enhancement (v1.2.0)
  instruqtor:
    provider: local
    model: instruqtor      # ← FREE task splitting
  construqtor:
    provider: local
    model: mindstaq        # ← FREE code generation
  inspeqtor:
    provider: local
    model: inspeqtor       # ← FREE code review
```

Run QonQrete as normal:

```bash
./qonqrete.sh run
```

**Note:** When using local construqtor, `calqulator` and `qontrabender` are automatically skipped (no API costs to calculate, no Gemini caching needed).

---

## 🆕 LocalTasqLeveler (v1.2.0)

**LocalTasqLeveler** is the zero-cost task enhancement agent that only triggers on complex tasks above a threshold.

### Features

| Feature | Description |
|---------|-------------|
| **Threshold Detection** | Only enhances tasks above min chars/lines/sections |
| **Build Order** | Suggests file build order based on naming patterns |
| **Success Criteria** | Adds verification checklist templates |
| **Docker Notes** | Adds containerization guidance if Dockerfile detected |
| **File Detection** | Detects Python, JS, Docker, config files |

### Threshold Configuration

```yaml
mindstaq:
  tasqleveler:
    min_chars: 100         # Minimum characters to trigger (v1.2.1)
    min_lines: 5           # Minimum lines to trigger
    min_sections: 2        # Minimum section headers to trigger
    min_bullets: 3         # Minimum bullet points to trigger
    skip_single_file: true # Skip single-file projects
```

### CLI Usage

```bash
python -m worqer.mindstaq.local_tasqleveler task.md enhanced.md
```

---

## 🆕 LocalInstruQtor (v1.1.2)

**LocalInstruQtor** is the zero-cost task decomposition agent that splits tasks into BRIQs using pattern-based analysis.

### Features

| Feature | Description |
|---------|-------------|
| **Section Splitting** | `# Headers`, `## Subheaders`, `CAPS TITLES` |
| **Bullet Splitting** | `- bullets`, `* asterisks`, `1. numbered lists` |
| **Paragraph Splitting** | Double newline separation |
| **Logical Splitting** | `and`, `then`, `also`, `additionally` conjunctions |
| **Compound Patterns** | "build X and Dockerfile" → two tasks |
| **Sensitivity Aware** | Respects 0-9 sensitivity scale |

### CLI Usage

```bash
# From file
python -m worqer.mindstaq.local_instruqtor --file task.md --sensitivity 5

# With detailed analysis
python -m worqer.mindstaq.local_instruqtor --file task.md --explain

# From stdin
echo "Build webserver and Dockerfile" | python -m worqer.mindstaq.local_instruqtor
```

---

## 🔍 LocalInspeQtor (v1.1.2)

**LocalInspeQtor** is the zero-cost code review agent that analyzes code using AST and pattern matching.

### Features

| Category | Checks |
|----------|--------|
| **Syntax** | Python compile() validation |
| **Security** | Hardcoded secrets, SQL injection, eval(), os.system() |
| **Quality** | Cyclomatic complexity, function length, docstrings, type hints |
| **Performance** | String concat in loops, deep attribute chains |
| **Style** | Line length, TODO comments, print statements |

### CLI Usage

```bash
# Review a file
python -m worqer.mindstaq.local_inspeqtor path/to/file.py

# Review a directory
python -m worqer.mindstaq.local_inspeqtor path/to/dir/

# Set minimum passing score
python -m worqer.mindstaq.local_inspeqtor --min-score 70 path/to/file.py

# XML output for integration
python -m worqer.mindstaq.local_inspeqtor --format xml path/to/file.py
```

### Enable in config.yaml

```yaml
agents:
  inspeqtor:
    provider: local
    model: inspeqtor
```

---

## 🤖 Agent Architecture

| Agent | File | Role | Tier |
|-------|------|------|------|
| **Qomputator** | `qomputator.py` | Complexity scoring (0-666) | Router |
| **Qrystallizer** | `qrystallizer.py` | Template engine | Tier 0 |
| **sQavanger** | `sqavanger.py` | Search harvester via Qrawler | Tier 1 |
| **Qombinator** | `qombinator.py` | Evolutionary synthesis | Tier 2 |
| **Qoncentrator** | `qoncentrator.py` | AST grafting | Post-process |
| **Qonscience** | `qonscience.py` | Verification & auto-fix | Post-process |

### Pipeline Flow

```
USER BRIQ / TASK
       │
       ▼
┌──────────────────────────────┐
│  QOMPUTATOR                  │  Score complexity (0-666)
│  (Complexity Scoring)        │  Route to appropriate tier
└──────────────────────────────┘
       │
       ├─── 0-85 ─────▶ QRYSTALLIZER (Tier 0 - Templates)
       │
       ├─── 86-400 ───▶ SQAVANGER (Tier 1 - Search via Qrawler)
       │
       └─── 401-666 ──▶ QOMBINATOR (Tier 2 - Evolutionary)
              │
              ▼
┌──────────────────────────────┐
│  QONCENTRATOR                │  AST manipulation
│  (AST Grafting)              │  Import resolution
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  QONSCIENCE                  │  Syntax validation
│  (Verification)              │  Auto-fix loop (max 5 iterations)
└──────────────────────────────┘
       │
       ▼
   OUTPUT CODE
```

---

## 📐 Qomputator: Complexity Scoring (0-666)

The Qomputator scores task complexity on a **0-666 scale** (The Beast Number 😈):

### Score Components

| Component | Range | Description |
|-----------|-------|-------------|
| **Lexical** | 0-100 | Word count, conditionals, negations |
| **Technical** | 0-150 | Entity count, library mentions |
| **Semantic** | 0-150 | Task novelty, requirement specificity |
| **Reasoning** | 0-116 | Optimization, design, concurrency, security |

### Routing Thresholds

| Score Range | Tier | Agent | Method |
|-------------|------|-------|--------|
| **0-85** | 0 | Qrystallizer | Template matching (~10-50ms) |
| **86-400** | 1 | sQavanger | Pattern search (~500ms-2s) |
| **401-666** | 2 | Qombinator | Evolutionary synthesis (~2-10s) |

---

## 🔧 Configuration Reference

```yaml
mindstaq:
  enabled: true
  qomputator:
    thresholds:
      tier_0_max: 85
      tier_1_max: 400
  qrystallizer:
    enabled: true
  sqavanger:
    strategy: parallel
  qrawler:
    enabled: false
  qombinator:
    enabled: true
  qoncentrator:
    auto_resolve_imports: true
  qonscience:
    max_iterations: 5
```

---

## 📊 Expected Quality

| Tier | Cloud AI | mindstaQ | Cost |
|------|----------|----------|------|
| Tier 0 | 98% | 99% | $0 |
| Tier 1 | 95% | 85-90% | $0 |
| Tier 2 | 90% | 70-80% | $0 |
| Overall | ~95% | ~85-90% | **$0** |

---

## 🛠️ CLI Usage

```bash
# Score complexity
python worqer/qomputator.py --text "Add email validation"

# Generate from template
python worqer/qrystallizer.py --text "Create validation function" --list

# Search patterns
python worqer/sqavanger.py --text "HTTP GET request" --list

# Verify code
python worqer/qonscience.py --file mycode.py --fix
```

---

*mindstaQ: Because the best code generation is the one that costs nothing.* 🔥
