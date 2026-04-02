#!/usr/bin/env python3
# worqer/tasqleveler.py
# ═══════════════════════════════════════════════════════════════════════════════
# TasqLeveler Agent - Automatic Tasq Enhancement
# v0.9.0 - Supercharges tasq.md with Golden Paths, Dependency Graphs & Mocks
# ═══════════════════════════════════════════════════════════════════════════════
#
# RUNS ONCE: Only on Cycle 1, before InstruQtor
#
# What it does:
#   1. Reads the original tasq.md
#   2. Analyzes the project structure and requirements
#   3. Enhances with:
#      - Explicit dependency graph (what can import what)
#      - Golden path tests for each module (success criteria)
#      - Mock infrastructure specs where needed
#      - Import structure to prevent circular deps
#      - Phase priority guidance
#   4. Writes enhanced tasq back (original preserved as tasq_original.md)
#
# Why: A well-structured tasq = dramatically better output quality (+15-20%)
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
import re
import yaml
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
    import lib_provider_config
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

# Import cost estimation
sys.path.insert(0, str(Path(__file__).parent.parent / 'qrane'))
try:
    from lib_funqtions import estimate_tokens, calculate_cost, format_cost
except ImportError:
    def estimate_tokens(text, model="gpt-4.1"): return len(text) // 4
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (2.0 if is_input else 8.0)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"


TASQLEVELER_PROMPT = '''You are a **Senior Software Architect** specializing in AI-assisted code generation. Your job is to ENHANCE a project specification (tasq.md) to maximize the success rate of automated code generation.

## YOUR MISSION

Take the INPUT TASQ and enhance it with the following additions. PRESERVE all original content - you're ADDING enhancements, not replacing.

### 1. 📦 DEPENDENCY GRAPH (Add near the top, after overview)
Add an explicit module dependency graph showing what can import what:
```
src/
├── shared/          # NO external deps (base layer)
│   ├── constants.py # Pure Python only
│   ├── exceptions.py # Pure Python only  
│   ├── logger.py    # Only: logging, os
│   └── config.py    # Only: yaml, os + shared.exceptions
├── module_a/        # Depends on: shared
├── module_b/        # Depends on: shared, module_a
└── module_c/        # Depends on: shared, module_a, module_b
```
This prevents circular imports and guides build order.

### 2. 🎯 GOLDEN PATH TESTS (Add to each phase/module)
For EACH significant module/class, add a code block showing what MUST work:
```python
# 🎯 Golden Path Test:
from module.submodule import ClassName
obj = ClassName(config={{'test': True}})
assert hasattr(obj, 'required_method')
result = obj.required_method('input')
assert isinstance(result, expected_type)
```
Be SPECIFIC - test actual expected behavior, not just existence.

### 3. 🧪 MOCK INFRASTRUCTURE (Add if external services involved)
If the project involves external APIs, databases, or servers, add mock class specifications:
```python
class MockExternalService:
    """Mock for testing without real service."""
    def __init__(self):
        self._data = {{'mock': 'data'}}
    
    def connect(self) -> bool:
        return True
    
    def get_items(self) -> list:
        return [{{'id': 1, 'name': 'mock_item'}}]
```

### 4. 📋 GLOBAL SUCCESS CRITERIA (Add near the top)
Add a section defining what SUCCESS means:
```markdown
## 🎯 Global Success Criteria
Before ANY cycle is marked SUCCESS:
1. All Python files pass `python -m py_compile <file>`
2. All imports resolve within the project structure
3. No circular import dependencies
4. All classes are instantiable with mock/test configs
5. All Dockerfiles pass syntax validation (if applicable)
```

### 5. ⏱️ TOKEN BUDGET PRIORITY (Add at the end)
Add guidance on what to prioritize:
```markdown
## Token Budget Priority (if running low on cycles)
1. ✅ MUST HAVE: Core utilities, base classes
2. ✅ MUST HAVE: Main business logic
3. ⚠️ SHOULD HAVE: Integration modules
4. ⚠️ NICE TO HAVE: Advanced features, polish
```

### 6. 🔗 BASE CLASSES (Add if inheritance patterns detected)
If the project has multiple similar classes (e.g., multiple API clients), add a base class spec:
```python
from abc import ABC, abstractmethod

class BaseClient(ABC):
    @abstractmethod
    def connect(self) -> bool: pass
    
    @abstractmethod  
    def disconnect(self) -> None: pass
```

## RULES

1. **PRESERVE** all original content - enhance, don't replace
2. **INLINE** enhancements where they make sense (golden tests after each phase)
3. **BE SPECIFIC** - vague tests don't help ("assert works" is useless)
4. **CONSIDER FAILURES** - what could go wrong? Add tests for edge cases
5. **USE CODE BLOCKS** for all Python/bash examples
6. **KEEP STRUCTURE** - maintain original phase organization

## OUTPUT FORMAT

Return the COMPLETE enhanced tasq.md. Include EVERYTHING from the original plus your additions.
Start directly with the enhanced content (no preamble like "Here is the enhanced...").

---

## INPUT TASQ TO ENHANCE:

{tasq_content}

---

## ENHANCED TASQ OUTPUT:
'''


