#!/usr/bin/env python3
# worqer/instruqtor.py
# ═══════════════════════════════════════════════════════════════════════════════
# InstruQtor Agent - Task Decomposition & Planning
# v1.3.0 - QONTRACT Generation + Invariant Injection
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
#   1  = Tiny split (2 briqs)        - Ultra-small tasqs
#   2  = Very broad (2-3 briqs)      - Small tasqs
#   3  = Broad (3-4 briqs)           - Small/medium tasqs
#   4  = Feature-level (4-6 briqs)   - Medium tasqs
#   5  = Balanced (5-7 briqs)        - Solid default for beefier work
#   6  = Detailed (6-9 briqs)        - Larger but still bounded work
#   7  = High (8-12 briqs)           - Multi-part implementations
#   8  = Very High (10-15 briqs)     - Denser architectures
#   9  = Atomic-ish (12-18 briqs)    - Fine-grained but sane
#  10  = Ultra (15-22 briqs)         - Large project slices
#  11  = Mega (18-28 briqs)          - Large multi-scope work
#  12  = Hyper (22-36 briqs)         - Huge specifications
#  13  = Extreme (28-48 briqs)       - Multi-layer systems
#  14  = Maximum (36-64 briqs)       - Enterprise-scale decomposition
#  15  = Insane (48-84 briqs)        - Massive specifications
#  16  = QONQRETE MAX (64-120 briqs) - Mega tasqs only
#
# Auto briq sensitivity:
# - If QONQ_AUTO_BRIQ_SENS=1, InstruQtor estimates the required sensitivity
#   immediately before briq generation.
# - Manual CLI -b overrides config auto_briq_sens.
# - Forced CLI -B overrides everything and always uses auto estimation.
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


def _runtime_version() -> str:
    env_version = str(os.environ.get("QONQ_VERSION", "")).strip()
    if env_version:
        return env_version
    try:
        return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "?.?.?"


RUNTIME_VERSION = _runtime_version()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import lib_ai.py: {e}\n")
    sys.exit(1)

# Import cost estimation
try:
    from calqulator import estimate_tokens, calculate_cost, format_cost
except ImportError:
    def estimate_tokens(text, model="deepseek-v4-flash"):
        return len(text or "") // 4

    def calculate_cost(tokens, model, is_input=True):
        return (tokens / 1_000_000) * (0.4 if is_input else 1.6)

    def format_cost(cost):
        return f"${cost:.5f}" if cost < 0.01 else f"${cost:.2f}"


# ═══════════════════════════════════════════════════════════════════════════════
# SIX-SHOOTER QONTRACT ARCHITECTURE (v1.3.13)
# ═══════════════════════════════════════════════════════════════════════════════

def select_six_shooter_docs(sensitivity: int) -> list[str]:
    """Determine which docs to include based on sensitivity tier."""
    if sensitivity <= 3:
        return ["01", "02", "05"]
    if sensitivity <= 7:
        return ["01", "02", "04", "05"]
    return ["00", "01", "02", "03", "04", "05"]

def generate_six_shooter_docs(
    workspace_root: Path,
    selected_ids: list[str],
    task_content: str,
    contract: dict,
    complexity_result: dict,
) -> list[str]:
    """
    Instantiate selected Qontract docs from templates.
    Templates are located in qontract.d/ (copied by launcher).
    """
    qontract_dir = workspace_root / "qontract.d"
    generated_files = []
    
    # Mapping of doc ID to template filename (glob)
    for doc_id in selected_ids:
        patterns = [f"{doc_id}-*.md"]
        matches = list(qontract_dir.glob(patterns[0]))
        if not matches:
            continue
        
        template_path = matches[0]
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple instantiation logic: replace placeholders
            # In a real impl, this might use lib_ai to tailor docs,
            # but for now we follow the blueprint's "instantiation"
            instantiated = content
            instantiated = instantiated.replace("{{TASK_CONTENT}}", task_content)
            instantiated = instantiated.replace("{{COMPLEXITY}}", str(complexity_result.get("score", "unknown")))
            
            # Write back the instantiated doc
            # We keep the same filename
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(instantiated)
            generated_files.append(template_path.name)
        except Exception as e:
            print(f"  [WARN] Failed to instantiate {template_path.name}: {e}", flush=True)
            
    return generated_files

def write_six_shooter_manifest(
    workspace_root: Path,
    selected_docs: list[str],
    sensitivity: int,
    complexity_result: dict,
    auto_repair_budget: dict,
) -> str:
    """Emit the machine-readable six-shooter-manifest.v1.json."""
    manifest = {
        "schema_version": "six-shooter-manifest.v1",
        "generated_at": now_utc(),
        "sensitivity": sensitivity,
        "complexity_score": complexity_result.get("score", 0),
        "selected_docs": selected_docs,
        "auto_repair_budget": auto_repair_budget,
        "tier": "big" if sensitivity >= 8 else ("medium" if sensitivity >= 4 else "small"),
    }
    manifest_path = workspace_root / "qontract.d" / "six-shooter-manifest.v1.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return "qontract.d/six-shooter-manifest.v1.json"

def now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

# ═══════════════════════════════════════════════════════════════════════════════
# QONTRACT GENERATION (v1.3.0) - Persistent Constitution from Cycle 1
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
    Deterministically extract contractual invariants from the first build-pass tasq markdown.

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
        'version': '1.4.4',
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
    md += f"_Generated by InstruQtor v{RUNTIME_VERSION} | Source build pass: {meta.get('source_cycle', 1)} | Hash: {meta.get('hash', 'n/a')}_\n\n"
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
# INVARIANT INJECTION INTO BRIQS (v1.3.0)
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
    0: (1, 1, 1),        # Monolithic
    1: (2, 2, 2),        # Tiny split
    2: (2, 3, 3),        # Very broad
    3: (3, 4, 4),        # Broad
    4: (4, 6, 5),        # Feature-level
    5: (5, 7, 6),        # Balanced
    6: (6, 9, 8),        # Detailed
    7: (8, 12, 10),      # High
    8: (10, 15, 12),     # Very high
    9: (12, 18, 15),     # Atomic-ish
    10: (15, 22, 18),    # Ultra
    11: (18, 28, 22),    # Mega
    12: (22, 36, 28),    # Hyper
    13: (28, 48, 36),    # Extreme
    14: (36, 64, 48),    # Maximum
    15: (48, 84, 64),    # Insane
    16: (64, 120, 90),   # QONQRETE MAX
}


def clamp_sensitivity(level: int) -> int:
    return max(0, min(16, int(level)))


SENSITIVITY_THRESHOLDS = [
    (2, 0),
    (10, 1),
    (14, 2),
    (18, 3),
    (22, 4),
    (28, 5),
    (36, 6),
    (44, 7),
    (52, 8),
    (60, 9),
    (66, 10),
    (72, 11),
    (78, 12),
    (84, 13),
    (92, 14),
    (104, 15),
]


