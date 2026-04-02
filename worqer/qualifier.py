#!/usr/bin/env python3
# worqer/qualifier.py
# ═══════════════════════════════════════════════════════════════════════════════
# Qualifier Agent - Execution-Validation Gate
# v1.2.2-stable
# ═══════════════════════════════════════════════════════════════════════════════
import ast
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class VerificationResult:
    """Result of a single builtin verification check."""

    file_path: str
    check_type: str  # 'syntax' | 'import' | 'signature'
    passed: bool
    message: str
    line_number: Optional[int] = None
    severity: str = 'error'  # 'error' | 'warning' | 'info'


@dataclass
class VerificationReport:
    """Structured builtin validation report for a cycle."""

    cycle_num: str
    total_files: int = 0
    files_checked: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    results: list[VerificationResult] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if self.errors > 0:
            return "FAILURE"
        if self.warnings > 0:
            return "PARTIAL"
        return "SUCCESS"

    def add_result(self, result: VerificationResult) -> None:
        self.results.append(result)
        if result.passed:
            self.passed += 1
        elif result.severity == 'warning':
            self.warnings += 1
        else:
            self.errors += 1


def load_config(worqspace_root: Path) -> dict:
    config_path = worqspace_root / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_verification_checks(config: dict) -> dict:
    checks = config.get('verification', {}).get('checks', {})
    return {
        'syntax': checks.get('syntax', True),
        'imports': checks.get('imports', True),
        'skeleton_match': checks.get('skeleton_match', True),
    }


def check_python_syntax(file_path: Path) -> list[VerificationResult]:
    """Check Python file for syntax errors."""
    results: list[VerificationResult] = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()

        compile(code, str(file_path), 'exec')
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=True,
            message='Syntax OK',
        ))
    except SyntaxError as e:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=False,
            message=e.msg,
            line_number=e.lineno,
            severity='error',
        ))
    except Exception as e:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='syntax',
            passed=False,
            message=f'Could not parse: {e}',
            severity='error',
        ))

    return results


