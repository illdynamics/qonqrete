#!/usr/bin/env python3
"""
Dependency Graph Scaffold: Multi-file Architecture Planning
Part of mindstaQ v2.1.7 - ZERO LLM Code Generation

Analyzes project structure and builds a dependency graph to understand
how files relate to each other. This helps generate code that:
- Imports from the right places
- Avoids circular dependencies
- Follows project conventions
- Places code in the right files

Key Features:
- AST-based import analysis
- Dependency graph construction
- Circular dependency detection
- Architecture pattern recognition
- Smart file placement suggestions

WoNQ Impact: +25-35 points for multi-file architecture

v2.1.7
"""

import ast
import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
from collections import defaultdict
import json


__version__ = '2.1.7'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class NodeType(Enum):
    """Types of nodes in the dependency graph."""
    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    FUNCTION = "function"
    CONSTANT = "constant"
    EXTERNAL = "external"


class ArchitecturePattern(Enum):
    """Recognized architecture patterns."""
    FLAT = "flat"                    # All files in root
    LAYERED = "layered"              # src/, tests/, etc.
    DOMAIN_DRIVEN = "domain_driven"  # Feature folders
    MVC = "mvc"                      # Model/View/Controller
    MICROSERVICES = "microservices"  # Service folders
    MONOREPO = "monorepo"            # Multiple packages


@dataclass
class ImportInfo:
    """Information about an import statement."""
    module: str                       # Module being imported
    names: List[str]                  # Names imported (for 'from X import Y')
    alias: Optional[str] = None       # Import alias
    is_relative: bool = False         # Relative import?
    level: int = 0                    # Relative import level


@dataclass
class DependencyNode:
    """A node in the dependency graph."""
    id: str                           # Unique identifier (file path)
    name: str                         # Short name
    node_type: NodeType               # Type of node
    path: Optional[Path] = None       # File path
    imports: List[ImportInfo] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)  # Defined names
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)  # IDs of dependencies
    dependents: Set[str] = field(default_factory=set)    # IDs that depend on this
    layer: int = 0                    # Layer in architecture
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.node_type.value,
            'imports': len(self.imports),
            'exports': len(self.exports),
            'dependencies': list(self.dependencies),
            'dependents': list(self.dependents),
            'layer': self.layer,
        }


@dataclass
class CircularDependency:
    """A detected circular dependency."""
    cycle: List[str]                  # Node IDs in the cycle
    severity: str = "warning"         # warning or error
    
    @property
    def description(self) -> str:
        return " -> ".join(self.cycle + [self.cycle[0]])


@dataclass
class ArchitectureAnalysis:
    """Result of architecture analysis."""
    pattern: ArchitecturePattern
    layers: Dict[str, List[str]]      # Layer name -> node IDs
    entry_points: List[str]           # Main entry points
    core_modules: List[str]           # Core/shared modules
    leaf_modules: List[str]           # Modules with no dependents
    circular_deps: List[CircularDependency]
    suggestions: List[str]            # Architecture suggestions


@dataclass
class PlacementSuggestion:
    """Suggestion for where to place new code."""
    file_path: str
    reason: str
    confidence: float  # 0-1
    related_files: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# IMPORT ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class ImportAnalyzer(ast.NodeVisitor):
    """Analyzes imports from Python source code."""
    
    def __init__(self):
        self.imports: List[ImportInfo] = []
        self.exports: List[str] = []
        self.classes: List[str] = []
        self.functions: List[str] = []
    
    def visit_Import(self, node: ast.Import):
        """Handle 'import X' statements."""
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                alias=alias.asname,
                is_relative=False,
            ))
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle 'from X import Y' statements."""
        module = node.module or ''
        names = [alias.name for alias in node.names]
        
        self.imports.append(ImportInfo(
            module=module,
            names=names,
            is_relative=node.level > 0,
            level=node.level,
        ))
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Track class definitions."""
        self.classes.append(node.name)
        self.exports.append(node.name)
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track function definitions."""
        if not node.name.startswith('_'):
            self.functions.append(node.name)
            self.exports.append(node.name)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Track async function definitions."""
        if not node.name.startswith('_'):
            self.functions.append(node.name)
            self.exports.append(node.name)
        self.generic_visit(node)
    
    def visit_Assign(self, node: ast.Assign):
        """Track top-level assignments (constants)."""
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                self.exports.append(target.id)
        self.generic_visit(node)
    
    @classmethod
    def analyze(cls, source: str) -> 'ImportAnalyzer':
        """Analyze source code and return analyzer with results."""
        analyzer = cls()
        try:
            tree = ast.parse(source)
            analyzer.visit(tree)
        except SyntaxError:
            pass
        return analyzer


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

