# Release Notes v2.1.8

**Release Date:** January 2026  
**Codename:** "STRATEGIC SEARCH"

---

## 🎯 Overview

v2.1.8 introduces **Monte Carlo Tree Search (MCTS)** for strategic code generation - the same algorithm that powered AlphaGo's world champion victories! This complements Darwinian Evolution by adding STRATEGIC exploration of the code space.

---

## 🆕 New Features

### Monte Carlo Tree Search for Code 🌳🎮

**File:** `worqer/mindstaq/mcts_code.py`  
**WoNQ Impact:** +35-50 points for complex algorithm generation

MCTS treats code generation as a game-like search problem:

```
                    ROOT (seed code)
                   /    |    \
                ADD   MODIFY  DELETE
               / | \
            IF  FOR  ASSIGN
           / \
        ...  ...   ← UCB1 selects best path!
```

**Key Components:**

1. **UCB1 Selection** - Balances exploration vs exploitation
   ```
   UCB1 = average_reward + C * sqrt(ln(parent_visits) / child_visits)
   ```

2. **Code Actions** - 15 different AST transformations:
   - `ADD_ASSIGNMENT` - Add variable assignment
   - `ADD_IF_STATEMENT` - Add conditional logic
   - `ADD_FOR_LOOP` - Add iteration
   - `ADD_WHILE_LOOP` - Add loop
   - `ADD_RETURN` - Add/modify return statement
   - `MODIFY_OPERATOR` - Change +/-/*/etc
   - `MODIFY_CONSTANT` - Tweak numeric values
   - `DELETE_STATEMENT` - Remove code
   - `WRAP_IN_TRY` - Add error handling
   - And more...

3. **Rollout Simulation** - Random playouts to evaluate paths

4. **Backpropagation** - Update tree with discovered rewards

**Usage:**

```python
from worqer.mindstaq.mcts_code import mcts_generate

tests = [
    {'inputs': {'x': 5}, 'expected': 25},
    {'inputs': {'x': 3}, 'expected': 9},
]

code, fitness = mcts_generate(
    tests,
    function_name='square',
    iterations=500,
    time_limit=10.0,
)
```

---

## 🔧 How MCTS Differs from Darwinian Evolution

| Aspect | Darwinian Evolution | MCTS |
|--------|---------------------|------|
| **Strategy** | Random mutation + selection | Strategic tree search |
| **Exploration** | Novelty-based | UCB1-balanced |
| **Memory** | Population of candidates | Tree of paths |
| **Best For** | Novel algorithms | Optimization problems |
| **Inspiration** | Biology | Game AI (AlphaGo) |

**They work TOGETHER:**
- Darwinian: "Try random things, keep what works"
- MCTS: "Strategically explore promising paths"

---

## 📊 Expected WoNQ Improvements

### v2.1.8 Predictions

| Config | v2.1.7 | v2.1.8 | Improvement |
|--------|--------|--------|-------------|
| **b3c3** | ~520-560 | ~560-600 | +40 |
| **b16c6** | ~580-620 | ~620-660 | +40 |
| **b16c7** | ~600-640 | ~640-666 | +40 |

### Confidence Improvements

| Metric | v2.1.7 | v2.1.8 |
|--------|--------|--------|
| Overall Confidence | 68-72% | 72-78% |
| Complex Algorithms | 55% | 70% |
| Novel Solutions | 45% | 60% |
| vs LLM Quality | ~87% | ~90% |

---

## 🎮 Technical Details

### MCTS Parameters

```python
# Default configuration
UCB1_C = sqrt(2)           # Exploration constant
ROLLOUT_DEPTH = 10         # Simulation depth
DEFAULT_ITERATIONS = 500   # Search iterations
TIME_LIMIT = 30.0          # Seconds
```

### Integration Points

```
triple_threat.py
├── check_wisdom_pits()    # v2.1.7
├── try_mcts_improvement() # v2.1.8 NEW!
├── run_tier_parallel()    # All tiers
└── select_best_result()   # Selection
```

### Code Actions Available

```python
class CodeAction(Enum):
    ADD_ASSIGNMENT = "add_assignment"
    ADD_IF_STATEMENT = "add_if_statement"
    ADD_FOR_LOOP = "add_for_loop"
    ADD_WHILE_LOOP = "add_while_loop"
    ADD_RETURN = "add_return"
    ADD_FUNCTION_CALL = "add_function_call"
    MODIFY_OPERATOR = "modify_operator"
    MODIFY_CONSTANT = "modify_constant"
    MODIFY_VARIABLE = "modify_variable"
    DELETE_STATEMENT = "delete_statement"
    WRAP_IN_TRY = "wrap_in_try"
    ADD_LIST_COMPREHENSION = "add_list_comprehension"
    ADD_DICT_COMPREHENSION = "add_dict_comprehension"
    SWAP_STATEMENTS = "swap_statements"
    DUPLICATE_STATEMENT = "duplicate_statement"
```

---

## 🚀 Upgrade Guide

### From v2.1.7

1. Replace `worqer/mindstaq/` directory
2. New file: `mcts_code.py`
3. Updated: `triple_threat.py`
4. No configuration changes needed

### Testing

```bash
# Verify MCTS module
python3 -c "from worqer.mindstaq.mcts_code import MCTSCodeGenerator; print('✅ MCTS')"

# Run MCTS test
python3 worqer/mindstaq/mcts_code.py
```

---

## 🔮 Roadmap

### v2.2.0 (Planned)

- Local Wisdom Pits storage (~/.qonqrete/wisdom/)
- Auto-learning from successful builds
- `qonqrete wisdom` CLI commands

### v2.3.0 (Planned)

- Public Wisdom Pits API (pits.qonqrete.sh)
- Community contribution system
- Quality scoring and ranking

---

## 📝 Known Issues

1. MCTS may take 10-30 seconds for complex functions
2. Works best with well-defined test cases
3. Random rollouts may miss optimal solutions

---

## 🙏 Credits

- MCTS algorithm inspired by AlphaGo (DeepMind)
- UCB1 formula from Auer, Cesa-Bianchi, Fischer (2002)
- AST manipulation using Python's ast module

---

**Full Changelog:** [v2.1.7...v2.1.8](https://github.com/qonqrete/qonqrete/compare/v2.1.7...v2.1.8)
