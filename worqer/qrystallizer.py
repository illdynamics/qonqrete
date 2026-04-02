#!/usr/bin/env python3
# worqer/qrystallizer.py
# ═══════════════════════════════════════════════════════════════════════════════
# Qrystallizer Agent - Cycle-1 Preflight & Artifact Generator
# v1.2.2-stable
# ═══════════════════════════════════════════════════════════════════════════════

import os
import sys
import json
import yaml
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
    from mode_policy import load_mode_policy_from_env, render_qrystallizer_directives
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

# Import cost estimation
sys.path.insert(0, str(Path(__file__).parent.parent / 'qrane'))
try:
    from lib_funqtions import estimate_tokens, calculate_cost, format_cost
except ImportError:
    def estimate_tokens(text, model="gpt-4.1-mini"): return len(text) // 4
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (0.4 if is_input else 1.6)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"

QRYSTALLIZER_PROMPT = '''You are the **Qrystallizer**, an expert cycle-1 preflight agent. Your job is to analyze the initial project specification (`tasq.md`) and produce stable artifacts.

You must return EXACTLY one valid JSON object containing the following keys. DO NOT output any markdown fencing around the JSON. DO NOT output any other text.
{{
  "readiness": {{
    "status": "ready",
    "critical_gaps": ["List of missing critical information, empty if none"],
    "missing_context": ["List of helpful but non-critical missing context"]
  }},
  "requirements": [
    {{
      "id": "REQ-001",
      "type": "functional",
      "priority": "must_have",
      "text": "Specific functional or non-functional requirement",
      "source": "Reference to original tasq section",
      "blocking": true
    }}
  ],
  "enhancement_backlog": [
    {{
      "title": "Optional improvement idea",
      "reason": "Why it could help",
      "promotion_trigger": "User or canonical ledger explicitly promotes it"
    }}
  ],
  "recommended_cycles_initial": 3,
  "recommended_cycles_hard_cap": 5,
  "recommended_sensitivity": 5,
  "acceptance_tests": "# Acceptance Tests & Golden Paths\n\n```python\ndef test_module_a():\n    pass\n```",
  "assumptions": "# Explicit Assumptions\n- **Architecture**: Assumes REST API over GraphQL.",
  "enhanced_tasq": "# Original Tasq Content with prepended Qrystal Summary..."
}}

{mode_directives}

CRITICAL MODE RULES:
- The `requirements` array is the canonical mandatory ledger.
- `enhancement_backlog` is optional-only and MUST NOT silently extend the mandatory ledger.
- In `program` mode, keep `enhancement_backlog` empty unless the tasq explicitly asks for optional idea capture.
- In `innovative` mode, optional improvements belong in `enhancement_backlog`, not in the mandatory `requirements` ledger.

INPUT TASQ:
{tasq_content}
'''

