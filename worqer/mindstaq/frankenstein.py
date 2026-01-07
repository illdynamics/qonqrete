#!/usr/bin/env python3
"""
Frankenstein Combinator: Smart Code Snippet Merger
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Combines the best parts from multiple code snippets using AST manipulation.
Creates hybrid code that takes the best features from each source.

v1.5.0
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple
from collections import defaultdict


__version__ = '1.5.0'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodeComponent:
    """A component extracted from code (function, class, import, etc.)."""
    type: str                   # 'function', 'class', 'import', 'constant', 'docstring'
    name: str                   # Name of the component
    code: str                   # The actual code
    source_index: int           # Which snippet it came from
    has_type_hints: bool = False
    has_docstring: bool = False
    has_error_handling: bool = False
    async_def: bool = False
    complexity: int = 0         # Rough complexity score


@dataclass
class CombinedCode:
    """Result of combining multiple snippets."""
    code: str                   # The final combined code
    imports: List[str]          # All imports used
    functions: List[str]        # All function names
    classes: List[str]          # All class names
    sources_used: List[int]     # Which source snippets contributed
    quality_score: float        # Estimated quality 0-1


# ═══════════════════════════════════════════════════════════════════════════════
# AST ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_function(node: ast.FunctionDef) -> dict:
    """Analyze a function node for quality metrics."""
    analysis = {
        'name': node.name,
        'async': isinstance(node, ast.AsyncFunctionDef),
        'has_docstring': False,
        'has_type_hints': False,
        'has_return_type': False,
        'has_error_handling': False,
        'num_args': len(node.args.args),
        'has_defaults': len(node.args.defaults) > 0,
        'complexity': 1,
    }
    
    # Check for docstring
    if (node.body and isinstance(node.body[0], ast.Expr) and 
        isinstance(node.body[0].value, ast.Constant) and 
        isinstance(node.body[0].value.value, str)):
        analysis['has_docstring'] = True
    
    # Check for type hints
    for arg in node.args.args:
        if arg.annotation:
            analysis['has_type_hints'] = True
            break
    
    # Check return type
    if node.returns:
        analysis['has_return_type'] = True
        analysis['has_type_hints'] = True
    
    # Check for error handling
    for child in ast.walk(node):
        if isinstance(child, ast.Try):
            analysis['has_error_handling'] = True
            break
    
    # Estimate complexity (count branches)
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            analysis['complexity'] += 1
    
    return analysis


def extract_components(code: str, source_index: int = 0) -> List[CodeComponent]:
    """Extract all components from code snippet."""
    components = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return components
    
    for node in ast.iter_child_nodes(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                comp = CodeComponent(
                    type='import',
                    name=alias.name,
                    code=ast.unparse(node),
                    source_index=source_index
                )
                components.append(comp)
        
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            comp = CodeComponent(
                type='import_from',
                name=module,
                code=ast.unparse(node),
                source_index=source_index
            )
            components.append(comp)
        
        # Functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            analysis = analyze_function(node)
            comp = CodeComponent(
                type='function',
                name=node.name,
                code=ast.unparse(node),
                source_index=source_index,
                has_type_hints=analysis['has_type_hints'],
                has_docstring=analysis['has_docstring'],
                has_error_handling=analysis['has_error_handling'],
                async_def=analysis['async'],
                complexity=analysis['complexity']
            )
            components.append(comp)
        
        # Classes
        elif isinstance(node, ast.ClassDef):
            has_docstring = False
            if (node.body and isinstance(node.body[0], ast.Expr) and 
                isinstance(node.body[0].value, ast.Constant)):
                has_docstring = True
            
            comp = CodeComponent(
                type='class',
                name=node.name,
                code=ast.unparse(node),
                source_index=source_index,
                has_docstring=has_docstring
            )
            components.append(comp)
        
        # Constants / Assignments at module level
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id.isupper():  # Constants
                        comp = CodeComponent(
                            type='constant',
                            name=target.id,
                            code=ast.unparse(node),
                            source_index=source_index
                        )
                        components.append(comp)
    
    return components


# ═══════════════════════════════════════════════════════════════════════════════
# FRANKENSTEIN COMBINATOR
# ═══════════════════════════════════════════════════════════════════════════════

class FrankensteinCombinator:
    """
    Combines multiple code snippets into a single optimized output.
    
    Strategy:
    1. Extract components (functions, classes, imports) from each snippet
    2. Rank components by quality (type hints, docstrings, error handling)
    3. Merge: pick best version of each function/class
    4. Deduplicate imports
    5. Assemble final code
    
    Usage:
        combinator = FrankensteinCombinator()
        
        snippets = [
            "def fetch(url): return requests.get(url)",
            "def fetch(url, timeout=30): ...",
            "async def fetch(url): ...",
        ]
        
        result = combinator.combine(snippets)
        print(result.code)
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Weights for quality scoring
        self.weights = {
            'has_type_hints': 0.25,
            'has_docstring': 0.20,
            'has_error_handling': 0.20,
            'has_defaults': 0.10,
            'complexity_penalty': -0.05,  # Per complexity point above 3
        }
    
    def score_component(self, comp: CodeComponent) -> float:
        """Score a component for quality."""
        score = 0.5  # Base score
        
        if comp.has_type_hints:
            score += self.weights['has_type_hints']
        if comp.has_docstring:
            score += self.weights['has_docstring']
        if comp.has_error_handling:
            score += self.weights['has_error_handling']
        
        # Complexity penalty
        if comp.complexity > 3:
            score += self.weights['complexity_penalty'] * (comp.complexity - 3)
        
        return max(0.0, min(1.0, score))
    
    def merge_imports(self, components: List[CodeComponent]) -> List[str]:
        """Merge and deduplicate imports."""
        imports = set()
        import_froms = defaultdict(set)
        
        for comp in components:
            if comp.type == 'import':
                imports.add(comp.name)
            elif comp.type == 'import_from':
                # Parse the import_from to get module and names
                try:
                    tree = ast.parse(comp.code)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            module = node.module or ''
                            for alias in node.names:
                                import_froms[module].add(alias.name)
                except:
                    pass
        
        # Generate import statements
        result = []
        
        # Regular imports
        for name in sorted(imports):
            result.append(f"import {name}")
        
        # From imports (grouped by module)
        for module in sorted(import_froms.keys()):
            names = sorted(import_froms[module])
            result.append(f"from {module} import {', '.join(names)}")
        
        return result
    
    def select_best_function(
        self, 
        candidates: List[CodeComponent],
        prefer_async: bool = False
    ) -> CodeComponent:
        """Select the best function from candidates with the same name."""
        if len(candidates) == 1:
            return candidates[0]
        
        # Score each candidate
        scored = []
        for comp in candidates:
            score = self.score_component(comp)
            
            # Bonus for async if preferred
            if prefer_async and comp.async_def:
                score += 0.15
            
            scored.append((comp, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: -x[1])
        
        return scored[0][0]
    
    def create_sync_async_pair(
        self,
        sync_func: CodeComponent,
        async_func: CodeComponent
    ) -> str:
        """Create both sync and async versions of a function."""
        # Return both versions
        sync_code = sync_func.code if sync_func else ""
        async_code = async_func.code if async_func else ""
        
        if sync_code and async_code:
            return f"{sync_code}\n\n{async_code}"
        return sync_code or async_code
    
    def combine(
        self,
        snippets: List[str],
        prefer_async: bool = False,
        include_both_sync_async: bool = True
    ) -> CombinedCode:
        """
        Combine multiple code snippets into one.
        
        Args:
            snippets: List of code snippets to combine
            prefer_async: Prefer async versions when available
            include_both_sync_async: Include both sync and async versions
        
        Returns:
            CombinedCode with the combined result
        """
        if not snippets:
            return CombinedCode(
                code="",
                imports=[],
                functions=[],
                classes=[],
                sources_used=[],
                quality_score=0.0
            )
        
        # Extract components from all snippets
        all_components = []
        for i, snippet in enumerate(snippets):
            components = extract_components(snippet, source_index=i)
            all_components.extend(components)
        
        if not all_components:
            # No parseable code - return the longest snippet
            longest = max(snippets, key=len)
            return CombinedCode(
                code=longest,
                imports=[],
                functions=[],
                classes=[],
                sources_used=[0],
                quality_score=0.3
            )
        
        # Group components by type and name
        imports = [c for c in all_components if c.type in ('import', 'import_from')]
        functions = defaultdict(list)
        classes = defaultdict(list)
        constants = defaultdict(list)
        
        for comp in all_components:
            if comp.type == 'function':
                functions[comp.name].append(comp)
            elif comp.type == 'class':
                classes[comp.name].append(comp)
            elif comp.type == 'constant':
                constants[comp.name].append(comp)
        
        # Select best versions
        selected_functions = []
        for name, candidates in functions.items():
            # Separate sync and async
            sync_candidates = [c for c in candidates if not c.async_def]
            async_candidates = [c for c in candidates if c.async_def]
            
            if include_both_sync_async and sync_candidates and async_candidates:
                # Include both versions with different names
                best_sync = self.select_best_function(sync_candidates)
                best_async = self.select_best_function(async_candidates, prefer_async=True)
                
                # Rename async version if same name
                if best_sync.name == best_async.name:
                    async_code = best_async.code.replace(
                        f"async def {best_async.name}",
                        f"async def {best_async.name}_async",
                        1
                    )
                    best_async = CodeComponent(
                        type='function',
                        name=f"{best_async.name}_async",
                        code=async_code,
                        source_index=best_async.source_index,
                        has_type_hints=best_async.has_type_hints,
                        has_docstring=best_async.has_docstring,
                        has_error_handling=best_async.has_error_handling,
                        async_def=True
                    )
                
                selected_functions.append(best_sync)
                selected_functions.append(best_async)
            else:
                # Just pick the best
                best = self.select_best_function(candidates, prefer_async=prefer_async)
                selected_functions.append(best)
        
        selected_classes = []
        for name, candidates in classes.items():
            # Pick the one with docstring if available
            with_doc = [c for c in candidates if c.has_docstring]
            if with_doc:
                selected_classes.append(with_doc[0])
            else:
                selected_classes.append(candidates[0])
        
        selected_constants = []
        for name, candidates in constants.items():
            selected_constants.append(candidates[0])
        
        # Merge imports
        merged_imports = self.merge_imports(imports)
        
        # Assemble final code
        parts = []
        
        # Imports first
        if merged_imports:
            parts.append('\n'.join(merged_imports))
            parts.append('')  # Blank line
        
        # Constants
        for const in selected_constants:
            parts.append(const.code)
        
        if selected_constants:
            parts.append('')  # Blank line
        
        # Classes
        for cls in selected_classes:
            parts.append(cls.code)
            parts.append('')
        
        # Functions
        for func in selected_functions:
            parts.append(func.code)
            parts.append('')
        
        final_code = '\n'.join(parts).strip()
        
        # Calculate quality score
        all_selected = selected_functions + selected_classes
        if all_selected:
            avg_quality = sum(self.score_component(c) for c in all_selected) / len(all_selected)
        else:
            avg_quality = 0.3
        
        # Track which sources were used
        sources_used = set()
        for comp in all_selected + selected_constants:
            sources_used.add(comp.source_index)
        for imp in imports:
            sources_used.add(imp.source_index)
        
        return CombinedCode(
            code=final_code,
            imports=merged_imports,
            functions=[f.name for f in selected_functions],
            classes=[c.name for c in selected_classes],
            sources_used=sorted(sources_used),
            quality_score=avg_quality
        )
    
    def enhance_with_types(self, code: str) -> str:
        """
        Add type hints to code that lacks them.
        Uses simple inference based on common patterns.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        # Common type mappings
        type_hints = {
            'url': 'str',
            'path': 'str',
            'name': 'str',
            'text': 'str',
            'message': 'str',
            'data': 'dict',
            'config': 'dict',
            'params': 'dict',
            'timeout': 'int',
            'count': 'int',
            'size': 'int',
            'limit': 'int',
            'offset': 'int',
            'enabled': 'bool',
            'active': 'bool',
            'items': 'list',
            'results': 'list',
        }
        
        modified = False
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if arg.annotation is None:
                        # Try to infer type from name
                        arg_name = arg.arg.lower()
                        for pattern, type_name in type_hints.items():
                            if pattern in arg_name:
                                arg.annotation = ast.Name(id=type_name, ctx=ast.Load())
                                modified = True
                                break
        
        if modified:
            return ast.unparse(tree)
        return code
    
    def add_docstrings(self, code: str, task_description: str = '') -> str:
        """
        Add docstrings to functions that lack them.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code
        
        modified = False
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if already has docstring
                has_doc = (node.body and isinstance(node.body[0], ast.Expr) and 
                          isinstance(node.body[0].value, ast.Constant) and 
                          isinstance(node.body[0].value.value, str))
                
                if not has_doc:
                    # Generate simple docstring
                    func_name = node.name.replace('_', ' ')
                    docstring = f'"""{func_name.capitalize()}."""'
                    
                    doc_node = ast.Expr(value=ast.Constant(value=f"{func_name.capitalize()}."))
                    node.body.insert(0, doc_node)
                    modified = True
        
        if modified:
            return ast.unparse(tree)
        return code


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Frankenstein Combinator v{__version__}")
    print("=" * 60)
    
    combinator = FrankensteinCombinator()
    
    # Test snippets
    snippets = [
        # Snippet 1: Basic, no types
        '''
import requests

def fetch(url):
    return requests.get(url)
''',
        # Snippet 2: Has timeout parameter
        '''
import requests

def fetch(url, timeout=30):
    response = requests.get(url, timeout=timeout)
    return response.json()
''',
        # Snippet 3: Has type hints and error handling
        '''
import requests
from typing import Optional, Dict, Any

def fetch(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """Fetch data from URL."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None
''',
        # Snippet 4: Async version
        '''
import aiohttp

async def fetch(url, timeout=30):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as response:
            return await response.json()
''',
    ]
    
    print("\n[1] Input Snippets:")
    for i, s in enumerate(snippets):
        print(f"\n--- Snippet {i+1} ---")
        print(s.strip()[:200] + "..." if len(s) > 200 else s.strip())
    
    print("\n" + "=" * 60)
    print("[2] Combined Output:")
    print("=" * 60)
    
    result = combinator.combine(snippets, include_both_sync_async=True)
    print(result.code)
    
    print("\n[3] Stats:")
    print(f"  Functions: {result.functions}")
    print(f"  Classes: {result.classes}")
    print(f"  Sources used: {result.sources_used}")
    print(f"  Quality score: {result.quality_score:.2f}")
    
    print("\n✅ Frankenstein Combinator working!")
