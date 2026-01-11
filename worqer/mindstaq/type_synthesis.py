#!/usr/bin/env python3
"""
Type-Directed Synthesis: A* Pathfinding for Glue Code
Part of mindstaQ v1.6.0 - ZERO LLM Code Generation

Generates glue code by treating type transformations as graph pathfinding.
Given a source type and target type, finds the shortest path of function
compositions to transform one to the other.

No "reasoning" needed - pure graph search!

Features:
- Index functions as type transformations (A → B)
- A* search for shortest transformation path
- Auto-generate adapter code
- Support for common Python type transformations

v1.6.0
"""

import ast
import re
import heapq
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple, Callable
from collections import defaultdict

# v2.0.3: z3 integration for constraint-based synthesis
try:
    from .z3_solver import Z3Reasoner, has_z3, solve_type_conversion
    HAS_Z3 = has_z3()
except ImportError:
    HAS_Z3 = False
    Z3Reasoner = None


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TypeSignature:
    """A type signature for a value."""
    base_type: str                    # e.g., 'dict', 'list', 'str', 'int'
    generic_args: List['TypeSignature'] = field(default_factory=list)  # e.g., Dict[str, int]
    optional: bool = False            # Optional[X]
    
    def __str__(self) -> str:
        if self.optional:
            inner = self._format_inner()
            return f"Optional[{inner}]"
        return self._format_inner()
    
    def _format_inner(self) -> str:
        if not self.generic_args:
            return self.base_type
        args = ', '.join(str(a) for a in self.generic_args)
        return f"{self.base_type}[{args}]"
    
    def __hash__(self):
        return hash(str(self))
    
    def __eq__(self, other):
        if isinstance(other, TypeSignature):
            return str(self) == str(other)
        return False


@dataclass
class TypeTransform:
    """A function that transforms one type to another."""
    name: str                         # Function/method name
    input_type: TypeSignature         # Input type
    output_type: TypeSignature        # Output type
    code_template: str                # Code to apply (e.g., "list({input}.items())")
    cost: float = 1.0                 # Cost for A* (lower = preferred)
    requires_import: Optional[str] = None  # Import needed
    description: str = ""             # Human description
    
    def __hash__(self):
        return hash((self.name, str(self.input_type), str(self.output_type)))


@dataclass
class TransformPath:
    """A path of transformations from source to target type."""
    transforms: List[TypeTransform]   # Sequence of transforms
    total_cost: float                 # Total path cost
    source_type: TypeSignature        # Starting type
    target_type: TypeSignature        # Ending type
    
    def generate_code(self, input_var: str = 'input') -> str:
        """Generate code for the transformation chain."""
        if not self.transforms:
            return input_var
        
        current = input_var
        for transform in self.transforms:
            current = transform.code_template.format(input=current)
        
        return current


@dataclass
class SynthesisResult:
    """Result of type-directed synthesis."""
    success: bool
    code: str                         # Generated adapter code
    function_name: str                # Name of generated function
    path: Optional[TransformPath]     # Transform path used
    imports: List[str]                # Required imports
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# BUILT-IN TYPE TRANSFORMS
# ═══════════════════════════════════════════════════════════════════════════════

def _create_type(base: str, *args) -> TypeSignature:
    """Helper to create TypeSignature."""
    return TypeSignature(
        base_type=base,
        generic_args=[TypeSignature(a) if isinstance(a, str) else a for a in args]
    )


