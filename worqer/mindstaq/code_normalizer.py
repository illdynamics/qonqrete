#!/usr/bin/env python3
"""
Code Normalizer: AST-Based Code Style Normalization
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Normalizes code style for consistent output:
- Variable naming (snake_case)
- Import organization
- Docstring standardization
- Type hint inference
- Code formatting

v1.5.0
"""

import ast
import re
from typing import List, Dict, Optional, Any, Set, Tuple
from collections import defaultdict


__version__ = '1.5.0'


# ═══════════════════════════════════════════════════════════════════════════════
# NAMING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def to_snake_case(name: str) -> str:
    """Convert name to snake_case."""
    # Handle already snake_case
    if '_' in name and name.islower():
        return name
    
    # Handle camelCase and PascalCase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def to_pascal_case(name: str) -> str:
    """Convert name to PascalCase."""
    words = re.split(r'[_\s]+', name)
    return ''.join(word.capitalize() for word in words)


def is_private_name(name: str) -> bool:
    """Check if name is private (starts with _)."""
    return name.startswith('_') and not name.startswith('__')


def is_dunder(name: str) -> bool:
    """Check if name is dunder (__name__)."""
    return name.startswith('__') and name.endswith('__')


# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT ORGANIZER
# ═══════════════════════════════════════════════════════════════════════════════

