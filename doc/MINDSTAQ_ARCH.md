# mindstaQ Architecture

**Version:** 1.0.0  
**QonQrete:** v1.2.3-stable

---

## Master Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                           mindstaQ MASTER ARCHITECTURE                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │                          USER BRIQ / TASK                               │ ║
║  └───────────────────────────────┬─────────────────────────────────────────┘ ║
║                                  │                                           ║
║                                  ▼                                           ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │                        QOMPUTATOR (worqer/qomputator.py)                │ ║
║  │  SCORING ALGORITHM (0-666 Scale - The Beast Number 😈)                  │ ║
║  │  ├─ Lexical score     [0-100]                                           │ ║
║  │  ├─ Technical score   [0-150]                                           │ ║
║  │  ├─ Semantic score    [0-150]                                           │ ║
║  │  └─ Reasoning score   [0-116]                                           │ ║
║  │                                                                         │ ║
║  │  ROUTING THRESHOLDS:                                                    │ ║
║  │  ├─ 0-100:   TIER 0 → Qrystallizer                                      │ ║
║  │  ├─ 101-400: TIER 1 → sQavenger                                         │ ║
║  │  └─ 401-666: TIER 2 → Qombinator                                        │ ║
║  └───────────────────────────────┬─────────────────────────────────────────┘ ║
║                                  │                                           ║
║         ┌────────────────────────┼────────────────────────────┐              ║
║         ▼                        ▼                            ▼              ║
║  ┌─────────────┐      ┌─────────────────────┐      ┌─────────────────────┐   ║
║  │   TIER 0    │      │       TIER 1        │      │       TIER 2        │   ║
║  │ QRYSTALLIZER│      │      SQAVENGER      │      │     QOMBINATOR      │   ║
║  │  (0-100)    │      │      (101-400)      │      │      (401-666)      │   ║
║  │             │      │                     │      │                     │   ║
║  │ 20+ built-in│      │ Pattern Library     │      │ Multi-source        │   ║
║  │ templates   │      │ + Qrawler (v2.0)    │      │ combination         │   ║
║  │             │      │                     │      │                     │   ║
║  │ ~10-50ms    │      │ ~500ms-2s           │      │ ~2-10s              │   ║
║  └──────┬──────┘      └──────────┬──────────┘      └──────────┬──────────┘   ║
║         │                        │                            │              ║
║         └────────────────────────┴────────────────────────────┘              ║
║                                  │                                           ║
║                                  ▼                                           ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │                   QONCENTRATOR (worqer/qoncentrator.py)                 │ ║
║  │  ├─ AST-based code manipulation                                         │ ║
║  │  ├─ Import resolution                                                   │ ║
║  │  └─ Import sorting (isort-style)                                        │ ║
║  └───────────────────────────────┬─────────────────────────────────────────┘ ║
║                                  │                                           ║
║                                  ▼                                           ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │                     QONSCIENCE (worqer/qonscience.py)                   │ ║
║  │  ├─ Syntax validation                                                   │ ║
║  │  ├─ Import checking                                                     │ ║
║  │  ├─ Linter integration (Ruff)                                           │ ║
║  │  └─ Auto-fix loop (max 5 iterations)                                    │ ║
║  └───────────────────────────────┬─────────────────────────────────────────┘ ║
║                                  │                                           ║
║                                  ▼                                           ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │                            OUTPUT                                        │ ║
║  │  Generated code in markdown format                                      │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Mermaid Diagram

```mermaid
flowchart TD
    subgraph Input
        BRIQ[User Briq / Task]
    end

    subgraph Scoring["Qomputator (0-666)"]
        LEX[Lexical 0-100]
        TECH[Technical 0-150]
        SEM[Semantic 0-150]
        REASON[Reasoning 0-116]
        TOTAL[Total Score]
        ROUTE{Route}
        
        LEX --> TOTAL
        TECH --> TOTAL
        SEM --> TOTAL
        REASON --> TOTAL
        TOTAL --> ROUTE
    end

    subgraph Tiers
        T0["Qrystallizer<br/>(0-100)"]
        T1["sQavenger<br/>(101-400)"]
        T2["Qombinator<br/>(401-666)"]
    end

    subgraph PostProcess
        CONC[Qoncentrator]
        CONS[Qonscience]
    end

    BRIQ --> LEX
    BRIQ --> TECH
    BRIQ --> SEM
    BRIQ --> REASON
    
    ROUTE -->|0-100| T0
    ROUTE -->|101-400| T1
    ROUTE -->|401-666| T2
    
    T0 --> CONC
    T1 --> CONC
    T2 --> CONC
    
    CONC --> CONS
    CONS --> OUTPUT[Generated Code]

    style BRIQ fill:#e1f5fe
    style OUTPUT fill:#c8e6c9
```

---

## File Structure

```
qonqrete-localai/
├── worqer/
│   ├── mindstaq/
│   │   └── __init__.py         # MindstaQEngine orchestrator
│   │
│   ├── qomputator.py           # Complexity scoring (0-666)
│   ├── qrystallizer.py         # Template engine (Tier 0)
│   ├── sqavenger.py            # Search harvester (Tier 1)
│   ├── qombinator.py           # Evolutionary synthesis (Tier 2)
│   ├── qoncentrator.py         # AST grafting
│   ├── qonscience.py           # Verification
│   │
│   └── lib_ai.py               # Provider abstraction (includes mindstaq)
│
├── worqspace/
│   └── config.yaml             # mindstaq configuration
│
└── doc/
    ├── MINDSTAQ.md             # User documentation
    └── MINDSTAQ_ARCH.md        # Architecture (this file)
```

---

## Integration

```mermaid
graph TB
    subgraph QonQrete
        TASQ --> INSTRUQTOR
        INSTRUQTOR --> BRIQ
        BRIQ --> CALQ
        CALQ --> CONSTRUQTOR
        CONSTRUQTOR --> INSPEQTOR
        INSPEQTOR --> QODEYARD
    end

    subgraph Provider
        CONSTRUQTOR --> PROV{Provider?}
        PROV -->|gemini/openai| CLOUD[Cloud AI]
        PROV -->|local + mindstaq| MINDSTAQ[mindstaQ]
    end

    CLOUD --> OUTPUT
    MINDSTAQ --> OUTPUT
    OUTPUT --> QODEYARD

    style MINDSTAQ fill:#c8e6c9
    style CLOUD fill:#bbdefb
```

---

*Built for the QonQrete ecosystem* 🔥
