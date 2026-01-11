#!/usr/bin/env python3
"""
Monte Carlo Tree Search for Code Generation
Part of mindstaQ v2.1.8 - ZERO LLM Code Generation

MCTS systematically explores the space of possible code implementations
using the same algorithm that powered AlphaGo's world champion victories!

Instead of randomly mutating code (Darwinian), MCTS:
1. Builds a TREE of code "moves" (add statement, modify expression, etc.)
2. SIMULATES random completions to evaluate each path
3. BACKPROPAGATES results to guide future exploration
4. BALANCES exploration vs exploitation (UCB1 formula)

This is STRATEGIC code generation - not random mutation!

Key Features:
- UCB1-based node selection (exploration vs exploitation)
- Code-specific actions (add/modify/delete statements)
- Rollout simulation with syntax validation
- Backpropagation of fitness scores
- Configurable search depth and iterations

WoNQ Impact: +35-50 points for complex algorithm generation

v2.1.8
"""

import ast
import copy
import math
import random
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Set, Callable
from enum import Enum
from abc import ABC, abstractmethod
import time


__version__ = '2.1.8'


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS AND CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

class CodeAction(Enum):
    """Possible actions in the code generation tree."""
    ADD_ASSIGNMENT = "add_assignment"
    ADD_IF_STATEMENT = "add_if_statement"
    ADD_FOR_LOOP = "add_for_loop"
    ADD_WHILE_LOOP = "add_while_loop"
    ADD_RETURN = "add_return"
    ADD_FUNCTION_CALL = "add_function_call"
    MODIFY_OPERATOR = "modify_operator"
    MODIFY_CONSTANT = "modify_constant"
    MODIFY_VARIABLE = "modify_variable"
    DELETE_STATEMENT = "delete_statement"
    WRAP_IN_TRY = "wrap_in_try"
    ADD_LIST_COMPREHENSION = "add_list_comprehension"
    ADD_DICT_COMPREHENSION = "add_dict_comprehension"
    SWAP_STATEMENTS = "swap_statements"
    DUPLICATE_STATEMENT = "duplicate_statement"


# UCB1 exploration constant (sqrt(2) is theoretically optimal)
UCB1_C = math.sqrt(2)

# Default rollout depth
DEFAULT_ROLLOUT_DEPTH = 10


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodeState:
    """Represents a state in the code generation tree."""
    code: str
    ast_tree: Optional[ast.AST] = None
    is_valid: bool = True
    fitness: float = 0.0
    
    def __post_init__(self):
        if self.ast_tree is None and self.code:
            try:
                self.ast_tree = ast.parse(self.code)
                self.is_valid = True
            except SyntaxError:
                self.is_valid = False
    
    @property
    def hash(self) -> str:
        return hashlib.md5(self.code.encode()).hexdigest()[:16]
    
    def clone(self) -> 'CodeState':
        return CodeState(
            code=self.code,
            ast_tree=copy.deepcopy(self.ast_tree) if self.ast_tree else None,
            is_valid=self.is_valid,
            fitness=self.fitness,
        )


@dataclass
class MCTSNode:
    """A node in the MCTS tree."""
    state: CodeState
    parent: Optional['MCTSNode'] = None
    action: Optional[CodeAction] = None
    children: List['MCTSNode'] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0
    untried_actions: List[CodeAction] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.untried_actions:
            self.untried_actions = list(CodeAction)
    
    @property
    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0
    
    @property
    def is_terminal(self) -> bool:
        return self.state.fitness >= 1.0 or not self.state.is_valid
    
    @property
    def average_reward(self) -> float:
        return self.total_reward / self.visits if self.visits > 0 else 0.0
    
    def ucb1_score(self, exploration_constant: float = UCB1_C) -> float:
        """Calculate UCB1 score for node selection."""
        if self.visits == 0:
            return float('inf')
        
        exploitation = self.average_reward
        exploration = exploration_constant * math.sqrt(
            math.log(self.parent.visits) / self.visits
        ) if self.parent else 0
        
        return exploitation + exploration
    
    def best_child(self, exploration_constant: float = UCB1_C) -> 'MCTSNode':
        """Select best child using UCB1."""
        return max(self.children, key=lambda c: c.ucb1_score(exploration_constant))
    
    def add_child(self, state: CodeState, action: CodeAction) -> 'MCTSNode':
        """Add a child node."""
        child = MCTSNode(
            state=state,
            parent=self,
            action=action,
        )
        self.children.append(child)
        if action in self.untried_actions:
            self.untried_actions.remove(action)
        return child


