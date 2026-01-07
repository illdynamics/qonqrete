#!/usr/bin/env python3
"""Qonscience: Code Verification Agent - Code quality verification & auto-fix"""

import ast
import re
import subprocess
import sys
from typing import Dict, List, Any
from worqer.mindstaq import CrystallizedIntent


class Qonscience:
    """Code verification and auto-fix. The 'conscience' of mindstaQ."""
    
    VALID_MODULES = {
        'os', 'sys', 're', 'json', 'yaml', 'time', 'datetime', 'math',
        'random', 'collections', 'itertools', 'functools', 'typing',
        'pathlib', 'io', 'shutil', 'tempfile', 'glob', 'csv', 'pickle',
        'sqlite3', 'xml', 'html', 'http', 'urllib', 'socket', 'ssl',
        'threading', 'multiprocessing', 'asyncio', 'concurrent',
        'logging', 'argparse', 'configparser', 'hashlib', 'hmac',
        'secrets', 'uuid', 'base64', 'struct', 'copy', 'pprint',
        'inspect', 'traceback', 'warnings', 'contextlib', 'dataclasses',
        'enum', 'abc', 'unittest', 'doctest', 'types',
        'requests', 'flask', 'fastapi', 'django', 'sqlalchemy',
        'pydantic', 'pytest', 'numpy', 'pandas', 'aiohttp', 'httpx',
        'jwt', 'redis', 'boto3', 'click', 'rich', 'typer',
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        cfg = self.config.get('qonscience', {})
        self.max_iterations = cfg.get('max_iterations', 5)
        self.auto_fix_cfg = cfg.get('auto_fix', {})
        self._ruff_available = self._check_command('ruff')
    
    def _check_command(self, cmd: str) -> bool:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, timeout=5)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def verify(self, code: str, intent: CrystallizedIntent = None) -> Dict[str, Any]:
        result = {'passed': True, 'errors': [], 'warnings': [], 'syntax_valid': True, 'imports_valid': True}
        
        syntax_result = self._check_syntax(code)
        result['syntax_valid'] = syntax_result['valid']
        if not syntax_result['valid']:
            result['passed'] = False
            result['errors'].extend(syntax_result['errors'])
            return result
        
        import_result = self._check_imports(code)
        result['imports_valid'] = import_result['valid']
        if not import_result['valid']:
            result['warnings'].extend(import_result['warnings'])
        
        if self._ruff_available:
            lint_result = self._run_ruff(code)
            result['errors'].extend(lint_result.get('errors', []))
            result['warnings'].extend(lint_result.get('warnings', []))
            if lint_result.get('errors'):
                result['passed'] = False
        
        return result
    
    def _check_syntax(self, code: str) -> Dict[str, Any]:
        result = {'valid': True, 'errors': []}
        try:
            ast.parse(code)
        except SyntaxError as e:
            result['valid'] = False
            error_msg = f"SyntaxError at line {e.lineno}: {e.msg}"
            if e.text:
                error_msg += f"\n  {e.text.strip()}"
            result['errors'].append(error_msg)
        return result
    
    def _check_imports(self, code: str) -> Dict[str, Any]:
        result = {'valid': True, 'warnings': []}
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return result
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module not in self.VALID_MODULES and not module.startswith('_'):
                        result['warnings'].append(f"Unknown import: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split('.')[0]
                if module not in self.VALID_MODULES and not module.startswith(('_', '.')):
                    result['warnings'].append(f"Unknown import: from {node.module}")
        return result
    
    def _run_ruff(self, code: str) -> Dict[str, Any]:
        result = {'errors': [], 'warnings': []}
        if not self._ruff_available:
            return result
        try:
            proc = subprocess.run(['ruff', 'check', '--stdin-filename=code.py', '-'],
                                  input=code, capture_output=True, text=True, timeout=30)
            if proc.stdout:
                for line in proc.stdout.strip().split('\n'):
                    if line:
                        if 'error' in line.lower() or ':E' in line:
                            result['errors'].append(line)
                        else:
                            result['warnings'].append(line)
        except Exception:
            pass
        return result
    
    def auto_fix(self, code: str, verification_result: Dict[str, Any]) -> str:
        if not verification_result.get('syntax_valid', True):
            if self.auto_fix_cfg.get('syntax_errors', True):
                code = self._fix_syntax(code, verification_result['errors'])
        
        if self.auto_fix_cfg.get('missing_imports', True):
            code = self._fix_imports(code)
        
        return code
    
    def _fix_syntax(self, code: str, errors: List[str]) -> str:
        lines = code.split('\n')
        for error in errors:
            line_match = re.search(r'line (\d+)', error, re.I)
            if not line_match:
                continue
            line_num = int(line_match.group(1)) - 1
            if line_num < 0 or line_num >= len(lines):
                continue
            
            problem_line = lines[line_num]
            
            if 'expected' in error.lower() and ':' in error:
                if re.match(r'^\s*(def|class|if|elif|else|for|while|try|except|finally|with|async)', problem_line):
                    if not problem_line.rstrip().endswith(':'):
                        lines[line_num] = problem_line.rstrip() + ':'
            
            if 'indent' in error.lower() and line_num > 0:
                prev_line = lines[line_num - 1]
                if prev_line.rstrip().endswith(':'):
                    prev_indent = len(prev_line) - len(prev_line.lstrip())
                    lines[line_num] = ' ' * (prev_indent + 4) + problem_line.lstrip()
            
            if 'parenthesis' in error.lower() or 'bracket' in error.lower():
                for char, close in [('(', ')'), ('[', ']'), ('{', '}')]:
                    diff = problem_line.count(char) - problem_line.count(close)
                    if diff > 0:
                        lines[line_num] = lines[line_num].rstrip() + close * diff
        
        return '\n'.join(lines)
    
    def _fix_imports(self, code: str) -> str:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
        
        existing_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    existing_imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                existing_imports.add(node.module.split('.')[0])
        
        import_map = {
            'Path': 'from pathlib import Path', 'json': 'import json', 'os': 'import os',
            'sys': 'import sys', 're': 'import re', 'datetime': 'from datetime import datetime',
            'Optional': 'from typing import Optional', 'List': 'from typing import List',
            'Dict': 'from typing import Dict', 'Any': 'from typing import Any',
            'dataclass': 'from dataclasses import dataclass', 'field': 'from dataclasses import field',
        }
        
        missing = []
        for name, import_stmt in import_map.items():
            if name in used_names:
                module = import_stmt.split()[1] if 'from' not in import_stmt else import_stmt.split()[1]
                if module not in existing_imports:
                    missing.append(import_stmt)
        
        if missing:
            lines = code.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('import ') or stripped.startswith('from '):
                    insert_pos = i + 1
            for imp in sorted(set(missing)):
                lines.insert(insert_pos, imp)
                insert_pos += 1
            code = '\n'.join(lines)
        
        return code
    
    def get_quality_score(self, code: str) -> int:
        score = 100
        result = self.verify(code)
        if not result['syntax_valid']:
            score -= 50
        score -= len(result['errors']) * 10
        score -= len(result['warnings']) * 2
        return max(0, score)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qonscience - Verification Agent')
    parser.add_argument('--file', '-f', type=str, help='Python file to verify')
    parser.add_argument('--code', '-c', type=str, help='Code string')
    parser.add_argument('--fix', action='store_true', help='Attempt auto-fix')
    args = parser.parse_args()
    
    qonscience = Qonscience()
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
    elif args.code:
        code = args.code
    else:
        print("Usage: python qonscience.py --file <path> or --code 'code'")
        sys.exit(1)
    
    result = qonscience.verify(code)
    print(f"Syntax Valid: {result['syntax_valid']}")
    print(f"Passed: {result['passed']}")
    print(f"Quality Score: {qonscience.get_quality_score(code)}/100")
    
    if args.fix and not result['passed']:
        print("\n--- Fixed Code ---")
        print(qonscience.auto_fix(code, result))