def extract_imports(file_path: Path) -> list[tuple[str, int]]:
    """Extract import statements from a Python file."""
    imports: list[tuple[str, int]] = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()

        tree = ast.parse(code, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((node.module, node.lineno))
    except Exception:
        pass

    return imports


def check_imports_resolve(file_path: Path, qodeyard_path: Path) -> list[VerificationResult]:
    """Check if imported local modules exist in qodeyard."""
    results: list[VerificationResult] = []
    imports = extract_imports(file_path)

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

    for module_name, line_num in imports:
        if any(module_name == prefix or module_name.startswith(prefix + '.') for prefix in stdlib_prefixes):
            continue

        if not module_name.startswith(('src.', 'lib.', 'app.', 'core.', 'utils.', 'tests.')):
            continue

        module_parts = module_name.split('.')
        possible_paths = [
            qodeyard_path / '/'.join(module_parts) / '__init__.py',
            qodeyard_path / ('/'.join(module_parts) + '.py'),
        ]

        if len(module_parts) > 1:
            possible_paths.extend([
                qodeyard_path / '/'.join(module_parts[1:]) / '__init__.py',
                qodeyard_path / ('/'.join(module_parts[1:]) + '.py'),
            ])

        final_module = module_parts[-1]
        possible_paths.extend(qodeyard_path.rglob(f'{final_module}.py'))
        possible_paths.extend(qodeyard_path.rglob(f'{final_module}/__init__.py'))

        if not any(path.exists() for path in possible_paths):
            results.append(VerificationResult(
                file_path=str(file_path.name),
                check_type='import',
                passed=False,
                message=f"Local module '{module_name}' not found in qodeyard",
                line_number=line_num,
                severity='warning',
            ))

    if not results:
        results.append(VerificationResult(
            file_path=str(file_path.name),
            check_type='import',
            passed=True,
            message='All local imports resolved',
        ))

    return results


def extract_function_signatures(file_path: Path) -> dict[str, dict]:
    """Extract function and method signatures from a Python file."""
    signatures: dict[str, dict] = {}

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
                        except Exception:
                            pass
                    args.append(arg_info)

                signatures[node.name] = {
                    'args': args,
                    'line': node.lineno,
                    'is_async': isinstance(node, ast.AsyncFunctionDef),
                    'returns': ast.unparse(node.returns) if node.returns else None,
                }
    except Exception:
        pass

    return signatures


def compare_with_qontext(file_path: Path, qontext_path: Path) -> list[VerificationResult]:
    """Compare generated file with its qontext skeleton (if present)."""
    results: list[VerificationResult] = []
    ignore_symbols = {
        'argparse', 'sys', 'os', 're', 'json', 'yaml', 'time', 'datetime',
        'pathlib', 'typing', 'collections', 'logging', 'subprocess', 'asyncio',
        'hashlib', 'base64', 'uuid', 'math', 'random', 'io', 'shutil',
        'http', 'urllib', 'socket', 'ssl', 'ast', 'inspect', 'functools',
        'itertools', 'copy', 'pickle', 'struct', 'tempfile', 'glob',
        'threading', 'multiprocessing', 'queue', 'contextlib', 'dataclasses',
        'enum', 'abc', 'warnings', 'traceback', 'platform', 'signal',
        'List', 'Dict', 'Set', 'Tuple', 'Optional', 'Union', 'Any', 'Callable',
        'Type', 'TypeVar', 'Generic', 'Protocol', 'Literal', 'Final',
        'Sequence', 'Mapping', 'Iterable', 'Iterator', 'Generator',
        'Awaitable', 'Coroutine', 'AsyncGenerator', 'ClassVar',
        'numpy', 'pandas', 'requests', 'flask', 'django', 'fastapi',
        'openai', 'anthropic', 'google', 'grpc', 'proto', 'pydantic',
        'sqlalchemy', 'pytest', 'click', 'typer', 'rich', 'aiohttp',
        'Path', 'Field', 'dataclass', 'Enum', 'ABC',
    }

    qontext_file = qontext_path / (file_path.name + '.q.yaml')
    if not qontext_file.exists():
        return results

    try:
        with open(qontext_file, 'r', encoding='utf-8') as f:
            qontext_data = yaml.safe_load(f) or {}

        expected_symbols = qontext_data.get('symbols', [])
        if not expected_symbols:
            return results

        actual_signatures = extract_function_signatures(file_path)

        for symbol in expected_symbols:
            if not isinstance(symbol, dict):
                continue

            name = symbol.get('name', '')
            symbol_type = symbol.get('type', '')

            if not name or name in ignore_symbols:
                continue
            if symbol_type in ('import', 'module', 'class', 'type', 'constant'):
                continue
            if len(name) == 1:
                continue
            if name[0].isupper() and symbol_type != 'function':
                continue

            if name not in actual_signatures:
                results.append(VerificationResult(
                    file_path=str(file_path.name),
                    check_type='signature',
                    passed=False,
                    message=f"Expected function '{name}' not found",
                    severity='warning',
                ))
    except Exception:
        pass

    return results


def run_builtin_verification(qodeyard_path: Path, qontext_path: Path, cycle_num: str, config: dict) -> VerificationReport:
    """Run Qualifier builtin deterministic checks."""
    report = VerificationReport(cycle_num=cycle_num)
    checks_config = _get_verification_checks(config)
    python_files = list(qodeyard_path.rglob('*.py'))
    report.total_files = len(python_files)

    print(f"[Qualifier] Builtin checks scanning {len(python_files)} Python files...", flush=True)

    for py_file in python_files:
        report.files_checked += 1

        if checks_config['syntax']:
            for result in check_python_syntax(py_file):
                report.add_result(result)

        if checks_config['imports']:
            for result in check_imports_resolve(py_file, qodeyard_path):
                report.add_result(result)

        if checks_config['skeleton_match']:
            for result in compare_with_qontext(py_file, qontext_path):
                report.add_result(result)

    print(f"[Qualifier] Builtin checks complete: {report.overall_status}", flush=True)
    print(f"           ✅ {report.passed} | ⚠️ {report.warnings} | ❌ {report.errors}", flush=True)
    return report


def _group_builtin_results(report: VerificationReport, checks_config: dict) -> list[dict]:
    grouped = []
    specs = [
        ('syntax', 'python_syntax'),
        ('import', 'import_resolution'),
        ('signature', 'qontext_skeleton_match'),
    ]

    for check_type, name in specs:
        if check_type == 'syntax' and not checks_config['syntax']:
            continue
        if check_type == 'import' and not checks_config['imports']:
            continue
        if check_type == 'signature' and not checks_config['skeleton_match']:
            continue

        details = [
            {
                'file_path': item.file_path,
                'passed': item.passed,
                'message': item.message,
                'line_number': item.line_number,
                'severity': item.severity,
            }
            for item in report.results
            if item.check_type == check_type
        ]
        errors = sum(1 for item in details if not item['passed'] and item['severity'] == 'error')
        warnings = sum(1 for item in details if not item['passed'] and item['severity'] == 'warning')
        passed = errors == 0
        status = 'FAIL' if errors else ('WARN' if warnings else 'PASS')

        grouped.append({
            'name': name,
            'type': 'builtin',
            'required': True,
            'passed': passed,
            'status': status,
            'details': details,
            'summary': {
                'files_checked': report.files_checked,
                'total_results': len(details),
                'warnings': warnings,
                'errors': errors,
            },
            'message': {
                'python_syntax': 'Python syntax compilation checks',
                'import_resolution': 'Local import resolution checks',
                'qontext_skeleton_match': 'Qontext signature drift checks',
            }[name],
        })

    return grouped


def _render_builtin_markdown(report: VerificationReport, grouped_results: list[dict]) -> str:
    lines = [
        f"# Qualifier Builtin Report - CyQle {report.cycle_num}",
        '',
        f"**Status:** {report.overall_status}",
        f"**Files:** {report.files_checked}/{report.total_files}",
        f"**Results:** ✅ {report.passed} passed | ⚠️ {report.warnings} warnings | ❌ {report.errors} errors",
        '',
        '## Builtin Checks',
        '',
    ]

    for result in grouped_results:
        icon = '✅' if result['status'] == 'PASS' else ('⚠️' if result['status'] == 'WARN' else '❌')
        lines.append(f"### {icon} {result['name']} — {result['status']}")
        lines.append(f"- Files checked: {result['summary']['files_checked']}")
        lines.append(f"- Errors: {result['summary']['errors']}")
        lines.append(f"- Warnings: {result['summary']['warnings']}")
        lines.append('')
        failures = [detail for detail in result['details'] if not detail['passed']]
        if failures:
            for detail in failures:
                line_info = f" (line {detail['line_number']})" if detail['line_number'] else ''
                lines.append(f"- **{detail['file_path']}**{line_info}: [{detail['severity']}] {detail['message']}")
        else:
            lines.append('- No issues found.')
        lines.append('')

    return '\n'.join(lines)


def _contains_unsafe_shell_syntax(command: str) -> bool:
    unsafe_fragments = ('&&', '||', ';', '|', '>', '<', '`', '$(', '\n', '\r', '&')
    return any(fragment in command for fragment in unsafe_fragments)


def run_shell_command(cmd_spec: dict, default_timeout: int, cwd: Path) -> dict:
    """Safely execute a configured command without invoking a shell."""
    name = cmd_spec.get('name', 'unnamed')
    command = cmd_spec.get('cmd', '')
    required = cmd_spec.get('required', True)
    timeout = cmd_spec.get('timeout', default_timeout)
    start_time = time.time()

    if not isinstance(command, str) or not command.strip():
        return {
            'name': name,
            'type': 'shell',
            'required': required,
            'passed': False,
            'status': 'FAIL',
            'command': command,
            'exit_code': 1,
            'stdout': '',
            'stderr': 'Missing command string.',
            'duration': f"{time.time() - start_time:.2f}s",
            'message': 'Command configuration error',
        }

    if _contains_unsafe_shell_syntax(command):
        return {
            'name': name,
            'type': 'shell',
            'required': required,
            'passed': False,
            'status': 'FAIL',
            'command': command,
            'exit_code': 1,
            'stdout': '',
            'stderr': 'Rejected unsafe shell metacharacters in command. Use plain argv-style commands only.',
            'duration': f"{time.time() - start_time:.2f}s",
            'message': 'Command rejected by Qualifier security policy',
        }

    try:
        args = shlex.split(command)
    except ValueError as e:
        return {
            'name': name,
            'type': 'shell',
            'required': required,
            'passed': False,
            'status': 'FAIL',
            'command': command,
            'exit_code': 1,
            'stdout': '',
            'stderr': f'Could not parse command: {e}',
            'duration': f"{time.time() - start_time:.2f}s",
            'message': 'Command parsing failed',
        }

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd),
        )
        stdout, stderr = process.communicate(timeout=timeout)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        exit_code = -1
        stderr += f"\n[ERROR] Command timed out after {timeout} seconds."
    except FileNotFoundError as e:
        stdout, stderr = '', str(e)
        exit_code = 127
    except Exception as e:
        stdout, stderr = '', str(e)
        exit_code = 1

    duration = time.time() - start_time
    passed = exit_code == 0
    return {
        'name': name,
        'type': 'shell',
        'required': required,
        'passed': passed,
        'status': 'PASS' if passed else 'FAIL',
        'command': command,
        'exit_code': exit_code,
        'stdout': stdout[-5000:],
        'stderr': stderr[-5000:],
        'duration': f"{duration:.2f}s",
        'message': 'Command passed' if passed else 'Command failed',
    }