AUTO_SENSITIVITY_KEYWORDS = {
    'websocket': 2.0,
    'real-time': 2.0,
    'realtime': 2.0,
    'background worker': 1.5,
    'scheduler': 1.5,
    'queue': 1.0,
    'docker': 1.2,
    'vagrant': 2.0,
    'postgres': 1.5,
    'redis': 1.5,
    'neo4j': 1.5,
    'elasticsearch': 1.5,
    'kibana': 1.0,
    'nginx': 1.0,
    'fastapi': 0.5,
    'frontend': 0.8,
    'backend': 0.8,
    'api': 0.4,
    'webapp': 0.8,
    'chat': 0.6,
    'upload': 0.8,
    'download': 0.8,
    'authentication': 0.7,
    'authorization': 0.8,
    'encryption': 1.2,
    'orchestration': 1.8,
    'microservice': 1.5,
    'agent': 0.8,
    'payload': 1.5,
    'implant': 1.5,
    'c2': 2.0,
    'provision': 1.2,
    'bootstrap': 0.8,
    'integration test': 1.2,
    'test': 0.3,
}


def analyze_task_complexity(task_content: str, qodeyard_file_count: int = 0) -> dict:
    lines = task_content.splitlines()
    headings = sum(1 for line in lines if re.match(r'^\s*#+\s', line))
    bullet_lines = sum(1 for line in lines if re.match(r'^\s*[-*]\s+', line))
    numbered_lines = sum(1 for line in lines if re.match(r'^\s*\d+[\.)]\s+', line))
    file_mentions = len(set(re.findall(
        r'\b[\w./-]+\.(?:py|md|sh|yaml|yml|json|html|css|js|ts|tsx|jsx|java|kt|rb|rs|go|c|cpp|h|hpp|xml|ini|toml|cfg|sql)\b',
        task_content,
        flags=re.IGNORECASE,
    )))
    route_mentions = len(re.findall(r'\b(GET|POST|PUT|PATCH|DELETE|WS|WebSocket|websocket)\b', task_content, flags=re.IGNORECASE))
    strictness_hits = len(re.findall(r'\b(exactly|must|required|strict|only|do not|never|shall|allowed|forbidden|mandatory)\b', task_content, flags=re.IGNORECASE))
    code_fences = task_content.count('```') // 2

    lowered = task_content.lower()
    keyword_score = 0.0
    matched_keywords = []
    for keyword, weight in AUTO_SENSITIVITY_KEYWORDS.items():
        if keyword in lowered:
            keyword_score += weight
            matched_keywords.append(keyword)

    score = 0.0
    score += min(len(lines) / 70.0, 10.0)
    score += min(len(task_content) / 3000.0, 10.0)
    score += min(headings / 8.0, 6.0)
    score += min((bullet_lines + numbered_lines) / 35.0, 6.0)
    score += min(file_mentions * 0.8, 18.0)
    score += min(route_mentions * 0.6, 5.0)
    score += min(strictness_hits / 25.0, 5.0)
    score += min(code_fences * 0.5, 5.0)
    score += min(keyword_score, 12.0)
    score += min(qodeyard_file_count / 25.0, 4.0)

    if file_mentions >= 25:
        score += 4.0
    elif file_mentions >= 10:
        score += 2.0
    elif file_mentions >= 5:
        score += 1.0

    sensitivity = 16
    for upper_bound, level in SENSITIVITY_THRESHOLDS:
        if score <= upper_bound:
            sensitivity = level
            break

    if len(task_content) < 900 and file_mentions <= 2 and strictness_hits <= 16:
        sensitivity = min(sensitivity, 1)
    elif len(task_content) < 2500 and file_mentions <= 3:
        sensitivity = min(sensitivity, 3)

    if headings >= 3 and bullet_lines >= 18 and file_mentions >= 3:
        sensitivity = max(sensitivity, 2)

    # Repository-scale specs with dozens of explicit files should never collapse
    # into medium sensitivities. These need heavy decomposition even when the
    # prose itself is relatively compact.
    if file_mentions >= 80 and headings >= 3 and bullet_lines >= 50:
        sensitivity = max(sensitivity, 12)
    elif file_mentions >= 50 and headings >= 3 and bullet_lines >= 35:
        sensitivity = max(sensitivity, 10)
    elif file_mentions >= 25 and headings >= 2 and bullet_lines >= 20:
        sensitivity = max(sensitivity, 8)

    return {
        'score': round(score, 2),
        'suggested_sensitivity': clamp_sensitivity(sensitivity),
        'lines': len(lines),
        'chars': len(task_content),
        'headings': headings,
        'bullet_lines': bullet_lines,
        'numbered_lines': numbered_lines,
        'file_mentions': file_mentions,
        'route_mentions': route_mentions,
        'strictness_hits': strictness_hits,
        'code_fences': code_fences,
        'qodeyard_file_count': qodeyard_file_count,
        'matched_keywords': matched_keywords[:20],
    }


def estimate_auto_sensitivity(
    ai_provider: str,
    ai_model: str,
    task_content: str,
    qodeyard_tree: str,
    qodeyard_file_count: int = 0,
) -> tuple[int, dict]:
    heuristics = analyze_task_complexity(task_content, qodeyard_file_count=qodeyard_file_count)
    heuristic_level = heuristics['suggested_sensitivity']

    # v1.3.13: Removed sequential AI call for sensitivity to improve end-to-end speed.
    # Rely entirely on the robust heuristic rules.
    ai_level = clamp_sensitivity(heuristic_level)
    min_briqs, max_briqs, target_briqs, _ = get_sensitivity_config(ai_level)
    details = {
        'mode': 'auto',
        'heuristics': heuristics,
        'ai_confidence': 'heuristic-only',
        'ai_rationale': ['Using fast heuristic analysis'],
        'resolved_sensitivity': ai_level,
        'expected_briq_range': [min_briqs, max_briqs],
        'target_briqs': target_briqs,
    }
    return ai_level, details


def clean_input_content(text: str) -> str:
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = text.replace('\xa0', ' ')
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    return text