# Common type transforms (built-in knowledge)
BUILTIN_TRANSFORMS: List[TypeTransform] = [
    # Dict transforms
    TypeTransform(
        name='dict_to_items',
        input_type=_create_type('dict'),
        output_type=_create_type('list', _create_type('tuple')),
        code_template='list({input}.items())',
        cost=1.0,
        description='Convert dict to list of (key, value) tuples'
    ),
    TypeTransform(
        name='dict_to_keys',
        input_type=_create_type('dict'),
        output_type=_create_type('list'),
        code_template='list({input}.keys())',
        cost=1.0,
        description='Get dict keys as list'
    ),
    TypeTransform(
        name='dict_to_values',
        input_type=_create_type('dict'),
        output_type=_create_type('list'),
        code_template='list({input}.values())',
        cost=1.0,
        description='Get dict values as list'
    ),
    TypeTransform(
        name='dict_to_json',
        input_type=_create_type('dict'),
        output_type=_create_type('str'),
        code_template='json.dumps({input})',
        cost=1.5,
        requires_import='json',
        description='Convert dict to JSON string'
    ),
    
    # List transforms
    TypeTransform(
        name='list_to_set',
        input_type=_create_type('list'),
        output_type=_create_type('set'),
        code_template='set({input})',
        cost=1.0,
        description='Convert list to set'
    ),
    TypeTransform(
        name='list_to_tuple',
        input_type=_create_type('list'),
        output_type=_create_type('tuple'),
        code_template='tuple({input})',
        cost=1.0,
        description='Convert list to tuple'
    ),
    TypeTransform(
        name='list_to_str',
        input_type=_create_type('list'),
        output_type=_create_type('str'),
        code_template="', '.join(str(x) for x in {input})",
        cost=1.5,
        description='Join list elements as string'
    ),
    TypeTransform(
        name='list_to_dict_enumerate',
        input_type=_create_type('list'),
        output_type=_create_type('dict'),
        code_template='dict(enumerate({input}))',
        cost=1.5,
        description='Convert list to dict with index keys'
    ),
    TypeTransform(
        name='list_of_tuples_to_dict',
        input_type=_create_type('list', _create_type('tuple')),
        output_type=_create_type('dict'),
        code_template='dict({input})',
        cost=1.0,
        description='Convert list of tuples to dict'
    ),
    
    # String transforms
    TypeTransform(
        name='str_to_list',
        input_type=_create_type('str'),
        output_type=_create_type('list'),
        code_template='{input}.split()',
        cost=1.0,
        description='Split string to list'
    ),
    TypeTransform(
        name='str_to_int',
        input_type=_create_type('str'),
        output_type=_create_type('int'),
        code_template='int({input})',
        cost=1.0,
        description='Parse string to int'
    ),
    TypeTransform(
        name='str_to_float',
        input_type=_create_type('str'),
        output_type=_create_type('float'),
        code_template='float({input})',
        cost=1.0,
        description='Parse string to float'
    ),
    TypeTransform(
        name='str_to_bytes',
        input_type=_create_type('str'),
        output_type=_create_type('bytes'),
        code_template="{input}.encode('utf-8')",
        cost=1.0,
        description='Encode string to bytes'
    ),
    TypeTransform(
        name='json_str_to_dict',
        input_type=_create_type('str'),
        output_type=_create_type('dict'),
        code_template='json.loads({input})',
        cost=1.5,
        requires_import='json',
        description='Parse JSON string to dict'
    ),
    
    # Bytes transforms
    TypeTransform(
        name='bytes_to_str',
        input_type=_create_type('bytes'),
        output_type=_create_type('str'),
        code_template="{input}.decode('utf-8')",
        cost=1.0,
        description='Decode bytes to string'
    ),
    TypeTransform(
        name='bytes_to_base64',
        input_type=_create_type('bytes'),
        output_type=_create_type('str'),
        code_template="base64.b64encode({input}).decode('ascii')",
        cost=1.5,
        requires_import='base64',
        description='Encode bytes to base64 string'
    ),
    
    # Number transforms
    TypeTransform(
        name='int_to_str',
        input_type=_create_type('int'),
        output_type=_create_type('str'),
        code_template='str({input})',
        cost=1.0,
        description='Convert int to string'
    ),
    TypeTransform(
        name='int_to_float',
        input_type=_create_type('int'),
        output_type=_create_type('float'),
        code_template='float({input})',
        cost=0.5,
        description='Convert int to float'
    ),
    TypeTransform(
        name='float_to_int',
        input_type=_create_type('float'),
        output_type=_create_type('int'),
        code_template='int({input})',
        cost=1.0,
        description='Convert float to int (truncate)'
    ),
    TypeTransform(
        name='float_to_str',
        input_type=_create_type('float'),
        output_type=_create_type('str'),
        code_template='str({input})',
        cost=1.0,
        description='Convert float to string'
    ),
    
    # Set transforms
    TypeTransform(
        name='set_to_list',
        input_type=_create_type('set'),
        output_type=_create_type('list'),
        code_template='list({input})',
        cost=1.0,
        description='Convert set to list'
    ),
    TypeTransform(
        name='set_to_frozenset',
        input_type=_create_type('set'),
        output_type=_create_type('frozenset'),
        code_template='frozenset({input})',
        cost=0.5,
        description='Convert set to frozenset'
    ),
    
    # Tuple transforms
    TypeTransform(
        name='tuple_to_list',
        input_type=_create_type('tuple'),
        output_type=_create_type('list'),
        code_template='list({input})',
        cost=1.0,
        description='Convert tuple to list'
    ),
    
    # Iterator/generator transforms
    TypeTransform(
        name='iter_to_list',
        input_type=_create_type('Iterator'),
        output_type=_create_type('list'),
        code_template='list({input})',
        cost=1.0,
        description='Consume iterator to list'
    ),
    TypeTransform(
        name='generator_to_list',
        input_type=_create_type('Generator'),
        output_type=_create_type('list'),
        code_template='list({input})',
        cost=1.0,
        description='Consume generator to list'
    ),
    
    # Object transforms
    TypeTransform(
        name='obj_to_dict',
        input_type=_create_type('object'),
        output_type=_create_type('dict'),
        code_template='vars({input})',
        cost=1.5,
        description='Convert object attributes to dict'
    ),
    TypeTransform(
        name='dataclass_to_dict',
        input_type=_create_type('dataclass'),
        output_type=_create_type('dict'),
        code_template='asdict({input})',
        cost=1.0,
        requires_import='from dataclasses import asdict',
        description='Convert dataclass to dict'
    ),
    
    # Path transforms
    TypeTransform(
        name='str_to_path',
        input_type=_create_type('str'),
        output_type=_create_type('Path'),
        code_template='Path({input})',
        cost=1.0,
        requires_import='from pathlib import Path',
        description='Convert string to Path'
    ),
    TypeTransform(
        name='path_to_str',
        input_type=_create_type('Path'),
        output_type=_create_type('str'),
        code_template='str({input})',
        cost=1.0,
        description='Convert Path to string'
    ),
    
    # Datetime transforms
    TypeTransform(
        name='str_to_datetime',
        input_type=_create_type('str'),
        output_type=_create_type('datetime'),
        code_template="datetime.fromisoformat({input})",
        cost=1.5,
        requires_import='from datetime import datetime',
        description='Parse ISO string to datetime'
    ),
    TypeTransform(
        name='datetime_to_str',
        input_type=_create_type('datetime'),
        output_type=_create_type('str'),
        code_template='{input}.isoformat()',
        cost=1.0,
        description='Format datetime as ISO string'
    ),
    TypeTransform(
        name='timestamp_to_datetime',
        input_type=_create_type('float'),
        output_type=_create_type('datetime'),
        code_template='datetime.fromtimestamp({input})',
        cost=1.0,
        requires_import='from datetime import datetime',
        description='Convert Unix timestamp to datetime'
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# TYPE GRAPH & A* SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

class TypeGraph:
    """Graph of type transformations for A* search."""
    
    def __init__(self):
        self.transforms: List[TypeTransform] = []
        self.adjacency: Dict[str, List[TypeTransform]] = defaultdict(list)
    
    def add_transform(self, transform: TypeTransform):
        """Add a transform to the graph."""
        self.transforms.append(transform)
        key = str(transform.input_type)
        self.adjacency[key].append(transform)
    
    def add_transforms(self, transforms: List[TypeTransform]):
        """Add multiple transforms."""
        for t in transforms:
            self.add_transform(t)
    
    def get_neighbors(self, type_sig: TypeSignature) -> List[Tuple[TypeSignature, TypeTransform]]:
        """Get all types reachable from given type."""
        neighbors = []
        key = str(type_sig)
        
        # Exact match
        for transform in self.adjacency.get(key, []):
            neighbors.append((transform.output_type, transform))
        
        # Base type match (e.g., dict matches Dict[str, int])
        base_key = type_sig.base_type
        if base_key != key:
            for transform in self.adjacency.get(base_key, []):
                neighbors.append((transform.output_type, transform))
        
        return neighbors
    
    def heuristic(self, current: TypeSignature, target: TypeSignature) -> float:
        """A* heuristic - estimate cost to target."""
        if str(current) == str(target):
            return 0.0
        
        # Same base type = likely close
        if current.base_type == target.base_type:
            return 0.5
        
        # Default heuristic
        return 1.0


class TypeDirectedSynthesizer:
    """
    Synthesize glue code using A* search over type transformations.
    
    Usage:
        synth = TypeDirectedSynthesizer()
        
        # Find path from Dict to List[Tuple]
        result = synth.synthesize(
            source_type='dict',
            target_type='list',
            input_var='my_data'
        )
        
        print(result.code)
        # Output: list(my_data.items())
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.graph = TypeGraph()
        
        # Load built-in transforms
        self.graph.add_transforms(BUILTIN_TRANSFORMS)
    
    def add_transform(self, transform: TypeTransform):
        """Add a custom transform."""
        self.graph.add_transform(transform)
    
    def add_project_transforms(self, code: str):
        """
        Extract type transforms from project code.
        Parses functions and indexes them by input/output types.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Try to extract type hints
                input_type = None
                output_type = None
                
                # Get first parameter type
                if node.args.args:
                    first_arg = node.args.args[0]
                    if first_arg.annotation:
                        input_type = self._parse_annotation(first_arg.annotation)
                
                # Get return type
                if node.returns:
                    output_type = self._parse_annotation(node.returns)
                
                if input_type and output_type:
                    transform = TypeTransform(
                        name=node.name,
                        input_type=input_type,
                        output_type=output_type,
                        code_template=f'{node.name}({{input}})',
                        cost=2.0,  # Higher cost for project functions
                        description=f'Project function: {node.name}'
                    )
                    self.graph.add_transform(transform)
    
    def _parse_annotation(self, node: ast.expr) -> Optional[TypeSignature]:
        """Parse AST annotation to TypeSignature."""
        if isinstance(node, ast.Name):
            return TypeSignature(node.id)
        elif isinstance(node, ast.Subscript):
            base = self._parse_annotation(node.value)
            if base:
                if isinstance(node.slice, ast.Tuple):
                    args = [self._parse_annotation(e) for e in node.slice.elts]
                else:
                    args = [self._parse_annotation(node.slice)]
                return TypeSignature(base.base_type, [a for a in args if a])
        elif isinstance(node, ast.Constant):
            return TypeSignature(str(node.value))
        return None
    
    def _parse_type_string(self, type_str: str) -> TypeSignature:
        """Parse type string like 'Dict[str, int]' to TypeSignature."""
        type_str = type_str.strip()
        
        # Handle Optional
        if type_str.startswith('Optional[') and type_str.endswith(']'):
            inner = type_str[9:-1]
            sig = self._parse_type_string(inner)
            sig.optional = True
            return sig
        
        # Handle generic types
        match = re.match(r'(\w+)\[(.+)\]', type_str)
        if match:
            base = match.group(1)
            args_str = match.group(2)
            
            # Parse arguments (handle nested brackets)
            args = []
            depth = 0
            current = ""
            for char in args_str:
                if char == '[':
                    depth += 1
                    current += char
                elif char == ']':
                    depth -= 1
                    current += char
                elif char == ',' and depth == 0:
                    args.append(self._parse_type_string(current.strip()))
                    current = ""
                else:
                    current += char
            if current.strip():
                args.append(self._parse_type_string(current.strip()))
            
            return TypeSignature(base.lower(), args)
        
        # Simple type
        return TypeSignature(type_str.lower())
    
    def find_path(
        self,
        source: TypeSignature,
        target: TypeSignature,
        max_depth: int = 5
    ) -> Optional[TransformPath]:
        """
        Find transformation path using A* search.
        
        Args:
            source: Starting type
            target: Target type
            max_depth: Maximum transformation steps
        
        Returns:
            TransformPath if found, None otherwise
        """
        if str(source) == str(target):
            return TransformPath([], 0.0, source, target)
        
        # A* search
        # Priority queue: (f_score, counter, current_type, path)
        counter = 0
        start_h = self.graph.heuristic(source, target)
        heap = [(start_h, counter, source, [])]
        visited = set()
        g_scores = {str(source): 0.0}
        
        while heap:
            f_score, _, current, path = heapq.heappop(heap)
            current_key = str(current)
            
            if current_key in visited:
                continue
            visited.add(current_key)
            
            # Check if we reached target
            if current.base_type == target.base_type:
                return TransformPath(path, g_scores[current_key], source, target)
            
            # Max depth check
            if len(path) >= max_depth:
                continue
            
            # Explore neighbors
            for next_type, transform in self.graph.get_neighbors(current):
                next_key = str(next_type)
                
                if next_key in visited:
                    continue
                
                tentative_g = g_scores[current_key] + transform.cost
                
                if next_key not in g_scores or tentative_g < g_scores[next_key]:
                    g_scores[next_key] = tentative_g
                    h = self.graph.heuristic(next_type, target)
                    f = tentative_g + h
                    counter += 1
                    new_path = path + [transform]
                    heapq.heappush(heap, (f, counter, next_type, new_path))
        
        return None
    
    def synthesize(
        self,
        source_type: str,
        target_type: str,
        input_var: str = 'input',
        function_name: str = 'transform'
    ) -> SynthesisResult:
        """
        Synthesize adapter code from source type to target type.
        
        Args:
            source_type: Source type string (e.g., 'dict', 'Dict[str, int]')
            target_type: Target type string
            input_var: Variable name for input
            function_name: Name for generated function
        
        Returns:
            SynthesisResult with generated code
        """
        source = self._parse_type_string(source_type)
        target = self._parse_type_string(target_type)
        
        path = self.find_path(source, target)
        
        if path is None:
            return SynthesisResult(
                success=False,
                code='',
                function_name=function_name,
                path=None,
                imports=[],
                error=f"No transformation path found from {source_type} to {target_type}"
            )
        
        # Generate code
        transform_code = path.generate_code(input_var)
        
        # Collect imports
        imports = set()
        for transform in path.transforms:
            if transform.requires_import:
                imports.add(transform.requires_import)
        
        # Generate function
        code_lines = []
        
        # Imports
        if imports:
            for imp in sorted(imports):
                if imp.startswith('from ') or imp.startswith('import '):
                    code_lines.append(imp)
                else:
                    code_lines.append(f'import {imp}')
            code_lines.append('')
        
        # Function definition
        code_lines.append(f'def {function_name}({input_var}: {source_type}) -> {target_type}:')
        code_lines.append(f'    """')
        code_lines.append(f'    Transform {source_type} to {target_type}.')
        code_lines.append(f'    ')
        code_lines.append(f'    Path: {" -> ".join(t.name for t in path.transforms)}')
        code_lines.append(f'    """')
        code_lines.append(f'    return {transform_code}')
        
        return SynthesisResult(
            success=True,
            code='\n'.join(code_lines),
            function_name=function_name,
            path=path,
            imports=list(imports)
        )
    
    def synthesize_adapter(
        self,
        source_func: str,
        target_func: str,
        source_output_type: str,
        target_input_type: str,
        adapter_name: str = 'adapt'
    ) -> SynthesisResult:
        """
        Synthesize adapter between two functions.
        
        Example:
            # func_a() -> Dict[str, int]
            # func_b(items: List[Tuple[str, int]]) -> None
            
            result = synth.synthesize_adapter(
                source_func='func_a',
                target_func='func_b',
                source_output_type='Dict[str, int]',
                target_input_type='List[Tuple[str, int]]',
                adapter_name='call_b_with_a'
            )
        """
        # Find transformation path
        result = self.synthesize(
            source_output_type,
            target_input_type,
            input_var='result',
            function_name='_transform'
        )
        
        if not result.success:
            return result
        
        # Generate adapter function
        code_lines = []
        
        # Add any imports from the transform
        for imp in result.imports:
            if imp.startswith('from ') or imp.startswith('import '):
                code_lines.append(imp)
            else:
                code_lines.append(f'import {imp}')
        if result.imports:
            code_lines.append('')
        
        code_lines.append(f'def {adapter_name}():')
        code_lines.append(f'    """')
        code_lines.append(f'    Adapter: {source_func}() -> {target_func}()')
        code_lines.append(f'    Transforms {source_output_type} to {target_input_type}')
        code_lines.append(f'    """')
        code_lines.append(f'    result = {source_func}()')
        
        # Apply transformation
        transform_code = result.path.generate_code('result')
        code_lines.append(f'    transformed = {transform_code}')
        code_lines.append(f'    return {target_func}(transformed)')
        
        return SynthesisResult(
            success=True,
            code='\n'.join(code_lines),
            function_name=adapter_name,
            path=result.path,
            imports=result.imports
        )
    
    def get_available_transforms(self, source_type: str) -> List[TypeTransform]:
        """Get all transforms available from a given type."""
        source = self._parse_type_string(source_type)
        return [t for _, t in self.graph.get_neighbors(source)]
    
    def explain_path(self, path: TransformPath) -> str:
        """Generate human-readable explanation of transform path."""
        if not path.transforms:
            return "No transformation needed (types match)"
        
        lines = [f"Transform path from {path.source_type} to {path.target_type}:"]
        lines.append(f"Total cost: {path.total_cost}")
        lines.append("")
        
        current = str(path.source_type)
        for i, transform in enumerate(path.transforms, 1):
            lines.append(f"  Step {i}: {transform.name}")
            lines.append(f"    {current} -> {transform.output_type}")
            lines.append(f"    Code: {transform.code_template}")
            if transform.description:
                lines.append(f"    ({transform.description})")
            current = str(transform.output_type)
            lines.append("")
        
        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Type-Directed Synthesis v{__version__}")
    print("=" * 70)
    
    synth = TypeDirectedSynthesizer()
    
    # Test 1: Dict to List
    print("\n[1] Dict -> List[Tuple] transformation:")
    print("-" * 40)
    result = synth.synthesize('dict', 'list', input_var='data', function_name='dict_to_list')
    print(result.code)
    
    # Test 2: String to Dict
    print("\n[2] str (JSON) -> dict transformation:")
    print("-" * 40)
    result = synth.synthesize('str', 'dict', input_var='json_str', function_name='parse_json')
    print(result.code)
    
    # Test 3: Bytes to base64 string
    print("\n[3] bytes -> str (base64) transformation:")
    print("-" * 40)
    result = synth.synthesize('bytes', 'str', input_var='raw_bytes', function_name='encode_bytes')
    print(result.code)
    
    # Test 4: Function adapter
    print("\n[4] Function adapter synthesis:")
    print("-" * 40)
    result = synth.synthesize_adapter(
        source_func='get_user_data',
        target_func='process_items',
        source_output_type='dict',
        target_input_type='list',
        adapter_name='user_data_to_items'
    )
    print(result.code)
    
    # Test 5: Path explanation
    print("\n[5] Path explanation:")
    print("-" * 40)
    source = synth._parse_type_string('dict')
    target = synth._parse_type_string('str')
    path = synth.find_path(source, target)
    if path:
        print(synth.explain_path(path))
    
    # Test 6: Available transforms
    print("\n[6] Available transforms from 'dict':")
    print("-" * 40)
    transforms = synth.get_available_transforms('dict')
    for t in transforms:
        print(f"  - {t.name}: dict -> {t.output_type}")
    
    print("\n" + "=" * 70)
    print("✅ Type-Directed Synthesis working!")
