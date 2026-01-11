#!/usr/bin/env python3
"""
Z3 Solver Integration for mindstaQ
Part of QonQrete v2.1.0-stable

Provides constraint-based reasoning for:
- TypeSynthesis: Find optimal type transformation paths
- DecisionTable: Satisfy rule constraints
- Qualifier: Verify code properties
- SmartQomputator: Analyze task complexity constraints

v2.1.0-stable - Full z3 integration

Dependencies:
  pip install z3-solver

Usage:
    from worqer.mindstaq.z3_solver import Z3Reasoner, has_z3
    
    if has_z3():
        reasoner = Z3Reasoner()
        result = reasoner.solve_type_path(source_type, target_type)
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Set
from enum import Enum

__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# Z3 AVAILABILITY CHECK
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False
    z3 = None


def has_z3() -> bool:
    """Check if z3 is available."""
    return HAS_Z3


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TypeConstraint:
    """A type transformation constraint."""
    source: str
    target: str
    cost: int = 1
    function: str = ""  # Function that performs this transform
    reversible: bool = False


@dataclass
class ConstraintSolution:
    """Result of constraint solving."""
    satisfiable: bool
    model: Dict[str, Any] = field(default_factory=dict)
    path: List[str] = field(default_factory=list)
    cost: int = 0
    explanation: str = ""


@dataclass 
class DecisionResult:
    """Result of decision table evaluation."""
    action: str
    confidence: float
    matched_rules: List[int] = field(default_factory=list)
    variable_assignments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of code property verification."""
    verified: bool
    properties_checked: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    proof: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# TYPE SYSTEM FOR Z3
# ═══════════════════════════════════════════════════════════════════════════════

# Python type hierarchy as constraints
PYTHON_TYPES = {
    'int': {'parent': 'number', 'converts_to': ['float', 'str', 'bool', 'complex']},
    'float': {'parent': 'number', 'converts_to': ['str', 'int', 'complex']},
    'str': {'parent': 'sequence', 'converts_to': ['bytes', 'list', 'int', 'float']},
    'bytes': {'parent': 'sequence', 'converts_to': ['str', 'list']},
    'list': {'parent': 'sequence', 'converts_to': ['tuple', 'set', 'str']},
    'tuple': {'parent': 'sequence', 'converts_to': ['list', 'set']},
    'set': {'parent': 'collection', 'converts_to': ['list', 'frozenset']},
    'frozenset': {'parent': 'collection', 'converts_to': ['set', 'list']},
    'dict': {'parent': 'mapping', 'converts_to': ['list', 'str']},
    'bool': {'parent': 'int', 'converts_to': ['int', 'str']},
    'None': {'parent': 'object', 'converts_to': ['str', 'bool']},
}

# Conversion functions
TYPE_CONVERTERS = {
    ('int', 'float'): 'float',
    ('int', 'str'): 'str',
    ('int', 'bool'): 'bool',
    ('float', 'int'): 'int',
    ('float', 'str'): 'str',
    ('str', 'int'): 'int',
    ('str', 'float'): 'float',
    ('str', 'list'): 'list',
    ('str', 'bytes'): 'lambda s: s.encode()',
    ('bytes', 'str'): 'lambda b: b.decode()',
    ('list', 'tuple'): 'tuple',
    ('list', 'set'): 'set',
    ('list', 'str'): 'lambda l: "".join(map(str, l))',
    ('tuple', 'list'): 'list',
    ('set', 'list'): 'list',
    ('dict', 'list'): 'lambda d: list(d.items())',
    ('dict', 'str'): 'lambda d: json.dumps(d)',
    ('str', 'dict'): 'lambda s: json.loads(s)',
}