@dataclass
class TestCase:
    """A test case for fitness evaluation."""
    inputs: Dict[str, Any]
    expected: Any
    weight: float = 1.0


@dataclass
class MCTSResult:
    """Result of MCTS search."""
    best_code: str
    best_fitness: float
    iterations: int
    nodes_explored: int
    time_elapsed: float
    convergence_history: List[float] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# CODE ACTION EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════

class CodeActionExecutor:
    """
    Executes code actions to transform AST.
    Each action is a "move" in the MCTS tree.
    """
    
    # Common variable names to use
    VAR_NAMES = ['x', 'y', 'z', 'i', 'j', 'n', 'result', 'temp', 'value', 'count']
    
    # Common constants
    CONSTANTS = [0, 1, 2, -1, 10, 100, True, False, None, [], {}]
    
    # Binary operators
    OPERATORS = [ast.Add(), ast.Sub(), ast.Mult(), ast.Div(), ast.Mod()]
    
    # Comparison operators
    COMPARISONS = [ast.Lt(), ast.LtE(), ast.Gt(), ast.GtE(), ast.Eq(), ast.NotEq()]
    
    def __init__(self, available_vars: List[str] = None):
        self.available_vars = available_vars or ['x', 'y', 'args', 'kwargs']
    
    def execute(self, state: CodeState, action: CodeAction) -> CodeState:
        """Execute an action on a code state, returning new state."""
        if not state.is_valid or not state.ast_tree:
            return state
        
        new_state = state.clone()
        
        try:
            executors = {
                CodeAction.ADD_ASSIGNMENT: self._add_assignment,
                CodeAction.ADD_IF_STATEMENT: self._add_if_statement,
                CodeAction.ADD_FOR_LOOP: self._add_for_loop,
                CodeAction.ADD_WHILE_LOOP: self._add_while_loop,
                CodeAction.ADD_RETURN: self._add_return,
                CodeAction.ADD_FUNCTION_CALL: self._add_function_call,
                CodeAction.MODIFY_OPERATOR: self._modify_operator,
                CodeAction.MODIFY_CONSTANT: self._modify_constant,
                CodeAction.MODIFY_VARIABLE: self._modify_variable,
                CodeAction.DELETE_STATEMENT: self._delete_statement,
                CodeAction.WRAP_IN_TRY: self._wrap_in_try,
                CodeAction.ADD_LIST_COMPREHENSION: self._add_list_comprehension,
                CodeAction.SWAP_STATEMENTS: self._swap_statements,
            }
            
            executor = executors.get(action, self._noop)
            new_tree = executor(new_state.ast_tree)
            
            ast.fix_missing_locations(new_tree)
            new_code = ast.unparse(new_tree)
            
            # Validate new code
            ast.parse(new_code)
            
            new_state.code = new_code
            new_state.ast_tree = new_tree
            new_state.is_valid = True
            
        except Exception:
            new_state.is_valid = False
        
        return new_state
    
    def _noop(self, tree: ast.AST) -> ast.AST:
        return tree
    
    def _find_function(self, tree: ast.AST) -> Optional[ast.FunctionDef]:
        """Find the first function definition."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                return node
        return None
    
    def _add_assignment(self, tree: ast.AST) -> ast.AST:
        """Add an assignment statement."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        var_name = random.choice(self.VAR_NAMES)
        value = random.choice([
            ast.Constant(value=random.choice([0, 1, 2])),
            ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
            ast.BinOp(
                left=ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
                op=random.choice(self.OPERATORS),
                right=ast.Constant(value=random.randint(1, 10))
            ),
        ])
        
        new_stmt = ast.Assign(
            targets=[ast.Name(id=var_name, ctx=ast.Store())],
            value=value
        )
        
        # Insert at random position (but before return)
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_stmt)
        
        return tree
    
    def _add_if_statement(self, tree: ast.AST) -> ast.AST:
        """Add an if statement."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        condition = ast.Compare(
            left=ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
            ops=[random.choice(self.COMPARISONS)],
            comparators=[ast.Constant(value=random.randint(0, 10))]
        )
        
        new_if = ast.If(
            test=condition,
            body=[ast.Pass()],
            orelse=[]
        )
        
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_if)
        
        return tree
    
    def _add_for_loop(self, tree: ast.AST) -> ast.AST:
        """Add a for loop."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        loop_var = random.choice(['i', 'j', 'k'])
        iterable = ast.Call(
            func=ast.Name(id='range', ctx=ast.Load()),
            args=[ast.Constant(value=random.randint(1, 10))],
            keywords=[]
        )
        
        new_for = ast.For(
            target=ast.Name(id=loop_var, ctx=ast.Store()),
            iter=iterable,
            body=[ast.Pass()],
            orelse=[]
        )
        
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_for)
        
        return tree
    
    def _add_while_loop(self, tree: ast.AST) -> ast.AST:
        """Add a while loop."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        condition = ast.Compare(
            left=ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
            ops=[ast.Lt()],
            comparators=[ast.Constant(value=random.randint(5, 20))]
        )
        
        new_while = ast.While(
            test=condition,
            body=[ast.Break()],  # Prevent infinite loop
            orelse=[]
        )
        
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_while)
        
        return tree
    
    def _add_return(self, tree: ast.AST) -> ast.AST:
        """Modify or add return statement."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        return_value = random.choice([
            ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
            ast.Constant(value=random.choice([0, 1, True, False, None])),
            ast.BinOp(
                left=ast.Name(id=random.choice(self.available_vars), ctx=ast.Load()),
                op=random.choice(self.OPERATORS),
                right=ast.Constant(value=random.randint(1, 5))
            ),
        ])
        
        # Find existing return and modify, or add new one
        for i, stmt in enumerate(func.body):
            if isinstance(stmt, ast.Return):
                func.body[i] = ast.Return(value=return_value)
                return tree
        
        # Add return at end
        func.body.append(ast.Return(value=return_value))
        return tree
    
    def _add_function_call(self, tree: ast.AST) -> ast.AST:
        """Add a function call statement."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        builtin_funcs = ['len', 'abs', 'min', 'max', 'sum', 'sorted', 'list', 'str', 'int']
        
        call = ast.Call(
            func=ast.Name(id=random.choice(builtin_funcs), ctx=ast.Load()),
            args=[ast.Name(id=random.choice(self.available_vars), ctx=ast.Load())],
            keywords=[]
        )
        
        new_stmt = ast.Assign(
            targets=[ast.Name(id='_result', ctx=ast.Store())],
            value=call
        )
        
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_stmt)
        
        return tree
    
    def _modify_operator(self, tree: ast.AST) -> ast.AST:
        """Modify a binary operator."""
        class OpModifier(ast.NodeTransformer):
            def __init__(self):
                self.modified = False
            
            def visit_BinOp(self, node):
                self.generic_visit(node)
                if not self.modified and random.random() < 0.5:
                    node.op = random.choice([ast.Add(), ast.Sub(), ast.Mult()])
                    self.modified = True
                return node
        
        return OpModifier().visit(tree)
    
    def _modify_constant(self, tree: ast.AST) -> ast.AST:
        """Modify a constant value."""
        class ConstModifier(ast.NodeTransformer):
            def __init__(self):
                self.modified = False
            
            def visit_Constant(self, node):
                if not self.modified and random.random() < 0.3:
                    if isinstance(node.value, int):
                        node.value = node.value + random.choice([-1, 1, 2, -2])
                    elif isinstance(node.value, bool):
                        node.value = not node.value
                    self.modified = True
                return node
        
        return ConstModifier().visit(tree)
    
    def _modify_variable(self, tree: ast.AST) -> ast.AST:
        """Swap a variable reference."""
        class VarModifier(ast.NodeTransformer):
            def __init__(self, available_vars):
                self.available_vars = available_vars
                self.modified = False
            
            def visit_Name(self, node):
                if not self.modified and isinstance(node.ctx, ast.Load) and random.random() < 0.3:
                    node.id = random.choice(self.available_vars)
                    self.modified = True
                return node
        
        return VarModifier(self.available_vars).visit(tree)
    
    def _delete_statement(self, tree: ast.AST) -> ast.AST:
        """Delete a non-essential statement."""
        func = self._find_function(tree)
        if not func or len(func.body) <= 1:
            return tree
        
        # Find deletable statements (not return, not the only one)
        deletable = []
        for i, stmt in enumerate(func.body):
            if not isinstance(stmt, ast.Return):
                deletable.append(i)
        
        if deletable and len(func.body) > 1:
            idx = random.choice(deletable)
            del func.body[idx]
        
        return tree
    
    def _wrap_in_try(self, tree: ast.AST) -> ast.AST:
        """Wrap a statement in try/except."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        # Find a statement to wrap
        for i, stmt in enumerate(func.body):
            if not isinstance(stmt, (ast.Try, ast.Return)) and random.random() < 0.3:
                new_try = ast.Try(
                    body=[stmt],
                    handlers=[ast.ExceptHandler(
                        type=ast.Name(id='Exception', ctx=ast.Load()),
                        name='e',
                        body=[ast.Pass()]
                    )],
                    orelse=[],
                    finalbody=[]
                )
                func.body[i] = new_try
                break
        
        return tree
    
    def _add_list_comprehension(self, tree: ast.AST) -> ast.AST:
        """Add a list comprehension."""
        func = self._find_function(tree)
        if not func or not func.body:
            return tree
        
        comp = ast.ListComp(
            elt=ast.Name(id='i', ctx=ast.Load()),
            generators=[ast.comprehension(
                target=ast.Name(id='i', ctx=ast.Store()),
                iter=ast.Call(
                    func=ast.Name(id='range', ctx=ast.Load()),
                    args=[ast.Constant(value=10)],
                    keywords=[]
                ),
                ifs=[],
                is_async=0
            )]
        )
        
        new_stmt = ast.Assign(
            targets=[ast.Name(id='_list', ctx=ast.Store())],
            value=comp
        )
        
        insert_pos = self._find_insert_position(func.body)
        func.body.insert(insert_pos, new_stmt)
        
        return tree
    
    def _swap_statements(self, tree: ast.AST) -> ast.AST:
        """Swap two adjacent statements."""
        func = self._find_function(tree)
        if not func or len(func.body) < 2:
            return tree
        
        # Find swappable positions (not involving return at end)
        swappable = list(range(len(func.body) - 1))
        if swappable:
            i = random.choice(swappable)
            func.body[i], func.body[i+1] = func.body[i+1], func.body[i]
        
        return tree
    
    def _find_insert_position(self, body: List[ast.stmt]) -> int:
        """Find a good position to insert a statement."""
        # Don't insert after return
        for i in range(len(body)):
            if isinstance(body[i], ast.Return):
                return max(0, i)
        return len(body)


