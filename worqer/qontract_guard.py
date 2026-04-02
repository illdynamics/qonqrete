#!/usr/bin/env python3
# worqer/qontract_guard.py
# ═══════════════════════════════════════════════════════════════════════════════
# QontractGuard - Deterministic Contract Verification (No LLM)
# v1.2.4-stable - QONTRACT enforcement via Python AST parsing
# ═══════════════════════════════════════════════════════════════════════════════
#
# Verifies generated code against qontract.json invariants:
#   1. Forbidden imports (e.g. uuid)
#   2. Exact schema field sets for named models
#   3. Forbidden field names
#   4. ID type rules (int vs str)
#   5. ID assignment strategy (monotonic int)
#   6. Required endpoints (route paths in decorators)
#
# All checks use Python ast — zero external dependencies.
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import ast
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Violation:
    """A single contract violation."""
    rule: str           # e.g. 'forbidden_import', 'schema_field', 'id_type'
    file_path: str
    line_number: Optional[int]
    message: str
    severity: str = 'error'  # 'error' | 'warning'

    def __str__(self):
        loc = f" (line {self.line_number})" if self.line_number else ""
        return f"[{self.rule}] {self.file_path}{loc}: {self.message}"


@dataclass
class GuardReport:
    """Complete QontractGuard verification report."""
    passed: bool = True
    violations: list = field(default_factory=list)
    files_checked: int = 0
    rules_checked: int = 0

    def add_violation(self, v: Violation):
        self.violations.append(v)
        if v.severity == 'error':
            self.passed = False

    def to_markdown(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        md = f"# QontractGuard Report\n\n"
        md += f"**Status:** {status}\n"
        md += f"**Files checked:** {self.files_checked}\n"
        md += f"**Rules checked:** {self.rules_checked}\n"
        md += f"**Violations:** {len(self.violations)}\n\n"

        if self.violations:
            errors = [v for v in self.violations if v.severity == 'error']
            warnings = [v for v in self.violations if v.severity == 'warning']

            if errors:
                md += "## ❌ Errors\n\n"
                for v in errors:
                    md += f"- {v}\n"
                md += "\n"

            if warnings:
                md += "## ⚠️ Warnings\n\n"
                for v in warnings:
                    md += f"- {v}\n"
                md += "\n"
        else:
            md += "No violations found.\n"

        return md

    def to_json(self) -> dict:
        """Machine-usable JSON representation of guard results."""
        return {
            'status': 'PASS' if self.passed else 'FAIL',
            'files_checked': self.files_checked,
            'rules_checked': self.rules_checked,
            'violations': [
                {
                    'rule_id': v.rule,
                    'file': v.file_path,
                    'line': v.line_number,
                    'message': v.message,
                    'severity': v.severity,
                }
                for v in self.violations
            ]
        }

    def to_text_summary(self) -> str:
        """Short text summary for logs."""
        status = "PASS" if self.passed else "FAIL"
        if not self.violations:
            return f"QontractGuard: {status} — 0 violations in {self.files_checked} files"
        lines = [f"QontractGuard: {status} — {len(self.violations)} violations in {self.files_checked} files"]
        for v in self.violations:
            loc = f" (line {v.line_number})" if v.line_number else ""
            lines.append(f"  [{v.severity.upper()}] {v.file_path}{loc}: {v.message}")
        return "\n".join(lines)

    def get_correction_directive(self, contract: dict = None) -> str:
        """
        Build a strict correction prompt for ConstruQtor auto-retry.
        Includes violation list + relevant contract snippets.
        """
        if not self.violations:
            return ""
        parts = [
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🛡️ QONTRACT GUARD VIOLATIONS — FIX THESE EXACTLY",
            "Do NOT change unrelated code. Only fix the listed violations.",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        ]
        for v in self.violations:
            loc = f" (line {v.line_number})" if v.line_number else ""
            parts.append(f"- [{v.rule}] {v.file_path}{loc}: {v.message}")

        if contract:
            inv = contract.get('invariants', {})
            # Include relevant contract snippets
            relevant = []
            rule_ids = {v.rule for v in self.violations}
            if 'forbidden_import' in rule_ids and inv.get('forbidden_imports'):
                relevant.append(f"Forbidden imports: {', '.join(inv['forbidden_imports'])}")
            if any(r.startswith('schema') for r in rule_ids) and inv.get('schemas'):
                for model, spec in inv['schemas'].items():
                    fields = ', '.join(f"`{f}`" for f in spec.get('fields', {}))
                    exact = " (EXACT)" if spec.get('exact') else ""
                    relevant.append(f"Schema {model}{exact}: {fields}")
            if 'forbidden_field' in rule_ids and inv.get('forbidden_fields'):
                relevant.append(f"Forbidden fields: {', '.join(inv['forbidden_fields'])}")
            if 'id_type' in rule_ids and inv.get('id_type'):
                relevant.append(f"ID type must be: {inv['id_type']}")
            if 'id_assignment' in rule_ids and inv.get('id_strategy'):
                relevant.append(f"ID strategy: {inv['id_strategy']}")
            if 'required_endpoint' in rule_ids and inv.get('required_endpoints'):
                eps = [f"{e['method'].upper()} {e['path']}" for e in inv['required_endpoints']]
                relevant.append(f"Required endpoints: {', '.join(eps)}")
            if relevant:
                parts.append("\nRelevant contract rules:")
                for r in relevant:
                    parts.append(f"  • {r}")

        parts.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_contract(contract_path: Path) -> dict:
    """Load qontract.json and return its contents."""
    if not contract_path.exists():
        return {}
    try:
        with open(contract_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[QontractGuard] ⚠️ Could not load contract: {e}", flush=True)
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# AST-BASED CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def check_forbidden_imports(tree: ast.AST, file_path: str, forbidden: list[str]) -> list[Violation]:
    """Check for forbidden import statements."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split('.')[0]
                if module_root in forbidden:
                    violations.append(Violation(
                        rule='forbidden_import',
                        file_path=file_path,
                        line_number=node.lineno,
                        message=f"Forbidden import '{alias.name}' (contract forbids '{module_root}')"
                    ))
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_root = node.module.split('.')[0]
            if module_root in forbidden:
                violations.append(Violation(
                    rule='forbidden_import',
                    file_path=file_path,
                    line_number=node.lineno,
                    message=f"Forbidden import from '{node.module}' (contract forbids '{module_root}')"
                ))
    return violations


def check_schema_fields(tree: ast.AST, file_path: str, schemas: dict) -> list[Violation]:
    """
    Check that Pydantic/dataclass model fields match contract-specified schemas.

    schemas format: {"ModelName": {"fields": {"field_name": "type_hint", ...}, "exact": true}}
    """
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in schemas:
            continue

        spec = schemas[node.name]
        expected_fields = spec.get('fields', {})
        exact = spec.get('exact', False)

        # Extract actual annotated assignments in the class body
        actual_fields = {}
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                try:
                    type_str = ast.unparse(item.annotation)
                except:
                    type_str = "unknown"
                actual_fields[field_name] = type_str

        # Check for missing required fields
        for field_name, expected_type in expected_fields.items():
            if field_name not in actual_fields:
                violations.append(Violation(
                    rule='schema_missing_field',
                    file_path=file_path,
                    line_number=node.lineno,
                    message=f"Model '{node.name}' missing required field '{field_name}' (expected type: {expected_type})"
                ))
            elif expected_type and expected_type != '*':
                # Type check: normalize and compare
                actual_type = actual_fields[field_name]
                if not _types_compatible(actual_type, expected_type):
                    violations.append(Violation(
                        rule='schema_field_type',
                        file_path=file_path,
                        line_number=node.lineno,
                        message=f"Model '{node.name}' field '{field_name}' has type '{actual_type}', expected '{expected_type}'",
                        severity='warning'
                    ))

        # Check for extra fields if exact mode
        if exact:
            for field_name in actual_fields:
                if field_name not in expected_fields:
                    violations.append(Violation(
                        rule='schema_extra_field',
                        file_path=file_path,
                        line_number=node.lineno,
                        message=f"Model '{node.name}' has unexpected field '{field_name}' (contract specifies exact fields)"
                    ))

    return violations


def _types_compatible(actual: str, expected: str) -> bool:
    """Fuzzy type compatibility check."""
    # Normalize whitespace
    actual_norm = actual.replace(' ', '').lower()
    expected_norm = expected.replace(' ', '').lower()

    if actual_norm == expected_norm:
        return True

    # Optional[X] == X | None == Optional[X]
    if 'optional' in expected_norm:
        inner = expected_norm.replace('optional[', '').rstrip(']')
        if inner in actual_norm:
            return True
    if 'optional' in actual_norm:
        inner = actual_norm.replace('optional[', '').rstrip(']')
        if inner in expected_norm:
            return True

    # int matches int, Optional[int], etc.
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True

    return False


def check_forbidden_fields(tree: ast.AST, file_path: str, forbidden_fields: list[str]) -> list[Violation]:
    """Check that no class has forbidden field names."""
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id in forbidden_fields:
                    violations.append(Violation(
                        rule='forbidden_field',
                        file_path=file_path,
                        line_number=item.lineno,
                        message=f"Forbidden field '{item.target.id}' in class '{node.name}'"
                    ))
    return violations


def check_id_type(tree: ast.AST, file_path: str, id_type: str) -> list[Violation]:
    """
    Check that 'id' fields in model classes use the specified type.

    id_type: "int" or "Optional[int]" etc.
    """
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id == 'id':
                    try:
                        actual_type = ast.unparse(item.annotation)
                    except:
                        actual_type = "unknown"

                    if not _types_compatible(actual_type, id_type):
                        violations.append(Violation(
                            rule='id_type',
                            file_path=file_path,
                            line_number=item.lineno,
                            message=f"Field 'id' in '{node.name}' has type '{actual_type}', contract requires '{id_type}'"
                        ))
    return violations


def check_id_assignment(source: str, file_path: str) -> list[Violation]:
    """
    Check that ID assignment uses monotonic int (next_id counter or max+1 pattern).
    
    Two checks:
    1. Flags if uuid is used for ID generation (always bad when contract forbids it)
    2. Verifies a valid monotonic strategy EXISTS somewhere in the file:
       - next_id initialized to 1 (literal) and incremented
       - id assigned as max(existing_ids)+1 with fallback 1
       - equivalent monotonic counter stored somewhere (module/class)
       Also verifies that assigned id populates a field/key named "id".
    """
    violations = []

    # Check 1: uuid-based ID assignment patterns (always forbidden)
    uuid_patterns = [
        r'uuid\.(uuid[14]|uuid3|uuid5)\(\)',
        r'str\(uuid\.',
        r'uuid\.uuid4\(\)\.hex',
        r'["\']id["\']\s*:\s*str\(uuid',
    ]
    for pattern in uuid_patterns:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            line_num = source[:match.start()].count('\n') + 1
            violations.append(Violation(
                rule='id_assignment',
                file_path=file_path,
                line_number=line_num,
                message="UUID-based ID assignment detected; contract requires monotonic int IDs"
            ))

    # Check 2: Verify a valid monotonic strategy exists via AST
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return violations

    has_id_strategy = False

    # Pattern A: next_id = 1 (module-level or class-level counter initialized to int literal)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = ""
                if isinstance(target, ast.Name):
                    name = target.id
                elif isinstance(target, ast.Attribute):
                    name = target.attr
                if 'next_id' in name.lower() or name.lower() in ('_id_counter', 'id_counter', '_next_id'):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        has_id_strategy = True

    # Pattern B: max(...) + 1 pattern for ID generation
    max_plus_one_patterns = [
        r'max\s*\([^)]*\)\s*\+\s*1',
        r'len\s*\([^)]*\)\s*\+\s*1',
    ]
    for pat in max_plus_one_patterns:
        if re.search(pat, source):
            has_id_strategy = True

    # Pattern C: += 1 on something with 'id' in the name
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            target_name = ""
            if isinstance(node.target, ast.Name):
                target_name = node.target.id
            elif isinstance(node.target, ast.Attribute):
                target_name = node.target.attr
            if 'id' in target_name.lower() or 'counter' in target_name.lower():
                if isinstance(node.value, ast.Constant) and node.value.value == 1:
                    has_id_strategy = True

    # Pattern D: explicit assignment like obj["id"] = <int-expression> or obj.id = <int-expression>
    has_id_population = False
    for node in ast.walk(tree):
        # Dict-style: something["id"] = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.slice, ast.Constant) and target.slice.value == 'id':
                        has_id_population = True
                elif isinstance(target, ast.Attribute) and target.attr == 'id':
                    has_id_population = True

    # Only flag if neither strategy nor population found and file has class/function bodies
    # (skip files that don't deal with ID at all)
    has_id_relevance = ('id' in source.lower() and 
                         any(kw in source for kw in ['class ', 'def ', 'BaseModel']))
    
    if has_id_relevance and not has_id_strategy:
        # Check if file actually assigns IDs (don't flag read-only files)
        assigns_id = bool(re.search(r'["\']id["\']\s*[:=]|\.id\s*=', source))
        if assigns_id:
            violations.append(Violation(
                rule='id_assignment',
                file_path=file_path,
                line_number=None,
                message="No valid monotonic ID strategy found (expected: next_id=1 + increment, or max(ids)+1 pattern)"
            ))

    return violations


def check_required_endpoints(tree: ast.AST, source: str, file_path: str, endpoints: list[dict]) -> list[Violation]:
    """
    Check that required route endpoints exist as decorators.

    endpoints format: [{"method": "get", "path": "/users"}, ...]
    """
    violations = []

    # Extract all route decorators from the file
    found_routes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                route_info = _extract_route_from_decorator(decorator)
                if route_info:
                    found_routes.add(route_info)

    # Also do a regex scan for common patterns the AST might miss
    route_patterns = [
        r'@\w+\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
        r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    ]
    for pattern in route_patterns:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            method = match.group(1).lower()
            path = match.group(2)
            found_routes.add((method, path))

    # Check each required endpoint
    for ep in endpoints:
        method = ep.get('method', '').lower()
        path = ep.get('path', '')
        if not method or not path:
            continue

        if (method, path) not in found_routes:
            violations.append(Violation(
                rule='required_endpoint',
                file_path=file_path,
                line_number=None,
                message=f"Required endpoint '{method.upper()} {path}' not found"
            ))

    return violations


def _extract_route_from_decorator(node) -> Optional[tuple]:
    """Extract (method, path) from a decorator AST node."""
    try:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                method = func.attr.lower()
                if method in ('get', 'post', 'put', 'delete', 'patch', 'options', 'head'):
                    if node.args:
                        arg = node.args[0]
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            return (method, arg.value)
    except:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GUARD RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_guard(contract: dict, code_dir: Path, file_patterns: list[str] = None) -> GuardReport:
    """
    Run all QontractGuard checks against code files.

    Args:
        contract: Parsed qontract.json dict
        code_dir: Directory containing code to check (prefer qodeyard)
        file_patterns: Optional list of glob patterns to check (default: *.py)

    Returns:
        GuardReport with PASS/FAIL and violation details
    """
    report = GuardReport()

    if not contract:
        # B) Never silently skip — treat empty contract as FAIL
        report.add_violation(Violation(
            rule='CONTRACT_MISSING',
            file_path='qontract.json',
            line_number=None,
            message="No contract loaded — cannot enforce invariants. Ensure qontract.d/qontract.json exists."
        ))
        print("[QontractGuard] FAIL — No contract loaded", flush=True)
        return report

    invariants = contract.get('invariants', {})

    # Extract rule sets
    forbidden_imports = invariants.get('forbidden_imports', [])
    schemas = invariants.get('schemas', {})
    forbidden_fields = invariants.get('forbidden_fields', [])
    id_type = invariants.get('id_type', '')
    id_strategy = invariants.get('id_strategy', '')
    required_endpoints = invariants.get('required_endpoints', [])

    # Count active rules
    active_rules = 0
    if forbidden_imports: active_rules += 1
    if schemas: active_rules += 1
    if forbidden_fields: active_rules += 1
    if id_type: active_rules += 1
    if id_strategy: active_rules += 1
    if required_endpoints: active_rules += 1
    report.rules_checked = active_rules

    if active_rules == 0:
        print("[QontractGuard] No invariant rules in contract — nothing to check", flush=True)
        return report

    print(f"[QontractGuard] Running {active_rules} rule checks...", flush=True)

    # Collect Python files
    if file_patterns:
        py_files = []
        for pattern in file_patterns:
            py_files.extend(code_dir.rglob(pattern))
    else:
        py_files = list(code_dir.rglob('*.py'))

    report = _run_checks_on_files(py_files, code_dir, invariants, report)

    status = "PASS ✅" if report.passed else "FAIL ❌"
    print(f"[QontractGuard] {status} — {len(report.violations)} violations in {report.files_checked} files", flush=True)
    return report


def run_guard_for_files(contract: dict, code_dir: Path, file_list: list[str]) -> GuardReport:
    """
    Run QontractGuard on specific files only (for per-briq gating).

    Args:
        contract: Parsed qontract.json dict
        code_dir: Base code directory (qodeyard)
        file_list: List of relative file paths to check

    Returns:
        GuardReport with PASS/FAIL for just these files
    """
    report = GuardReport()

    if not contract:
        return report

    invariants = contract.get('invariants', {})
    if not invariants:
        return report

    # Count active rules
    active_rules = sum(1 for k in ('forbidden_imports', 'schemas', 'forbidden_fields',
                                     'id_type', 'id_strategy', 'required_endpoints')
                       if invariants.get(k))
    report.rules_checked = active_rules

    if active_rules == 0:
        return report

    # Resolve file paths
    py_files = []
    for rel_path in file_list:
        full_path = code_dir / rel_path
        if full_path.exists() and full_path.suffix == '.py':
            py_files.append(full_path)

    if not py_files:
        return report

    report = _run_checks_on_files(py_files, code_dir, invariants, report)
    return report


def _run_checks_on_files(py_files: list, code_dir: Path, invariants: dict, report: GuardReport) -> GuardReport:
    """Internal: Run all invariant checks on a list of Python files."""
    forbidden_imports = invariants.get('forbidden_imports', [])
    schemas = invariants.get('schemas', {})
    forbidden_fields = invariants.get('forbidden_fields', [])
    id_type = invariants.get('id_type', '')
    id_strategy = invariants.get('id_strategy', '')
    required_endpoints = invariants.get('required_endpoints', [])

    for py_file in py_files:
        report.files_checked += 1
        try:
            rel_path = str(py_file.relative_to(code_dir))
        except ValueError:
            rel_path = str(py_file)

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        except Exception:
            continue

        # Run each check
        if forbidden_imports:
            for v in check_forbidden_imports(tree, rel_path, forbidden_imports):
                report.add_violation(v)

        if schemas:
            for v in check_schema_fields(tree, rel_path, schemas):
                report.add_violation(v)

        if forbidden_fields:
            for v in check_forbidden_fields(tree, rel_path, forbidden_fields):
                report.add_violation(v)

        if id_type:
            for v in check_id_type(tree, rel_path, id_type):
                report.add_violation(v)

        if id_strategy and 'monotonic' in id_strategy.lower():
            for v in check_id_assignment(source, rel_path):
                report.add_violation(v)

        if required_endpoints:
            for v in check_required_endpoints(tree, source, rel_path, required_endpoints):
                report.add_violation(v)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Standalone QontractGuard entry point."""
    if len(sys.argv) < 3:
        print("Usage: qontract_guard.py <qontract_json> <code_dir> [output_path]", flush=True)
        sys.exit(1)

    contract_path = Path(sys.argv[1])
    code_dir = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    contract = load_contract(contract_path)
    report = run_guard(contract, code_dir)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report.to_markdown())
        print(f"[QontractGuard] Report written to {output_path}", flush=True)
    else:
        print(report.to_markdown())

    sys.exit(0 if report.passed else 1)


if __name__ == '__main__':
    main()
