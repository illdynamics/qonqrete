#!/usr/bin/env python3
# worqer/instruqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InstruQtor Agent - Task Decomposition & Planning
# v1.0.4-stable - QONTRACT Generation + Invariant Injection
# ═══════════════════════════════════════════════════════════════════════════════
#
# v1.0.3: BATCHED BRIQ GENERATION! 🚀
# Enables generating 50-250+ briqs without hitting token limits!
# Uses 2-phase approach: Blueprint (JSON) → Fabrication (batched XML)
#
# v1.0.2: INVERTED BRIQ SENSITIVITY SCALE! 🔄
# Higher number = MORE briqs (more intuitive!)
#
# v1.0.0 MAJOR FIX: Briq sensitivity now ENFORCES exact briq count ranges.
# Previously, sensitivity was just a "hint" to the AI, resulting in wildly
# inconsistent outputs (1-10 briqs with the same sensitivity setting).
#
# Now each sensitivity level has a HARD MIN/MAX range that is enforced:
#   - If AI produces too few briqs → regenerate with stronger prompt
#   - If AI produces too many briqs → merge similar briqs together
#
# BRIQ SENSITIVITY SCALE (0-16):
#   0  = Monolithic (1 briq)         - Single giant briq
#   1  = Very Broad (2-3 briqs)      - Major chunks only
#   2  = Broad (3-5 briqs)           - Large components
#   3  = Feature-level (5-8 briqs)   - Per-feature
#   4  = Component-level (8-12)      - Per-component
#   5  = Balanced (10-15 briqs)      ← RECOMMENDED DEFAULT
#   6  = Standard (15-20 briqs)      - Most files separate
#   7  = High (20-30 briqs)          - Detailed split
#   8  = Very High (30-40 briqs)     - Fine-grained
#   9  = Atomic (40-60 briqs)        - Maximum detail
#  10  = Ultra (50-75 briqs)         - Enterprise projects
#  11  = Mega (60-90 briqs)          - Large enterprise
#  12  = Hyper (75-110 briqs)        - Complex architectures
#  13  = Extreme (90-130 briqs)      - Multi-layer systems
#  14  = Maximum (110-160 briqs)     - Critical systems
#  15  = Insane (130-200 briqs)      - Mega specifications
#  16  = QONQRETE MAX (160-250)      - Enterprise mega-tasqs!
#
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import yaml
import re
import math
import json
import hashlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

# Import cost estimation
sys.path.insert(0, str(Path(__file__).parent.parent / 'qrane'))
try:
    from lib_funqtions import estimate_tokens, calculate_cost, format_cost
except ImportError:
    # Fallback if lib_funqtions not available
    def estimate_tokens(text, model="gpt-4.1-mini"): return len(text) // 4
    def calculate_cost(tokens, model, is_input=True): return (tokens / 1_000_000) * (0.4 if is_input else 1.6)
    def format_cost(cost): return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# QONTRACT GENERATION (v1.0.4) - Persistent Constitution from Cycle 1
# ═══════════════════════════════════════════════════════════════════════════════

# Keywords that signal contractual rules in tasq markdown
RULE_HEADERS = re.compile(
    r'^#+\s*(Rules?|Requirements?|Strict\s+rules?|Constraints?|Invariants?|Specifications?|Must\s+haves?|Non-negotiables?)',
    re.IGNORECASE | re.MULTILINE
)

IMPERATIVE_PATTERN = re.compile(
    r'^\s*[-*]\s+.*\b(MUST|SHALL|EXACTLY|NEVER|ALWAYS|NO\s|DO\s+NOT|FORBIDDEN|REQUIRED|MANDATORY)\b',
    re.IGNORECASE | re.MULTILINE
)


def extract_qontract_from_tasq(tasq_content: str, source_file: str) -> dict:
    """
    Deterministically extract contractual invariants from cycle1 tasq markdown.

    Returns a structured contract dict ready for JSON serialization.
    """
    rules_text = []

    # Strategy 1: Extract sections under explicit rule headers
    lines = tasq_content.split('\n')
    in_rules_section = False
    current_depth = 0

    for i, line in enumerate(lines):
        header_match = re.match(r'^(#+)\s+', line)
        if header_match:
            depth = len(header_match.group(1))
            if RULE_HEADERS.match(line):
                in_rules_section = True
                current_depth = depth
                continue
            elif in_rules_section and depth <= current_depth:
                in_rules_section = False
                continue

        if in_rules_section and line.strip():
            rules_text.append(line)

    # Strategy 2: If no explicit headers, extract imperative bullet lines
    if not rules_text:
        for match in IMPERATIVE_PATTERN.finditer(tasq_content):
            rules_text.append(match.group(0).strip())

    # Parse into structured invariants
    invariants = _parse_invariants_from_rules(rules_text, tasq_content)

    # Build contract
    contract = {
        'version': '1.0.4',
        'meta': {
            'source_cycle': 1,
            'source_file': source_file,
            'hash': hashlib.sha256(tasq_content.encode()).hexdigest()[:16],
        },
        'invariants': invariants,
        'raw_rules': rules_text[:50]  # Cap for compactness
    }

    return contract


def _parse_invariants_from_rules(rules_text: list[str], full_tasq: str) -> dict:
    """
    Parse structured invariants from extracted rule text.
    Uses pattern matching to identify common contract patterns.
    """
    invariants = {}

    combined = '\n'.join(rules_text) + '\n' + full_tasq

    # Detect forbidden imports
    forbidden_imports = []
    for match in re.finditer(r'\b(?:no|forbid|do\s+not\s+use|never\s+use|must\s+not.*?import)\s+[`"\']*(\w+)[`"\']*', combined, re.IGNORECASE):
        candidate = match.group(1).lower()
        if candidate in ('uuid', 'pickle', 'eval', 'exec', 'subprocess'):
            forbidden_imports.append(candidate)
    # Also check explicit patterns
    for match in re.finditer(r'(?:forbidden|banned|prohibited)\s+(?:imports?|modules?|packages?)\s*:?\s*([\w,\s`]+)', combined, re.IGNORECASE):
        for item in re.findall(r'`?(\w+)`?', match.group(1)):
            if item.lower() not in forbidden_imports and len(item) > 1:
                forbidden_imports.append(item.lower())
    if forbidden_imports:
        invariants['forbidden_imports'] = list(set(forbidden_imports))

    # Detect forbidden fields
    forbidden_fields = []
    for match in re.finditer(r'(?:forbid|no|must\s+not\s+have)\s+(?:field|column|attribute)\s+(?:named?\s+)?[`"\']*(\w+)[`"\']*', combined, re.IGNORECASE):
        forbidden_fields.append(match.group(1))
    if forbidden_fields:
        invariants['forbidden_fields'] = list(set(forbidden_fields))

    # Detect schema field sets: "User must have exactly id, username, email, password"
    schemas = {}
    schema_pattern = re.compile(
        r'(\w+)\s+(?:must|shall)\s+have\s+(?:exactly\s+)?(?:fields?\s*:?\s*)?([`\w,\s]+)',
        re.IGNORECASE
    )
    for match in schema_pattern.finditer(combined):
        model_name = match.group(1)
        if model_name[0].isupper():  # Likely a model name
            field_str = match.group(2)
            fields_raw = re.findall(r'`?(\w+)`?', field_str)
            fields = {f: '*' for f in fields_raw if f.lower() not in ('must', 'have', 'exactly', 'fields', 'and', 'the')}
            if fields:
                schemas[model_name] = {'fields': fields, 'exact': 'exactly' in match.group(0).lower()}
    if schemas:
        invariants['schemas'] = schemas

    # Detect ID type rules
    id_type_match = re.search(r'id\s+(?:must|shall)\s+be\s+(?:an?\s+)?(\w+(?:\[\w+\])?)', combined, re.IGNORECASE)
    if id_type_match:
        invariants['id_type'] = id_type_match.group(1)
    elif re.search(r'\bid\b.*\b(?:int|integer)\b', combined, re.IGNORECASE):
        invariants['id_type'] = 'int'

    # Detect ID assignment strategy
    if re.search(r'(?:auto.?assign|start\s+at\s+1|monotonic|sequential|incrementing)\s+(?:id|integer)', combined, re.IGNORECASE):
        invariants['id_strategy'] = 'monotonic_int_start_1'
    elif re.search(r'id.*(?:start|begin).*\b1\b', combined, re.IGNORECASE):
        invariants['id_strategy'] = 'monotonic_int_start_1'

    # Detect required endpoints
    endpoints = []
    ep_pattern = re.compile(r'(GET|POST|PUT|DELETE|PATCH)\s+[`"\']*(/[\w/{}\-]+)[`"\']*', re.IGNORECASE)
    for match in ep_pattern.finditer(combined):
        ep = {'method': match.group(1).lower(), 'path': match.group(2)}
        if ep not in endpoints:
            endpoints.append(ep)
    if endpoints:
        invariants['required_endpoints'] = endpoints

    return invariants