def extract_goal_text(task_spec: dict | None, planning_task_content: str) -> str:
    if isinstance(task_spec, dict):
        for key in ('goal', 'summary', 'title'):
            value = str(task_spec.get(key, '')).strip()
            if value:
                return value

    lines = [line.strip() for line in planning_task_content.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        normalized = line.lower().rstrip(':')
        if normalized in {'goal', 'objective'} and idx + 1 < len(lines):
            candidate = lines[idx + 1].strip('- ').strip()
            if candidate:
                return candidate
        if line.startswith('#'):
            candidate = line.lstrip('#').strip()
            if candidate:
                return candidate
    return (lines[0] if lines else 'Implement the clarified task scope.').strip()


from path_hygiene import is_infra_path


def extract_required_files_from_task(task_content: str) -> list[str]:
    def _looks_numeric_decimal_token(text: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:\.\d+)+", text))

    def _normalize(candidate: str) -> str:
        text = str(candidate or "").strip().replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        if text.startswith("/qodeyard/"):
            text = text[len("/qodeyard/"):]
        if text.startswith("qodeyard/"):
            text = text[len("qodeyard/"):]
        return text.strip()

    def _looks_like_file(candidate: str) -> bool:
        text = _normalize(candidate)
        if not text:
            return False
        if is_infra_path(text):
            return False
        if _looks_numeric_decimal_token(text):
            return False
        if text.startswith("../") or text.startswith("/"):
            return False
        if ":" in text and "/" not in text:
            return False
        if "/" in text:
            parts = [part for part in text.split("/") if part]
            if parts and all(re.match(r"^[A-Za-z0-9_.-]+$", part) for part in parts):
                return True
        if re.match(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,10}$", text):
            return True
        if text in {"Dockerfile", "Makefile"}:
            return True
        return False

    required: list[str] = []
    forbidden_line_markers = (
        "do not add",
        "don't add",
        "do not include",
        "don't include",
        "forbidden",
        "must not include",
        "must not add",
        "unexpected",
        "extra file",
        "no extra file",
    )

    for raw_line in task_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(marker in lower for marker in forbidden_line_markers):
            continue
        for candidate in re.findall(r'`([^`]+)`', line):
            cleaned = _normalize(candidate)
            if _looks_like_file(cleaned):
                required.append(cleaned)

    in_required_block = False
    for raw_line in task_content.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        inline_required = re.search(r"required[-_ ]files?\s*:\s*\[(.+)\]", line, flags=re.IGNORECASE)
        if inline_required:
            for part in inline_required.group(1).split(","):
                cleaned = _normalize(part.strip().strip("`\"'"))
                if _looks_like_file(cleaned):
                    required.append(cleaned)
        if (
            re.search(r"\brequired[-_ ]files?\b", lower)
            or "project must contain exactly these files" in lower
            or "must contain exactly these files" in lower
            or "repo root contains" in lower
            or "the repo root contains" in lower
        ):
            in_required_block = True
            continue
        if in_required_block:
            if line.startswith("#"):
                in_required_block = False
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9 _-]+:\s*$", line) and not re.search(r"\brequired[-_ ]files?\b", lower):
                in_required_block = False
                continue
        if not in_required_block or not line:
            continue
        candidate = line.lstrip("-*").strip()
        candidate = re.sub(r"^\d+\.\s*", "", candidate).strip()
        candidate = candidate.strip("`\"'")
        cleaned = _normalize(candidate)
        if _looks_like_file(cleaned):
            required.append(cleaned)

    file_token_re = re.compile(
        r"(?<![\w])(?:/?qodeyard/)?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,10}|Dockerfile|Makefile)(?![\w/])"
    )
    for raw_line in task_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(marker in lower for marker in forbidden_line_markers):
            continue
        for match in file_token_re.finditer(line):
            cleaned = _normalize(match.group(1))
            if _looks_like_file(cleaned):
                required.append(cleaned)

    seen: set[str] = set()
    ordered: list[str] = []
    for item in required:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def extract_target_files_from_briq(briq_content: str) -> list[str]:
    """Extract probable target files from a briq body."""
    return extract_required_files_from_task(briq_content or "")


def extract_primary_files_from_briq(briq_content: str, target_files: list[str]) -> list[str]:
    """
    Infer primary deliverables for a briq from explicit action phrases.
    Falls back to the first target file to avoid empty ownership.
    """
    if not target_files:
        return []
    text = briq_content or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fragments: list[str] = []
    for line in lines:
        parts = [part.strip() for part in re.split(r"[.!?]", line) if part.strip()]
        if parts:
            fragments.extend(parts)
        else:
            fragments.append(line)
    action_markers = (
        "create",
        "write",
        "implement",
        "update",
        "modify",
        "build",
        "add",
        "edit",
        "generate",
    )
    inferred: list[str] = []
    for fragment in fragments:
        lower = fragment.lower()
        if not any(marker in lower for marker in action_markers):
            continue
        file_hits: list[tuple[int, str]] = []
        for rel_path in target_files:
            match = re.search(rf"(?<![\w/]){re.escape(rel_path)}(?![\w/])", fragment)
            if match:
                file_hits.append((match.start(), rel_path))
        if not file_hits:
            continue
        file_hits.sort(key=lambda item: item[0])
        # Keep only the first actionable file in the sentence to avoid
        # over-scoping primary ownership from reference mentions.
        inferred.append(file_hits[0][1])
    if not inferred:
        inferred = [target_files[0]]
    seen: set[str] = set()
    ordered: list[str] = []
    for item in inferred:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def resolve_agent_ai_params(config: dict, agent_name: str, default_provider: str, default_model: str) -> tuple[str, str]:
    """Thin compatibility shim around lib_ai.get_agent_ai_params()."""
    getter = getattr(lib_ai, "get_agent_ai_params", None)
    if callable(getter):
        return getter(config, agent_name, default_provider, default_model)
    agent_cfg = (config or {}).get("agents", {}).get(agent_name, {}) or {}
    provider = str(agent_cfg.get("provider", default_provider) or default_provider)
    model = str(agent_cfg.get("model", default_model) or default_model)
    return provider, model


def _normalize_nonnegative_int(value, default: int) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


def compute_auto_repair_budget(
    *,
    config: dict,
    plan_payload: dict,
    sensitivity: int,
    required_files: list[str],
) -> dict:
    """
    Compute bounded recommended retry/repair budgets from planning complexity.
    This recommendation is advisory metadata and runtime applies it only when
    explicit non-default overrides are absent.
    """
    basis = plan_payload.get("estimation_basis", {}) or {}
    complexity = str(basis.get("complexity", "")).strip().lower()
    target_briqs = _normalize_nonnegative_int(basis.get("target_briqs"), 0)
    required_count = len(required_files or [])
    score = target_briqs + required_count + max(0, int(sensitivity))
    if complexity in {"high", "very_high", "extreme"} or score >= 24:
        tier = "high"
    elif complexity in {"medium"} or score >= 10:
        tier = "medium"
    else:
        tier = "low"

    # Small stays cheap, medium gets room, big gets full bounded room.
    if tier == "low":
        retry_rec = 2
        repair_rec = 2
    elif tier == "medium":
        retry_rec = 3
        repair_rec = 2
    else:
        retry_rec = 4
        repair_rec = 2

    retry_cfg = (config or {}).get("retry", {}) or {}
    repair_cfg = (config or {}).get("repair", {}) or {}
    retry_cap = _normalize_nonnegative_int(retry_cfg.get("hard_cap_max_attempts", 6), 6)
    repair_cap = _normalize_nonnegative_int(
        repair_cfg.get("hard_cap_max_attempts_per_build_pass", repair_cfg.get("hard_cap_max_attempts", 3)),
        3,
    )
    retry_rec = max(1, min(retry_rec, retry_cap if retry_cap > 0 else retry_rec))
    repair_rec = max(0, min(repair_rec, repair_cap if repair_cap > 0 else repair_rec))

    return {
        "enabled": bool(repair_cfg.get("auto_repair_amount", True)),
        "tier": tier,
        "retry_max_attempts": retry_rec,
        "repair_max_attempts_per_build_pass": repair_rec,
        "caps": {
            "retry_max_attempts": retry_cap,
            "repair_max_attempts_per_build_pass": repair_cap,
        },
        "basis": {
            "complexity": complexity or "unknown",
            "target_briqs": target_briqs,
            "required_file_count": required_count,
            "sensitivity": int(sensitivity),
            "score": score,
        },
        "source": "instruqtor_auto_repair_policy_v1",
    }