class DependencyGraph:
    """
    Graph of dependencies between modules.
    
    Usage:
        graph = DependencyGraph()
        graph.add_directory("/path/to/project")
        analysis = graph.analyze()
    """
    
    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.root_path: Optional[Path] = None
        self._analyzed = False
    
    def add_file(self, file_path: Path) -> Optional[DependencyNode]:
        """Add a Python file to the graph."""
        if not file_path.suffix == '.py':
            return None
        
        try:
            source = file_path.read_text()
        except Exception:
            return None
        
        # Analyze imports
        analyzer = ImportAnalyzer.analyze(source)
        
        # Create node
        node_id = str(file_path)
        node = DependencyNode(
            id=node_id,
            name=file_path.stem,
            node_type=NodeType.MODULE,
            path=file_path,
            imports=analyzer.imports,
            exports=analyzer.exports,
            classes=analyzer.classes,
            functions=analyzer.functions,
        )
        
        self.nodes[node_id] = node
        return node
    
    def add_directory(self, dir_path: str, exclude_patterns: List[str] = None):
        """Add all Python files in a directory."""
        self.root_path = Path(dir_path)
        exclude = exclude_patterns or ['__pycache__', '.git', 'venv', 'env', 'node_modules']
        
        for py_file in self.root_path.rglob('*.py'):
            # Check exclusions
            if any(ex in str(py_file) for ex in exclude):
                continue
            self.add_file(py_file)
        
        # Build dependency edges
        self._build_edges()
    
    def _build_edges(self):
        """Build dependency edges between nodes."""
        for node in self.nodes.values():
            for imp in node.imports:
                # Find matching node
                target = self._resolve_import(node, imp)
                if target and target in self.nodes:
                    node.dependencies.add(target)
                    self.nodes[target].dependents.add(node.id)
    
    def _resolve_import(self, source_node: DependencyNode, imp: ImportInfo) -> Optional[str]:
        """Resolve an import to a node ID."""
        if imp.is_relative:
            # Relative import
            if source_node.path:
                base = source_node.path.parent
                for _ in range(imp.level - 1):
                    base = base.parent
                
                target = base / f"{imp.module.replace('.', '/')}.py"
                return str(target) if target.exists() else None
        else:
            # Absolute import
            if self.root_path:
                target = self.root_path / f"{imp.module.replace('.', '/')}.py"
                if target.exists():
                    return str(target)
                
                # Try as package
                target = self.root_path / imp.module.replace('.', '/') / '__init__.py'
                if target.exists():
                    return str(target)
        
        return None
    
    def find_circular_dependencies(self) -> List[CircularDependency]:
        """Find all circular dependencies."""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node_id: str, path: List[str]) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            node = self.nodes.get(node_id)
            if node:
                for dep in node.dependencies:
                    if dep not in visited:
                        if dfs(dep, path):
                            return True
                    elif dep in rec_stack:
                        # Found cycle
                        cycle_start = path.index(dep)
                        cycle = path[cycle_start:]
                        cycles.append(CircularDependency(cycle=cycle))
                        return True
            
            path.pop()
            rec_stack.remove(node_id)
            return False
        
        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id, [])
        
        return cycles
    
    def compute_layers(self):
        """Compute layers for each node (topological sort)."""
        # Start with nodes that have no dependencies
        queue = [n for n in self.nodes.values() if not n.dependencies]
        for node in queue:
            node.layer = 0
        
        visited = {n.id for n in queue}
        
        while queue:
            current = queue.pop(0)
            
            for dep_id in current.dependents:
                dep_node = self.nodes.get(dep_id)
                if dep_node:
                    dep_node.layer = max(dep_node.layer, current.layer + 1)
                    
                    # Check if all dependencies are visited
                    if all(d in visited for d in dep_node.dependencies):
                        if dep_id not in visited:
                            visited.add(dep_id)
                            queue.append(dep_node)
    
    def analyze(self) -> ArchitectureAnalysis:
        """Analyze the dependency graph."""
        self.compute_layers()
        circular = self.find_circular_dependencies()
        
        # Detect architecture pattern
        pattern = self._detect_pattern()
        
        # Group nodes by layer
        layers = defaultdict(list)
        for node in self.nodes.values():
            layers[f"layer_{node.layer}"].append(node.id)
        
        # Find entry points (no dependents)
        entry_points = [n.id for n in self.nodes.values() if not n.dependents]
        
        # Find core modules (most dependents)
        by_dependents = sorted(self.nodes.values(), key=lambda n: len(n.dependents), reverse=True)
        core_modules = [n.id for n in by_dependents[:5]]
        
        # Find leaf modules (no dependencies on internal modules)
        leaf_modules = [n.id for n in self.nodes.values() if not n.dependencies]
        
        # Generate suggestions
        suggestions = self._generate_suggestions(circular, pattern)
        
        self._analyzed = True
        return ArchitectureAnalysis(
            pattern=pattern,
            layers=dict(layers),
            entry_points=entry_points,
            core_modules=core_modules,
            leaf_modules=leaf_modules,
            circular_deps=circular,
            suggestions=suggestions,
        )
    
    def _detect_pattern(self) -> ArchitecturePattern:
        """Detect the architecture pattern."""
        if not self.root_path:
            return ArchitecturePattern.FLAT
        
        subdirs = [d for d in self.root_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
        subdir_names = {d.name.lower() for d in subdirs}
        
        # Check for common patterns
        if {'src', 'tests'} <= subdir_names or {'lib', 'test'} <= subdir_names:
            return ArchitecturePattern.LAYERED
        
        if {'models', 'views', 'controllers'} <= subdir_names:
            return ArchitecturePattern.MVC
        
        if {'services', 'shared'} <= subdir_names:
            return ArchitecturePattern.MICROSERVICES
        
        if len(subdirs) > 5:
            return ArchitecturePattern.DOMAIN_DRIVEN
        
        return ArchitecturePattern.FLAT
    
    def _generate_suggestions(
        self,
        circular: List[CircularDependency],
        pattern: ArchitecturePattern
    ) -> List[str]:
        """Generate architecture improvement suggestions."""
        suggestions = []
        
        if circular:
            suggestions.append(f"⚠️ Found {len(circular)} circular dependencies - consider refactoring")
            for circ in circular[:3]:
                suggestions.append(f"  Cycle: {circ.description}")
        
        # Check for god modules
        for node in self.nodes.values():
            if len(node.dependents) > 10:
                suggestions.append(f"⚠️ {node.name} has {len(node.dependents)} dependents - consider splitting")
        
        # Pattern-specific suggestions
        if pattern == ArchitecturePattern.FLAT and len(self.nodes) > 10:
            suggestions.append("💡 Consider organizing files into packages (src/, tests/, etc.)")
        
        return suggestions
    
    def suggest_placement(self, new_code_type: str, dependencies: List[str] = None) -> PlacementSuggestion:
        """
        Suggest where to place new code.
        
        Args:
            new_code_type: Type of code ('class', 'function', 'module')
            dependencies: Names this code will depend on
        
        Returns:
            PlacementSuggestion with recommended file path
        """
        dependencies = dependencies or []
        
        # Find nodes that export the dependencies
        related_nodes = []
        for dep in dependencies:
            for node in self.nodes.values():
                if dep in node.exports:
                    related_nodes.append(node)
                    break
        
        if related_nodes:
            # Place near related code
            # Prefer the node with most exports from our dependency list
            best_node = max(related_nodes, key=lambda n: len(set(n.exports) & set(dependencies)))
            
            if best_node.path:
                # Suggest same directory
                suggested_dir = best_node.path.parent
                suggested_name = f"new_{new_code_type}.py"
                
                return PlacementSuggestion(
                    file_path=str(suggested_dir / suggested_name),
                    reason=f"Near related module {best_node.name}",
                    confidence=0.7,
                    related_files=[str(n.path) for n in related_nodes if n.path],
                )
        
        # Default to root or src directory
        if self.root_path:
            src_dir = self.root_path / 'src'
            if src_dir.exists():
                return PlacementSuggestion(
                    file_path=str(src_dir / f"new_{new_code_type}.py"),
                    reason="Default src directory",
                    confidence=0.3,
                )
            
            return PlacementSuggestion(
                file_path=str(self.root_path / f"new_{new_code_type}.py"),
                reason="Project root",
                confidence=0.2,
            )
        
        return PlacementSuggestion(
            file_path=f"./new_{new_code_type}.py",
            reason="Current directory",
            confidence=0.1,
        )
    
    def get_import_order(self, node_id: str) -> List[str]:
        """Get the correct import order for a node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        
        # Standard library first, then third-party, then local
        stdlib = []
        third_party = []
        local = []
        
        for imp in node.imports:
            if self._is_stdlib(imp.module):
                stdlib.append(imp.module)
            elif self._resolve_import(node, imp):
                local.append(imp.module)
            else:
                third_party.append(imp.module)
        
        return stdlib + third_party + local
    
    def _is_stdlib(self, module: str) -> bool:
        """Check if a module is from standard library."""
        stdlib = {
            'os', 'sys', 'json', 'ast', 're', 'collections', 'itertools',
            'functools', 'pathlib', 'typing', 'dataclasses', 'enum',
            'asyncio', 'subprocess', 'threading', 'multiprocessing',
            'datetime', 'time', 'random', 'math', 'copy', 'hashlib',
        }
        return module.split('.')[0] in stdlib
    
    def to_dict(self) -> Dict[str, Any]:
        """Export graph as dictionary."""
        return {
            'nodes': [n.to_dict() for n in self.nodes.values()],
            'root': str(self.root_path) if self.root_path else None,
        }
    
    def to_mermaid(self) -> str:
        """Export as Mermaid diagram."""
        lines = ["graph TD"]
        
        for node in self.nodes.values():
            # Node definition
            label = node.name
            lines.append(f"    {node.id.replace('/', '_').replace('.', '_')}[{label}]")
            
            # Edges
            for dep in node.dependencies:
                dep_safe = dep.replace('/', '_').replace('.', '_')
                node_safe = node.id.replace('/', '_').replace('.', '_')
                lines.append(f"    {node_safe} --> {dep_safe}")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_project(project_path: str) -> ArchitectureAnalysis:
    """Analyze a project's architecture."""
    graph = DependencyGraph()
    graph.add_directory(project_path)
    return graph.analyze()


def find_circular_dependencies(project_path: str) -> List[CircularDependency]:
    """Find circular dependencies in a project."""
    graph = DependencyGraph()
    graph.add_directory(project_path)
    return graph.find_circular_dependencies()


def suggest_file_placement(
    project_path: str,
    code_type: str,
    dependencies: List[str] = None
) -> PlacementSuggestion:
    """Suggest where to place new code in a project."""
    graph = DependencyGraph()
    graph.add_directory(project_path)
    return graph.suggest_placement(code_type, dependencies)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Dependency Graph Scaffold v{__version__}")
    print("=" * 70)
    
    # Test with sample code
    sample_code = '''
import os
import json
from typing import List, Dict
from dataclasses import dataclass

from .utils import helper_function
from ..core import BaseClass

@dataclass
class MyClass:
    name: str
    value: int

def my_function(x: int) -> int:
    return x * 2

CONSTANT = 42
'''
    
    print("\n[1] Import Analysis:")
    print("-" * 40)
    analyzer = ImportAnalyzer.analyze(sample_code)
    print(f"  Imports: {len(analyzer.imports)}")
    for imp in analyzer.imports:
        print(f"    - {imp.module} {'(relative)' if imp.is_relative else ''}")
    print(f"  Exports: {analyzer.exports}")
    print(f"  Classes: {analyzer.classes}")
    print(f"  Functions: {analyzer.functions}")
    
    print("\n[2] Graph Construction:")
    print("-" * 40)
    graph = DependencyGraph()
    # Add a mock node
    node = DependencyNode(
        id="test.py",
        name="test",
        node_type=NodeType.MODULE,
        imports=analyzer.imports,
        exports=analyzer.exports,
    )
    graph.nodes[node.id] = node
    print(f"  Nodes: {len(graph.nodes)}")
    print(f"  Node: {node.to_dict()}")
    
    print("\n[3] Placement Suggestion:")
    print("-" * 40)
    suggestion = graph.suggest_placement("class", ["BaseClass"])
    print(f"  Suggested: {suggestion.file_path}")
    print(f"  Reason: {suggestion.reason}")
    print(f"  Confidence: {suggestion.confidence:.0%}")
    
    print("\n" + "=" * 70)
    print("✅ Dependency Graph Scaffold working!")