def main() -> None:
    """
    TasqLeveler: Enhances tasq.md with golden paths, dependency graphs, and mocks.
    Only runs on Cycle 1.
    """
    if len(sys.argv) < 2:
        print("[TasqLeveler] Usage: tasqleveler.py <tasq_path> [output_path]", flush=True)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path
    
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    
    # Only run on cycle 1
    if cycle_num != '1':
        print(f"[TasqLeveler] ⏭️ Skipping - only runs on Cycle 1 (current: Cycle {cycle_num})", flush=True)
        return
    
    print("", flush=True)
    print("═" * 70, flush=True)
    print("🚀 TasqLeveler v0.9.0 - Supercharging your tasq.md", flush=True)
    print("═" * 70, flush=True)
    
    # Read original tasq
    if not input_path.exists():
        print(f"[TasqLeveler] ❌ ERROR: Input file not found: {input_path}", flush=True)
        sys.exit(1)
    
    with open(input_path, 'r', encoding='utf-8') as f:
        original_tasq = f.read()
    
    original_lines = len(original_tasq.split('\n'))
    original_chars = len(original_tasq)
    print(f"[TasqLeveler] 📄 Original tasq: {original_lines} lines, {original_chars:,} chars", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.0.4: COMPLEXITY SCORING - Skip enhancement for tiny tasqs
    # ═══════════════════════════════════════════════════════════════════════════
    tasqleveler_cfg = config.get('agents', {}).get('tasqleveler', {}) if 'config' in dir() else {}
    # Try to load config now if not yet loaded
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            tl_config = yaml.safe_load(f) or {}
    except:
        tl_config = {}
    tasqleveler_cfg = tl_config.get('agents', {}).get('tasqleveler', {})
    tl_options = tl_config.get('tasqleveler', {})

    tl_enabled = tl_options.get('enabled', tasqleveler_cfg.get('enabled', True))
    min_complexity_score = tl_options.get('min_complexity_score', tasqleveler_cfg.get('min_complexity_score', 15))
    min_lines = tl_options.get('min_lines', tasqleveler_cfg.get('min_lines', 20))

    if not tl_enabled:
        print(f"[TasqLeveler] ⏭️ Disabled in config", flush=True)
        return

    # Compute complexity score
    complexity_score = 0
    complexity_score += original_lines  # 1 point per line
    complexity_score += len(re.findall(r'^#+\s', original_tasq, re.MULTILINE)) * 3  # 3 points per section header
    complexity_score += len(re.findall(r'^\s*[-*]\s', original_tasq, re.MULTILINE))  # 1 point per bullet
    complexity_score += len(re.findall(r'```', original_tasq)) * 2  # 2 points per code block fence
    complexity_score += original_chars // 200  # 1 point per 200 chars

    print(f"[TasqLeveler] 📊 Complexity score: {complexity_score} (threshold: {min_complexity_score}, min_lines: {min_lines})", flush=True)

    if complexity_score < min_complexity_score or original_lines < min_lines:
        print(f"[TasqLeveler] ⏭️ Tasq too simple (score {complexity_score} < {min_complexity_score} or lines {original_lines} < {min_lines}) — skipping enhancement", flush=True)
        return
    
    # Check if already enhanced (skip if so)
    enhancement_markers = ['🎯 Golden Path', 'Dependency Graph', '📦', 'Global Success Criteria']
    already_enhanced = sum(1 for marker in enhancement_markers if marker in original_tasq)
    if already_enhanced >= 3:
        print(f"[TasqLeveler] ✨ Tasq appears already enhanced ({already_enhanced}/4 markers found)", flush=True)
        print(f"[TasqLeveler] ⏭️ Skipping enhancement", flush=True)
        return
    
    # Load config
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except:
        config = {}
    
    # Get AI config - use tasqleveler's config, fall back to instruqtor
    agent_name = 'tasqleveler' if config.get('agents', {}).get('tasqleveler') else 'instruqtor'
    provider_options = lib_provider_config.resolve_agent_provider_options(config, agent_name)
    agent_cfg = config.get('agents', {}).get(agent_name, {})
    
    ai_provider = provider_options.get('provider') or agent_cfg.get('provider', 'openai')
    ai_model = provider_options.get('model') or agent_cfg.get('model', 'gpt-4.1-mini')
    
    # Build prompt
    prompt = TASQLEVELER_PROMPT.format(tasq_content=original_tasq)
    
    # Estimate cost
    input_tokens = estimate_tokens(prompt, ai_model)
    estimated_output_tokens = int(input_tokens * 1.8)  # Enhanced ~1.8x original
    input_cost = calculate_cost(input_tokens, ai_model, is_input=True, provider=ai_provider)
    output_cost = calculate_cost(estimated_output_tokens, ai_model, is_input=False, provider=ai_provider)
    total_cost = input_cost + output_cost
    
    print(f"[TasqLeveler] 🧠 Model: {ai_provider}/{ai_model}", flush=True)
    print(f"[TasqLeveler] 💰 Estimated cost: {format_cost(total_cost)} ({input_tokens:,} in + ~{estimated_output_tokens:,} out)", flush=True)
    print(f"[TasqLeveler] ⏳ Enhancing tasq (this may take a moment)...", flush=True)
    
    # Call AI
    try:
        enhanced_tasq = lib_ai.run_ai_completion(
            ai_provider,
            ai_model,
            prompt,
            timeout=provider_options.get('timeout'),
            request_options=provider_options,
        )
    except Exception as e:
        print(f"[TasqLeveler] ❌ AI call failed: {e}", flush=True)
        print(f"[TasqLeveler] ⚠️ Proceeding with original tasq", flush=True)
        return
    
    # Clean up response (remove any markdown fences if present)
    enhanced_tasq = enhanced_tasq.strip()
    if enhanced_tasq.startswith('```markdown'):
        enhanced_tasq = enhanced_tasq[len('```markdown'):].strip()
    if enhanced_tasq.startswith('```md'):
        enhanced_tasq = enhanced_tasq[len('```md'):].strip()
    if enhanced_tasq.startswith('```'):
        enhanced_tasq = enhanced_tasq[3:].strip()
    if enhanced_tasq.endswith('```'):
        enhanced_tasq = enhanced_tasq[:-3].strip()
    
    # Validate we got something reasonable
    enhanced_lines = len(enhanced_tasq.split('\n'))
    enhanced_chars = len(enhanced_tasq)
    
    if enhanced_lines < original_lines * 0.7:
        print(f"[TasqLeveler] ⚠️ Enhanced tasq seems truncated ({enhanced_lines} < {int(original_lines * 0.7)})", flush=True)
        print(f"[TasqLeveler] ⚠️ Keeping original tasq to be safe", flush=True)
        return
    
    if enhanced_chars < original_chars * 0.7:
        print(f"[TasqLeveler] ⚠️ Enhanced tasq too short ({enhanced_chars:,} < {int(original_chars * 0.7):,})", flush=True)
        print(f"[TasqLeveler] ⚠️ Keeping original tasq to be safe", flush=True)
        return
    
    # Backup original
    backup_path = input_path.parent / f"{input_path.stem}_original{input_path.suffix}"
    shutil.copy(input_path, backup_path)
    print(f"[TasqLeveler] 💾 Original backed up to: {backup_path.name}", flush=True)
    
    # Write enhanced tasq
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(enhanced_tasq)
    
    # Report results
    lines_added = enhanced_lines - original_lines
    chars_added = enhanced_chars - original_chars
    print(f"[TasqLeveler] ✅ Enhanced tasq: {enhanced_lines} lines (+{lines_added}), {enhanced_chars:,} chars (+{chars_added:,})", flush=True)
    print(f"[TasqLeveler] 📝 Written to: {output_path}", flush=True)
    
    # Detect what was added
    enhancements = []
    if '📦' in enhanced_tasq or 'Dependency Graph' in enhanced_tasq or 'Depends on:' in enhanced_tasq:
        enhancements.append("📦 Dependency Graph")
    if '🎯' in enhanced_tasq or 'Golden Path' in enhanced_tasq:
        enhancements.append("🎯 Golden Path Tests")
    if 'class Mock' in enhanced_tasq or 'MockServer' in enhanced_tasq:
        enhancements.append("🧪 Mock Infrastructure")
    if 'Success Criteria' in enhanced_tasq or 'Global Success' in enhanced_tasq:
        enhancements.append("📋 Success Criteria")
    if 'Priority' in enhanced_tasq or 'Token Budget' in enhanced_tasq or 'MUST HAVE' in enhanced_tasq:
        enhancements.append("⏱️ Phase Priority")
    if 'BaseClient' in enhanced_tasq or 'ABC' in enhanced_tasq or 'abstractmethod' in enhanced_tasq:
        enhancements.append("🔗 Base Classes")
    
    if enhancements:
        print(f"[TasqLeveler] 🎉 Enhancements added: {', '.join(enhancements)}", flush=True)
    else:
        print(f"[TasqLeveler] ✨ Tasq enhanced (check content for details)", flush=True)
    
    print("═" * 70, flush=True)
    print("", flush=True)


if __name__ == '__main__':
    main()
