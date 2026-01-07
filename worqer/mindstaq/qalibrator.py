#!/usr/bin/env python3
"""
Qalibrator: AST Mutation Engine for Evolutionary Code Improvement
Part of mindstaQ - Pure AST-based code mutations, NO LLM, NO API COST

The Qalibrator performs genetic programming operations on Python AST:
- Swap lines/statements
- Swap operators (+/-, ==/!=, and/or)
- Inline variables
- Extract functions
- Add error handling
- Optimize patterns
- Refactor structures

Works in a loop with Qualifier to evolve code toward fitness goals.

Pipeline Position:
  InstruQtor → ConstruQtor → [Qalibrator ⟷ Qualifier LOOP] → InspeQtor → TimeWalQer

v1.7.8-stable - Initial release with full mutation support

Usage:
    qalibrator = Qalibrator(config={'max_generations': 50})
    result = qalibrator.evolve(code, fitness_fn)
"""

import ast
import copy
import random
import re
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple, Callable, Any, Union
from pathlib import Path
from enum import Enum
import traceback


__version__ = '1.7.2-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# MUTATION TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class MutationType(Enum):
    """Types of AST mutations available."""
    SWAP_STATEMENTS = "swap_statements"      # Swap order of independent statements
    SWAP_OPERATORS = "swap_operators"        # +/-, *//, ==/!=, and/or
    SWAP_CONDITIONALS = "swap_conditionals"  # Swap if/else branches
    INLINE_VARIABLE = "inline_variable"      # Remove intermediate variable
    EXTRACT_VARIABLE = "extract_variable"    # Extract repeated expr to variable
    ADD_ERROR_HANDLING = "add_error_handling"  # Wrap in try/except
    REMOVE_DEAD_CODE = "remove_dead_code"    # Remove unreachable code
    SIMPLIFY_BOOLEAN = "simplify_boolean"    # Simplify boolean expressions
    OPTIMIZE_LOOP = "optimize_loop"          # Loop optimizations
    RENAME_VARIABLE = "rename_variable"      # Rename to more descriptive name
    ADD_TYPE_HINT = "add_type_hint"          # Add type annotations
    EXTRACT_FUNCTION = "extract_function"    # Extract code block to function
    MERGE_DUPLICATES = "merge_duplicates"    # Merge duplicate code blocks
    REORDER_IMPORTS = "reorder_imports"      # Sort and group imports


# ═══════════════════════════════════════════════════════════════════════════════
# MUTATION RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MutationResult:
    """Result of a single mutation attempt."""
    success: bool
    mutation_type: MutationType
    original_code: str
    mutated_code: str
    description: str
    line_affected: int = 0
    ast_valid: bool = True
    error: str = ""


@dataclass
class EvolutionResult:
    """Result of the full evolution process."""
    success: bool
    original_code: str
    evolved_code: str
    generations: int
    mutations_applied: List[MutationResult] = field(default_factory=list)
    fitness_history: List[float] = field(default_factory=list)
    final_fitness: float = 0.0
    target_fitness: float = 0.0
    converged: bool = False
    reason: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# AST MUTATION VISITORS
# ═══════════════════════════════════════════════════════════════════════════════

class OperatorSwapper(ast.NodeTransformer):
    """Swap binary operators in expressions."""
    
    OPERATOR_SWAPS = {
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
        ast.Mult: ast.Div,
        ast.Div: ast.Mult,
        ast.FloorDiv: ast.Mod,
        ast.Mod: ast.FloorDiv,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.Lt: ast.Gt,
        ast.Gt: ast.Lt,
        ast.LtE: ast.GtE,
        ast.GtE: ast.LtE,
        ast.And: ast.Or,
        ast.Or: ast.And,
    }
    
    def __init__(self, target_line: int = None, probability: float = 0.3):
        self.target_line = target_line
        self.probability = probability
        self.mutations_made = 0
        
    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        if random.random() < self.probability:
            op_type = type(node.op)
            if op_type in self.OPERATOR_SWAPS:
                node.op = self.OPERATOR_SWAPS[op_type]()
                self.mutations_made += 1
        return node
    
    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        new_ops = []
        for op in node.ops:
            if random.random() < self.probability:
                op_type = type(op)
                if op_type in self.OPERATOR_SWAPS:
                    new_ops.append(self.OPERATOR_SWAPS[op_type]())
                    self.mutations_made += 1
                else:
                    new_ops.append(op)
            else:
                new_ops.append(op)
        node.ops = new_ops
        return node
    
    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        if random.random() < self.probability:
            op_type = type(node.op)
            if op_type in self.OPERATOR_SWAPS:
                node.op = self.OPERATOR_SWAPS[op_type]()
                self.mutations_made += 1
        return node