def _candidate_json_blocks(text: str, expected: str | None = None) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    fence_matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', stripped, re.IGNORECASE)
    candidates.extend(block.strip() for block in fence_matches if block.strip())
    if stripped:
        candidates.append(stripped)

    open_chars = ['{', '[']
    if expected == 'object':
        open_chars = ['{']
    elif expected == 'array':
        open_chars = ['[']

    for opener in open_chars:
        start = stripped.find(opener)
        if start != -1:
            candidates.append(stripped[start:].strip())

    unique: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            unique.append(candidate)
            seen.add(candidate)
    return unique


def _repair_truncated_json(candidate: str) -> str:
    text = candidate.strip()
    if not text:
        return text

    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in '{[':
            stack.append('}' if char == '{' else ']')
        elif char in '}]' and stack and char == stack[-1]:
            stack.pop()

    repaired = text.rstrip()
    if in_string:
        repaired += '"'
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in ',:':
        repaired = repaired[:-1].rstrip()
    if stack:
        repaired += ''.join(reversed(stack))
    return repaired


def parse_json_payload(response: str, expected: str | None = None):
    last_error: Exception | None = None
    decoder = json.JSONDecoder()
    for candidate in _candidate_json_blocks(response, expected=expected):
        for payload_text in (candidate, _repair_truncated_json(candidate)):
            payload_text = payload_text.strip()
            if not payload_text:
                continue
            try:
                return json.loads(payload_text)
            except Exception as exc:
                last_error = exc
            try:
                first_open = payload_text.find('{')
                first_array = payload_text.find('[')
                starts = [idx for idx in (first_open, first_array) if idx != -1]
                if not starts:
                    continue
                parsed, _ = decoder.raw_decode(payload_text[min(starts):])
                return parsed
            except Exception as exc:
                last_error = exc
    raise ValueError(f'Could not parse JSON payload: {last_error or "no JSON candidate found"}')


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
        target_files = extract_target_files_from_briq(content)
        primary_files = extract_primary_files_from_briq(content, target_files)
        summaries.append({
            'briq_index': index,
            'briq_ref': f"briq-{index:03d}",
            'title': title,
            'component_hint': component_id_from_title(title),
            'scope_tags': scope_tags,
            'contract_relevant': bool(scope_tags and any(tag in scope_tags for tag in ('schema', 'storage', 'routing', 'id'))),
            'objective': re.sub(r'\s+', ' ', content[:260]).strip(),
            'target_files': target_files,
            'primary_files': primary_files,
        })
    return summaries


def build_planning_task_input(raw_task: str, task_spec: dict, qonstrictor_result: dict) -> str:
    if not task_spec:
        return raw_task

    # Use synthesized goal if available
    goal = task_spec.get('clarified_goal') or task_spec.get('goal', '').strip()
    
    # Use clarified task body if available, else raw task
    task_body = task_spec.get('clarified_task_body') or raw_task.strip()

    lines = [
        "# Canonical Qrystalized Task Spec",
        "",
        f"Goal: {goal}",
        f"Readiness: {task_spec.get('status', 'UNKNOWN')}",
        f"Goal Source: {task_spec.get('goal_source', 'raw_task')}",
        f"Clarified Goal Status: {task_spec.get('clarified_goal_status', 'unresolved')}",
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

    effective_constraints = qonstrictor_result.get('effective_constraints', [])
    if effective_constraints:
        lines.append("## Qonstrictor Effective Constraints")
        for item in effective_constraints:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## Task Body (Canonical Intent)",
            task_body,
            "",
        ]
    )
    
    # If we had answers, include them explicitly as well for provenance
    answers = task_spec.get('clarification_answers', [])
    if answers:
        lines.append("## Clarification Answers (Structured)")
        for ans in answers:
            q = ans.get('question', ans.get('question_id', 'Q'))
            a = ans.get('answer', '')
            lines.append(f"- Q: {q}")
            lines.append(f"  A: {a}")
        lines.append("")

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
7. Be terse. Keep summaries short and keep list fields to 1-3 concise items unless the actual briq/build-group count requires more.
8. Do not restate task prose inside the JSON. Prefer compact phrases over sentences when possible.
9. Keep same-file churn low: briqs touching the same large target files should usually map to the same build group/component.

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
        "owned_scopes": ["component-group:string"],
        "owned_files": ["path.ext"]
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
        "primary_files": ["path.ext"],
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
{planning_task_content[:9000]}

