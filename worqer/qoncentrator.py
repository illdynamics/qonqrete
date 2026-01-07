#!/usr/bin/env python3
"""Qoncentrator: AST Grafting Agent - Surgical code manipulation and import resolution"""

import ast
import re
from typing import List, Set
from worqer.mindstaq import CrystallizedIntent


class Qoncentrator:
    """AST-based code manipulation. Validates syntax, resolves imports."""
    
    STDLIB_MODULES: Set[str] = {
        'os', 'sys', 're', 'json', 'time', 'datetime', 'math', 'random',
        'collections', 'itertools', 'functools', 'operator', 'pathlib', 'io',
        'shutil', 'tempfile', 'glob', 'csv', 'pickle', 'sqlite3', 'xml', 'html',
        'http', 'urllib', 'socket', 'ssl', 'threading', 'multiprocessing',
        'asyncio', 'concurrent', 'typing', 'types', 'abc', 'dataclasses', 'enum',
        'logging', 'argparse', 'configparser', 'hashlib', 'hmac', 'secrets',
        'uuid', 'base64', 'struct', 'copy', 'pprint', 'inspect', 'traceback',
        'warnings', 'contextlib', 'unittest', 'doctest',
    }
    
    TYPING_IMPORTS = {
        'Optional': 'from typing import Optional',
        'List': 'from typing import List',
        'Dict': 'from typing import Dict',
        'Any': 'from typing import Any',
        'Union': 'from typing import Union',
        'Tuple': 'from typing import Tuple',
        'Callable': 'from typing import Callable',
        'Set': 'from typing import Set',
    }
    
    UTILITY_IMPORTS = {
        'Path': 'from pathlib import Path',
        'dataclass': 'from dataclasses import dataclass',
        'field': 'from dataclasses import field',
        'Enum': 'from enum import Enum',
        'ABC': 'from abc import ABC',
        'abstractmethod': 'from abc import abstractmethod',
        'wraps': 'from functools import wraps',
        'contextmanager': 'from contextlib import contextmanager',
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        cfg = self.config.get('qoncentrator', {})
        self.auto_resolve_imports = cfg.get('auto_resolve_imports', True)
        self.sort_imports = cfg.get('sort_imports', True)
    
    def process(self, code: str, intent: CrystallizedIntent, context_files: List[str] = None) -> str:
        """Process code with language-aware handling.
        
        v1.8.3: Multi-language support - only apply AST processing to Python.
        """
        # v1.8.3: Detect language from target file
        target_file = intent.target_file or ''
        lang = self._detect_language(target_file)
        
        # Always clean code
        code = self._clean_code(code)
        
        # v1.8.3: Only apply Python-specific processing to Python files
        if lang == 'python':
            try:
                ast.parse(code)
            except SyntaxError as e:
                code = self._fix_syntax_errors(code, e)
            if self.auto_resolve_imports:
                code = self._resolve_imports(code)
            if self.sort_imports:
                code = self._sort_imports(code)
        elif lang == 'shell':
            # Shell-specific processing
            code = self._process_shell(code)
        elif lang == 'rust':
            # Rust-specific processing
            code = self._process_rust(code)
        elif lang == 'go':
            # Go-specific processing
            code = self._process_go(code)
        
        return code
    
    def _detect_language(self, filepath: str) -> str:
        """v1.8.3: Detect language from file extension."""
        ext_map = {
            '.py': 'python',
            '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell',
            '.rs': 'rust',
            '.go': 'go',
            '.js': 'javascript', '.ts': 'typescript',
        }
        for ext, lang in ext_map.items():
            if filepath.endswith(ext):
                return lang
        return 'python'  # Default to Python for backward compatibility
    
    def _process_shell(self, code: str) -> str:
        """v1.8.3: Process shell script."""
        lines = code.split('\n')
        
        # Ensure shebang is first line
        if lines and not lines[0].startswith('#!'):
            # Add shebang if missing
            code = '#!/bin/bash\n' + code
        
        # Ensure file ends with newline
        if not code.endswith('\n'):
            code += '\n'
        
        return code
    
    def _process_rust(self, code: str) -> str:
        """v1.8.3: Process Rust code."""
        # Basic cleanup
        if not code.endswith('\n'):
            code += '\n'
        return code
    
    def _process_go(self, code: str) -> str:
        """v1.8.3: Process Go code."""
        lines = code.split('\n')
        
        # Ensure package declaration exists
        has_package = any(line.strip().startswith('package ') for line in lines)
        if not has_package and lines:
            # Add default package main
            code = 'package main\n\n' + code
        
        # Ensure file ends with newline
        if not code.endswith('\n'):
            code += '\n'
        
        return code
    
    def _clean_code(self, code: str) -> str:
        code = re.sub(r'\n{4,}', '\n\n\n', code)
        if not code.endswith('\n'):
            code += '\n'
        return '\n'.join(line.rstrip() for line in code.split('\n'))
    
    def _fix_syntax_errors(self, code: str, error: SyntaxError) -> str:
        lines = code.split('\n')
        if error.lineno and error.lineno <= len(lines):
            problem_line = lines[error.lineno - 1]
            if re.match(r'^\s*(def|class|if|elif|else|for|while|try|except|finally|with|async)\s', problem_line):
                if not problem_line.rstrip().endswith(':'):
                    lines[error.lineno - 1] = problem_line.rstrip() + ':'
            if error.msg and 'bracket' in error.msg.lower():
                for char, close in [('(', ')'), ('[', ']'), ('{', '}')]:
                    diff = problem_line.count(char) - problem_line.count(close)
                    if diff > 0:
                        lines[error.lineno - 1] += close * diff
            if 'indent' in str(error.msg).lower():
                if not problem_line.startswith(' ') and not problem_line.startswith('\t'):
                    lines[error.lineno - 1] = '    ' + problem_line
        return '\n'.join(lines)
    
    def _resolve_imports(self, code: str) -> str:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        existing_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    existing_imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                existing_imports.add(node.module.split('.')[0])
        
        used_names = self._collect_used_names(tree)
        missing_imports = []
        
        for name in used_names:
            if name in self.STDLIB_MODULES and name not in existing_imports:
                missing_imports.append(f"import {name}")
        
        for name, import_stmt in self.TYPING_IMPORTS.items():
            if name in used_names and 'typing' not in existing_imports:
                missing_imports.append(import_stmt)
        
        for name, import_stmt in self.UTILITY_IMPORTS.items():
            if name in used_names:
                module = import_stmt.split()[1]
                if module not in existing_imports:
                    missing_imports.append(import_stmt)
        
        if missing_imports:
            lines = code.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#!'):
                    insert_pos = i + 1
                elif stripped.startswith('"""') or stripped.startswith("'''"):
                    break
                elif stripped and not stripped.startswith('#'):
                    break
            
            import_block = '\n'.join(sorted(set(missing_imports)))
            lines.insert(insert_pos, import_block)
            if insert_pos > 0:
                lines.insert(insert_pos, '')
            lines.insert(insert_pos + (2 if insert_pos > 0 else 1), '')
            code = '\n'.join(lines)
        
        return code
    
    def _collect_used_names(self, tree: ast.AST) -> Set[str]:
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                current = node
                while isinstance(current, ast.Attribute):
                    current = current.value
                if isinstance(current, ast.Name):
                    used_names.add(current.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns:
                    used_names.update(self._extract_annotation_names(node.returns))
                for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                    if arg.annotation:
                        used_names.update(self._extract_annotation_names(arg.annotation))
            elif isinstance(node, ast.AnnAssign) and node.annotation:
                used_names.update(self._extract_annotation_names(node.annotation))
        return used_names
    
    def _extract_annotation_names(self, annotation: ast.expr) -> Set[str]:
        names = set()
        if isinstance(annotation, ast.Name):
            names.add(annotation.id)
        elif isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                names.add(annotation.value.id)
            names.update(self._extract_annotation_names(annotation.slice))
        elif isinstance(annotation, ast.Tuple):
            for elt in annotation.elts:
                names.update(self._extract_annotation_names(elt))
        elif isinstance(annotation, ast.BinOp):
            names.update(self._extract_annotation_names(annotation.left))
            names.update(self._extract_annotation_names(annotation.right))
        return names
    
    def _sort_imports(self, code: str) -> str:
        try:
            ast.parse(code)
        except SyntaxError:
            return code
        
        lines = code.split('\n')
        import_lines, import_start, import_end = [], None, None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                if import_start is None:
                    import_start = i
                import_end = i
                import_lines.append(stripped)
        
        if not import_lines or import_start is None:
            return code
        
        stdlib, thirdparty, local = [], [], []
        for imp in import_lines:
            module = imp.split()[1].split('.')[0]
            if module in self.STDLIB_MODULES:
                stdlib.append(imp)
            elif module.startswith('.'):
                local.append(imp)
            else:
                thirdparty.append(imp)
        
        sorted_imports = []
        if stdlib:
            sorted_imports.extend(sorted(stdlib))
        if thirdparty:
            if sorted_imports:
                sorted_imports.append('')
            sorted_imports.extend(sorted(thirdparty))
        if local:
            if sorted_imports:
                sorted_imports.append('')
            sorted_imports.extend(sorted(local))
        
        return '\n'.join(lines[:import_start] + sorted_imports + lines[import_end + 1:])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qoncentrator - AST Grafting Agent')
    parser.add_argument('--file', '-f', type=str, help='Python file to process')
    parser.add_argument('--code', '-c', type=str, help='Code string')
    args = parser.parse_args()
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
        print(Qoncentrator().process(code, CrystallizedIntent()))
    elif args.code:
        print(Qoncentrator().process(args.code, CrystallizedIntent()))