def _render_quality_markdown(report_json: dict) -> str:
    lines = [
        f"# Quality Report: CyQle {report_json['cycle']}",
        '',
        f"**Overall Status:** {'✅ PASS' if report_json['overall_status'] == 'PASS' else '❌ FAIL'}",
        f"**Timestamp:** {report_json['timestamp']}",
        '',
        '## Result Summary',
        '',
    ]

    for result in report_json['results']:
        status_icon = '✅' if result['passed'] else '❌'
        optionality = 'required' if result.get('required', True) else 'optional'
        lines.append(f"- {status_icon} **{result['name']}** ({result['type']}, {optionality})")
    lines.append('')

    for result in report_json['results']:
        if result['type'] == 'builtin':
            lines.append(f"## Builtin Check: {result['name']} ({result['status']})")
            failures = [detail for detail in result.get('details', []) if not detail.get('passed')]
            if failures:
                for detail in failures:
                    line_info = f" (line {detail['line_number']})" if detail.get('line_number') else ''
                    lines.append(f"- **{detail['file_path']}**{line_info}: [{detail['severity']}] {detail['message']}")
            else:
                lines.append('- No issues found.')
            lines.append('')
        elif result['type'] == 'shell':
            lines.append(f"## Command: {result['name']}")
            lines.append(f"**Exit Code:** {result.get('exit_code')}")
            lines.append(f"**Duration:** {result.get('duration')}")
            if result.get('stderr'):
                lines.append('### Stderr')
                lines.append('```')
                lines.append(result['stderr'])
                lines.append('```')
            if result.get('stdout'):
                lines.append('<details><summary>Stdout</summary>')
                lines.append('')
                lines.append('```')
                lines.append(result['stdout'])
                lines.append('```')
                lines.append('</details>')
            lines.append('')

    return '\n'.join(lines)


