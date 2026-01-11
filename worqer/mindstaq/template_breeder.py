#!/usr/bin/env python3
"""
Template Breeder: Genetic Algorithm for Code Evolution
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Evolves code templates through breeding and mutation using AST manipulation.
No LLM needed - pure algorithmic code improvement!

v1.5.0
"""

import ast
import re
import random
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple, Callable
from collections import defaultdict


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Individual:
    """A code individual in the population."""
    code: str
    fitness: float = 0.0
    generation: int = 0
    parent_ids: List[int] = field(default_factory=list)
    mutations: List[str] = field(default_factory=list)
    
    def __hash__(self):
        return hash(self.code)


@dataclass
class EvolutionResult:
    """Result of evolution process."""
    best_individual: Individual
    final_population: List[Individual]
    generations_run: int
    fitness_history: List[float]      # Best fitness per generation
    diversity_history: List[float]    # Population diversity per generation


# ═══════════════════════════════════════════════════════════════════════════════
# FITNESS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def syntax_valid(code: str) -> bool:
    """Check if code has valid syntax."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def count_features(code: str) -> Dict[str, int]:
    """Count code features for fitness scoring."""
    features = {
        'functions': 0,
        'classes': 0,
        'type_hints': 0,
        'docstrings': 0,
        'try_blocks': 0,
        'comprehensions': 0,
        'async_defs': 0,
        'decorators': 0,
        'imports': 0,
        'lines': len(code.strip().split('\n')),
    }
    
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                features['functions'] += 1
                if node.returns:
                    features['type_hints'] += 1
                for arg in node.args.args:
                    if arg.annotation:
                        features['type_hints'] += 1
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        if isinstance(node.body[0].value.value, str):
                            features['docstrings'] += 1
                if node.decorator_list:
                    features['decorators'] += 1
            
            elif isinstance(node, ast.AsyncFunctionDef):
                features['async_defs'] += 1
                features['functions'] += 1
            
            elif isinstance(node, ast.ClassDef):
                features['classes'] += 1
            
            elif isinstance(node, ast.Try):
                features['try_blocks'] += 1
            
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
                features['comprehensions'] += 1
            
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                features['imports'] += 1
    
    except SyntaxError:
        pass
    
    return features


def default_fitness(code: str) -> float:
    """
    Default fitness function for code quality.
    
    Scores:
    - Syntax validity: 30 points
    - Has functions: 15 points
    - Type hints: up to 15 points
    - Docstrings: up to 10 points
    - Error handling: 10 points
    - Reasonable length: up to 10 points
    - Code features: up to 10 points
    
    Returns: 0-100 fitness score
    """
    # Must have valid syntax
    if not syntax_valid(code):
        return 0.0
    
    score = 30.0  # Valid syntax base
    
    features = count_features(code)
    
    # Has functions
    if features['functions'] > 0:
        score += 15.0
    
    # Type hints (up to 15)
    type_hint_score = min(15, features['type_hints'] * 3)
    score += type_hint_score
    
    # Docstrings (up to 10)
    doc_score = min(10, features['docstrings'] * 5)
    score += doc_score
    
    # Error handling
    if features['try_blocks'] > 0:
        score += 10.0
    
    # Reasonable length (10-100 lines is ideal)
    lines = features['lines']
    if 10 <= lines <= 100:
        score += 10.0
    elif 5 <= lines < 10 or 100 < lines <= 200:
        score += 5.0
    
    # Code features bonus
    if features['comprehensions'] > 0:
        score += 2.0
    if features['classes'] > 0:
        score += 3.0
    if features['async_defs'] > 0:
        score += 3.0
    if features['decorators'] > 0:
        score += 2.0
    
    return min(100.0, score)


# ═══════════════════════════════════════════════════════════════════════════════
# MUTATION OPERATORS
# ═══════════════════════════════════════════════════════════════════════════════

class ASTMutator(ast.NodeTransformer):
    """Base class for AST mutations."""
    
    def __init__(self):
        self.mutations_applied = []


class AddTypeHints(ASTMutator):
    """Add type hints to functions that lack them."""
    
    TYPE_GUESSES = {
        'url': 'str',
        'path': 'str',
        'name': 'str',
        'text': 'str',
        'data': 'dict',
        'config': 'dict',
        'timeout': 'int',
        'count': 'int',
        'size': 'int',
        'enabled': 'bool',
        'items': 'list',
        'result': 'Any',
    }
    
    def visit_FunctionDef(self, node):
        modified = False
        
        # Add parameter type hints
        for arg in node.args.args:
            if arg.annotation is None:
                arg_name = arg.arg.lower()
                for pattern, type_name in self.TYPE_GUESSES.items():
                    if pattern in arg_name:
                        arg.annotation = ast.Name(id=type_name, ctx=ast.Load())
                        modified = True
                        break
        
        # Add return type if missing
        if node.returns is None and node.body:
            # Simple heuristic: check what's being returned
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value:
                    if isinstance(child.value, ast.Dict):
                        node.returns = ast.Name(id='dict', ctx=ast.Load())
                        modified = True
                    elif isinstance(child.value, ast.List):
                        node.returns = ast.Name(id='list', ctx=ast.Load())
                        modified = True
                    elif isinstance(child.value, ast.Constant):
                        if isinstance(child.value.value, str):
                            node.returns = ast.Name(id='str', ctx=ast.Load())
                        elif isinstance(child.value.value, bool):
                            node.returns = ast.Name(id='bool', ctx=ast.Load())
                        elif isinstance(child.value.value, int):
                            node.returns = ast.Name(id='int', ctx=ast.Load())
                        modified = True
                    break
        
        if modified:
            self.mutations_applied.append('add_type_hints')
        
        return self.generic_visit(node)


class AddDocstrings(ASTMutator):
    """Add docstrings to functions that lack them."""
    
    def visit_FunctionDef(self, node):
        # Check if already has docstring
        has_doc = (node.body and isinstance(node.body[0], ast.Expr) and 
                  isinstance(node.body[0].value, ast.Constant) and 
                  isinstance(node.body[0].value.value, str))
        
        if not has_doc:
            # Generate simple docstring from function name
            func_name = node.name.replace('_', ' ')
            docstring = f"{func_name.capitalize()}."
            
            doc_node = ast.Expr(value=ast.Constant(value=docstring))
            node.body.insert(0, doc_node)
            self.mutations_applied.append('add_docstring')
        
        return self.generic_visit(node)


class AddErrorHandling(ASTMutator):
    """Wrap function body in try-except."""
    
    def visit_FunctionDef(self, node):
        # Check if already has try-except
        has_try = any(isinstance(n, ast.Try) for n in node.body)
        
        if not has_try and len(node.body) > 1:
            # Wrap body in try-except
            try_node = ast.Try(
                body=node.body.copy(),
                handlers=[
                    ast.ExceptHandler(
                        type=ast.Name(id='Exception', ctx=ast.Load()),
                        name='e',
                        body=[
                            ast.Raise(exc=None, cause=None)
                        ]
                    )
                ],
                orelse=[],
                finalbody=[]
            )
            node.body = [try_node]
            self.mutations_applied.append('add_error_handling')
        
        return self.generic_visit(node)


class AddDefaultArgs(ASTMutator):
    """Add default values to function arguments."""
    
    COMMON_DEFAULTS = {
        'timeout': ast.Constant(value=30),
        'retries': ast.Constant(value=3),
        'limit': ast.Constant(value=100),
        'offset': ast.Constant(value=0),
        'verbose': ast.Constant(value=False),
        'debug': ast.Constant(value=False),
        'encoding': ast.Constant(value='utf-8'),
    }
    
    def visit_FunctionDef(self, node):
        # Add defaults for known patterns
        args = node.args
        
        for i, arg in enumerate(args.args):
            arg_name = arg.arg.lower()
            
            # Skip if already has default
            default_index = i - (len(args.args) - len(args.defaults))
            if default_index >= 0:
                continue
            
            for pattern, default in self.COMMON_DEFAULTS.items():
                if pattern in arg_name:
                    # Pad defaults list
                    while len(args.defaults) < len(args.args) - i - 1:
                        args.defaults.insert(0, ast.Constant(value=None))
                    args.defaults.append(copy.deepcopy(default))
                    self.mutations_applied.append(f'add_default_{pattern}')
                    break
        
        return self.generic_visit(node)


def apply_mutation(code: str, mutator_class: type) -> Tuple[str, List[str]]:
    """Apply a mutation to code."""
    try:
        tree = ast.parse(code)
        mutator = mutator_class()
        new_tree = mutator.visit(tree)
        ast.fix_missing_locations(new_tree)
        new_code = ast.unparse(new_tree)
        return new_code, mutator.mutations_applied
    except Exception:
        return code, []


# ═══════════════════════════════════════════════════════════════════════════════
# CROSSOVER OPERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def crossover_functions(parent_a: str, parent_b: str) -> str:
    """
    Crossover: Take functions from one parent, imports from another.
    """
    try:
        tree_a = ast.parse(parent_a)
        tree_b = ast.parse(parent_b)
    except SyntaxError:
        return parent_a
    
    # Extract components
    imports_a = [n for n in tree_a.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    imports_b = [n for n in tree_b.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    
    funcs_a = [n for n in tree_a.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    funcs_b = [n for n in tree_b.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    
    classes_a = [n for n in tree_a.body if isinstance(n, ast.ClassDef)]
    classes_b = [n for n in tree_b.body if isinstance(n, ast.ClassDef)]
    
    # Randomly choose what to take from which parent
    imports = imports_a if random.random() > 0.5 else imports_b
    
    # For functions/classes, take best of each
    func_names_a = {f.name for f in funcs_a}
    func_names_b = {f.name for f in funcs_b}
    
    child_funcs = []
    
    # Common functions: randomly pick one version
    for name in func_names_a & func_names_b:
        fa = next(f for f in funcs_a if f.name == name)
        fb = next(f for f in funcs_b if f.name == name)
        child_funcs.append(fa if random.random() > 0.5 else fb)
    
    # Unique functions: include both
    for name in func_names_a - func_names_b:
        child_funcs.append(next(f for f in funcs_a if f.name == name))
    
    for name in func_names_b - func_names_a:
        child_funcs.append(next(f for f in funcs_b if f.name == name))
    
    # Build child tree
    child_body = imports + classes_a + child_funcs
    child_tree = ast.Module(body=child_body, type_ignores=[])
    ast.fix_missing_locations(child_tree)
    
    try:
        return ast.unparse(child_tree)
    except:
        return parent_a


def crossover_merge_best(parent_a: str, parent_b: str) -> str:
    """
    Merge best features from both parents.
    """
    # Try to get AST patterns
    try:
        tree_a = ast.parse(parent_a)
        tree_b = ast.parse(parent_b)
    except SyntaxError:
        return parent_a if len(parent_a) >= len(parent_b) else parent_b
    
    # Count features
    features_a = count_features(parent_a)
    features_b = count_features(parent_b)
    
    # Take the better one based on features
    score_a = (features_a['type_hints'] * 3 + features_a['docstrings'] * 2 + 
               features_a['try_blocks'] * 2)
    score_b = (features_b['type_hints'] * 3 + features_b['docstrings'] * 2 + 
               features_b['try_blocks'] * 2)
    
    # Slight randomness to maintain diversity
    if random.random() < 0.8:
        return parent_a if score_a >= score_b else parent_b
    else:
        return parent_a if score_a < score_b else parent_b


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE BREEDER
# ═══════════════════════════════════════════════════════════════════════════════

class TemplateBreeder:
    """
    Genetic algorithm for evolving code templates.
    
    Process:
    1. Initialize population from seed templates
    2. Evaluate fitness of each individual
    3. Select best individuals as parents
    4. Create offspring through crossover
    5. Apply mutations
    6. Repeat for N generations
    7. Return best individual
    
    Usage:
        breeder = TemplateBreeder()
        
        seeds = [
            "def fetch(url): return requests.get(url)",
            "def fetch(url, timeout=30): ...",
        ]
        
        result = breeder.evolve(seeds, generations=5)
        print(result.best_individual.code)
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Evolution parameters
        self.population_size = self.config.get('population_size', 10)
        self.elite_count = self.config.get('elite_count', 2)
        self.mutation_rate = self.config.get('mutation_rate', 0.3)
        self.crossover_rate = self.config.get('crossover_rate', 0.7)
        
        # Available mutators
        self.mutators = [
            AddTypeHints,
            AddDocstrings,
            AddErrorHandling,
            AddDefaultArgs,
        ]
        
        # Fitness function (can be overridden)
        self.fitness_fn: Callable[[str], float] = default_fitness
    
    def set_fitness_function(self, fn: Callable[[str], float]):
        """Set custom fitness function."""
        self.fitness_fn = fn
    
    def _initialize_population(self, seeds: List[str]) -> List[Individual]:
        """Create initial population from seeds."""
        population = []
        
        # Add seeds directly
        for i, seed in enumerate(seeds):
            if syntax_valid(seed):
                ind = Individual(
                    code=seed,
                    fitness=self.fitness_fn(seed),
                    generation=0
                )
                population.append(ind)
        
        # Generate variants through mutation if needed
        while len(population) < self.population_size:
            base = random.choice(seeds)
            mutator = random.choice(self.mutators)
            
            new_code, mutations = apply_mutation(base, mutator)
            
            if syntax_valid(new_code):
                ind = Individual(
                    code=new_code,
                    fitness=self.fitness_fn(new_code),
                    generation=0,
                    mutations=mutations
                )
                population.append(ind)
        
        return population[:self.population_size]
    
    def _select_parents(self, population: List[Individual]) -> List[Individual]:
        """Tournament selection for parents."""
        parents = []
        
        for _ in range(len(population)):
            # Tournament of 3
            contestants = random.sample(population, min(3, len(population)))
            winner = max(contestants, key=lambda x: x.fitness)
            parents.append(winner)
        
        return parents
    
    def _crossover(self, parent_a: Individual, parent_b: Individual, generation: int) -> Individual:
        """Create offspring through crossover."""
        if random.random() < self.crossover_rate:
            child_code = crossover_functions(parent_a.code, parent_b.code)
        else:
            child_code = parent_a.code if random.random() > 0.5 else parent_b.code
        
        return Individual(
            code=child_code,
            fitness=self.fitness_fn(child_code),
            generation=generation,
            parent_ids=[id(parent_a), id(parent_b)]
        )
    
    def _mutate(self, individual: Individual) -> Individual:
        """Apply random mutations."""
        if random.random() > self.mutation_rate:
            return individual
        
        mutator = random.choice(self.mutators)
        new_code, mutations = apply_mutation(individual.code, mutator)
        
        if syntax_valid(new_code):
            individual.code = new_code
            individual.fitness = self.fitness_fn(new_code)
            individual.mutations.extend(mutations)
        
        return individual
    
    def _calculate_diversity(self, population: List[Individual]) -> float:
        """Calculate population diversity (0-1)."""
        if len(population) < 2:
            return 0.0
        
        unique_codes = len(set(ind.code for ind in population))
        return unique_codes / len(population)
    
    def evolve(
        self,
        seeds: List[str],
        generations: int = 10,
        target_fitness: float = 90.0,
        early_stop: bool = True
    ) -> EvolutionResult:
        """
        Evolve templates over multiple generations.
        
        Args:
            seeds: Initial code templates
            generations: Number of generations to run
            target_fitness: Stop early if reached
            early_stop: Enable early stopping
        
        Returns:
            EvolutionResult with best individual and stats
        """
        # Initialize
        population = self._initialize_population(seeds)
        
        fitness_history = []
        diversity_history = []
        
        best_ever = max(population, key=lambda x: x.fitness)
        
        for gen in range(generations):
            # Track stats
            best_fitness = max(ind.fitness for ind in population)
            fitness_history.append(best_fitness)
            diversity_history.append(self._calculate_diversity(population))
            
            # Update best ever
            gen_best = max(population, key=lambda x: x.fitness)
            if gen_best.fitness > best_ever.fitness:
                best_ever = gen_best
            
            # Early stopping
            if early_stop and best_fitness >= target_fitness:
                break
            
            # Selection
            parents = self._select_parents(population)
            
            # Create next generation
            next_gen = []
            
            # Elitism: keep best individuals
            elite = sorted(population, key=lambda x: x.fitness, reverse=True)[:self.elite_count]
            next_gen.extend(elite)
            
            # Fill rest with offspring
            while len(next_gen) < self.population_size:
                parent_a = random.choice(parents)
                parent_b = random.choice(parents)
                
                child = self._crossover(parent_a, parent_b, gen + 1)
                child = self._mutate(child)
                
                if syntax_valid(child.code):
                    next_gen.append(child)
            
            population = next_gen[:self.population_size]
        
        # Final best
        final_best = max(population, key=lambda x: x.fitness)
        if final_best.fitness > best_ever.fitness:
            best_ever = final_best
        
        return EvolutionResult(
            best_individual=best_ever,
            final_population=population,
            generations_run=len(fitness_history),
            fitness_history=fitness_history,
            diversity_history=diversity_history
        )
    
    def quick_improve(self, code: str, iterations: int = 3) -> str:
        """
        Quick improvement without full evolution.
        Just applies beneficial mutations.
        """
        current = code
        
        for _ in range(iterations):
            for mutator in self.mutators:
                new_code, _ = apply_mutation(current, mutator)
                
                if syntax_valid(new_code):
                    new_fitness = self.fitness_fn(new_code)
                    old_fitness = self.fitness_fn(current)
                    
                    if new_fitness > old_fitness:
                        current = new_code
        
        return current


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Template Breeder v{__version__}")
    print("=" * 60)
    
    breeder = TemplateBreeder()
    
    # Seed templates
    seeds = [
        '''
def fetch(url):
    return requests.get(url)
''',
        '''
def fetch(url, timeout=30):
    response = requests.get(url, timeout=timeout)
    return response.json()
''',
        '''
import requests

def fetch(url):
    try:
        return requests.get(url).json()
    except Exception:
        return None
''',
    ]
    
    print("\n[1] Initial Seeds:")
    for i, seed in enumerate(seeds):
        fitness = default_fitness(seed)
        print(f"  Seed {i+1}: fitness={fitness:.1f}")
    
    print("\n[2] Evolving...")
    result = breeder.evolve(seeds, generations=5)
    
    print(f"\n[3] Evolution Results:")
    print(f"  Generations: {result.generations_run}")
    print(f"  Best fitness: {result.best_individual.fitness:.1f}")
    print(f"  Mutations applied: {result.best_individual.mutations}")
    print(f"  Fitness history: {[f'{f:.1f}' for f in result.fitness_history]}")
    
    print(f"\n[4] Best Code:")
    print("-" * 40)
    print(result.best_individual.code)
    print("-" * 40)
    
    print("\n[5] Quick Improve Test:")
    simple = "def add(a, b): return a + b"
    improved = breeder.quick_improve(simple)
    print(f"  Before: {simple}")
    print(f"  After:  {improved}")
    
    print("\n✅ Template Breeder working!")