Current qodeyard tree:
```
{qodeyard_tree[:2500]}
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
        output_tokens=3200,
    )

    payload = parse_json_payload(response, expected='object')
    if not isinstance(payload, dict):
        raise ValueError('Structured planning response must be a JSON object')
    return payload


def build_fallback_structured_plan(
    goal: str,
    briq_summaries: list[dict],
    qonstrictor_result: dict,
    sensitivity: int,
    min_briqs: int,
    max_briqs: int,
    target_briqs: int,
) -> dict:
    components_map: dict[str, dict] = {}
    build_groups_map: dict[str, dict] = {}
    seen_file_owner: dict[str, str] = {}
    for summary in briq_summaries:
        component_id = summary['component_hint']
        component_title = summary['title'].replace('_', ' ')
        build_group_id = f"bg-{component_id}"
        scope_id = f"scope_build_group_{component_id.replace('-', '_')}"
        target_files = [str(item).strip() for item in (summary.get('target_files') or []) if str(item).strip()]
        explicit_primary = [
            str(item).strip()
            for item in (summary.get('primary_files') or [])
            if str(item).strip()
        ]
        if not explicit_primary and target_files:
            explicit_primary = [target_files[0]]
        primary_files: list[str] = []
        for rel_path in explicit_primary:
            if rel_path not in seen_file_owner:
                seen_file_owner[rel_path] = build_group_id
                primary_files.append(rel_path)
        components_map.setdefault(component_id, {
            'component_id': component_id,
            'title': component_title,
            'summary': f"Component grouped around {component_title}.",
            'owned_scopes': [f"component-group:{component_id}"],
            'dependencies': [],
            'owned_files': [],
        })
        component_entry = components_map[component_id]
        component_entry['owned_files'] = sorted(set(component_entry.get('owned_files', []) + target_files))
        group = build_groups_map.setdefault(build_group_id, {
            'build_group_id': build_group_id,
            'title': component_title,
            'objective': f"Implement and stabilize the {component_title} scope.",
            'scope_id': scope_id,
            'component_refs': [component_id],
            'briq_refs': [],
            'primary_files': [],
            'validation_focus': ['local syntax/import coherence', 'declared scope coherence'],
        })
        group['briq_refs'].append(summary['briq_ref'])
        group['primary_files'] = sorted(set(group.get('primary_files', []) + primary_files))

    components = list(components_map.values())
    build_groups = list(build_groups_map.values())
    effective_constraints = qonstrictor_result.get('effective_constraints', [])
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
            'project_specific_checks': ['Qonfirmer gate for contract-relevant briqs'],
            'build_group_checks': [
                {
                    'build_group_id': group['build_group_id'],
                    'checks': ['files stay within declared scope', 'group briqs produce coherent outputs'],
                }
                for group in build_groups
            ],
            'capability_notes': ['Executed tests are not yet a canonical build-stage guarantee in the current runtime.'],
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
            'mode': os.environ.get('QONQ_SENSITIVITY_MODE', 'manual').strip().lower() or 'manual',
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
    required_files = [str(item).strip() for item in criteria.get('required_files', []) if str(item).strip()]
    if required_files:
        lines.extend(["", "## Required Files"])
        for item in required_files:
            lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)


def derive_file_ownership_map(
    briq_summaries: list[dict],
    blueprint_groups: list[dict],
) -> tuple[list[dict], dict[str, list[str]], dict[str, list[str]]]:
    """
    Derive deterministic file ownership by first mention in briq order.
    Returns:
      - ownership rows
      - primary files per build_group_id
      - all target files per build_group_id
    """
    group_by_ref: dict[str, str] = {}
    for group in blueprint_groups:
        group_id = str(group.get("build_group_id", "")).strip()
        if not group_id:
            continue
        for briq_ref in group.get("briq_refs", []) or []:
            norm = normalize_ref(str(briq_ref))
            if norm:
                group_by_ref[norm] = group_id

    ownership_rows: list[dict] = []
    first_owner: dict[str, str] = {}
    primary_by_group: dict[str, list[str]] = {}
    targets_by_group: dict[str, list[str]] = {}
    default_group = str(blueprint_groups[0].get("build_group_id", "ungrouped")) if blueprint_groups else "ungrouped"

    for summary in briq_summaries:
        briq_ref = str(summary.get("briq_ref", "")).strip()
        target_files = [str(item).strip() for item in (summary.get("target_files") or []) if str(item).strip()]
        explicit_primary = [
            str(item).strip()
            for item in (summary.get("primary_files") or [])
            if str(item).strip()
        ]
        if not explicit_primary and target_files:
            explicit_primary = [target_files[0]]
        if not target_files:
            continue
        group_id = group_by_ref.get(normalize_ref(briq_ref), default_group)
        targets_by_group.setdefault(group_id, [])
        primary_by_group.setdefault(group_id, [])
        for rel_path in target_files:
            if rel_path not in targets_by_group[group_id]:
                targets_by_group[group_id].append(rel_path)
            ownership_rows.append(
                {
                    "path": rel_path,
                    "owner_briq_ref": first_owner.get(rel_path, briq_ref),
                    "group_id": group_id,
                }
            )
        for rel_path in explicit_primary:
            if rel_path not in first_owner:
                first_owner[rel_path] = briq_ref
                primary_by_group[group_id].append(rel_path)

    for key in list(primary_by_group.keys()):
        primary_by_group[key] = sorted(set(primary_by_group[key]))
    for key in list(targets_by_group.keys()):
        targets_by_group[key] = sorted(set(targets_by_group[key]))

    deduped_rows: list[dict] = []
    seen_row: set[tuple[str, str, str]] = set()
    for row in ownership_rows:
        sig = (row["path"], row["owner_briq_ref"], row["group_id"])
        if sig in seen_row:
            continue
        seen_row.add(sig)
        deduped_rows.append(row)
    return deduped_rows, primary_by_group, targets_by_group


def write_planning_artifacts(
    worqspace_root: Path,
    cycle_num: str,
    task_spec: dict,
    qonstrictor_result: dict,
    plan_payload: dict,
    briq_summaries: list[dict],
    required_files: list[str] | None = None,
) -> None:
    planning_dir = worqspace_root / 'planning'
    planning_dir.mkdir(parents=True, exist_ok=True)
    run_id = task_spec.get('run_id', worqspace_root.name) if task_spec else (worqspace_root.name)
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
        'estimated_build_passes': plan_payload.get('estimation_basis', {}).get('estimated_build_passes'),
        'cycle_estimate_mode': os.environ.get('QONQ_CYCLE_ESTIMATE_MODE', 'advisory'),
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
        'qonstrictor_result_ref': 'qontract.d/qonstrictor-result.v1.json' if qonstrictor_result else None,
        **plan_payload.get('validation_plan', {}),
    }
    payload_required_files = [
        str(item).strip()
        for item in (plan_payload.get('completion_criteria', {}).get('required_files', []) or [])
        if str(item).strip()
    ]
    if required_files:
        # Contract/harness-required files are authoritative for this qage.
        # Do not let planner-proposed extras mutate deterministic deliverables.
        merged_required_files = sorted(set(required_files))
    else:
        merged_required_files = sorted(set(payload_required_files))

    completion_criteria = {
        'schema_version': 'completion-criteria.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        'tier': plan_payload.get('estimation_basis', {}).get('auto_repair_budget', {}).get('tier', 'low'),
        **plan_payload.get('completion_criteria', {}),
        'required_files': merged_required_files,
    }
    file_ownership_rows, primary_by_group, targets_by_group = derive_file_ownership_map(
        briq_summaries,
        blueprint.get('build_groups', []),
    )
    enriched_groups = []
    for group in blueprint.get('build_groups', []):
        group_id = str(group.get('build_group_id', 'ungrouped'))
        group_entry = dict(group)
        existing_primary = [str(item).strip() for item in (group_entry.get('primary_files') or []) if str(item).strip()]
        merged_primary = sorted(set(existing_primary + primary_by_group.get(group_id, [])))
        if merged_primary:
            group_entry['primary_files'] = merged_primary
        target_files = targets_by_group.get(group_id, [])
        if target_files:
            group_entry['target_files'] = target_files
        enriched_groups.append(group_entry)
    build_groups = {
        'schema_version': 'build-groups.v1',
        'run_id': run_id,
        'cycle': int(cycle_num),
        'items': enriched_groups,
        'briq_inventory': briq_summaries,
        'estimation_basis': plan_payload.get('estimation_basis', {}),
        'estimated_build_passes': plan_payload.get('estimation_basis', {}).get('estimated_build_passes'),
        'file_ownership': file_ownership_rows,
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
    Higher number = more briqs, but on a bounded practical scale.
    """
    level = clamp_sensitivity(level)
    min_b, max_b, target_b = BRIQ_RANGES.get(level, BRIQ_RANGES[5])

    prompts = {
        0: f"**MANDATORY BRIQ COUNT: EXACTLY 1 BRIQ.** Keep the whole job monolithic unless absolutely impossible.",
        1: f"**MANDATORY BRIQ COUNT: EXACTLY {target_b} BRIQS.** Keep the split tiny and pragmatic.",
        2: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use very broad briqs covering the major chunks only.",
        3: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use broad briqs, usually one briq per major feature cluster.",
        4: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use feature-level briqs with clear boundaries.",
        5: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use a balanced split. This is a strong default for beefier tasks.",
        6: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use detailed decomposition while keeping related files grouped.",
        7: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use high granularity across distinct scopes and subsystems.",
        8: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use very high granularity. Split dense implementation areas further.",
        9: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use atomic-ish decomposition. Separate risky or validation-heavy work.",
        10: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use ultra decomposition for large project slices.",
        11: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use mega decomposition across many moving parts.",
        12: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use hyper decomposition for huge specs and repository-scale work.",
        13: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use extreme decomposition across layered systems.",
        14: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use maximum decomposition for enterprise-scale plans.",
        15: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** Use insane decomposition only when the task is truly massive.",
        16: f"**MANDATORY BRIQ COUNT: {min_b}-{max_b} BRIQS (target: {target_b}).** QONQRETE MAX. Reserve this for monster specifications.",
    }

    prompt = prompts.get(level, prompts[5])
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
        blueprint_response = lib_ai.run_ai_completion(
            ai_provider,
            ai_model,
            blueprint_prompt,
            context_files=[],
            prompt_sections=[{
                'label': 'blueprint_prompt',
                'content': blueprint_prompt,
                'required': True,
                'loss_policy': 'chunkable',
                'section_type': 'planning',
            }],
            agent_name='instruqtor',
            task_type='planning',
            output_tokens=2200,
        )
    except Exception as e:
        print(f"  ⚠️  [BLUEPRINT] AI call failed: {e}. Falling back to single-shot.", flush=True)
        return []  # Signal to fallback
    
    # Parse JSON blueprint
    try:
        # Extract JSON from response (may have markdown fences)
        blueprint = parse_json_payload(blueprint_response, expected='array')
        
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
            fabrication_response = lib_ai.run_ai_completion(
                ai_provider,
                ai_model,
                fabrication_prompt,
                context_files=[],
                prompt_sections=[{
                    'label': f'fabrication_prompt_batch_{batch_idx + 1}',
                    'content': fabrication_prompt,
                    'required': True,
                    'loss_policy': 'chunkable',
                    'section_type': 'planning',
                }],
                agent_name='instruqtor',
                task_type='planning',
                output_tokens=8000,
            )
            
            # Parse XML briqs from response
            batch_briqs = parse_xml_briqs(fabrication_response)
            
            if not batch_briqs:
                print(f"  ⚠️  [Batch {batch_idx + 1}] No briqs parsed, retrying...", flush=True)
                # Retry once
                fabrication_response = lib_ai.run_ai_completion(
                    ai_provider,
                    ai_model,
                    fabrication_prompt,
                    context_files=[],
                    prompt_sections=[{
                        'label': f'fabrication_prompt_batch_{batch_idx + 1}_retry',
                        'content': fabrication_prompt,
                        'required': True,
                        'loss_policy': 'chunkable',
                        'section_type': 'planning',
                    }],
                    agent_name='instruqtor',
                    task_type='planning',
                    output_tokens=8000,
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
    max_retries: int = 1
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
    qonstrictor_result = load_optional_json(worqspace_root / 'qontract.d' / 'qonstrictor-result.v1.json')

    print(f"--- Analyzing: {input_file.name} ---", flush=True)
    with open(input_file, 'r', encoding='utf-8') as f: task_content = clean_input_content(f.read())
    planning_task_content = build_planning_task_input(task_content, task_spec, qonstrictor_result)
    task_required_files = extract_required_files_from_task(planning_task_content)
    harness_required_files: list[str] = []

    os.makedirs(output_dir, exist_ok=True)

    config_path = worqspace_root / "config.yaml"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        config = {}

    agent_cfg = config.get('agents', {}).get('instruqtor', {})
    ai_provider, ai_model = resolve_agent_ai_params(config, 'instruqtor', 'venice', 'deepseek-v3.2')
    print(f"  [AI] instruqtor provider={ai_provider} model={ai_model}", flush=True)
    
    # v1.0.3: Load batched generation config
    batch_mode = agent_cfg.get('batch_mode', True)
    batch_size = agent_cfg.get('batch_size', 5)

    requested_mode = os.environ.get('QONQ_SENSITIVITY_MODE', 'manual').strip().lower()
    auto_requested = os.environ.get('QONQ_AUTO_BRIQ_SENS', '').strip().lower() in ('1', 'true', 'yes', 'on')
    manual_sensitivity_raw = os.environ.get('QONQ_SENSITIVITY', '5')

    try:
        manual_sensitivity = clamp_sensitivity(int(manual_sensitivity_raw))
    except Exception:
        manual_sensitivity = 5

    sensitivity_source = 'auto' if (auto_requested or requested_mode == 'auto') else 'manual'
    sensitivity = manual_sensitivity
    auto_sensitivity_details = None

    min_briqs, max_briqs, target_briqs, _ = get_sensitivity_config(sensitivity)
    strategy = 'Single-shot'

    if task_spec:
        print(f"  [INPUT] Canonical Task Spec: {task_spec.get('status', 'UNKNOWN')} ({task_spec.get('task_spec_id', 'n/a')})", flush=True)
    if qonstrictor_result:
        print(f"  [INPUT] Qonstrictor Result: {qonstrictor_result.get('status', 'UNKNOWN')}", flush=True)
        if qonstrictor_result.get('status') == 'FAIL':
            print("  [FAIL-FAST] Qonstrictor blocked planning. Review qontract.d/qonstrictor-result.v1.json.", flush=True)
            sys.exit(1)

    # Gather Qodeyard Context
    qodeyard_path = Path(os.environ.get('QONQ_WORKSPACE', '/qonq')) / 'qodeyard'
    qodeyard_tree = ""
    qodeyard_file_count = 0

    # v1.3.10: Import path hygiene for infra-dir filtering. This prevents
    # the qodeyard tree shown to the AI from including build/, attempts/,
    # validation-root/, reqap.d/, .qonqrete/ or any other qonqrete-internal
    # artifact dirs. Prior versions walked blindly and showed the AI a
    # polluted tree which it then planned briqs against via the
    # "qodeyard is your source of truth" universal_file_rule — causing
    # self-amplifying nesting like qodeyard/<name>/build/attempts/...
    try:
        from path_hygiene import INFRA_DIR_NAMES as _INFRA
    except ImportError:
        _INFRA = frozenset({
            "build", "attempts", "validation-root", "recovery", "staging",
            "reqap.d", ".qonqrete", "qonstructions", "sqrapyard", "struqture",
            "exeq.d", "qontext.d", "bloq.d", "tasq.d", "briq.d", "qontract.d",
            "qache.d", "planning", "__pycache__", ".git", ".venv", "venv",
            "node_modules", "__MACOSX",
        })

    def _is_infra_dir(p: Path) -> bool:
        name = p.name
        if name in _INFRA:
            return True
        # qage_<timestamp> directories are transient state, never source
        if name.startswith("qage_"):
            return True
        return False

    if qodeyard_path.exists() and any(qodeyard_path.iterdir()):
        tree_lines = []
        tree_lines.append(f"{qodeyard_path.name}/")
        
        def build_tree(dir_path: Path, prefix: str):
            nonlocal qodeyard_file_count
            # v1.3.10: filter infra dirs + skip symlinks (avoid bind-mount loops)
            all_items = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name))
            items = [
                p for p in all_items
                if not p.is_symlink() and not (p.is_dir() and _is_infra_dir(p))
            ]
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

    # Resolve auto briq sensitivity only after repository context is known.
    if sensitivity_source == 'auto':
        sensitivity, auto_sensitivity_details = estimate_auto_sensitivity(
            ai_provider=ai_provider,
            ai_model=ai_model,
            task_content=planning_task_content,
            qodeyard_tree=qodeyard_tree,
            qodeyard_file_count=qodeyard_file_count,
        )
        sensitivity = clamp_sensitivity(sensitivity)
        min_briqs, max_briqs, target_briqs, _ = get_sensitivity_config(sensitivity)
        strategy = 'Single-shot'

    if sensitivity_source == 'auto':
        heuristics = (auto_sensitivity_details or {}).get('heuristics', {})
        print(f"  [AUTO] Sensitivity: {sensitivity} → Target: {target_briqs} briqs (range: {min_briqs}-{max_briqs})", flush=True)
        print(
            f"  [AUTO] Complexity score: {heuristics.get('score', '?')} | "
            f"files: {heuristics.get('file_mentions', '?')} | "
            f"lines: {heuristics.get('lines', '?')} | "
            f"keywords: {', '.join(heuristics.get('matched_keywords', [])[:6]) or 'none'}",
            flush=True,
        )
        for rationale in (auto_sensitivity_details or {}).get('ai_rationale', [])[:3]:
            print(f"  [AUTO] {rationale}", flush=True)
    else:
        print(f"  [CONFIG] Sensitivity: {sensitivity} → Target: {target_briqs} briqs (range: {min_briqs}-{max_briqs})", flush=True)

    print(f"  [CONFIG] Strategy: {strategy} (batch_size: {batch_size}, batch_mode: {batch_mode})", flush=True)

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

This rule applies to all global iterations and build passes. The qodeyard is your source of truth.

━━━ 🚫 HARD PROHIBITIONS (v1.3.10) ━━━
The qodeyard is the PROJECT ROOT. Files live directly in it, NOT in a subfolder
named after the project, run, or qonstruction. Absolutely NEVER:

  ❌ Create briqs that place files inside a subdirectory matching the project
     name / qonstruction name / run name (e.g. `test-small/main.py`,
     `my-api/src/server.py`). Files go DIRECTLY in qodeyard (`main.py`,
     `src/server.py`).
  ❌ Create briqs that write to, modify, or reference any of these INTERNAL
     qonqrete infrastructure directories. They are NOT user code, they are
     runtime artifacts and must never appear in a briq path:
        build/   attempts/   validation-root/   recovery/   staging/
        reqap.d/   .qonqrete/   qonstructions/   struqture/
        exeq.d/   qontext.d/   bloq.d/   tasq.d/   briq.d/   qontract.d/
        qache.d/   planning/   qage_*/
  ❌ Create briqs that modify qonqrete artifact files (names ending in
     _qonfirmer.json, _qonfirmer.md, _reqap.md, _verification.md,
     _smoketest.md, _smoketest.v1.json, attempt-manifest.v1.json,
     run-manifest.v1.json, recovery-metadata.v1.json).

If you see any of those paths in the file tree below, IGNORE them — they are
transient runtime state, not part of the codebase. Plan briqs only against
genuine source files (*.py, *.js, *.ts, *.html, *.css, *.sh, README, configs,
tests, etc.) at qodeyard root or in conventional source dirs (src/, lib/,
tests/, app/, etc.).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    # Context awareness message
    if qodeyard_file_count > 0:
        context_msg = f"\n📊 QODEYARD STATUS: {qodeyard_file_count} files exist. Build on this foundation.\n"
    else:
        context_msg = "\n📊 QODEYARD STATUS: Empty. This is the first build pass - build from scratch.\n"

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
6.  **MINIMIZE SAME-FILE CHURN:** For large files, assign one primary briq owner and avoid repeated full-file rewrites across many briqs.
7.  **FASTAPI MODELS & IDs:** For POST/PUT endpoints, you MUST use a separate Pydantic model (e.g. `UserCreate`) that DOES NOT include the `id` field. The `id` field MUST be auto-assigned by the server (e.g. using a global counter or `len(users)+1`). Absolutely NEVER require the client to send an `id` in a creation request, as this will cause validation failures (422) during automated probing.

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

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW v1.4: HARNESS GENERATION (Before briqs)
    # ═══════════════════════════════════════════════════════════════════════════
    import contract_harness
    harness_class = contract_harness.detect_harness_class(planning_task_content)
    if harness_class:
        print(f"  📜 [HARNESS] Detected authoritative harness: {harness_class}", flush=True)
        harness = contract_harness.build_harness(
            planning_task_content,
            worqspace_root=worqspace_root,
        )
        contract_harness.write_harness(worqspace_root, harness)
        harness_required_files = [
            str(item).strip()
            for item in (
                (harness.get("file_rules", {}) or {}).get("required_files", [])
                if isinstance(harness.get("file_rules", {}), dict)
                else []
            )
            if str(item).strip()
        ]
        if harness_required_files:
            # Contract-derived required files are authoritative for this qage.
            # This prevents legacy/fallback mention parsing from leaking unrelated
            # files into completion criteria or repair targeting.
            task_required_files = sorted(set(harness_required_files))
        # Add compact harness summary to planner_prompt
        if harness_required_files:
            planner_prompt += (
                "\n\n**AUTHORITATIVE HARNESS:**\n"
                "You MUST ensure these required files are built: "
                + ", ".join(harness_required_files)
                + "\n"
            )

    print("Splitting briqs", flush=True)
    # v1.0.3: Generate briqs using single-shot enforcement
    briqs = generate_briqs_with_enforcement(
        ai_provider=ai_provider,
        ai_model=ai_model,
        base_prompt=planner_prompt,
        sensitivity=sensitivity,
        task_content=planning_task_content,
        qodeyard_tree=qodeyard_tree
    )
    print(f"--- Generated {len(briqs)} Build Phases (Sens:{sensitivity}, Range:{min_briqs}-{max_briqs}) ---", flush=True)
    for i, item in enumerate(briqs):
        step_slug = clean_filename_slug(item['title'])
        filename = f"cyqle{cycle_num}_tasq1_briq{i:03d}_{step_slug}.md"
        print(f"- Briq: {filename}", flush=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # v1.3.0: QONTRACT GENERATION (Cycle 1 only)
    # ═══════════════════════════════════════════════════════════════════════════
    qontract_dir = worqspace_root / 'qontract.d'
    contract = {}

    build_pass_index = os.environ.get('QONQ_BUILD_PASS_INDEX', cycle_num)
    if build_pass_index == '1' and os.environ.get('QONQ_PASS_KIND', 'build') == 'build':
        print(f"\n  📜 [QONTRACT] Generating project constitution from first-build-pass tasq...", flush=True)
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
    print("Planning build groups", flush=True)
    force_structured = os.environ.get("QONQ_FORCE_STRUCTURED_PLAN", "").strip().lower() in {"1", "true", "yes", "on"}
    use_deterministic_structured_plan = (
        not force_structured
        and len(briq_summaries) <= 8
        and len(planning_task_content) <= 18000
    )
    if use_deterministic_structured_plan:
        print("  [PLAN] Fast-path: using deterministic grouped plan for small scoped task.", flush=True)
        plan_payload = build_fallback_structured_plan(
            goal=extract_goal_text(task_spec, planning_task_content),
            briq_summaries=briq_summaries,
            qonstrictor_result=qonstrictor_result,
            sensitivity=sensitivity,
            min_briqs=min_briqs,
            max_briqs=max_briqs,
            target_briqs=target_briqs,
        )
    else:
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
                goal=extract_goal_text(task_spec, planning_task_content),
                briq_summaries=briq_summaries,
                qonstrictor_result=qonstrictor_result,
                sensitivity=sensitivity,
                min_briqs=min_briqs,
                max_briqs=max_briqs,
                target_briqs=target_briqs,
            )

    auto_repair_budget = compute_auto_repair_budget(
        config=config,
        plan_payload=plan_payload,
        sensitivity=sensitivity,
        required_files=task_required_files,
    )
    if auto_repair_budget.get("enabled", True):
        plan_payload.setdefault('estimation_basis', {})
        plan_payload['estimation_basis']['auto_repair_budget'] = auto_repair_budget
        print(
            "  [AUTO] Repair budget recommendation "
            f"(tier={auto_repair_budget.get('tier')}): "
            f"retry={auto_repair_budget.get('retry_max_attempts')}, "
            f"repair/build={auto_repair_budget.get('repair_max_attempts_per_build_pass')}",
            flush=True,
        )

    # v1.3.13: Six-Shooter Qontract support
    if build_pass_index == '1' and os.environ.get('QONQ_PASS_KIND', 'build') == 'build':
        print(f"  🔫 [SIX-SHOOTER] Instantiating scale-gated Qontract docs...", flush=True)
        complexity_result = analyze_task_complexity(planning_task_content, qodeyard_file_count)
        selected_ids = select_six_shooter_docs(sensitivity)
        generated_docs = generate_six_shooter_docs(worqspace_root, selected_ids, planning_task_content, contract, complexity_result)
        manifest_path = write_six_shooter_manifest(worqspace_root, generated_docs, sensitivity, complexity_result, auto_repair_budget)
        print(f"  🔫 [SIX-SHOOTER] Selected {len(generated_docs)} docs: {', '.join(selected_ids)}", flush=True)

    write_planning_artifacts(
        worqspace_root=worqspace_root,
        cycle_num=cycle_num,
        task_spec=task_spec,
        qonstrictor_result=qonstrictor_result,
        plan_payload=plan_payload,
        briq_summaries=briq_summaries,
        required_files=task_required_files,
    )
    print("Wrote execution blueprint", flush=True)
    briq_assignments = assign_briqs_to_groups(briq_summaries, plan_payload)
    first_owner_by_file: dict[str, str] = {}
    primary_by_briq_ref: dict[str, list[str]] = {}
    for summary in briq_summaries:
        briq_ref = str(summary.get('briq_ref', '')).strip()
        targets = [str(item).strip() for item in (summary.get('target_files') or []) if str(item).strip()]
        explicit_primary = [
            str(item).strip()
            for item in (summary.get('primary_files') or [])
            if str(item).strip()
        ]
        if not explicit_primary and targets:
            explicit_primary = [targets[0]]
        primary: list[str] = []
        for rel_path in explicit_primary:
            if rel_path not in first_owner_by_file:
                first_owner_by_file[rel_path] = briq_ref
                primary.append(rel_path)
        primary_by_briq_ref[briq_ref] = sorted(set(primary))
    build_groups = plan_payload.get('execution_blueprint', {}).get('build_groups', [])
    print(f"Generated {len(build_groups)} Build groups", flush=True)
    for group in build_groups:
        group_id = group.get('build_group_id', 'ungrouped')
        group_title = group.get('title', group_id)
        print(f"- Build group: {group_id} — {group_title}", flush=True)
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
        target_files = extract_target_files_from_briq(briq_content)
        primary_deliverables = primary_by_briq_ref.get(briq_ref, [])

        # v1.3.0: Inject relevant invariants based on scope tags + add Contract-Relevant header
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
                print(f"- Wrote [Plan] {filename}", flush=True)
                print(f"- Scope: {', '.join(scope_tags)}, contract-relevant: {contract_relevant}", flush=True)
            else:
                print(f"- Wrote [Plan] {filename}", flush=True)
                print("- Scope: none, contract-relevant: False", flush=True)
        else:
            print(f"- Wrote [Plan] {filename}", flush=True)
            print(f"- Scope: {', ' .join(metadata_scope_tags) if metadata_scope_tags else 'none'}, contract-relevant: {contract_relevant}", flush=True)
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
        if target_files:
            grouped_scope_section += f"- Target Files: {', '.join(target_files)}\n"
        if primary_deliverables:
            grouped_scope_section += f"- Primary Deliverables: {', '.join(primary_deliverables)}\n"
        briq_content = briq_content + grouped_scope_section

        # v1.3.0: Build briq with frontmatter including scope + contract relevance
        scope_str = ', '.join(scope_tags) if scope_tags else 'none'
        frontmatter = (
            f"Scope: {scope_str}\n"
            f"Contract-Relevant: {'yes' if contract_relevant else 'no'}\n"
            f"Briq-Ref: {briq_ref}\n"
            f"Build-Group: {build_group_id}\n"
            f"Scope-ID: {scope_id}\n"
            f"Component-ID: {component_id}\n"
            f"Component-Title: {component_title}\n"
            f"Target-Files: {', '.join(target_files) if target_files else 'none'}\n"
            f"Primary-Deliverables: {', '.join(primary_deliverables) if primary_deliverables else 'none'}\n\n"
        )

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{frontmatter}# {item['title']} [Est: {briq_tokens:,} toks | {format_cost(briq_cost)}]\n\n**ARCHITECT'S INSTRUCTION:**\n{briq_content}")
        print(f"Wrote briq {filename}", flush=True)
        print(f"    ↳ Grouped Scope: {build_group_id} | Component: {component_id} | Scope: {scope_id}", flush=True)


if __name__ == '__main__':
    main()