class ImportOrganizer:
    """Organizes imports according to PEP 8."""
    
    # Standard library modules (common ones)
    STDLIB = {
        'abc', 'argparse', 'ast', 'asyncio', 'base64', 'collections',
        'contextlib', 'copy', 'csv', 'dataclasses', 'datetime', 'decimal',
        'enum', 'functools', 'glob', 'hashlib', 'heapq', 'hmac', 'html',
        'http', 'importlib', 'inspect', 'io', 'itertools', 'json', 'logging',
        'math', 'multiprocessing', 'os', 'pathlib', 'pickle', 'platform',
        'queue', 'random', 're', 'secrets', 'shutil', 'signal', 'socket',
        'sqlite3', 'ssl', 'statistics', 'string', 'struct', 'subprocess',
        'sys', 'tempfile', 'textwrap', 'threading', 'time', 'traceback',
        'typing', 'unittest', 'urllib', 'uuid', 'warnings', 'weakref', 'xml',
        'zipfile', 'zlib',
    }
    
    def organize(self, code: str) -> str:
        """Organize imports in code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        # Extract imports
        stdlib_imports = []
        third_party_imports = []
        local_imports = []
        other_nodes = []
        
        for node in tree.body:
            if isinstance(node, ast.Import):
                module = node.names[0].name.split('.')[0]
                if module in self.STDLIB:
                    stdlib_imports.append(node)
                else:
                    third_party_imports.append(node)
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or '').split('.')[0]
                if module.startswith('.'):
                    local_imports.append(node)
                elif module in self.STDLIB:
                    stdlib_imports.append(node)
                else:
                    third_party_imports.append(node)
            else:
                other_nodes.append(node)
        
        # Sort within each group
        def import_key(node):
            if isinstance(node, ast.Import):
                return node.names[0].name.lower()
            else:
                return (node.module or '').lower()
        
        stdlib_imports.sort(key=import_key)
        third_party_imports.sort(key=import_key)
        local_imports.sort(key=import_key)
        
        # Rebuild tree
        new_body = []
        
        if stdlib_imports:
            new_body.extend(stdlib_imports)
        
        if third_party_imports:
            if new_body:
                # Add blank line separator (as comment placeholder)
                pass
            new_body.extend(third_party_imports)
        
        if local_imports:
            new_body.extend(local_imports)
        
        new_body.extend(other_nodes)
        
        tree.body = new_body
        
        try:
            return ast.unparse(tree)
        except:
            return code


# ═══════════════════════════════════════════════════════════════════════════════
# AST TRANSFORMERS
# ═══════════════════════════════════════════════════════════════════════════════

class NameNormalizer(ast.NodeTransformer):
    """Normalize variable names to snake_case."""
    
    def __init__(self):
        self.renames: Dict[str, str] = {}
        self.skip_names = {'self', 'cls', 'args', 'kwargs'}
    
    def visit_Name(self, node):
        if node.id not in self.skip_names and not is_dunder(node.id):
            # Check if needs conversion
            snake = to_snake_case(node.id)
            if snake != node.id and not node.id.isupper():  # Skip constants
                self.renames[node.id] = snake
                node.id = snake
        return node
    
    def visit_FunctionDef(self, node):
        # Normalize function name
        if not is_dunder(node.name) and not is_private_name(node.name):
            node.name = to_snake_case(node.name)
        
        # Normalize arg names
        for arg in node.args.args:
            if arg.arg not in self.skip_names:
                arg.arg = to_snake_case(arg.arg)
        
        self.generic_visit(node)
        return node
    
    def visit_ClassDef(self, node):
        # Classes should be PascalCase
        if not node.name[0].isupper():
            node.name = to_pascal_case(node.name)
        
        self.generic_visit(node)
        return node


class TypeHintAdder(ast.NodeTransformer):
    """Add type hints where inferrable."""
    
    TYPE_PATTERNS = {
        'url': 'str',
        'path': 'str',
        'name': 'str',
        'text': 'str',
        'message': 'str',
        'key': 'str',
        'value': 'Any',
        'data': 'dict',
        'config': 'dict',
        'params': 'dict',
        'headers': 'dict',
        'options': 'dict',
        'timeout': 'int',
        'count': 'int',
        'size': 'int',
        'limit': 'int',
        'offset': 'int',
        'port': 'int',
        'index': 'int',
        'enabled': 'bool',
        'active': 'bool',
        'verbose': 'bool',
        'debug': 'bool',
        'items': 'list',
        'results': 'list',
        'values': 'list',
    }
    
    def visit_FunctionDef(self, node):
        # Add parameter type hints
        for arg in node.args.args:
            if arg.annotation is None:
                arg_name = arg.arg.lower()
                for pattern, type_name in self.TYPE_PATTERNS.items():
                    if pattern in arg_name or arg_name == pattern:
                        arg.annotation = ast.Name(id=type_name, ctx=ast.Load())
                        break
        
        # Add return type if missing and can be inferred
        if node.returns is None:
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value:
                    if isinstance(child.value, ast.Dict):
                        node.returns = ast.Name(id='dict', ctx=ast.Load())
                    elif isinstance(child.value, ast.List):
                        node.returns = ast.Name(id='list', ctx=ast.Load())
                    elif isinstance(child.value, ast.Constant):
                        val = child.value.value
                        if isinstance(val, str):
                            node.returns = ast.Name(id='str', ctx=ast.Load())
                        elif isinstance(val, bool):
                            node.returns = ast.Name(id='bool', ctx=ast.Load())
                        elif isinstance(val, int):
                            node.returns = ast.Name(id='int', ctx=ast.Load())
                        elif isinstance(val, float):
                            node.returns = ast.Name(id='float', ctx=ast.Load())
                        elif val is None:
                            node.returns = ast.Constant(value=None)
                    break
        
        self.generic_visit(node)
        return node


class DocstringAdder(ast.NodeTransformer):
    """Add docstrings to functions without them."""
    
    def visit_FunctionDef(self, node):
        # Check if has docstring
        has_doc = (node.body and isinstance(node.body[0], ast.Expr) and 
                  isinstance(node.body[0].value, ast.Constant) and 
                  isinstance(node.body[0].value.value, str))
        
        if not has_doc and not is_private_name(node.name):
            # Generate docstring from function name
            func_name = node.name.replace('_', ' ')
            docstring = f"{func_name.capitalize()}."
            
            doc_node = ast.Expr(value=ast.Constant(value=docstring))
            node.body.insert(0, doc_node)
        
        self.generic_visit(node)
        return node
    
    def visit_ClassDef(self, node):
        # Check if has docstring
        has_doc = (node.body and isinstance(node.body[0], ast.Expr) and 
                  isinstance(node.body[0].value, ast.Constant) and 
                  isinstance(node.body[0].value.value, str))
        
        if not has_doc:
            # Generate docstring from class name
            class_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', node.name)
            docstring = f"{class_name}."
            
            doc_node = ast.Expr(value=ast.Constant(value=docstring))
            node.body.insert(0, doc_node)
        
        self.generic_visit(node)
        return node


# ═══════════════════════════════════════════════════════════════════════════════
# CODE NORMALIZER
# ═══════════════════════════════════════════════════════════════════════════════

class CodeNormalizer:
    """
    Normalizes code for consistent style.
    
    Features:
    - Variable naming (snake_case for functions/vars, PascalCase for classes)
    - Import organization (stdlib, third-party, local)
    - Type hint inference
    - Docstring generation
    - Consistent formatting
    
    Usage:
        normalizer = CodeNormalizer()
        
        code = '''
        def FetchUrl(URL, Timeout=30):
            return requests.get(URL, timeout=Timeout)
        '''
        
        normalized = normalizer.normalize(code)
        # Result: snake_case, type hints, docstring added
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Options
        self.normalize_names = self.config.get('normalize_names', True)
        self.add_type_hints = self.config.get('add_type_hints', True)
        self.add_docstrings = self.config.get('add_docstrings', True)
        self.organize_imports = self.config.get('organize_imports', True)
        
        self.import_organizer = ImportOrganizer()
    
    def normalize(self, code: str) -> str:
        """
        Normalize code style.
        
        Args:
            code: Python code to normalize
        
        Returns:
            Normalized code string
        """
        if not code or not code.strip():
            return code
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        # Apply transformations
        if self.normalize_names:
            tree = NameNormalizer().visit(tree)
        
        if self.add_type_hints:
            tree = TypeHintAdder().visit(tree)
        
        if self.add_docstrings:
            tree = DocstringAdder().visit(tree)
        
        ast.fix_missing_locations(tree)
        
        try:
            result = ast.unparse(tree)
        except:
            return code
        
        # Organize imports
        if self.organize_imports:
            result = self.import_organizer.organize(result)
        
        return result
    
    def normalize_minimal(self, code: str) -> str:
        """
        Minimal normalization - just fix syntax issues.
        """
        try:
            tree = ast.parse(code)
            return ast.unparse(tree)
        except SyntaxError:
            return code
    
    def add_missing_imports(self, code: str) -> str:
        """
        Add missing imports based on used names.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        # Find used names
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)
        
        # Common auto-imports
        AUTO_IMPORTS = {
            'Dict': 'from typing import Dict',
            'List': 'from typing import List',
            'Optional': 'from typing import Optional',
            'Any': 'from typing import Any',
            'Tuple': 'from typing import Tuple',
            'Set': 'from typing import Set',
            'dataclass': 'from dataclasses import dataclass',
            'field': 'from dataclasses import field',
            'Path': 'from pathlib import Path',
            'datetime': 'from datetime import datetime',
            'timedelta': 'from datetime import timedelta',
        }
        
        # Find existing imports
        existing_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    existing_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    existing_imports.add(alias.name)
        
        # Add missing imports
        imports_to_add = []
        for name in used_names:
            if name in AUTO_IMPORTS and name not in existing_imports:
                imports_to_add.append(AUTO_IMPORTS[name])
        
        if imports_to_add:
            import_code = '\n'.join(sorted(set(imports_to_add)))
            code = import_code + '\n\n' + code
        
        return code
    
    def format_code(self, code: str) -> str:
        """
        Format code with consistent spacing.
        Uses ast.unparse for basic formatting.
        """
        try:
            tree = ast.parse(code)
            return ast.unparse(tree)
        except SyntaxError:
            return code
    
    def validate_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Validate code syntax.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Code Normalizer v{__version__}")
    print("=" * 60)
    
    normalizer = CodeNormalizer()
    
    # Test code with issues
    test_code = '''
import requests
import json
from typing import Dict

def FetchUrl(URL, Timeout=30):
    response = requests.get(URL, timeout=Timeout)
    return response.json()

class httpClient:
    def __init__(self, baseUrl):
        self.baseUrl = baseUrl
    
    def Get(self, path):
        return FetchUrl(self.baseUrl + path)
'''
    
    print("\n[1] Original Code:")
    print("-" * 40)
    print(test_code)
    
    print("\n[2] Normalized Code:")
    print("-" * 40)
    normalized = normalizer.normalize(test_code)
    print(normalized)
    
    print("\n[3] Validation:")
    is_valid, error = normalizer.validate_syntax(normalized)
    print(f"  Valid: {is_valid}")
    if error:
        print(f"  Error: {error}")
    
    print("\n[4] Name Conversion Tests:")
    test_names = ['FetchUrl', 'getUserData', 'XMLParser', 'HTTPClient', 'simple_name']
    for name in test_names:
        print(f"  {name} -> {to_snake_case(name)}")
    
    print("\n✅ Code Normalizer working!")