def generate_qontract_md(contract: dict) -> str:
    """Generate human-readable qontract.md from contract dict."""
    inv = contract.get('invariants', {})
    meta = contract.get('meta', {})

    md = f"# QONTRACT — Project Constitution\n\n"
    md += f"_Generated by InstruQtor v1.0.4 | Source: cycle {meta.get('source_cycle', 1)} | Hash: {meta.get('hash', 'n/a')}_\n\n"
    md += "---\n\n"

    if inv.get('forbidden_imports'):
        md += "## Forbidden Imports\n\n"
        for imp in inv['forbidden_imports']:
            md += f"- `{imp}` — MUST NOT be imported\n"
        md += "\n"

    if inv.get('forbidden_fields'):
        md += "## Forbidden Fields\n\n"
        for fld in inv['forbidden_fields']:
            md += f"- `{fld}` — MUST NOT be used as a field name\n"
        md += "\n"

    if inv.get('schemas'):
        md += "## Schema Invariants\n\n"
        for model, spec in inv['schemas'].items():
            exact = " (EXACT — no other fields)" if spec.get('exact') else ""
            md += f"### {model}{exact}\n\n"
            for field, ftype in spec.get('fields', {}).items():
                md += f"- `{field}`: {ftype}\n"
            md += "\n"

    if inv.get('id_type'):
        md += f"## ID Type Rule\n\n- `id` fields MUST be `{inv['id_type']}`\n\n"

    if inv.get('id_strategy'):
        md += f"## ID Assignment Strategy\n\n- {inv['id_strategy']}\n\n"

    if inv.get('required_endpoints'):
        md += "## Required Endpoints\n\n"
        for ep in inv['required_endpoints']:
            md += f"- `{ep['method'].upper()} {ep['path']}`\n"
        md += "\n"

    # Raw rules for reference
    raw = contract.get('raw_rules', [])
    if raw:
        md += "## Extracted Rules (Raw)\n\n"
        for rule in raw[:30]:
            md += f"{rule}\n"
        md += "\n"

    return md


