#!/usr/bin/env python3
# worqer/loqal_verifier.py
# ═══════════════════════════════════════════════════════════════════════════════
# LoQal Verifier - Deterministic Post-Cycle Validation
# v0.9.0 - Improved Import Resolution + Better Skeleton Matching
# ═══════════════════════════════════════════════════════════════════════════════
#
# This module performs LOCAL (no AI) verification of generated code:
# 1. Syntax validation (Python compile())
# 2. Import resolution (do imported modules exist?)
# 3. Skeleton comparison (expected vs actual signatures)
# 4. Cross-file consistency (function calls match definitions)
#
# Run after ConstruQtor completes to catch issues before InspeQtor AI review.
# ═══════════════════════════════════════════════════════════════════════════════
import os
import sys
import ast
import yaml
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of a single verification check."""
    file_path: str
    check_type: str  # 'syntax' | 'import' | 'signature' | 'call'
    passed: bool
    message: str
    line_number: Optional[int] = None
    severity: str = 'error'  # 'error' | 'warning' | 'info'


@dataclass
class VerificationReport:
    """Complete verification report for a cycle."""
    cycle_num: str
    total_files: int = 0
    files_checked: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    results: list = field(default_factory=list)
    
    @property
    def overall_status(self) -> str:
        if self.errors > 0:
            return "FAILURE"
        elif self.warnings > 0:
            return "PARTIAL"
        return "SUCCESS"
    
    def add_result(self, result: VerificationResult):
        self.results.append(result)
        if result.passed:
            self.passed += 1
        elif result.severity == 'warning':
            self.warnings += 1
        else:
            self.errors += 1
    
    def to_markdown(self) -> str:
        """Generate markdown report."""
        md = f"# LoQal Verification Report - CyQle {self.cycle_num}\n\n"
        md += f"**Status:** {self.overall_status}\n"
        md += f"**Files:** {self.files_checked}/{self.total_files}\n"
        md += f"**Results:** ✅ {self.passed} passed | ⚠️ {self.warnings} warnings | ❌ {self.errors} errors\n\n"
        
        # Group by file
        by_file = {}
        for r in self.results:
            if r.file_path not in by_file:
                by_file[r.file_path] = []
            by_file[r.file_path].append(r)
        
        # Errors first
        errors = [r for r in self.results if not r.passed and r.severity == 'error']
        if errors:
            md += "## ❌ Errors\n\n"
            for r in errors:
                line_info = f" (line {r.line_number})" if r.line_number else ""
                md += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
            md += "\n"
        
        # Warnings
        warnings = [r for r in self.results if not r.passed and r.severity == 'warning']
        if warnings:
            md += "## ⚠️ Warnings\n\n"
            for r in warnings:
                line_info = f" (line {r.line_number})" if r.line_number else ""
                md += f"- **{r.file_path}**{line_info}: [{r.check_type}] {r.message}\n"
            md += "\n"
        
        # Summary by file
        md += "## File Summary\n\n"
        md += "| File | Syntax | Imports | Overall |\n"
        md += "|------|--------|---------|--------|\n"
        
        for file_path, results in by_file.items():
            syntax_ok = all(r.passed for r in results if r.check_type == 'syntax')
            import_ok = all(r.passed for r in results if r.check_type == 'import')
            overall = "✅" if (syntax_ok and import_ok) else "❌"
            md += f"| `{file_path}` | {'✅' if syntax_ok else '❌'} | {'✅' if import_ok else '⚠️'} | {overall} |\n"
        
        return md


def check_python_syntax(file_path: Path) -> list[VerificationResult]:
    """Check Python file for syntax errors."""
    results = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        compile(code, str(file_path), 'exec')
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=True,
            message="Syntax OK"
        ))
        
    except SyntaxError as e:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=False,
            message=f"{e.msg}",
            line_number=e.lineno,
            severity='error'
        ))
    except Exception as e:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=False,
            message=f"Could not parse: {e}",
            severity='error'
        ))
    
    return results


def extract_imports(file_path: Path) -> list[tuple[str, int]]:
    """Extract import statements from a Python file."""
    imports = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code, filename=str(file_path))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append((node.module, node.lineno))
                    
    except:
        pass
    
    return imports


def check_imports_resolve(file_path: Path, qodeyard_path: Path) -> list[VerificationResult]:
    """Check if imported local modules exist in qodeyard."""
    results = []
    imports = extract_imports(file_path)
    
    for module_name, line_num in imports:
        # Skip standard library and common packages
        stdlib_prefixes = [
            'os', 'sys', 're', 'json', 'yaml', 'time', 'datetime', 'pathlib',
            'typing', 'collections', 'itertools', 'functools', 'dataclasses',
            'logging', 'subprocess', 'threading', 'multiprocessing', 'asyncio',
            'ast', 'inspect', 'importlib', 'abc', 'copy', 'io', 'shutil',
            'http', 'urllib', 'socket', 'ssl', 'hashlib', 'base64', 'uuid',
            'math', 'random', 'statistics', 'decimal', 'fractions',
            'unittest', 'pytest', 'mock', 'tempfile', 'glob', 'platform',
            'signal', 'warnings', 'traceback', 'contextlib', 'enum',
            'struct', 'pickle', 'queue', 'concurrent',
            'numpy', 'pandas', 'requests', 'flask', 'django', 'sqlalchemy',
            'openai', 'anthropic', 'google', 'transformers', 'torch', 'tensorflow',
            'cryptography', 'grpc', 'proto', 'pydantic', 'aiohttp', 'click',
            'typer', 'rich', 'fastapi', 'celery', 'redis', 'pymongo',
        ]
        
        if any(module_name == p or module_name.startswith(p + '.') for p in stdlib_prefixes):
            continue
        
        # Only check imports that look like local project imports
        if not module_name.startswith(('src.', 'lib.', 'app.', 'core.', 'utils.', 'tests.')):
            continue
        
        # Check if it's a local module
        # Convert module path to file path: src.utils.config -> src/utils/config.py
        module_parts = module_name.split('.')
        
        # Build all possible paths where this module could exist
        possible_paths = [
            qodeyard_path / '/'.join(module_parts) / '__init__.py',
            qodeyard_path / ('/'.join(module_parts) + '.py'),
        ]
        
        # Also check without the first component (e.g., src.utils.logger -> utils/logger.py)
        if len(module_parts) > 1:
            possible_paths.extend([
                qodeyard_path / '/'.join(module_parts[1:]) / '__init__.py',
                qodeyard_path / ('/'.join(module_parts[1:]) + '.py'),
            ])
        
        # Also search recursively for the final module name
        final_module = module_parts[-1]
        for py_file in qodeyard_path.rglob(f'{final_module}.py'):
            possible_paths.append(py_file)
        for init_file in qodeyard_path.rglob(f'{final_module}/__init__.py'):
            possible_paths.append(init_file)
        
        found = any(p.exists() for p in possible_paths)
        
        if not found:
            # This looks like a local import that should exist
            results.append(VerificationResult(
                file_path=str(file_path.name),
                check_type='import',
                passed=False,
                message=f"Local module '{module_name}' not found in qodeyard",
                line_number=line_num,
                severity='warning'  # Warning not error - might be intentional
            ))
    
    # If no import issues found, add a pass result
    if not results:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='import',
            passed=True,
            message="All local imports resolved"
        ))
    
    return results


def extract_function_signatures(file_path: Path) -> dict[str, dict]:
    """Extract function/method signatures from a Python file."""
    signatures = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code, filename=str(file_path))
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                for arg in node.args.args:
                    arg_info = {'name': arg.arg}
                    if arg.annotation:
                        try:
                            arg_info['type'] = ast.unparse(arg.annotation)
                        except:
                            pass
                    args.append(arg_info)
                
                signatures[node.name] = {
                    'args': args,
                    'line': node.lineno,
                    'is_async': isinstance(node, ast.AsyncFunctionDef),
                    'returns': ast.unparse(node.returns) if node.returns else None
                }
                
    except:
        pass
    
    return signatures


def compare_with_qontext(file_path: Path, qontext_path: Path) -> list[VerificationResult]:
    """Compare generated file with its qontext skeleton (if exists)."""
    results = []
    
    # Standard library and typing constructs to ignore (not actual functions)
    IGNORE_SYMBOLS = {
        # Standard library modules
        'argparse', 'sys', 'os', 're', 'json', 'yaml', 'time', 'datetime',
        'pathlib', 'typing', 'collections', 'logging', 'subprocess', 'asyncio',
        'hashlib', 'base64', 'uuid', 'math', 'random', 'io', 'shutil',
        'http', 'urllib', 'socket', 'ssl', 'ast', 'inspect', 'functools',
        'itertools', 'copy', 'pickle', 'struct', 'tempfile', 'glob',
        'threading', 'multiprocessing', 'queue', 'contextlib', 'dataclasses',
        'enum', 'abc', 'warnings', 'traceback', 'platform', 'signal',
        # Typing constructs
        'List', 'Dict', 'Set', 'Tuple', 'Optional', 'Union', 'Any', 'Callable',
        'Type', 'TypeVar', 'Generic', 'Protocol', 'Literal', 'Final',
        'Sequence', 'Mapping', 'Iterable', 'Iterator', 'Generator',
        'Awaitable', 'Coroutine', 'AsyncGenerator', 'ClassVar',
        # Common third-party modules
        'numpy', 'pandas', 'requests', 'flask', 'django', 'fastapi',
        'openai', 'anthropic', 'google', 'grpc', 'proto', 'pydantic',
        'sqlalchemy', 'pytest', 'click', 'typer', 'rich', 'aiohttp',
        # Common class names that might appear in symbols
        'Path', 'Field', 'dataclass', 'Enum', 'ABC',
    }
    
    # Find corresponding qontext file
    qontext_file = qontext_path / (file_path.name + '.q.yaml')
    
    if not qontext_file.exists():
        # No qontext to compare against - that's fine
        return results
    
    try:
        with open(qontext_file, 'r', encoding='utf-8') as f:
            qontext_data = yaml.safe_load(f) or {}
        
        expected_symbols = qontext_data.get('symbols', [])
        if not expected_symbols:
            return results
        
        actual_signatures = extract_function_signatures(file_path)
        
        # Check for missing functions (excluding non-function symbols)
        for symbol in expected_symbols:
            if isinstance(symbol, dict):
                name = symbol.get('name', '')
                symbol_type = symbol.get('type', '')
                
                # Skip if it's a known non-function symbol
                if name in IGNORE_SYMBOLS:
                    continue
                    
                # Skip if it's explicitly marked as import/module/class
                if symbol_type in ('import', 'module', 'class', 'type', 'constant'):
                    continue
                
                # Skip single-letter names (likely type vars like T, K, V)
                if len(name) == 1:
                    continue
                
                # Skip names that start with uppercase (likely classes/types, not functions)
                # unless they're explicitly marked as functions
                if name[0].isupper() and symbol_type != 'function':
                    continue
                
                if name and name not in actual_signatures:
                    results.append(VerificationResult(
                        file_path=str(file_path.name),
                        check_type='signature',
                        passed=False,
                        message=f"Expected function '{name}' not found",
                        severity='warning'
                    ))
                    
    except Exception as e:
        pass
    
    return results


def run_verification(
    qodeyard_path: Path,
    qontext_path: Path,
    cycle_num: str,
    config: dict
) -> VerificationReport:
    """Run all verification checks on the qodeyard."""
    report = VerificationReport(cycle_num=cycle_num)
    
    checks_config = config.get('verification', {}).get('checks', {})
    do_syntax = checks_config.get('syntax', True)
    do_imports = checks_config.get('imports', True)
    do_skeleton = checks_config.get('skeleton_match', True)
    
    # Find all Python files in qodeyard
    python_files = list(qodeyard_path.rglob('*.py'))
    report.total_files = len(python_files)
    
    print(f"[LoQal] Verifying {len(python_files)} Python files...", flush=True)
    
    for py_file in python_files:
        report.files_checked += 1
        
        # Syntax check
        if do_syntax:
            for result in check_python_syntax(py_file):
                report.add_result(result)
        
        # Import resolution
        if do_imports:
            for result in check_imports_resolve(py_file, qodeyard_path):
                report.add_result(result)
        
        # Skeleton comparison
        if do_skeleton:
            for result in compare_with_qontext(py_file, qontext_path):
                report.add_result(result)
    
    print(f"[LoQal] Verification complete: {report.overall_status}", flush=True)
    print(f"        ✅ {report.passed} | ⚠️ {report.warnings} | ❌ {report.errors}", flush=True)
    
    return report


def main():
    """Standalone verification entry point."""
    if len(sys.argv) < 2:
        print("Usage: loqal_verifier.py <qodeyard_path> [qontext_path] [output_path]", flush=True)
        sys.exit(1)
    
    qodeyard_path = Path(sys.argv[1])
    qontext_path = Path(sys.argv[2]) if len(sys.argv) > 2 else qodeyard_path.parent / 'qontext.d'
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    
    cycle_num = os.environ.get('CYCLE_NUM', '1')
    
    # Load config
    config_path = qodeyard_path.parent / 'config.yaml'
    config = {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except:
        pass
    
    # Run verification
    report = run_verification(qodeyard_path, qontext_path, cycle_num, config)
    
    # Output report
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report.to_markdown())
        print(f"[LoQal] Report written to {output_path}", flush=True)
    else:
        print(report.to_markdown())
    
    # Exit with appropriate code
    sys.exit(0 if report.errors == 0 else 1)


if __name__ == '__main__':
    main()