def main() -> None:
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX QUALIFIER RUNTIME CONTRACT (v1.2.2)
    # New signature: qualifier.py <input_path> <output_path>
    # ═══════════════════════════════════════════════════════════════════════════
    if len(sys.argv) < 3:
        print('Usage: qualifier.py <input_path> <output_path>')
        sys.exit(1)

    input_path_str = sys.argv[1]
    output_path_str = sys.argv[2]
    worqspace_root = Path(os.getcwd())

    # Derive cycle_num robustly
    cycle_num = None
    
    # Priority 1: Parse from output_path or input_path
    for path_str in [output_path_str, input_path_str]:
        match = re.search(r'cyqle(\d+)', path_str)
        if match:
            cycle_num = match.group(1)
            break
            
    # Priority 2: Check reqap.d/cyqleN_*.md or quality.d/cyqleN/
    if not cycle_num:
        reqap_files = list((worqspace_root / 'reqap.d').glob('cyqle*_*.md'))
        if reqap_files:
            # Get the highest cycle number from reqap files
            cycles = []
            for f in reqap_files:
                m = re.search(r'cyqle(\d+)', f.name)
                if m: cycles.append(int(m.group(1)))
            if cycles:
                cycle_num = str(max(cycles))

    # Priority 3: Fallback - count existing cycles in quality.d
    if not cycle_num:
        quality_dirs = list((worqspace_root / 'quality.d').glob('cyqle*'))
        if quality_dirs:
            cycle_num = str(len(quality_dirs))
            
    # Final Fallback
    if not cycle_num:
        cycle_num = "1"

    print(f"[Qualifier] Derived Cycle: {cycle_num}")

    qodeyard_path = worqspace_root / 'qodeyard'
    qontext_path = worqspace_root / 'qontext.d'
    
    # Ensure all writes use quality.d/cyqle{N}/
    quality_dir = worqspace_root / 'quality.d' / f"cyqle{cycle_num}"
    quality_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(worqspace_root)
    q_cfg = config.get('agents', {}).get('qualifier', {})
    if not q_cfg.get('enabled', True):
        print(f'Qualifier disabled for cycle {cycle_num}. Skipping.')
        sys.exit(0)

    print(f'=== Qualifier Agent v1.2.2: Validation for CyQle {cycle_num} ===')

    results: list[dict] = []
    commands_log: list[dict] = []
    checks_config = _get_verification_checks(config)
    configured_commands = q_cfg.get('commands', [])
    builtin_commands = [cmd for cmd in configured_commands if cmd.get('type') == 'builtin' and cmd.get('enabled', False)]
    builtin_suite_enabled = bool(builtin_commands) or not any(cmd.get('type') == 'builtin' for cmd in configured_commands)

    if builtin_suite_enabled:
        print('--- Running Qualifier builtin checks (syntax/imports/skeleton) ---')
        builtin_report = run_builtin_verification(qodeyard_path, qontext_path, cycle_num, config)
        builtin_results = _group_builtin_results(builtin_report, checks_config)
        results.extend(builtin_results)

        builtin_md = _render_builtin_markdown(builtin_report, builtin_results)
        for filename in ('builtin_report.md', 'syntax_report.md'):
            with open(quality_dir / filename, 'w', encoding='utf-8') as f:
                f.write(builtin_md)

    default_timeout = q_cfg.get('command_timeout', 300)
    for cmd_spec in configured_commands:
        if cmd_spec.get('type') != 'shell' or not cmd_spec.get('enabled', False):
            continue

        print(f"--- Executing: {cmd_spec.get('name', 'unnamed')} ({cmd_spec.get('cmd', '')}) ---")
        result = run_shell_command(cmd_spec, default_timeout, worqspace_root)
        results.append(result)
        commands_log.append({
            'name': result['name'],
            'command': result['command'],
            'exit_code': result['exit_code'],
            'duration': result['duration'],
            'passed': result['passed'],
            'required': result.get('required', True),
        })

    required_results = [result for result in results if result.get('required', True)]
    overall_passed = all(result['passed'] for result in required_results) if required_results else True
    summary = {
        'total': len(results),
        'passed': sum(1 for result in results if result['passed']),
        'failed': sum(1 for result in results if not result['passed']),
        'required_total': len(required_results),
        'required_passed': sum(1 for result in required_results if result['passed']),
        'required_failed': sum(1 for result in required_results if not result['passed']),
        'optional_failed': sum(1 for result in results if not result['passed'] and not result.get('required', True)),
    }
    failed_checks = [result['name'] for result in results if not result['passed']]

    report_json = {
        'cycle': int(cycle_num),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'overall_status': 'PASS' if overall_passed else 'FAIL',
        'results': results,
        'summary': summary,
        'failed_checks': failed_checks,
    }

    with open(quality_dir / 'report.json', 'w', encoding='utf-8') as f:
        json.dump(report_json, f, indent=2)
    with open(quality_dir / 'commands.json', 'w', encoding='utf-8') as f:
        json.dump(commands_log, f, indent=2)
    with open(worqspace_root / 'quality.d' / 'latest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report_json, f, indent=2)
    with open(quality_dir / 'report.md', 'w', encoding='utf-8') as f:
        f.write(_render_quality_markdown(report_json))

    print(f"=== Quality Check Complete: {'PASS' if overall_passed else 'FAIL'} ===")
    if not overall_passed:
        print(f"Errors found in {summary['failed']} checks.")


if __name__ == '__main__':
    main()