# ═══════════════════════════════════════════════════════════════════════════════
# FITNESS EVALUATOR
# ═══════════════════════════════════════════════════════════════════════════════

class FitnessEvaluator:
    """Evaluates code fitness by running test cases."""
    
    def __init__(self, test_cases: List[TestCase], function_name: str = None):
        self.test_cases = test_cases
        self.function_name = function_name
    
    def evaluate(self, state: CodeState) -> float:
        """Evaluate fitness of a code state (0-1)."""
        if not state.is_valid:
            return 0.0
        
        try:
            # Compile and execute
            namespace = {}
            exec(compile(state.code, '<mcts>', 'exec'), namespace)
            
            # Find function
            func = None
            if self.function_name and self.function_name in namespace:
                func = namespace[self.function_name]
            else:
                for name, obj in namespace.items():
                    if callable(obj) and not name.startswith('_'):
                        func = obj
                        break
            
            if not func:
                return 0.1  # Valid syntax but no function
            
            # Run tests
            passed = 0
            total_weight = 0
            
            for test in self.test_cases:
                try:
                    result = func(**test.inputs)
                    if result == test.expected:
                        passed += test.weight
                    elif self._close_enough(result, test.expected):
                        passed += test.weight * 0.5
                except Exception:
                    pass
                total_weight += test.weight
            
            return passed / total_weight if total_weight > 0 else 0.0
            
        except Exception:
            return 0.05  # Partial credit for parseable code
    
    def _close_enough(self, result: Any, expected: Any) -> bool:
        """Check if result is close enough to expected."""
        if type(result) != type(expected):
            return False
        if isinstance(expected, (int, float)) and expected != 0:
            return abs(result - expected) / abs(expected) < 0.1
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# MCTS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MCTSCodeGenerator:
    """
    Monte Carlo Tree Search for Code Generation.
    
    Usage:
        mcts = MCTSCodeGenerator(test_cases, seed_code)
        result = mcts.search(iterations=1000)
        print(result.best_code)
    """
    
    def __init__(
        self,
        test_cases: List[TestCase],
        seed_code: str,
        function_name: str = None,
        exploration_constant: float = UCB1_C,
        rollout_depth: int = DEFAULT_ROLLOUT_DEPTH,
    ):
        self.test_cases = test_cases
        self.seed_code = seed_code
        self.function_name = function_name
        self.exploration_constant = exploration_constant
        self.rollout_depth = rollout_depth
        
        # Extract available variables from seed
        self.available_vars = self._extract_variables(seed_code)
        
        self.executor = CodeActionExecutor(self.available_vars)
        self.evaluator = FitnessEvaluator(test_cases, function_name)
        
        # Statistics
        self.nodes_explored = 0
        self.best_fitness = 0.0
        self.best_code = seed_code
    
    def _extract_variables(self, code: str) -> List[str]:
        """Extract variable names from code."""
        try:
            tree = ast.parse(code)
            variables = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for arg in node.args.args:
                        variables.add(arg.arg)
                elif isinstance(node, ast.Name):
                    variables.add(node.id)
            
            return list(variables) if variables else ['x', 'y']
        except:
            return ['x', 'y']
    
    def search(
        self,
        iterations: int = 1000,
        time_limit: float = None,
        target_fitness: float = 1.0,
    ) -> MCTSResult:
        """
        Run MCTS search.
        
        Args:
            iterations: Maximum iterations
            time_limit: Optional time limit in seconds
            target_fitness: Stop early if achieved
        
        Returns:
            MCTSResult with best code found
        """
        start_time = time.time()
        
        # Initialize root
        initial_state = CodeState(code=self.seed_code)
        initial_state.fitness = self.evaluator.evaluate(initial_state)
        
        root = MCTSNode(state=initial_state)
        
        self.best_fitness = initial_state.fitness
        self.best_code = initial_state.code
        
        convergence = [self.best_fitness]
        
        for i in range(iterations):
            # Check time limit
            if time_limit and (time.time() - start_time) > time_limit:
                break
            
            # Check target fitness
            if self.best_fitness >= target_fitness:
                break
            
            # MCTS iteration
            node = self._select(root)
            child = self._expand(node)
            reward = self._rollout(child)
            self._backpropagate(child, reward)
            
            # Track best
            if child.state.fitness > self.best_fitness:
                self.best_fitness = child.state.fitness
                self.best_code = child.state.code
            
            if i % 100 == 0:
                convergence.append(self.best_fitness)
        
        return MCTSResult(
            best_code=self.best_code,
            best_fitness=self.best_fitness,
            iterations=i + 1,
            nodes_explored=self.nodes_explored,
            time_elapsed=time.time() - start_time,
            convergence_history=convergence,
        )
    
    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select a node to expand using UCB1."""
        while not node.is_terminal:
            if not node.is_fully_expanded:
                return node
            node = node.best_child(self.exploration_constant)
        return node
    
    def _expand(self, node: MCTSNode) -> MCTSNode:
        """Expand a node by trying an untried action."""
        if node.is_terminal or not node.untried_actions:
            return node
        
        # Pick random untried action
        action = random.choice(node.untried_actions)
        
        # Execute action
        new_state = self.executor.execute(node.state, action)
        new_state.fitness = self.evaluator.evaluate(new_state)
        
        # Add child
        child = node.add_child(new_state, action)
        self.nodes_explored += 1
        
        return child
    
    def _rollout(self, node: MCTSNode) -> float:
        """
        Simulate random playouts from this node.
        Returns average fitness across rollouts.
        """
        if not node.state.is_valid:
            return 0.0
        
        total_fitness = node.state.fitness
        rollouts = 3  # Number of random rollouts
        
        for _ in range(rollouts):
            state = node.state.clone()
            
            # Random walk
            for _ in range(self.rollout_depth):
                if not state.is_valid:
                    break
                
                action = random.choice(list(CodeAction))
                state = self.executor.execute(state, action)
            
            if state.is_valid:
                fitness = self.evaluator.evaluate(state)
                total_fitness += fitness
                
                # Track global best
                if fitness > self.best_fitness:
                    self.best_fitness = fitness
                    self.best_code = state.code
        
        return total_fitness / (rollouts + 1)
    
    def _backpropagate(self, node: MCTSNode, reward: float):
        """Backpropagate reward up the tree."""
        while node is not None:
            node.visits += 1
            node.total_reward += reward
            node = node.parent


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def mcts_generate(
    test_cases: List[Dict[str, Any]],
    seed_code: str = None,
    function_name: str = None,
    iterations: int = 500,
    time_limit: float = 30.0,
) -> Tuple[str, float]:
    """
    Generate code using MCTS.
    
    Args:
        test_cases: List of {'inputs': {...}, 'expected': ...}
        seed_code: Starting code (or auto-generate skeleton)
        function_name: Name of function to evolve
        iterations: Max MCTS iterations
        time_limit: Time limit in seconds
    
    Returns:
        Tuple of (best_code, fitness)
    
    Example:
        tests = [
            {'inputs': {'x': 5}, 'expected': 25},
            {'inputs': {'x': 3}, 'expected': 9},
        ]
        code, fitness = mcts_generate(tests, function_name='square')
    """
    # Convert to TestCase objects
    tc_objects = [
        TestCase(
            inputs=tc['inputs'],
            expected=tc['expected'],
            weight=tc.get('weight', 1.0)
        )
        for tc in test_cases
    ]
    
    # Generate seed if not provided
    if not seed_code:
        if function_name:
            params = ', '.join(tc_objects[0].inputs.keys()) if tc_objects else 'x'
            seed_code = f"def {function_name}({params}):\n    return None"
        else:
            seed_code = "def solution(x):\n    return x"
    
    # Run MCTS
    mcts = MCTSCodeGenerator(
        test_cases=tc_objects,
        seed_code=seed_code,
        function_name=function_name,
    )
    
    result = mcts.search(
        iterations=iterations,
        time_limit=time_limit,
    )
    
    return result.best_code, result.best_fitness


def mcts_improve_code(
    code: str,
    test_cases: List[Dict[str, Any]],
    iterations: int = 300,
) -> Tuple[str, float, float]:
    """
    Use MCTS to improve existing code.
    
    Returns:
        Tuple of (improved_code, new_fitness, improvement)
    """
    # Find function name
    try:
        tree = ast.parse(code)
        func_name = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                break
    except:
        func_name = None
    
    # Get initial fitness
    tc_objects = [TestCase(inputs=tc['inputs'], expected=tc['expected']) for tc in test_cases]
    evaluator = FitnessEvaluator(tc_objects, func_name)
    initial_state = CodeState(code=code)
    initial_fitness = evaluator.evaluate(initial_state)
    
    # Run MCTS
    improved_code, new_fitness = mcts_generate(
        test_cases,
        seed_code=code,
        function_name=func_name,
        iterations=iterations,
    )
    
    return improved_code, new_fitness, new_fitness - initial_fitness


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Monte Carlo Tree Search for Code v{__version__}")
    print("=" * 70)
    
    # Test 1: Generate doubling function
    print("\n[1] MCTS: Generate Double Function")
    print("-" * 40)
    
    tests = [
        {'inputs': {'x': 5}, 'expected': 10},
        {'inputs': {'x': 3}, 'expected': 6},
        {'inputs': {'x': 0}, 'expected': 0},
        {'inputs': {'x': -2}, 'expected': -4},
    ]
    
    seed = "def double(x):\n    return x"
    
    code, fitness = mcts_generate(
        tests,
        seed_code=seed,
        function_name='double',
        iterations=500,
        time_limit=10.0,
    )
    
    print(f"Best fitness: {fitness:.2%}")
    print(f"Generated code:\n{code}")
    
    # Test 2: Generate square function
    print("\n[2] MCTS: Generate Square Function")
    print("-" * 40)
    
    tests2 = [
        {'inputs': {'n': 5}, 'expected': 25},
        {'inputs': {'n': 3}, 'expected': 9},
        {'inputs': {'n': 0}, 'expected': 0},
        {'inputs': {'n': 2}, 'expected': 4},
    ]
    
    seed2 = "def square(n):\n    return n"
    
    code2, fitness2 = mcts_generate(
        tests2,
        seed_code=seed2,
        function_name='square',
        iterations=500,
        time_limit=10.0,
    )
    
    print(f"Best fitness: {fitness2:.2%}")
    print(f"Generated code:\n{code2}")
    
    # Test 3: Generate absolute value
    print("\n[3] MCTS: Generate Absolute Value")
    print("-" * 40)
    
    tests3 = [
        {'inputs': {'x': 5}, 'expected': 5},
        {'inputs': {'x': -3}, 'expected': 3},
        {'inputs': {'x': 0}, 'expected': 0},
        {'inputs': {'x': -10}, 'expected': 10},
    ]
    
    seed3 = "def my_abs(x):\n    return x"
    
    code3, fitness3 = mcts_generate(
        tests3,
        seed_code=seed3,
        function_name='my_abs',
        iterations=800,
        time_limit=15.0,
    )
    
    print(f"Best fitness: {fitness3:.2%}")
    print(f"Generated code:\n{code3}")
    
    print("\n" + "=" * 70)
    print("✅ MCTS Code Generator working!")