def write_qontract(contract: dict, qontract_dir: Path):
    """Write qontract.md and qontract.json to qontract.d/."""
    qontract_dir.mkdir(parents=True, exist_ok=True)

    json_path = qontract_dir / 'qontract.json'
    md_path = qontract_dir / 'qontract.md'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(contract, f, indent=2)
    print(f"  📜 Wrote QONTRACT: {json_path}", flush=True)

    md_content = generate_qontract_md(contract)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"  📜 Wrote QONTRACT: {md_path}", flush=True)

    inv_count = sum(1 for v in contract.get('invariants', {}).values() if v)
    print(f"  📜 QONTRACT: {inv_count} invariant categories extracted", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# INVARIANT INJECTION INTO BRIQS (v1.0.4)
# ═══════════════════════════════════════════════════════════════════════════════

# Scope tag keywords for matching briqs to invariants
SCOPE_KEYWORDS = {
    'schema': ['model', 'schema', 'pydantic', 'dataclass', 'class', 'entity', 'type'],
    'storage': ['storage', 'store', 'database', 'db', 'repository', 'persist', 'save', 'crud', 'memory'],
    'id': ['id', 'identifier', 'primary_key', 'pk', 'uuid', 'counter', 'sequence', 'auto_increment'],
    'routing': ['route', 'router', 'endpoint', 'api', 'handler', 'controller', 'path', 'url', 'http', 'rest'],
    'runtime': ['main', 'server', 'app', 'start', 'run', 'entrypoint', 'boot', 'config', 'port'],
}


def infer_scope_tags(briq_title: str, briq_content: str) -> list[str]:
    """Infer scope tags for a briq based on its title and content."""
    tags = set()
    combined = (briq_title + ' ' + briq_content).lower()

    for scope, keywords in SCOPE_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            tags.add(scope)
    return list(tags)


def get_relevant_invariants(scope_tags: list[str], contract: dict) -> str:
    """Get invariant snippets relevant to the given scope tags."""
    inv = contract.get('invariants', {})
    snippets = []

    if 'schema' in scope_tags and inv.get('schemas'):
        for model, spec in inv['schemas'].items():
            exact = " (EXACT)" if spec.get('exact') else ""
            fields = ', '.join(f"`{f}`" for f in spec.get('fields', {}))
            snippets.append(f"Schema: {model}{exact} fields: {fields}")

    if 'schema' in scope_tags and inv.get('forbidden_fields'):
        snippets.append(f"Forbidden fields: {', '.join(inv['forbidden_fields'])}")

    if ('storage' in scope_tags or 'id' in scope_tags) and inv.get('id_type'):
        snippets.append(f"ID type: {inv['id_type']}")

    if ('storage' in scope_tags or 'id' in scope_tags) and inv.get('id_strategy'):
        snippets.append(f"ID strategy: {inv['id_strategy']}")

    if ('storage' in scope_tags or 'id' in scope_tags) and inv.get('forbidden_imports'):
        if 'uuid' in inv['forbidden_imports']:
            snippets.append("FORBIDDEN: uuid import")

    if 'routing' in scope_tags and inv.get('required_endpoints'):
        eps = [f"{e['method'].upper()} {e['path']}" for e in inv['required_endpoints']]
        snippets.append(f"Required endpoints: {', '.join(eps)}")

    if inv.get('forbidden_imports'):
        snippets.append(f"Forbidden imports: {', '.join(inv['forbidden_imports'])}")

    return snippets


def inject_invariants_into_briq(briq_content: str, scope_tags: list[str], contract: dict) -> str:
    """Append relevant invariant snippets to a briq's content."""
    if not scope_tags:
        return briq_content
    snippets = get_relevant_invariants(scope_tags, contract)
    if not snippets:
        return briq_content

    invariant_section = "\n\n---\n**Invariant Snippets (from QONTRACT):**\n"
    invariant_section += f"_Scope: {', '.join(scope_tags)}_\n"
    for s in snippets:
        invariant_section += f"- {s}\n"

    return briq_content + invariant_section


# ═══════════════════════════════════════════════════════════════════════════════
# ENFORCED BRIQ SENSITIVITY RANGES (v1.0.2 - INVERTED SCALE!)
# ═══════════════════════════════════════════════════════════════════════════════
# Each sensitivity level has a strict (min, max, target) briq count.
# The system will ENFORCE these ranges, not just hint at them.
# v1.0.2: INVERTED SCALE - Higher number = More briqs!

BRIQ_RANGES = {
    0: (1, 1, 1),        # Monolithic: exactly 1 briq
    1: (2, 3, 2),        # Very Broad: 2-3 briqs
    2: (3, 5, 4),        # Broad: 3-5 briqs
    3: (5, 8, 6),        # Feature-level: 5-8 briqs
    4: (8, 12, 10),      # Component-level: 8-12 briqs
    5: (10, 15, 12),     # Balanced: 10-15 briqs (RECOMMENDED DEFAULT)
    6: (15, 20, 18),     # Standard: 15-20 briqs
    7: (20, 30, 25),     # High Granularity: 20-30 briqs
    8: (30, 40, 35),     # Very High: 30-40 briqs
    9: (40, 60, 50),     # Atomic: 40-60 briqs
    # v1.0.2: Extended range for mega-projects
    10: (50, 75, 60),    # Ultra: 50-75 briqs
    11: (60, 90, 75),    # Mega: 60-90 briqs
    12: (75, 110, 90),   # Hyper: 75-110 briqs
    13: (90, 130, 110),  # Extreme: 90-130 briqs
    14: (110, 160, 135), # Maximum: 110-160 briqs
    15: (130, 200, 165), # Insane: 130-200 briqs
    16: (160, 250, 200), # QONQRETE MAX: 160-250 briqs (enterprise mega-tasqs)
}


def clean_input_content(text: str) -> str:
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = text.replace('\xa0', ' ')
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text


def parse_xml_briqs(content: str) -> list[dict]:
    """Robust parsing that handles potential AI formatting glitches."""
    pattern_strict = re.compile(r'<briq\s+title=["\']([^"\']*)["\']>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
    matches = pattern_strict.findall(content)
    results = [{'title': m[0].strip(), 'content': m[1].strip()} for m in matches]

    if not results:
        pattern_loose = re.compile(r'<briq>(.*?)</briq>', re.DOTALL | re.IGNORECASE)
        loose_matches = pattern_loose.findall(content)
        for i, m in enumerate(loose_matches):
            lines = m.strip().split('\n')
            title = lines[0].strip() if lines else f"Task_{i+1}"
            content_body = "\n".join(lines[1:]) if len(lines) > 1 else m.strip()
            results.append({'title': title, 'content': content_body})
    return results


def clean_filename_slug(text: str) -> str:
    """Converts a title into a readable, lowercase, underscore-separated slug."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    s3 = re.sub(r'\W+', '_', s2)
    s4 = re.sub(r'_+', '_', s3)
    slug = s4.strip('_').lower()
    return "_".join(slug.split('_')[:8]) if slug else "task"


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def normalize_ref(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', text.lower())


def component_id_from_title(title: str) -> str:
    slug = clean_filename_slug(title).replace('_', '-')
    parts = [part for part in slug.split('-') if part and part not in {'build', 'create', 'update', 'implement', 'add', 'fix', 'refactor'}]
    if not parts:
        parts = ['general']
    return "-".join(parts[:3])


def summarize_briqs_for_planning(briqs: list[dict]) -> list[dict]:
    summaries = []
    for index, item in enumerate(briqs, start=1):
        title = item['title'].strip()
        content = item['content'].strip()
        scope_tags = infer_scope_tags(title, content)
        summaries.append({
            'briq_index': index,
            'briq_ref': f"briq-{index:03d}",
            'title': title,
            'component_hint': component_id_from_title(title),
            'scope_tags': scope_tags,
            'contract_relevant': bool(scope_tags and any(tag in scope_tags for tag in ('schema', 'storage', 'routing', 'id'))),
            'objective': re.sub(r'\s+', ' ', content[:260]).strip(),
        })
    return summaries


def build_planning_task_input(raw_task: str, task_spec: dict, guard_result: dict) -> str:
    if not task_spec:
        return raw_task

    lines = [
        "# Canonical Qrystalized Task Spec",
        "",
        f"Goal: {task_spec.get('goal', '').strip()}",
        f"Readiness: {task_spec.get('status', 'UNKNOWN')}",
        "",
        "## Clarification Summary",
        task_spec.get('clarification_summary', ''),
        "",
    ]

    assumptions = task_spec.get('assumptions', [])
    if assumptions:
        lines.append("## Assumptions")
        for item in assumptions:
            lines.append(f"- {item.get('statement', '').strip()}")
        lines.append("")

    constraints = task_spec.get('constraints', [])
    if constraints:
        lines.append("## Clarified Constraints")
        for item in constraints:
            lines.append(f"- {item}")
        lines.append("")

    unknowns = task_spec.get('non_blocking_unknowns', [])
    if unknowns:
        lines.append("## Non-Blocking Unknowns")
        for item in unknowns:
            lines.append(f"- {item}")
        lines.append("")

    effective_constraints = guard_result.get('effective_constraints', [])
    if effective_constraints:
        lines.append("## Guard Effective Constraints")
        for item in effective_constraints:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## Raw Intake Reference",
            raw_task.strip(),
            "",
        ]
    )
    return "\n".join(lines).strip()


def generate_structured_plan(
    ai_provider: str,
    ai_model: str,
    planning_task_content: str,
    qodeyard_tree: str,
    briq_summaries: list[dict],
    sensitivity: int,
    min_briqs: int,
    max_briqs: int,
    target_briqs: int,
) -> dict:
    prompt = f"""You are the Principal Software Architect for QonQrete planning.

Return ONLY valid JSON. No markdown fences.

Create a compact but useful structured plan for grouped execution. The output must be a JSON object with these keys:
- architecture_foundation
- execution_blueprint
- dependency_interaction_contract
- component_contracts
- validation_plan
- completion_criteria
- estimation_basis

Rules:
1. Build groups must be practical execution scopes, not cosmetic labels.
2. Every build group must reference component_ids and briq_refs from the provided briq list.
3. Keep dependency rules structural and concise.
4. Completion criteria must be concrete and auditable before coding begins.
5. Validation plan must distinguish universal checks, language-specific checks, and project-specific checks.
6. Do not invent user goals beyond the provided task.

Required JSON shape:
{{
  "architecture_foundation": {{
    "summary": "...",
    "principles": ["..."],
    "risk_focus": ["..."]
  }},
  "execution_blueprint": {{
    "summary": "...",
    "components": [
      {{
        "component_id": "string",
        "title": "string",
        "summary": "string",
        "owned_scopes": ["component-group:string"]
      }}
    ],
    "build_groups": [
      {{
        "build_group_id": "bg-string",
        "title": "string",
        "objective": "string",
        "scope_id": "scope_build_group_string",
        "component_refs": ["component_id"],
        "briq_refs": ["briq-001"],
        "validation_focus": ["..."]
      }}
    ]
  }},
  "dependency_interaction_contract": {{
    "summary": "string",
    "dependency_rules": ["..."],
    "edges": [
      {{
        "from_component": "component_id",
        "to_component": "component_id",
        "type": "runtime_call|shared_state|config_dependency|validation_dependency",
        "reason": "string"
      }}
    ],
    "critical_interactions": ["..."]
  }},
  "component_contracts": [
    {{
      "component_id": "component_id",
      "title": "string",
      "summary": "string",
      "inputs": ["..."],
      "outputs": ["..."],
      "dependencies": ["component_id"],
      "constraints": ["..."],
      "owned_scopes": ["component-group:string"],
      "build_group_id": "bg-string"
    }}
  ],
  "validation_plan": {{
    "summary": "string",
    "universal_checks": ["..."],
    "language_specific_checks": ["..."],
    "project_specific_checks": ["..."],
    "build_group_checks": [
      {{
        "build_group_id": "bg-string",
        "checks": ["..."]
      }}
    ],
    "capability_notes": ["..."]
  }},
  "completion_criteria": {{
    "summary": "string",
    "criteria": ["..."],
    "build_group_expectations": [
      {{
        "build_group_id": "bg-string",
        "expected_outcomes": ["..."]
      }}
    ]
  }},
  "estimation_basis": {{
    "complexity": "low|medium|high",
    "rationale": ["..."],
    "sensitivity": {sensitivity},
    "expected_briq_range": [{min_briqs}, {max_briqs}],
    "target_briqs": {target_briqs}
  }}
}}

Current task context:
{planning_task_content[:12000]}

Current qodeyard tree:
```
{qodeyard_tree[:6000]}
```

Actual briqs to organize:
{json.dumps(briq_summaries, indent=2)}
"""

    response = lib_ai.run_ai_completion(
        ai_provider,
        ai_model,
        prompt,
        context_files=[],
        max_prompt_chars=50000,
        prompt_sections=[{
            'label': 'structured_planning_prompt',
            'content': prompt,
            'required': True,
            'loss_policy': 'preserve',
            'section_type': 'planning',
        }],
        agent_name='instruqtor',
        task_type='planning',
        output_tokens=2500,
    )

    json_match = re.search(r'(\{.*\})', response, re.DOTALL)
    if not json_match:
        raise ValueError("No JSON object found in structured planning response")
    return json.loads(json_match.group(1))


def build_fallback_structured_plan(
    goal: str,
    briq_summaries: list[dict],
    guard_result: dict,
    sensitivity: int,
    min_briqs: int,
    max_briqs: int,
    target_briqs: int,
) -> dict:
    components_map: dict[str, dict] = {}
    build_groups_map: dict[str, dict] = {}
    for summary in briq_summaries:
        component_id = summary['component_hint']
        component_title = summary['title'].replace('_', ' ')
        build_group_id = f"bg-{component_id}"
        scope_id = f"scope_build_group_{component_id.replace('-', '_')}"
        components_map.setdefault(component_id, {
            'component_id': component_id,
            'title': component_title,
            'summary': f"Component grouped around {component_title}.",
            'owned_scopes': [f"component-group:{component_id}"],
            'dependencies': [],
        })
        group = build_groups_map.setdefault(build_group_id, {
            'build_group_id': build_group_id,
            'title': component_title,
            'objective': f"Implement and stabilize the {component_title} scope.",
            'scope_id': scope_id,
            'component_refs': [component_id],
            'briq_refs': [],
            'validation_focus': ['local syntax/import coherence', 'declared scope coherence'],
        })
        group['briq_refs'].append(summary['briq_ref'])

    components = list(components_map.values())
    build_groups = list(build_groups_map.values())
    effective_constraints = guard_result.get('effective_constraints', [])
    return {
        'architecture_foundation': {
            'summary': goal,
            'principles': [
                'Preserve existing repository patterns where possible.',
                'Build by grouped scope rather than isolated briq text only.',
            ],
            'risk_focus': [
                'Grouped coherence matters more than maximizing briq count.',
                'Validation remains strongest for Python-centric deterministic checks.',
            ],
        },
        'execution_blueprint': {
            'summary': f"Grouped execution plan across {len(build_groups)} build group(s) and {len(components)} component contract(s).",
            'components': components,
            'build_groups': build_groups,
        },
        'dependency_interaction_contract': {
            'summary': 'Dependency bridge generated from grouped planning heuristics.',
            'dependency_rules': effective_constraints[:4] or ['No scope expansion without replanning.'],
            'edges': [],
            'critical_interactions': ['Build groups must preserve declared component boundaries.'],
        },
        'component_contracts': [
            {
                'component_id': component['component_id'],
                'title': component['title'],
                'summary': component['summary'],
                'inputs': ['existing repository context', 'assigned briqs'],
                'outputs': ['implemented files within owned scope'],
                'dependencies': component.get('dependencies', []),
                'constraints': effective_constraints[:3] or ['Preserve existing behavior unless explicitly changed.'],
                'owned_scopes': component.get('owned_scopes', []),
                'build_group_id': f"bg-{component['component_id']}",
            }
            for component in components
        ],
        'validation_plan': {
            'summary': 'Bridge validation plan with grouped-scope handoff.',
            'universal_checks': ['changed-file truth', 'manifest artifact completeness', 'group-to-briq linkage'],
            'language_specific_checks': ['python syntax/import verification where applicable'],
            'project_specific_checks': ['qontract guard for contract-relevant briqs'],
            'build_group_checks': [
                {
                    'build_group_id': group['build_group_id'],
                    'checks': ['files stay within declared scope', 'group briqs produce coherent outputs'],
                }
                for group in build_groups
            ],
            'capability_notes': ['Executed tests are not yet a canonical build-stage guarantee in the legacy runtime.'],
        },
        'completion_criteria': {
            'summary': 'Bridge completion criteria for demo-ready grouped execution.',
            'criteria': [
                'Required planning artifacts exist and are manifest-linkable.',
                'Every briq is assigned to a build group and component scope.',
                'ConstruQtor consumes grouped scope metadata during build.',
            ],
            'build_group_expectations': [
                {
                    'build_group_id': group['build_group_id'],
                    'expected_outcomes': [group['objective']],
                }
                for group in build_groups
            ],
        },
        'estimation_basis': {
            'complexity': 'high' if target_briqs >= 20 else ('medium' if target_briqs >= 8 else 'low'),
            'rationale': [
                f"Sensitivity {sensitivity} selected target briq count {target_briqs}.",
                'Grouped planning reduces isolated execution drift.',
            ],
            'sensitivity': sensitivity,
            'expected_briq_range': [min_briqs, max_briqs],
            'target_briqs': target_briqs,
        },
    }


def assign_briqs_to_groups(briq_summaries: list[dict], plan_payload: dict) -> dict[str, dict]:
    blueprint = plan_payload.get('execution_blueprint', {})
    component_contracts = {
        item.get('component_id'): item
        for item in plan_payload.get('component_contracts', [])
        if item.get('component_id')
    }
    groups = {
        item.get('build_group_id'): item
        for item in blueprint.get('build_groups', [])
        if item.get('build_group_id')
    }
    group_ref_map: dict[str, str] = {}
    for group_id, group in groups.items():
        for briq_ref in group.get('briq_refs', []):
            group_ref_map[normalize_ref(briq_ref)] = group_id

    default_group_id = next(iter(groups), None)
    assignments: dict[str, dict] = {}
    for summary in briq_summaries:
        normalized_refs = [
            normalize_ref(summary['briq_ref']),
            normalize_ref(summary['title']),
            normalize_ref(clean_filename_slug(summary['title'])),
        ]
        group_id = next((group_ref_map[key] for key in normalized_refs if key in group_ref_map), default_group_id)
        if group_id is None:
            group_id = f"bg-{summary['component_hint']}"
        group = groups.get(group_id, {
            'build_group_id': group_id,
            'title': summary['title'],
            'objective': f"Implement {summary['title']}",
            'scope_id': f"scope_build_group_{summary['component_hint'].replace('-', '_')}",
            'component_refs': [summary['component_hint']],
            'validation_focus': [],
        })
        component_id = group.get('component_refs', [summary['component_hint']])[0]
        component_contract = component_contracts.get(component_id, {
            'component_id': component_id,
            'title': component_id.replace('-', ' ').title(),
            'summary': f"Component scope for {component_id}.",
            'constraints': [],
            'owned_scopes': [f"component-group:{component_id}"],
        })
        assignments[summary['briq_ref']] = {
            'group': group,
            'component': component_contract,
        }
    return assignments


def render_architecture_foundation(plan_payload: dict, task_spec: dict) -> str:
    foundation = plan_payload.get('architecture_foundation', {})
    lines = [
        "# Architecture Foundation",
        "",
        f"Goal: {task_spec.get('goal', foundation.get('summary', ''))}",
        "",
        "## Foundation Summary",
        foundation.get('summary', ''),
        "",
        "## Principles",
    ]
    for item in foundation.get('principles', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Risk Focus"])
    for item in foundation.get('risk_focus', []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_execution_blueprint(plan_payload: dict) -> str:
    blueprint = plan_payload.get('execution_blueprint', {})
    lines = [
        "# Execution Blueprint",
        "",
        blueprint.get('summary', ''),
        "",
        "## Components",
    ]
    for component in blueprint.get('components', []):
        lines.append(f"- `{component.get('component_id', 'component')}`: {component.get('summary', component.get('title', ''))}")
    lines.extend(["", "## Build Groups"])
    for group in blueprint.get('build_groups', []):
        lines.append(f"- `{group.get('build_group_id', 'group')}`: {group.get('objective', group.get('title', ''))}")
        lines.append(f"  Components: {', '.join(group.get('component_refs', [])) or 'n/a'}")
        lines.append(f"  Briqs: {', '.join(group.get('briq_refs', [])) or 'n/a'}")
    lines.append("")
    return "\n".join(lines)


def render_dependency_contract(plan_payload: dict) -> str:
    contract = plan_payload.get('dependency_interaction_contract', {})
    lines = [
        "# Dependency & Interaction Contract",
        "",
        contract.get('summary', ''),
        "",
        "## Dependency Rules",
    ]
    for item in contract.get('dependency_rules', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Edges"])
    edges = contract.get('edges', [])
    if edges:
        for edge in edges:
            lines.append(f"- `{edge.get('from_component', '?')}` -> `{edge.get('to_component', '?')}` ({edge.get('type', 'dependency')}): {edge.get('reason', '')}")
    else:
        lines.append("- No critical inter-component edges were declared in this bridge artifact.")
    lines.extend(["", "## Critical Interactions"])
    for item in contract.get('critical_interactions', []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_component_contracts(plan_payload: dict) -> str:
    lines = ["# Component Contracts", ""]
    for component in plan_payload.get('component_contracts', []):
        lines.append(f"## {component.get('component_id', 'component')}")
        lines.append(component.get('summary', component.get('title', '')))
        lines.append("")
        lines.append(f"- Build Group: `{component.get('build_group_id', 'n/a')}`")
        lines.append(f"- Inputs: {', '.join(component.get('inputs', [])) or 'n/a'}")
        lines.append(f"- Outputs: {', '.join(component.get('outputs', [])) or 'n/a'}")
        lines.append(f"- Dependencies: {', '.join(component.get('dependencies', [])) or 'none'}")
        lines.append(f"- Owned Scopes: {', '.join(component.get('owned_scopes', [])) or 'n/a'}")
        constraints = component.get('constraints', [])
        if constraints:
            lines.append("- Constraints:")
            for item in constraints:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)


def render_validation_plan(plan_payload: dict) -> str:
    plan = plan_payload.get('validation_plan', {})
    lines = [
        "# Validation Plan",
        "",
        plan.get('summary', ''),
        "",
        "## Universal Checks",
    ]
    for item in plan.get('universal_checks', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Language-Specific Checks"])
    for item in plan.get('language_specific_checks', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Project-Specific Checks"])
    for item in plan.get('project_specific_checks', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Build Group Checks"])
    for item in plan.get('build_group_checks', []):
        lines.append(f"- `{item.get('build_group_id', 'group')}`: {', '.join(item.get('checks', []))}")
    lines.extend(["", "## Capability Notes"])
    for item in plan.get('capability_notes', []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_completion_criteria(plan_payload: dict) -> str:
    criteria = plan_payload.get('completion_criteria', {})
    lines = [
        "# Completion Criteria",
        "",
        criteria.get('summary', ''),
        "",
        "## Criteria",
    ]
    for item in criteria.get('criteria', []):
        lines.append(f"- {item}")
    lines.extend(["", "## Build Group Expectations"])
    for item in criteria.get('build_group_expectations', []):
        lines.append(f"- `{item.get('build_group_id', 'group')}`: {', '.join(item.get('expected_outcomes', []))}")
    lines.append("")
    return "\n".join(lines)


def write_planning_artifacts(
    worqspace_root: Path,
    cycle_num: str,
    task_spec: dict,
    guard_result: dict,
    plan_payload: dict,
    briq_summaries: list[dict],
) -> None:
    planning_dir = worqspace_root / 'planning'
    planning_dir.mkdir(parents=True, exist_ok=True)
    run_id = task_spec.get('run_id', os.environ.get('QONQ_LEGACY_QAGE_ID') or worqspace_root.name) if task_spec else (os.environ.get('QONQ_LEGACY_QAGE_ID') or worqspace_root.name)
    blueprint = plan_payload.get('execution_blueprint', {})

    execution_blueprint = {
        'schema_version': 'execution-blueprint.v1',
        'execution_blueprint_id': f"{run_id}-execution-blueprint-cyqle{cycle_num}",
        'run_id': run_id,
        'status': 'PLANNING',
        'summary': blueprint.get('summary', ''),
        'components': blueprint.get('components', []),
        'dependencies': plan_payload.get('dependency_interaction_contract', {}).get('edges', []),
        'build_groups': blueprint.get('build_groups', []),
        'validation_plan_ref': 'planning/validation-plan.v1.json',
        'completion_criteria_ref': 'planning/completion-criteria.v1.json',
        'capability_mode': task_spec.get('capability_mode', 'MIXED_REASONING_EXECUTION') if task_spec else 'MIXED_REASONING_EXECUTION',
        'planning_version': int(cycle_num),
    }
    dependency_contract = {
        'schema_version': 'dependency-interaction-contract.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        **plan_payload.get('dependency_interaction_contract', {}),
    }
    component_contracts = {
        'schema_version': 'component-contracts.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        'items': plan_payload.get('component_contracts', []),
    }
    validation_plan = {
        'schema_version': 'validation-plan.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        'task_spec_ref': 'task/task-spec.v1.json' if task_spec else None,
        'guard_result_ref': 'guard/guard-result.v1.json' if guard_result else None,
        **plan_payload.get('validation_plan', {}),
    }
    completion_criteria = {
        'schema_version': 'completion-criteria.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        **plan_payload.get('completion_criteria', {}),
    }
    build_groups = {
        'schema_version': 'build-groups.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        'items': blueprint.get('build_groups', []),
        'briq_inventory': briq_summaries,
        'estimation_basis': plan_payload.get('estimation_basis', {}),
    }

    write_json(planning_dir / 'execution-blueprint.v1.json', execution_blueprint)
    write_text(planning_dir / 'execution-blueprint.md', render_execution_blueprint(plan_payload))
    write_text(planning_dir / 'architecture-foundation.md', render_architecture_foundation(plan_payload, task_spec or {}))
    write_json(planning_dir / 'dependency-interaction-contract.v1.json', dependency_contract)
    write_text(planning_dir / 'dependency-interaction-contract.md', render_dependency_contract(plan_payload))
    write_json(planning_dir / 'component-contracts.v1.json', component_contracts)
    write_text(planning_dir / 'component-contracts.md', render_component_contracts(plan_payload))
    write_json(planning_dir / 'validation-plan.v1.json', validation_plan)
    write_text(planning_dir / 'validation-plan.md', render_validation_plan(plan_payload))
    write_json(planning_dir / 'completion-criteria.v1.json', completion_criteria)
    write_text(planning_dir / 'completion-criteria.md', render_completion_criteria(plan_payload))
    write_json(planning_dir / 'build-groups.v1.json', build_groups)
    write_json(planning_dir / 'estimation-basis.v1.json', {
        'schema_version': 'estimation-basis.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        **plan_payload.get('estimation_basis', {}),
    })


def get_sensitivity_config(level: int) -> tuple[int, int, int, str]:
    """
    Returns (min_briqs, max_briqs, target_briqs, prompt_text) for the given sensitivity level.
    v1.0.2: INVERTED SCALE - Higher number = More briqs!
    """
    min_b, max_b, target_b = BRIQ_RANGES.get(level, BRIQ_RANGES[5])  # v1.0.2: Default to 5 (Balanced)
    
    prompts = {
        # v1.0.2: INVERTED - Higher = More briqs
        0: f"**MANDATORY BRIQ COUNT: EXACTLY 1 BRIQ.** Output the entire project as a single monolithic briq. Do not split under any circumstances. This is non-negotiable.",
        1: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create very broad briqs. Example: 'Backend' and 'Frontend' as separate briqs. Maximum {max_b} briqs allowed.",
        2: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create broad briqs covering major components. Each briq should handle multiple related files.",
        3: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create feature-level briqs. Each major feature or module gets its own briq.",
        4: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create component-level briqs. Group related classes and utilities together.",
        5: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Create balanced briqs. Each significant class or module gets a briq. This is the RECOMMENDED DEFAULT.",
        6: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Standard granularity. Most files get their own briq.",
        7: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** High granularity. Split classes into separate briqs where logical.",
        8: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Very high granularity. Each function or small utility gets a briq.",
        9: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** ATOMIC decomposition. Maximum granularity - every function, class, and config gets its own briq.",
        # v1.0.2: Extended levels for mega-projects
        10: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** ULTRA decomposition. Break down every component into fine-grained briqs.",
        11: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** MEGA decomposition. Extremely detailed briqs for large enterprise projects.",
        12: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** HYPER decomposition. Each method, config option, and utility gets its own briq.",
        13: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** EXTREME decomposition. Maximum detail for complex multi-layer architectures.",
        14: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** MAXIMUM decomposition. Near line-by-line granularity for critical systems.",
        15: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** INSANE decomposition. Every single requirement gets dedicated attention.",
        16: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** QONQRETE MAX. Enterprise mega-project level. Use for tasqs with 1000+ requirements.",
    }
    
    prompt = prompts.get(level, prompts[5])  # v1.0.2: Default to 5 (Balanced)
    return min_b, max_b, target_b, prompt


def merge_briqs(briqs: list[dict], target_count: int) -> list[dict]:
    """
    Merge briqs to reduce count to target.
    Strategy: Combine consecutive briqs until we reach target count.
    """
    if len(briqs) <= target_count:
        return briqs
    
    print(f"  [ENFORCE] Merging {len(briqs)} briqs down to {target_count}...", flush=True)
    
    # Calculate how many briqs to merge into each final briq
    merge_factor = math.ceil(len(briqs) / target_count)
    merged = []
    
    for i in range(0, len(briqs), merge_factor):
        chunk = briqs[i:i + merge_factor]
        if len(chunk) == 1:
            merged.append(chunk[0])
        else:
            # Combine titles and content
            combined_title = " + ".join([b['title'][:30] for b in chunk])
            combined_content = "\n\n---\n\n".join([
                f"## {b['title']}\n{b['content']}" for b in chunk
            ])
            merged.append({
                'title': combined_title[:80],
                'content': combined_content
            })
    
    return merged[:target_count]


# ═══════════════════════════════════════════════════════════════════════════════
# BATCHED BRIQ GENERATION (v1.0.3) - Blueprint → Fabrication Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def generate_briqs_paginated(
    ai_provider: str,
    ai_model: str,
    base_prompt: str,
    sensitivity: int,
    target_briqs: int,
    batch_size: int,
    task_content: str,
    qodeyard_tree: str,
    universal_file_rule: str
) -> list[dict]:
    """
    Generate briqs using 2-phase approach to bypass token limits.
    
    Phase 1: Blueprint (JSON) - Get list of briq titles/objectives
    Phase 2: Fabrication (Batched) - Generate full XML content in chunks
    
    Args:
        ai_provider: AI provider (openai, gemini, etc.)
        ai_model: Model name
        base_prompt: Base prompt template
        sensitivity: Briq sensitivity level
        target_briqs: Target number of briqs
        batch_size: Number of briqs to fabricate per batch
        task_content: Original task content
        qodeyard_tree: Qodeyard file tree
        universal_file_rule: Universal file rule text
    
    Returns:
        List of briq dicts with 'title' and 'content' keys
    """
    print(f"\n🚀 [BATCHED GENERATION] Phase 1: Blueprint (Target: {target_briqs} briqs)", flush=True)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1: BLUEPRINT (JSON) - Get list of titles/objectives
    # ═══════════════════════════════════════════════════════════════════════════
    
    blueprint_prompt = f"""You are the **Principal Software Architect** creating a project blueprint.

Your task: Generate a JSON list of EXACTLY {target_briqs} briq specifications.

**OUTPUT FORMAT (JSON ONLY):**
```json
[
  {{"title": "Setup_Project_Structure", "objective": "Create project directories and configuration files"}},
  {{"title": "Implement_Core_Module", "objective": "Build the main business logic module"}},
  ...
]
```

**RULES:**
1. Output ONLY the JSON array, nothing else
2. Each item must have "title" and "objective" keys
3. Titles should be Short_Snake_Case
4. Objectives should be 1-2 sentences
5. You MUST generate EXACTLY {target_briqs} items
6. Order logically (foundations before features)

{universal_file_rule}

**EXISTING FILE STRUCTURE in qodeyard:**
```
{qodeyard_tree}
```

**INPUT DOCUMENT:**
{task_content}

**BEGIN BLUEPRINT (JSON array with {target_briqs} items):**
"""

    # Call AI to get blueprint
    try:
        blueprint_response = lib_ai.ai_query(
            prompt=blueprint_prompt,
            provider=ai_provider,
            model=ai_model
        )
    except Exception as e:
        print(f"  ⚠️  [BLUEPRINT] AI call failed: {e}. Falling back to single-shot.", flush=True)
        return []  # Signal to fallback
    
    # Parse JSON blueprint
    try:
        # Extract JSON from response (may have markdown fences)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', blueprint_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = blueprint_response.strip()
        
        blueprint = json.loads(json_str)
        
        if not isinstance(blueprint, list):
            raise ValueError("Blueprint must be a JSON array")
        
        # Validate blueprint structure
        for item in blueprint:
            if not isinstance(item, dict) or 'title' not in item or 'objective' not in item:
                raise ValueError("Each blueprint item must have 'title' and 'objective'")
        
        print(f"  ✅ [BLUEPRINT] Generated {len(blueprint)} briq specifications", flush=True)
        
        # Estimate tokens for blueprint phase
        blueprint_tokens = estimate_tokens(blueprint_prompt + blueprint_response, ai_model)
        blueprint_cost = calculate_cost(blueprint_tokens, ai_model, is_input=True)
        print(f"  💰 [BLUEPRINT] Cost: {format_cost(blueprint_cost)} ({blueprint_tokens:,} tokens)", flush=True)
        
    except Exception as e:
        print(f"  ⚠️  [BLUEPRINT] Failed to parse JSON: {e}. Falling back to single-shot.", flush=True)
        return []  # Signal to fallback
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2: FABRICATION (BATCHED) - Generate full XML content in chunks
    # ═══════════════════════════════════════════════════════════════════════════
    
    num_batches = math.ceil(len(blueprint) / batch_size)
    print(f"\n🔨 [FABRICATION] Phase 2: Generating {len(blueprint)} briqs in {num_batches} batches (size: {batch_size})", flush=True)
    
    all_briqs = []
    total_fabrication_cost = 0
    
    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(blueprint))
        batch_items = blueprint[start_idx:end_idx]
        
        print(f"\n  📦 [Batch {batch_idx + 1}/{num_batches}] Fabricating briqs {start_idx + 1}-{end_idx}...", flush=True)
        
        # Build batch fabrication prompt
        batch_list = "\n".join([
            f"{i+1}. **{item['title']}**: {item['objective']}"
            for i, item in enumerate(batch_items)
        ])
        
        fabrication_prompt = f"""You are the **Principal Software Architect** fabricating detailed briqs.

**MASTER BLUEPRINT:** You are working on items {start_idx + 1}-{end_idx} of a {len(blueprint)}-briq project.

**YOUR BATCH (Generate full XML for these {len(batch_items)} briqs):**
{batch_list}

{universal_file_rule}

**EXISTING FILE STRUCTURE in qodeyard:**
```
{qodeyard_tree}
```

**ORIGINAL TASK CONTEXT:**
{task_content[:2000]}...

**OUTPUT FORMAT (STRICT XML):**
You must wrap each task in `<briq title="Title_From_Blueprint">...</briq>` tags.
Include detailed implementation instructions for each briq.
Do not include any other text outside of the `<briq>` tags.

**BEGIN FABRICATION (Generate {len(batch_items)} briqs):**
"""

        # Call AI to fabricate this batch
        try:
            fabrication_response = lib_ai.ai_query(
                prompt=fabrication_prompt,
                provider=ai_provider,
                model=ai_model
            )
            
            # Parse XML briqs from response
            batch_briqs = parse_xml_briqs(fabrication_response)
            
            if not batch_briqs:
                print(f"  ⚠️  [Batch {batch_idx + 1}] No briqs parsed, retrying...", flush=True)
                # Retry once
                fabrication_response = lib_ai.ai_query(
                    prompt=fabrication_prompt,
                    provider=ai_provider,
                    model=ai_model
                )
                batch_briqs = parse_xml_briqs(fabrication_response)
            
            # Estimate cost for this batch
            batch_tokens = estimate_tokens(fabrication_prompt + fabrication_response, ai_model)
            batch_cost = calculate_cost(batch_tokens, ai_model, is_input=True)
            total_fabrication_cost += batch_cost
            
            print(f"  ✅ [Batch {batch_idx + 1}] Generated {len(batch_briqs)} briqs | Cost: {format_cost(batch_cost)} ({batch_tokens:,} toks)", flush=True)
            
            all_briqs.extend(batch_briqs)
            
        except Exception as e:
            print(f"  ❌ [Batch {batch_idx + 1}] Fabrication failed: {e}", flush=True)
            # Continue with next batch rather than failing entire generation
            continue
    
    print(f"\n  💰 [FABRICATION] Total Cost: {format_cost(total_fabrication_cost)}", flush=True)
    print(f"  ✅ [COMPLETE] Generated {len(all_briqs)} briqs across {num_batches} batches", flush=True)
    
    return all_briqs


def generate_briqs_with_enforcement(
    ai_provider: str,
    ai_model: str,
    base_prompt: str,
    sensitivity: int,
    task_content: str,
    qodeyard_tree: str,
    max_retries: int = 2
) -> list[dict]:
    """
    Generate briqs with ENFORCED count ranges.
    Will retry with stronger prompts if AI doesn't comply.
    """
    min_briqs, max_briqs, target_briqs, sens_prompt = get_sensitivity_config(sensitivity)
    
    for attempt in range(max_retries + 1):
        # Build enforcement prompt
        if attempt == 0:
            enforcement = sens_prompt
        else:
            # Stronger enforcement on retry
            enforcement = f"""
⚠️ RETRY ATTEMPT {attempt + 1} - STRICT ENFORCEMENT ⚠️

{sens_prompt}

YOUR PREVIOUS OUTPUT DID NOT COMPLY. YOU MUST OUTPUT BETWEEN {min_briqs} AND {max_briqs} BRIQS.

COUNT YOUR BRIQS BEFORE OUTPUTTING. If you have fewer than {min_briqs}, split your briqs further.
If you have more than {max_briqs}, combine related briqs together.

THIS IS A HARD REQUIREMENT. NON-COMPLIANCE WILL CAUSE SYSTEM FAILURE.
"""
        
        full_prompt = base_prompt.replace("{SENSITIVITY_PROMPT}", enforcement)
        
        # Estimate and log cost
        input_tokens = estimate_tokens(full_prompt, ai_model)
        estimated_output_tokens = 2000
        input_cost = calculate_cost(input_tokens, ai_model, is_input=True)
        output_cost = calculate_cost(estimated_output_tokens, ai_model, is_input=False)
        total_cost = input_cost + output_cost
        
        if attempt == 0:
            print(f"Estimated cost: {format_cost(total_cost)} ({input_tokens:,} in + ~{estimated_output_tokens:,} out tokens @ {ai_model})", flush=True)
        
        # Call AI
        try:
            response = lib_ai.run_ai_completion(
                ai_provider,
                ai_model,
                full_prompt,
                prompt_sections=[{
                    'label': 'briq_generation_prompt',
                    'content': full_prompt,
                    'required': True,
                    'loss_policy': 'chunkable',
                    'section_type': 'planning',
                }],
                agent_name='instruqtor',
                task_type='planning',
                output_tokens=2000,
            )
        except Exception as e:
            sys.stderr.write(f"InstruQtor AI call failed: {e}\n")
            if attempt < max_retries:
                continue
            sys.exit(1)
        
        # Parse briqs
        briqs = parse_xml_briqs(response)
        
        if not briqs:
            print(f"  [WARN] No valid briqs parsed, attempt {attempt + 1}", flush=True)
            if attempt < max_retries:
                continue
            # Fallback: create single briq from raw response
            briqs = [{'title': 'Master_Plan_Fallback', 'content': response}]
        
        briq_count = len(briqs)
        
        # Check compliance
        if min_briqs <= briq_count <= max_briqs:
            print(f"  [OK] Briq count {briq_count} is within range [{min_briqs}-{max_briqs}]", flush=True)
            return briqs
        elif briq_count > max_briqs:
            # Too many - merge them
            print(f"  [ENFORCE] Got {briq_count} briqs, max is {max_briqs}. Merging...", flush=True)
            return merge_briqs(briqs, max_briqs)
        else:
            # Too few - retry with stronger prompt
            print(f"  [ENFORCE] Got {briq_count} briqs, need at least {min_briqs}. Retrying...", flush=True)
            if attempt >= max_retries:
                # Last resort: accept what we have
                print(f"  [WARN] Could not achieve minimum briq count after {max_retries + 1} attempts. Proceeding with {briq_count} briqs.", flush=True)
                return briqs
    
    return briqs


def main() -> None:
    if len(sys.argv) != 3: sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    worqspace_root = Path(os.environ.get('QONQ_WORKSPACE', os.getcwd()))
    task_spec = load_optional_json(worqspace_root / 'task' / 'task-spec.v1.json')
    guard_result = load_optional_json(worqspace_root / 'guard' / 'guard-result.v1.json')

    print(f"--- Architect analyzing: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f: task_content = clean_input_content(f.read())
    planning_task_content = build_planning_task_input(task_content, task_spec, guard_result)

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider = agent_cfg.get('provider', 'openai')
    ai_model = agent_cfg.get('model', 'gpt-4o')
    
    # v1.0.3: Load batched generation config
    batch_mode = agent_cfg.get('batch_mode', True)
    batch_size = agent_cfg.get('batch_size', 5)

    try: sensitivity = int(os.environ.get('QONQ_SENSITIVITY', 5))  # v1.0.2: Default to 5 (Balanced)
    except: sensitivity = 5
    
    # Clamp sensitivity to valid range (v1.0.2: 0-16 inverted scale)
    sensitivity = max(0, min(16, sensitivity))

    # Get briq range info for logging
    min_briqs, max_briqs, target_briqs, _ = get_sensitivity_config(sensitivity)
    
    # v1.0.3: Determine if we should use batched generation
    use_batched = batch_mode and sensitivity >= 8
    strategy = "Batched" if use_batched else "Single-shot"
    
    print(f"  [CONFIG] Sensitivity: {sensitivity} → Target: {target_briqs} briqs (range: {min_briqs}-{max_briqs})", flush=True)
    print(f"  [CONFIG] Strategy: {strategy} (batch_size: {batch_size}, batch_mode: {batch_mode})", flush=True)
    if task_spec:
        print(f"  [INPUT] Canonical Task Spec: {task_spec.get('status', 'UNKNOWN')} ({task_spec.get('task_spec_id', 'n/a')})", flush=True)
    if guard_result:
        print(f"  [INPUT] Guard Result: {guard_result.get('status', 'UNKNOWN')}", flush=True)
        if guard_result.get('status') == 'FAIL':
            print("  [FAIL-FAST] Guard blocked planning. Review guard/guard-result.v1.json.", flush=True)
            sys.exit(1)

    # Gather Qodeyard Context
    qodeyard_path = Path(os.environ.get('QONQ_WORKSPACE', '/qonq')) / 'qodeyard'
    qodeyard_tree = ""
    qodeyard_file_count = 0
    if qodeyard_path.exists() and any(qodeyard_path.iterdir()):
        tree_lines = []
        tree_lines.append(f"{qodeyard_path.name}/")
        
        def build_tree(dir_path: Path, prefix: str):
            nonlocal qodeyard_file_count
            items = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name))
            for i, path in enumerate(items):
                is_last = i == (len(items) - 1)
                connector = '└── ' if is_last else '├── '
                
                if path.is_dir():
                    tree_lines.append(f"{prefix}{connector}{path.name}/")
                    new_prefix = prefix + ('    ' if is_last else '│   ')
                    build_tree(path, new_prefix)
                else:
                    qodeyard_file_count += 1
                    tree_lines.append(f"{prefix}{connector}{path.name}")

        build_tree(qodeyard_path, "")
        qodeyard_tree = "\n".join(tree_lines)
    else:
        qodeyard_tree = "[qodeyard is empty - this is a fresh build]"

    # Build the universal file rule
    universal_file_rule = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 UNIVERSAL FILE RULE (STRICTLY ENFORCED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before creating ANY briq, check the file tree below:

  📁 FILE EXISTS in qodeyard?
     → Create a briq to MODIFY it (fix bugs, improve implementation)
     → Create a briq to EXTEND it (add new functions, classes, features)
     → NEVER create a briq to recreate it from scratch
     
  📄 FILE DOESN'T EXIST yet?
     → Create a briq to CREATE it (new modules are welcome!)

This rule applies to ALL cycles. The qodeyard is your source of truth.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # Context awareness message
    if qodeyard_file_count > 0:
        context_msg = f"\n📊 QODEYARD STATUS: {qodeyard_file_count} files exist. Build on this foundation.\n"
    else:
        context_msg = "\n📊 QODEYARD STATUS: Empty. This is cycle 1 - build from scratch.\n"

    # Build base prompt with placeholder for sensitivity
    planner_prompt = f"""
You are the **Principal Software Architect** and your only purpose is to break down a technical specification into a precise number of tasks, called 'briqs'. You must follow the rules EXACTLY as specified.

{{SENSITIVITY_PROMPT}}

{universal_file_rule}
{context_msg}

**ARCHITECTURAL DIRECTIVES:**
1.  **ADHERE TO THE BRIQ COUNT:** This is a STRICT requirement. Count your briqs before outputting!
2.  **RESPECT EXISTING FILES:** Check the file tree. Don't recreate what exists - modify or extend it.
3.  **ADDRESS THE INPUT:** If the input contains a review with issues, create briqs to fix those issues.
4.  **ADD MISSING PIECES:** Create briqs for genuinely missing functionality.
5.  **LOGICAL ORDERING:** Order briqs logically - foundations before features that depend on them.

**OUTPUT FORMAT (STRICT XML):**
You must wrap each task in `<briq title="A_Short_And_Clear_Title">...</briq>` tags. The title should be short and descriptive. Do not include any other text or formatting outside of the `<briq>` tags.

**EXISTING FILE STRUCTURE in qodeyard:**
```
{qodeyard_tree}
```

**INPUT DOCUMENT:**
{planning_task_content}

**BEGIN ATOMIC BREAKDOWN (Count your briqs to ensure compliance!):**
"""

    print("Instruqtor: splitting briqs", flush=True)
    # v1.0.3: Generate briqs using appropriate strategy
    if use_batched:
        # Try batched generation first
        briqs = generate_briqs_paginated(
            ai_provider=ai_provider,
            ai_model=ai_model,
            base_prompt=planner_prompt,
            sensitivity=sensitivity,
            target_briqs=target_briqs,
            batch_size=batch_size,
            task_content=planning_task_content,
            qodeyard_tree=qodeyard_tree,
            universal_file_rule=universal_file_rule
        )
        
        # Fallback to single-shot if batched fails
        if not briqs:
            print(f"\n  ⚠️  [FALLBACK] Batched generation failed, using single-shot enforcement...", flush=True)
            briqs = generate_briqs_with_enforcement(
                ai_provider=ai_provider,
                ai_model=ai_model,
                base_prompt=planner_prompt,
                sensitivity=sensitivity,
                task_content=planning_task_content,
                qodeyard_tree=qodeyard_tree
            )
    else:
        # Use traditional single-shot enforcement
        briqs = generate_briqs_with_enforcement(
            ai_provider=ai_provider,
            ai_model=ai_model,
            base_prompt=planner_prompt,
            sensitivity=sensitivity,
            task_content=planning_task_content,
            qodeyard_tree=qodeyard_tree
        )

    print(f"--- Architect Generated {len(briqs)} Build Phases (Sens:{sensitivity}, Range:{min_briqs}-{max_briqs}) ---", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.0.4: QONTRACT GENERATION (Cycle 1 only)
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_dir = worqspace_root / 'qontract.d'
    contract = {}

    if cycle_num == '1':
        print(f"\n  📜 [QONTRACT] Generating project constitution from cycle1 tasq...", flush=True)
        contract = extract_qontract_from_tasq(planning_task_content, input_file.name)
        write_qontract(contract, qontract_dir)
        # Fail-fast: assert contract files were created
        md_check = qontract_dir / 'qontract.json'
        if not md_check.exists():
            print(f"  ❌ FAIL-FAST: Contract files not created in {qontract_dir}", flush=True)
            sys.exit(1)
    else:
        # Load existing contract for invariant injection
        contract_path = qontract_dir / 'qontract.json'
        if contract_path.exists():
            try:
                with open(contract_path, 'r', encoding='utf-8') as f:
                    contract = json.load(f)
                print(f"  📜 [QONTRACT] Loaded existing contract ({len(contract.get('invariants', {}))} invariant categories)", flush=True)
            except Exception as e:
                print(f"  ⚠️  [QONTRACT] Could not load contract: {e}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3 BRIDGE: STRUCTURED PLANNING + GROUPED BUILD MODEL
    # ═══════════════════════════════════════════════════════════════════════════
    briq_summaries = summarize_briqs_for_planning(briqs)
    print("Instruqtor: planning build groups", flush=True)
    try:
        plan_payload = generate_structured_plan(
            ai_provider=ai_provider,
            ai_model=ai_model,
            planning_task_content=planning_task_content,
            qodeyard_tree=qodeyard_tree,
            briq_summaries=briq_summaries,
            sensitivity=sensitivity,
            min_briqs=min_briqs,
            max_briqs=max_briqs,
            target_briqs=target_briqs,
        )
        print(f"  [PLAN] Structured grouped execution plan generated", flush=True)
    except Exception as e:
        print(f"  [PLAN] ⚠️ Structured plan AI generation failed, using deterministic fallback: {e}", flush=True)
        plan_payload = build_fallback_structured_plan(
            goal=task_spec.get('goal', extract_goal(planning_task_content)) if task_spec else extract_goal(planning_task_content),
            briq_summaries=briq_summaries,
            guard_result=guard_result,
            sensitivity=sensitivity,
            min_briqs=min_briqs,
            max_briqs=max_briqs,
            target_briqs=target_briqs,
        )

    write_planning_artifacts(
        worqspace_root=worqspace_root,
        cycle_num=cycle_num,
        task_spec=task_spec,
        guard_result=guard_result,
        plan_payload=plan_payload,
        briq_summaries=briq_summaries,
    )
    print("Instruqtor: wrote execution blueprint", flush=True)
    briq_assignments = assign_briqs_to_groups(briq_summaries, plan_payload)
    print(f"  [PLAN] Build groups: {len(plan_payload.get('execution_blueprint', {}).get('build_groups', []))}", flush=True)
    print(f"  [PLAN] Component contracts: {len(plan_payload.get('component_contracts', []))}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # WRITE BRIQS (with invariant injection + grouped scope metadata)
    # ═══════════════════════════════════════════════════════════════════════════
    for i, item in enumerate(briqs):
        briq_ref = f"briq-{i + 1:03d}"
        assignment = briq_assignments.get(briq_ref, {})
        group = assignment.get('group', {})
        component = assignment.get('component', {})
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
        file_path = output_dir / filename

        briq_content = item['content']
        build_group_id = group.get('build_group_id', f"bg-{component_id_from_title(item['title'])}")
        scope_id = group.get('scope_id', f"scope_build_group_{build_group_id.replace('-', '_')}")
        component_id = component.get('component_id', component_id_from_title(item['title']))
        component_title = component.get('title', component_id.replace('-', ' ').title())
        group_title = group.get('title', build_group_id)
        group_objective = group.get('objective', component.get('summary', ''))
        validation_focus = group.get('validation_focus', [])
        constraints = component.get('constraints', [])

        # v1.0.4: Inject relevant invariants based on scope tags + add Contract-Relevant header
        scope_tags = []
        metadata_scope_tags = infer_scope_tags(
            " ".join(
                part
                for part in (
                    item['title'],
                    component_id,
                    component_title,
                    build_group_id,
                    scope_id,
                    group_objective,
                    " ".join(validation_focus),
                    " ".join(constraints),
                )
                if part
            ),
            briq_content,
        )
        contract_relevant = bool(metadata_scope_tags and any(
            tag in metadata_scope_tags for tag in ('schema', 'storage', 'routing', 'id')
        ))
        if contract.get('invariants'):
            scope_tags = infer_scope_tags(item['title'], briq_content)
            if not scope_tags:
                scope_tags = metadata_scope_tags
            # Contract-relevant if scope includes schema, storage, routing, or id
            contract_relevant = bool(scope_tags and any(
                t in scope_tags for t in ('schema', 'storage', 'routing', 'id')
            ))
            if scope_tags:
                briq_content = inject_invariants_into_briq(briq_content, scope_tags, contract)
                print(f"  - Wrote [Plan] {filename} (scope: {', '.join(scope_tags)}, contract-relevant: {contract_relevant})", flush=True)
            else:
                print(f"  - Wrote [Plan] {filename} (no invariants)", flush=True)
        else:
            print(f"  - Wrote [Plan] {filename}", flush=True)
            scope_tags = metadata_scope_tags

        # Estimate tokens for this briq
        full_briq = f"# {item['title']}\n\n**ARCHITECT'S INSTRUCTION:**\n{briq_content}"
        briq_tokens = estimate_tokens(full_briq, ai_model)
        briq_cost = calculate_cost(briq_tokens, ai_model, is_input=True)

        grouped_scope_section = "\n\n---\n**Grouped Scope Contract:**\n"
        grouped_scope_section += f"- Build Group: {build_group_id} ({group_title})\n"
        grouped_scope_section += f"- Scope ID: {scope_id}\n"
        grouped_scope_section += f"- Component: {component_id} ({component_title})\n"
        if group_objective:
            grouped_scope_section += f"- Group Objective: {group_objective}\n"
        if validation_focus:
            grouped_scope_section += f"- Validation Focus: {', '.join(validation_focus)}\n"
        if constraints:
            grouped_scope_section += "- Component Constraints:\n"
            for item_constraint in constraints[:6]:
                grouped_scope_section += f"  - {item_constraint}\n"
        briq_content = briq_content + grouped_scope_section

        # v1.0.4: Build briq with frontmatter including scope + contract relevance
        scope_str = ', '.join(scope_tags) if scope_tags else 'none'
        frontmatter = (
            f"Scope: {scope_str}\n"
            f"Contract-Relevant: {'yes' if contract_relevant else 'no'}\n"
            f"Briq-Ref: {briq_ref}\n"
            f"Build-Group: {build_group_id}\n"
            f"Scope-ID: {scope_id}\n"
            f"Component-ID: {component_id}\n"
            f"Component-Title: {component_title}\n\n"
        )

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{frontmatter}# {item['title']} [Est: {briq_tokens:,} toks | {format_cost(briq_cost)}]\n\n**ARCHITECT'S INSTRUCTION:**\n{briq_content}")
        print(f"Instruqtor: wrote briq {filename}", flush=True)
        print(f"    ↳ Grouped Scope: {build_group_id} | Component: {component_id} | Scope: {scope_id}", flush=True)


if __name__ == '__main__':
    main()