def main() -> None:
    if len(sys.argv) < 2:
        print("[Qrystallizer] Usage: qrystallizer.py <tasq_path> [output_path]", flush=True)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path
    
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    mode_policy = load_mode_policy_from_env()
    if cycle_num != '1':
        print(f"[Qrystallizer] ⏭️ Skipping - only runs on Cycle 1 (current: Cycle {cycle_num})", flush=True)
        return
        
    print("\n═" * 70, flush=True)
    print("💎 Qrystallizer v1.0.0 - Generating Stable Artifacts", flush=True)
    print("═" * 70, flush=True)
    
    if not input_path.exists():
        print(f"[Qrystallizer] ❌ ERROR: Input file not found: {input_path}", flush=True)
        sys.exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        original_tasq = f.read()
        
    # Read config
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except:
        config = {}
        
    # Fallback to tasqleveler config for backwards compatibility
    agent_cfg = config.get('agents', {}).get('qrystallizer')
    if not agent_cfg:
        agent_cfg = config.get('agents', {}).get('tasqleveler', {})
    
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')
    ai_timeout = agent_cfg.get('timeout')
    ai_provider_options = agent_cfg.get(ai_provider) if ai_provider == 'llamacpp' else None

    prompt = QRYSTALLIZER_PROMPT.format(
        tasq_content=original_tasq,
        mode_directives=render_qrystallizer_directives(mode_policy)
    )
    print(f"[Qrystallizer] 🧠 Model: {ai_provider}/{ai_model}", flush=True)
    
    try:
        response = lib_ai.run_ai_completion(
            ai_provider, 
            ai_model, 
            prompt,
            timeout=ai_timeout,
            provider_options=ai_provider_options
        )
    except Exception as e:
        print(f"[Qrystallizer] ❌ AI call failed: {e}", flush=True)
        print(f"[Qrystallizer] ⚠️ Proceeding with original tasq", flush=True)
        return
        
    # parse JSON
    response = response.strip()
    if response.startswith('```json'): response = response[7:]
    if response.endswith('```'): response = response[:-3]
    response = response.strip()
    
    try:
        data = json.loads(response)
    except Exception as e:
        print(f"[Qrystallizer] ❌ JSON parsing failed: {e}", flush=True)
        print(f"[Qrystallizer] ⚠️ Proceeding with original tasq", flush=True)
        return
        
    # Determine workspace and qrystal_dir
    # Usually input_path is worqspace/tasq.d/cyqle1_tasq.md, so worqspace is 2 levels up
    # Wait, the pipeline passes "tasq.d/cyqle{N}_tasq.md" as input.
    # We should place `qrystal.d` inside the current working directory, which is the root of the workspace.
    worqspace_root = Path(os.environ.get('QONQ_WORKSPACE', os.getcwd()))
    qrystal_dir = worqspace_root / 'qrystal.d'
    qrystal_dir.mkdir(parents=True, exist_ok=True)
    
    readiness = data.get('readiness', {})
    requirements = data.get('requirements', [])
    enhancement_backlog = data.get('enhancement_backlog', [])
    if not isinstance(enhancement_backlog, list):
        enhancement_backlog = []
    req_json = {
        "requirements": requirements,
        "recommended_cycles_initial": data.get("recommended_cycles_initial", 3),
        "recommended_cycles_hard_cap": data.get("recommended_cycles_hard_cap", 5),
        "recommended_sensitivity": data.get("recommended_sensitivity", 5)
    }
    tests = data.get('acceptance_tests', '')
    assumptions = data.get('assumptions', '')
    enhanced_tasq = data.get('enhanced_tasq', original_tasq)
    
    with open(qrystal_dir / 'readiness.json', 'w', encoding='utf-8') as f:
        json.dump(readiness, f, indent=2)
    with open(qrystal_dir / 'mode_policy.json', 'w', encoding='utf-8') as f:
        json.dump(mode_policy.as_dict(), f, indent=2)
    with open(qrystal_dir / 'requirements.json', 'w', encoding='utf-8') as f:
        json.dump(req_json, f, indent=2)
    with open(qrystal_dir / 'enhancement_backlog.json', 'w', encoding='utf-8') as f:
        json.dump({'enhancements': enhancement_backlog}, f, indent=2)
    with open(qrystal_dir / 'acceptance_tests.md', 'w', encoding='utf-8') as f:
        f.write(tests)
    with open(qrystal_dir / 'assumptions.md', 'w', encoding='utf-8') as f:
        f.write(assumptions)
        
    # write enhanced tasq
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(enhanced_tasq)
        
    print(f"[Qrystallizer] ✅ Wrote artifacts to {qrystal_dir.name}/", flush=True)
    print(f"[Qrystallizer] 🎛️ Mode policy: {mode_policy.semantic_mode}", flush=True)
    print(f"[Qrystallizer] 📝 Wrote enhanced tasq to {output_path.name}", flush=True)

if __name__ == '__main__':
    main()