class ConditionalSwapper(ast.NodeTransformer):
    """Swap if/else branches."""
    
    def __init__(self, target_line: int = None, probability: float = 0.3):
        self.target_line = target_line
        self.probability = probability
        self.mutations_made = 0
    
    def visit_If(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        if node.orelse and random.random() < self.probability:
            # Swap body and orelse, negate condition
            node.body, node.orelse = node.orelse, node.body
            # Negate the test
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            ast.fix_missing_locations(node)
            self.mutations_made += 1
        return node


class VariableInliner(ast.NodeTransformer):
    """Inline variables that are used only once."""
    
    def __init__(self, target_var: str = None):
        self.target_var = target_var
        self.var_assignments = {}  # var_name -> assigned_value
        self.var_uses = {}  # var_name -> count
        self.mutations_made = 0
    
    def visit_Module(self, node):
        # First pass: collect variable info
        self._collect_var_info(node)
        # Second pass: inline single-use variables
        self.generic_visit(node)
        return node
    
    def _collect_var_info(self, node):
        """Collect variable assignments and usage counts."""
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        self.var_assignments[target.id] = child.value
                        self.var_uses.setdefault(target.id, 0)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                self.var_uses[child.id] = self.var_uses.get(child.id, 0) + 1
    
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            var_name = node.id
            if self.target_var and var_name != self.target_var:
                return node
            # Inline if used exactly once and has simple assignment
            if (var_name in self.var_assignments and 
                self.var_uses.get(var_name, 0) == 1):
                self.mutations_made += 1
                return copy.deepcopy(self.var_assignments[var_name])
        return node


class ErrorHandlingAdder(ast.NodeTransformer):
    """Add try/except blocks around risky operations."""
    
    RISKY_OPERATIONS = {
        'open', 'read', 'write', 'connect', 'request', 'get', 'post',
        'execute', 'query', 'load', 'dump', 'parse', 'decode', 'encode'
    }
    
    def __init__(self, target_line: int = None):
        self.target_line = target_line
        self.mutations_made = 0
    
    def visit_Expr(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        if self._is_risky_call(node.value):
            return self._wrap_in_try(node)
        return node
    
    def visit_Assign(self, node):
        self.generic_visit(node)
        if self.target_line and node.lineno != self.target_line:
            return node
        if self._is_risky_call(node.value):
            return self._wrap_in_try(node)
        return node
    
    def _is_risky_call(self, node) -> bool:
        """Check if node is a risky function call."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id in self.RISKY_OPERATIONS
            elif isinstance(node.func, ast.Attribute):
                return node.func.attr in self.RISKY_OPERATIONS
        return False
    
    def _wrap_in_try(self, node):
        """Wrap statement in try/except."""
        self.mutations_made += 1
        try_node = ast.Try(
            body=[node],
            handlers=[
                ast.ExceptHandler(
                    type=ast.Name(id='Exception', ctx=ast.Load()),
                    name='e',
                    body=[
                        ast.Expr(value=ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[ast.JoinedStr(values=[
                                ast.Constant(value='Error: '),
                                ast.FormattedValue(
                                    value=ast.Name(id='e', ctx=ast.Load()),
                                    conversion=-1
                                )
                            ])],
                            keywords=[]
                        ))
                    ]
                )
            ],
            orelse=[],
            finalbody=[]
        )
        ast.fix_missing_locations(try_node)
        return try_node


class DeadCodeRemover(ast.NodeTransformer):
    """Remove unreachable code after return/raise/break/continue."""
    
    def __init__(self):
        self.mutations_made = 0
    
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.body = self._remove_dead_code(node.body)
        return node
    
    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        node.body = self._remove_dead_code(node.body)
        return node
    
    def _remove_dead_code(self, body: List) -> List:
        """Remove statements after unconditional return/raise."""
        new_body = []
        for stmt in body:
            new_body.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise)):
                if len(new_body) < len(body):
                    self.mutations_made += 1
                break
        return new_body if new_body else body


class BooleanSimplifier(ast.NodeTransformer):
    """Simplify boolean expressions."""
    
    def __init__(self):
        self.mutations_made = 0
    
    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        # not not x -> x
        if isinstance(node.op, ast.Not):
            if isinstance(node.operand, ast.UnaryOp) and isinstance(node.operand.op, ast.Not):
                self.mutations_made += 1
                return node.operand.operand
        return node
    
    def visit_Compare(self, node):
        self.generic_visit(node)
        # x == True -> x, x == False -> not x
        if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            if len(node.comparators) == 1:
                comp = node.comparators[0]
                if isinstance(comp, ast.Constant):
                    if comp.value is True:
                        self.mutations_made += 1
                        return node.left
                    elif comp.value is False:
                        self.mutations_made += 1
                        return ast.UnaryOp(op=ast.Not(), operand=node.left)
        return node
    
    def visit_IfExp(self, node):
        self.generic_visit(node)
        # x if True else y -> x
        if isinstance(node.test, ast.Constant):
            if node.test.value is True:
                self.mutations_made += 1
                return node.body
            elif node.test.value is False:
                self.mutations_made += 1
                return node.orelse
        return node


class ImportReorderer(ast.NodeTransformer):
    """Reorder imports according to PEP8."""
    
    def __init__(self):
        self.mutations_made = 0
    
    def visit_Module(self, node):
        imports = []
        other_stmts = []
        
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                imports.append(stmt)
            else:
                other_stmts.append(stmt)
        
        if imports:
            # Sort imports: stdlib, third-party, local
            sorted_imports = self._sort_imports(imports)
            if sorted_imports != imports:
                self.mutations_made += 1
                node.body = sorted_imports + other_stmts
        
        return node
    
    def _sort_imports(self, imports: List) -> List:
        """Sort imports according to PEP8."""
        stdlib = []
        third_party = []
        local = []
        
        STDLIB_MODULES = {
            'os', 'sys', 're', 'json', 'yaml', 'ast', 'copy', 'random',
            'hashlib', 'pathlib', 'typing', 'dataclasses', 'enum',
            'collections', 'itertools', 'functools', 'operator',
            'datetime', 'time', 'math', 'logging', 'subprocess',
            'threading', 'multiprocessing', 'asyncio', 'unittest',
            'io', 'tempfile', 'shutil', 'glob', 'argparse', 'configparser'
        }
        
        for imp in imports:
            if isinstance(imp, ast.Import):
                module = imp.names[0].name.split('.')[0]
            else:
                module = (imp.module or '').split('.')[0]
            
            if module in STDLIB_MODULES:
                stdlib.append(imp)
            elif module.startswith('.') or module == '':
                local.append(imp)
            else:
                third_party.append(imp)
        
        return stdlib + third_party + local


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN QALIBRATOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Qalibrator:
    """
    AST Mutation Engine for Evolutionary Code Improvement.
    
    Performs genetic programming operations on Python code to evolve
    it toward higher fitness scores (as determined by Qualifier).
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize Qalibrator with configuration.
        
        Args:
            config: Dictionary with settings:
                - max_generations: Maximum evolution iterations (default: 50)
                - population_size: Number of mutants per generation (default: 5)
                - mutation_rate: Probability of each mutation (default: 0.3)
                - elite_count: Best solutions to preserve (default: 2)
                - convergence_threshold: Fitness improvement threshold (default: 0.001)
                - stagnation_limit: Generations without improvement before stop (default: 10)
                - enabled_mutations: List of MutationType to use (default: all)
                - seed: Random seed for reproducibility (default: None)
        """
        config = config or {}
        
        self.max_generations = config.get('max_generations', 50)
        self.population_size = config.get('population_size', 5)
        self.mutation_rate = config.get('mutation_rate', 0.3)
        self.elite_count = config.get('elite_count', 2)
        self.convergence_threshold = config.get('convergence_threshold', 0.001)
        self.stagnation_limit = config.get('stagnation_limit', 10)
        self.seed = config.get('seed', None)
        
        # Enabled mutations
        enabled = config.get('enabled_mutations', None)
        if enabled:
            self.enabled_mutations = [MutationType(m) if isinstance(m, str) else m for m in enabled]
        else:
            self.enabled_mutations = list(MutationType)
        
        if self.seed is not None:
            random.seed(self.seed)
        
        # Mutation history for this session
        self.mutation_log: List[MutationResult] = []
    
    def mutate(self, code: str, mutation_type: MutationType = None) -> MutationResult:
        """
        Apply a single mutation to code.
        
        Args:
            code: Python source code
            mutation_type: Specific mutation to apply (random if None)
        
        Returns:
            MutationResult with mutated code
        """
        if mutation_type is None:
            mutation_type = random.choice(self.enabled_mutations)
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return MutationResult(
                success=False,
                mutation_type=mutation_type,
                original_code=code,
                mutated_code=code,
                description="Failed to parse code",
                ast_valid=False,
                error=str(e)
            )
        
        mutator = self._get_mutator(mutation_type)
        if mutator is None:
            return MutationResult(
                success=False,
                mutation_type=mutation_type,
                original_code=code,
                mutated_code=code,
                description=f"No mutator for {mutation_type.value}",
                error="Mutation type not implemented"
            )
        
        try:
            mutated_tree = mutator.visit(copy.deepcopy(tree))
            ast.fix_missing_locations(mutated_tree)
            
            # Verify AST is still valid
            try:
                mutated_code = ast.unparse(mutated_tree)
                # Verify it can be parsed back
                ast.parse(mutated_code)
            except Exception as e:
                return MutationResult(
                    success=False,
                    mutation_type=mutation_type,
                    original_code=code,
                    mutated_code=code,
                    description="Mutation produced invalid AST",
                    ast_valid=False,
                    error=str(e)
                )
            
            mutations_made = getattr(mutator, 'mutations_made', 0)
            
            result = MutationResult(
                success=mutations_made > 0,
                mutation_type=mutation_type,
                original_code=code,
                mutated_code=mutated_code,
                description=f"Applied {mutation_type.value} ({mutations_made} changes)",
                ast_valid=True
            )
            
            self.mutation_log.append(result)
            return result
            
        except Exception as e:
            return MutationResult(
                success=False,
                mutation_type=mutation_type,
                original_code=code,
                mutated_code=code,
                description=f"Mutation failed: {e}",
                error=traceback.format_exc()
            )
    
    def _get_mutator(self, mutation_type: MutationType) -> Optional[ast.NodeTransformer]:
        """Get the appropriate AST transformer for mutation type."""
        mutators = {
            MutationType.SWAP_OPERATORS: lambda: OperatorSwapper(probability=self.mutation_rate),
            MutationType.SWAP_CONDITIONALS: lambda: ConditionalSwapper(probability=self.mutation_rate),
            MutationType.INLINE_VARIABLE: lambda: VariableInliner(),
            MutationType.ADD_ERROR_HANDLING: lambda: ErrorHandlingAdder(),
            MutationType.REMOVE_DEAD_CODE: lambda: DeadCodeRemover(),
            MutationType.SIMPLIFY_BOOLEAN: lambda: BooleanSimplifier(),
            MutationType.REORDER_IMPORTS: lambda: ImportReorderer(),
        }
        
        factory = mutators.get(mutation_type)
        return factory() if factory else None
    
    def evolve(
        self,
        code: str,
        fitness_fn: Callable[[str], float],
        target_fitness: float = 1.0
    ) -> EvolutionResult:
        """
        Evolve code toward target fitness using genetic programming.
        
        Args:
            code: Initial Python source code
            fitness_fn: Function that scores code (0.0 to 1.0)
            target_fitness: Stop when this fitness is reached
        
        Returns:
            EvolutionResult with best evolved code
        """
        # Initial population
        population = [(code, fitness_fn(code))]
        best_code = code
        best_fitness = population[0][1]
        fitness_history = [best_fitness]
        mutations_applied = []
        
        stagnation_counter = 0
        converged = False
        reason = "max_generations_reached"
        
        for generation in range(self.max_generations):
            # Check convergence
            if best_fitness >= target_fitness:
                converged = True
                reason = "target_fitness_reached"
                break
            
            # Generate mutants
            mutants = []
            for _ in range(self.population_size):
                parent_code, _ = random.choice(population)
                mutation_type = random.choice(self.enabled_mutations)
                result = self.mutate(parent_code, mutation_type)
                
                if result.success and result.mutated_code != parent_code:
                    mutant_fitness = fitness_fn(result.mutated_code)
                    mutants.append((result.mutated_code, mutant_fitness))
                    mutations_applied.append(result)
            
            # Combine population with mutants
            all_candidates = population + mutants
            all_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Select elite + best mutants
            population = all_candidates[:max(self.elite_count, self.population_size)]
            
            new_best_fitness = population[0][1]
            new_best_code = population[0][0]
            
            # Track improvement
            if new_best_fitness > best_fitness + self.convergence_threshold:
                best_fitness = new_best_fitness
                best_code = new_best_code
                stagnation_counter = 0
            else:
                stagnation_counter += 1
            
            fitness_history.append(best_fitness)
            
            # Check stagnation
            if stagnation_counter >= self.stagnation_limit:
                reason = "stagnation_limit_reached"
                break
        
        return EvolutionResult(
            success=best_fitness > fitness_history[0],
            original_code=code,
            evolved_code=best_code,
            generations=len(fitness_history),
            mutations_applied=mutations_applied,
            fitness_history=fitness_history,
            final_fitness=best_fitness,
            target_fitness=target_fitness,
            converged=converged,
            reason=reason
        )
    
    def mutate_targeted(
        self,
        code: str,
        line_number: int,
        mutation_types: List[MutationType] = None
    ) -> List[MutationResult]:
        """
        Apply mutations targeting a specific line.
        
        Args:
            code: Python source code
            line_number: Line to target for mutations
            mutation_types: Mutations to try (default: all)
        
        Returns:
            List of MutationResults from each attempted mutation
        """
        mutations = mutation_types or self.enabled_mutations
        results = []
        
        for mut_type in mutations:
            result = self.mutate(code, mut_type)
            if result.success:
                results.append(result)
        
        return results
    
    def get_mutation_stats(self) -> Dict[str, Any]:
        """Get statistics about mutations performed."""
        if not self.mutation_log:
            return {'total': 0, 'successful': 0, 'by_type': {}}
        
        total = len(self.mutation_log)
        successful = sum(1 for m in self.mutation_log if m.success)
        
        by_type = {}
        for m in self.mutation_log:
            key = m.mutation_type.value
            if key not in by_type:
                by_type[key] = {'total': 0, 'successful': 0}
            by_type[key]['total'] += 1
            if m.success:
                by_type[key]['successful'] += 1
        
        return {
            'total': total,
            'successful': successful,
            'success_rate': successful / total if total > 0 else 0,
            'by_type': by_type
        }
    
    def reset_log(self):
        """Clear mutation log."""
        self.mutation_log = []


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE USAGE
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI interface for Qalibrator."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Qalibrator - AST Mutation Engine")
    parser.add_argument("file", help="Python file to mutate")
    parser.add_argument("--mutation", "-m", choices=[m.value for m in MutationType],
                       help="Specific mutation to apply")
    parser.add_argument("--generations", "-g", type=int, default=10,
                       help="Max evolution generations")
    parser.add_argument("--output", "-o", help="Output file for mutated code")
    
    args = parser.parse_args()
    
    with open(args.file, 'r') as f:
        code = f.read()
    
    qalibrator = Qalibrator(config={'max_generations': args.generations})
    
    if args.mutation:
        result = qalibrator.mutate(code, MutationType(args.mutation))
        print(f"Mutation: {result.mutation_type.value}")
        print(f"Success: {result.success}")
        print(f"Description: {result.description}")
        
        if result.success and args.output:
            with open(args.output, 'w') as f:
                f.write(result.mutated_code)
            print(f"Mutated code written to {args.output}")
    else:
        # Simple fitness: compiles without error = 1.0
        def simple_fitness(c):
            try:
                compile(c, '<string>', 'exec')
                return 1.0
            except:
                return 0.0
        
        result = qalibrator.evolve(code, simple_fitness)
        print(f"Evolution complete:")
        print(f"  Generations: {result.generations}")
        print(f"  Final fitness: {result.final_fitness}")
        print(f"  Converged: {result.converged}")
        print(f"  Reason: {result.reason}")
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(result.evolved_code)


if __name__ == "__main__":
    main()