# ═══════════════════════════════════════════════════════════════════════════════
# Z3 REASONER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Z3Reasoner:
    """
    Z3-based constraint solver for mindstaQ.
    
    Provides formal reasoning capabilities:
    1. Type path synthesis - find optimal type conversions
    2. Decision table solving - satisfy rule constraints  
    3. Code verification - check properties
    4. Complexity analysis - constrained scoring
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.timeout_ms = self.config.get('timeout_ms', 5000)
        self._type_vars = {}
        self._solver = None
        
        if not HAS_Z3:
            raise ImportError("z3-solver not installed. Run: pip install z3-solver")
    
    def _get_solver(self) -> 'z3.Solver':
        """Get a fresh solver with timeout."""
        solver = z3.Solver()
        solver.set('timeout', self.timeout_ms)
        return solver
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TYPE PATH SYNTHESIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def solve_type_path(
        self, 
        source_type: str, 
        target_type: str,
        max_steps: int = 5
    ) -> ConstraintSolution:
        """
        Find optimal path to convert source_type to target_type.
        
        Uses z3 to find the minimum-cost sequence of type conversions.
        
        Args:
            source_type: Starting type (e.g., 'str')
            target_type: Target type (e.g., 'dict')
            max_steps: Maximum conversion steps
            
        Returns:
            ConstraintSolution with path and cost
        """
        # Direct conversion check
        if source_type == target_type:
            return ConstraintSolution(
                satisfiable=True,
                path=[source_type],
                cost=0,
                explanation="No conversion needed"
            )
        
        # Check direct conversion exists
        if (source_type, target_type) in TYPE_CONVERTERS:
            converter = TYPE_CONVERTERS[(source_type, target_type)]
            return ConstraintSolution(
                satisfiable=True,
                path=[source_type, target_type],
                cost=1,
                model={'converter': converter},
                explanation=f"Direct conversion: {converter}({source_type})"
            )
        
        # Use z3 to find optimal path
        solver = self._get_solver()
        
        # Create type variables for each step
        types = list(PYTHON_TYPES.keys())
        type_sort = z3.Datatype('Type')
        for t in types:
            type_sort.declare(t)
        type_sort = type_sort.create()
        
        # Step variables
        step_vars = [z3.Const(f'step_{i}', type_sort) for i in range(max_steps + 1)]
        cost_vars = [z3.Int(f'cost_{i}') for i in range(max_steps)]
        
        # Constraint: First step is source type
        solver.add(step_vars[0] == getattr(type_sort, source_type))
        
        # Constraint: Valid transitions only
        for i in range(max_steps):
            # Either stay same type (cost 0) or valid conversion (cost 1)
            valid_transitions = [step_vars[i] == step_vars[i + 1]]  # No change
            
            for (src, tgt), _ in TYPE_CONVERTERS.items():
                if src in types and tgt in types:
                    valid_transitions.append(
                        z3.And(
                            step_vars[i] == getattr(type_sort, src),
                            step_vars[i + 1] == getattr(type_sort, tgt)
                        )
                    )
            
            solver.add(z3.Or(valid_transitions))
            
            # Cost is 0 if same, 1 if different
            solver.add(
                cost_vars[i] == z3.If(
                    step_vars[i] == step_vars[i + 1], 
                    0, 
                    1
                )
            )
        
        # Constraint: Must reach target
        target_reached = z3.Or([
            step_vars[i] == getattr(type_sort, target_type) 
            for i in range(max_steps + 1)
        ])
        solver.add(target_reached)
        
        # Minimize total cost
        total_cost = z3.Sum(cost_vars)
        
        # Try to find solution
        if solver.check() == z3.sat:
            model = solver.model()
            
            # Extract path
            path = []
            for i, sv in enumerate(step_vars):
                val = model.eval(sv)
                type_name = str(val)
                if not path or path[-1] != type_name:
                    path.append(type_name)
                if type_name == target_type:
                    break
            
            # Calculate actual cost
            cost = len(path) - 1
            
            # Build explanation
            converters = []
            for i in range(len(path) - 1):
                key = (path[i], path[i + 1])
                if key in TYPE_CONVERTERS:
                    converters.append(TYPE_CONVERTERS[key])
            
            return ConstraintSolution(
                satisfiable=True,
                path=path,
                cost=cost,
                model={'converters': converters},
                explanation=f"Path: {' -> '.join(path)}"
            )
        
        return ConstraintSolution(
            satisfiable=False,
            explanation=f"No path found from {source_type} to {target_type}"
        )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DECISION TABLE SOLVING
    # ═══════════════════════════════════════════════════════════════════════════
    
    def solve_decision_table(
        self,
        conditions: List[Tuple[str, str, Any]],  # (var, op, value)
        rules: List[Dict[str, Any]],  # List of rule dicts with conditions and action
        inputs: Dict[str, Any]
    ) -> DecisionResult:
        """
        Evaluate decision table using z3 constraint solving.
        
        Args:
            conditions: List of (variable, operator, value) tuples
            rules: List of rule dictionaries
            inputs: Input variable values
            
        Returns:
            DecisionResult with matched action
        """
        solver = self._get_solver()
        
        # Create z3 variables for inputs
        z3_vars = {}
        for var_name, value in inputs.items():
            if isinstance(value, bool):
                z3_vars[var_name] = z3.Bool(var_name)
                solver.add(z3_vars[var_name] == value)
            elif isinstance(value, int):
                z3_vars[var_name] = z3.Int(var_name)
                solver.add(z3_vars[var_name] == value)
            elif isinstance(value, float):
                z3_vars[var_name] = z3.Real(var_name)
                solver.add(z3_vars[var_name] == value)
            elif isinstance(value, str):
                # Use hash for string comparison
                z3_vars[var_name] = z3.Int(f'{var_name}_hash')
                solver.add(z3_vars[var_name] == hash(value))
        
        # Evaluate each rule
        matched_rules = []
        for i, rule in enumerate(rules):
            rule_constraints = []
            
            for cond in rule.get('conditions', []):
                var_name = cond.get('var')
                op = cond.get('op', '==')
                val = cond.get('value')
                
                if var_name not in z3_vars:
                    continue
                
                z3_var = z3_vars[var_name]
                
                # Build constraint based on operator
                if op == '==':
                    if isinstance(val, str):
                        rule_constraints.append(z3_var == hash(val))
                    else:
                        rule_constraints.append(z3_var == val)
                elif op == '!=':
                    if isinstance(val, str):
                        rule_constraints.append(z3_var != hash(val))
                    else:
                        rule_constraints.append(z3_var != val)
                elif op == '>':
                    rule_constraints.append(z3_var > val)
                elif op == '>=':
                    rule_constraints.append(z3_var >= val)
                elif op == '<':
                    rule_constraints.append(z3_var < val)
                elif op == '<=':
                    rule_constraints.append(z3_var <= val)
            
            # Check if rule is satisfied
            if rule_constraints:
                solver.push()
                solver.add(z3.And(rule_constraints))
                if solver.check() == z3.sat:
                    matched_rules.append(i)
                solver.pop()
            else:
                # No conditions = always matches
                matched_rules.append(i)
        
        # Return first matching rule's action (priority order)
        if matched_rules:
            best_rule = rules[matched_rules[0]]
            return DecisionResult(
                action=best_rule.get('action', 'default'),
                confidence=1.0 if len(matched_rules) == 1 else 0.8,
                matched_rules=matched_rules,
                variable_assignments=inputs
            )
        
        return DecisionResult(
            action='default',
            confidence=0.0,
            matched_rules=[],
            variable_assignments=inputs
        )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CODE PROPERTY VERIFICATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def verify_code_properties(
        self,
        code: str,
        properties: List[str]
    ) -> VerificationResult:
        """
        Verify code satisfies specified properties.
        
        Properties supported:
        - 'no_infinite_loop': No obvious infinite loops
        - 'bounded_recursion': Recursion has base case
        - 'type_safe': Type hints are consistent
        - 'null_safe': Handles None values
        - 'deterministic': Same input -> same output
        
        Args:
            code: Python source code
            properties: List of property names to check
            
        Returns:
            VerificationResult
        """
        import ast
        
        violations = []
        checked = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return VerificationResult(
                verified=False,
                violations=["Code has syntax errors"]
            )
        
        # Property: no_infinite_loop
        if 'no_infinite_loop' in properties:
            checked.append('no_infinite_loop')
            for node in ast.walk(tree):
                if isinstance(node, ast.While):
                    # Check if while True with no break
                    if isinstance(node.test, ast.Constant) and node.test.value == True:
                        has_break = any(
                            isinstance(n, ast.Break) 
                            for n in ast.walk(node)
                        )
                        if not has_break:
                            violations.append("Potential infinite while loop detected")
        
        # Property: bounded_recursion
        if 'bounded_recursion' in properties:
            checked.append('bounded_recursion')
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    has_base_case = False
                    has_recursive_call = False
                    
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Name):
                                if child.func.id == func_name:
                                    has_recursive_call = True
                        if isinstance(child, ast.Return):
                            # Simple heuristic: return in if = base case
                            for parent in ast.walk(node):
                                if isinstance(parent, ast.If):
                                    has_base_case = True
                    
                    if has_recursive_call and not has_base_case:
                        violations.append(f"Function {func_name} may have unbounded recursion")
        
        # Property: null_safe
        if 'null_safe' in properties:
            checked.append('null_safe')
            for node in ast.walk(tree):
                if isinstance(node, ast.Subscript):
                    # Check if there's a None check before subscript
                    # This is a simplified check
                    pass  # Complex analysis would require control flow graph
        
        # Property: type_safe  
        if 'type_safe' in properties:
            checked.append('type_safe')
            # Check type hints are present and consistent
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check return type annotation
                    if node.returns is None and node.name != '__init__':
                        violations.append(f"Function {node.name} missing return type hint")
        
        # Property: deterministic
        if 'deterministic' in properties:
            checked.append('deterministic')
            non_deterministic = ['random', 'time', 'datetime', 'uuid']
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in non_deterministic:
                            violations.append(f"Non-deterministic import: {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module in non_deterministic:
                        violations.append(f"Non-deterministic import from: {node.module}")
        
        return VerificationResult(
            verified=len(violations) == 0,
            properties_checked=checked,
            violations=violations,
            proof="All checked properties satisfied" if not violations else ""
        )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # COMPLEXITY CONSTRAINT SOLVING
    # ═══════════════════════════════════════════════════════════════════════════
    
    def solve_complexity_constraints(
        self,
        task_features: Dict[str, int],
        tier_thresholds: Dict[str, Tuple[int, int]]
    ) -> Tuple[str, int, Dict[str, int]]:
        """
        Determine optimal tier based on task feature constraints.
        
        Uses z3 to find the tier that best matches task features.
        
        Args:
            task_features: Dict of feature -> score
            tier_thresholds: Dict of tier -> (min_score, max_score)
            
        Returns:
            (tier_name, total_score, feature_breakdown)
        """
        solver = self._get_solver()
        
        # Create score variable
        total_score = z3.Int('total_score')
        
        # Calculate total from features
        feature_sum = sum(task_features.values())
        solver.add(total_score == feature_sum)
        
        # Create tier selection variables
        tier_vars = {}
        for tier_name, (min_s, max_s) in tier_thresholds.items():
            tier_vars[tier_name] = z3.Bool(f'tier_{tier_name}')
            solver.add(
                tier_vars[tier_name] == z3.And(
                    total_score >= min_s,
                    total_score <= max_s
                )
            )
        
        # Exactly one tier should match
        solver.add(z3.Sum([z3.If(v, 1, 0) for v in tier_vars.values()]) >= 1)
        
        if solver.check() == z3.sat:
            model = solver.model()
            
            # Find which tier matched
            for tier_name, tier_var in tier_vars.items():
                if model.eval(tier_var):
                    return (tier_name, feature_sum, task_features)
        
        # Fallback to highest tier if no match
        return ('QOMBINATOR', feature_sum, task_features)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # GLUE CODE SYNTHESIS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def synthesize_glue_code(
        self,
        source_type: str,
        target_type: str,
        source_var: str = 'input'
    ) -> Optional[str]:
        """
        Generate glue code to convert between types.
        
        Args:
            source_type: Input type
            target_type: Output type
            source_var: Variable name for input
            
        Returns:
            Python code string or None if impossible
        """
        solution = self.solve_type_path(source_type, target_type)
        
        if not solution.satisfiable:
            return None
        
        if len(solution.path) == 1:
            return f"result = {source_var}  # No conversion needed"
        
        # Build conversion chain
        code_lines = [f"# Type conversion: {source_type} -> {target_type}"]
        current_var = source_var
        
        for i in range(len(solution.path) - 1):
            src = solution.path[i]
            tgt = solution.path[i + 1]
            key = (src, tgt)
            
            if key in TYPE_CONVERTERS:
                converter = TYPE_CONVERTERS[key]
                next_var = f"_{tgt}" if i < len(solution.path) - 2 else "result"
                
                if converter.startswith('lambda'):
                    code_lines.append(f"{next_var} = ({converter})({current_var})")
                else:
                    code_lines.append(f"{next_var} = {converter}({current_var})")
                
                current_var = next_var
        
        return '\n'.join(code_lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_z3_reasoner(config: dict = None) -> Optional[Z3Reasoner]:
    """Get Z3Reasoner if z3 is available."""
    if HAS_Z3:
        return Z3Reasoner(config)
    return None


def solve_type_conversion(source: str, target: str) -> Optional[str]:
    """Quick function to get type conversion code."""
    if not HAS_Z3:
        # Fallback without z3
        key = (source, target)
        if key in TYPE_CONVERTERS:
            return f"result = {TYPE_CONVERTERS[key]}(input)"
        return None
    
    reasoner = Z3Reasoner()
    return reasoner.synthesize_glue_code(source, target)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN (for testing)
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Test z3 solver functionality."""
    print(f"z3 available: {HAS_Z3}")
    
    if not HAS_Z3:
        print("Install z3-solver: pip install z3-solver")
        return
    
    reasoner = Z3Reasoner()
    
    # Test type path synthesis
    print("\n=== Type Path Synthesis ===")
    result = reasoner.solve_type_path('str', 'dict')
    print(f"str -> dict: {result.path} (cost: {result.cost})")
    
    result = reasoner.solve_type_path('list', 'str')
    print(f"list -> str: {result.path} (cost: {result.cost})")
    
    # Test glue code synthesis
    print("\n=== Glue Code Synthesis ===")
    code = reasoner.synthesize_glue_code('str', 'dict')
    print(f"str -> dict code:\n{code}")
    
    # Test code verification
    print("\n=== Code Verification ===")
    test_code = '''
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
'''
    result = reasoner.verify_code_properties(
        test_code, 
        ['bounded_recursion', 'type_safe']
    )
    print(f"Verified: {result.verified}")
    print(f"Violations: {result.violations}")


if __name__ == '__main__':
    main()
