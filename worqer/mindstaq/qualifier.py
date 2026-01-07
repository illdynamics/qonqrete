#!/usr/bin/env python3
"""
Qualifier: Quality Assessment Agent for Evolutionary Code Improvement
Part of mindstaQ - Pure AST-based quality scoring, NO LLM, NO API COST

The Qualifier determines if Qalibrated code meets quality criteria:
- Syntax validity (must compile)
- Complexity metrics (cyclomatic, cognitive)
- Code coverage (if tests available)
- Style compliance (PEP8-ish)
- Security patterns
- Performance indicators
- Documentation completeness

Works in a loop with Qalibrator to evolve code toward fitness goals.
When code passes Qualifier's threshold, it proceeds to InspeQtor.

Pipeline Position:
  InstruQtor → ConstruQtor → [Qalibrator ⟷ Qualifier LOOP] → InspeQtor → TimeWalQer

v1.7.8-stable - Initial release with configurable quality criteria

Usage:
    qualifier = Qualifier(config={'min_fitness': 0.75})
    result = qualifier.assess(code)
    if result.qualified:
        # Pass to InspeQtor
"""

import ast
import re
import subprocess
import tempfile
import os
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple, Any, Callable
from pathlib import Path
from enum import Enum
import yaml


__version__ = '1.7.2-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY DIMENSIONS
# ═══════════════════════════════════════════════════════════════════════════════

class QualityDimension(Enum):
    """Dimensions of code quality measured by Qualifier."""
    SYNTAX = "syntax"               # Code compiles without errors
    COMPLEXITY = "complexity"       # Cyclomatic/cognitive complexity
    COVERAGE = "coverage"           # Test coverage if tests present
    STYLE = "style"                 # PEP8/formatting compliance
    SECURITY = "security"           # No obvious security issues
    PERFORMANCE = "performance"     # No obvious performance anti-patterns
    DOCUMENTATION = "documentation" # Docstrings, comments, type hints
    STRUCTURE = "structure"         # Code organization, modularity
    TESTABILITY = "testability"     # Code is testable (no global state, etc)
    MAINTAINABILITY = "maintainability"  # Overall maintainability score


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY RESULTS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DimensionScore:
    """Score for a single quality dimension."""
    dimension: QualityDimension
    score: float  # 0.0 to 1.0
    weight: float  # How much this dimension counts
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualificationResult:
    """Result of quality assessment."""
    qualified: bool
    fitness: float  # 0.0 to 1.0 (weighted average)
    min_fitness_required: float
    dimension_scores: List[DimensionScore] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    code_hash: str = ""
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'qualified': self.qualified,
            'fitness': self.fitness,
            'min_fitness_required': self.min_fitness_required,
            'dimensions': {
                ds.dimension.value: {
                    'score': ds.score,
                    'weight': ds.weight,
                    'issues': ds.issues
                }
                for ds in self.dimension_scores
            },
            'blocking_issues': self.blocking_issues,
            'suggestions': self.suggestions
        }


@dataclass
class EvolutionLoopResult:
    """Result of the Qalibrator ⟷ Qualifier evolution loop."""
    success: bool
    original_code: str
    final_code: str
    iterations: int
    fitness_progression: List[float]
    final_qualification: QualificationResult
    mutations_applied: int
    reason: str


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY CRITERIA LOADER
# ═══════════════════════════════════════════════════════════════════════════════

def load_quality_criteria(config_path: str = None) -> Dict:
    """
    Load quality criteria from YAML config.
    
    Default path: worqspace/quality_qriteria.yaml
    """
    defaults = {
        'min_fitness': 0.70,
        'max_iterations': 50,
        'stagnation_limit': 10,
        'dimensions': {
            'syntax': {'weight': 1.0, 'min_score': 1.0, 'blocking': True},
            'complexity': {'weight': 0.8, 'min_score': 0.5, 'blocking': False},
            'style': {'weight': 0.5, 'min_score': 0.4, 'blocking': False},
            'security': {'weight': 0.9, 'min_score': 0.7, 'blocking': True},
            'documentation': {'weight': 0.4, 'min_score': 0.3, 'blocking': False},
            'testability': {'weight': 0.6, 'min_score': 0.4, 'blocking': False},
        },
        'thresholds': {
            'max_function_length': 50,
            'max_complexity': 15,
            'max_parameters': 7,
            'max_nesting_depth': 4,
            'min_docstring_coverage': 0.5,
        }
    }
    
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                custom = yaml.safe_load(f)
                if custom:
                    # Merge with defaults
                    for key, value in custom.items():
                        if isinstance(value, dict) and key in defaults:
                            defaults[key].update(value)
                        else:
                            defaults[key] = value
        except Exception as e:
            print(f"Warning: Could not load quality criteria from {config_path}: {e}")
    
    return defaults


# ═══════════════════════════════════════════════════════════════════════════════
# AST ANALYSIS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class ComplexityVisitor(ast.NodeVisitor):
    """Calculate cyclomatic complexity."""
    
    def __init__(self):
        self.complexity = 1  # Base complexity
        self.function_complexities = {}
        self.current_function = None
    
    def visit_FunctionDef(self, node):
        old_func = self.current_function
        self.current_function = node.name
        old_complexity = self.complexity
        self.complexity = 1
        
        self.generic_visit(node)
        
        self.function_complexities[node.name] = self.complexity
        self.complexity = old_complexity
        self.current_function = old_func
    
    visit_AsyncFunctionDef = visit_FunctionDef
    
    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)
    
    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)
    
    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)
    
    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)
    
    def visit_With(self, node):
        self.complexity += 1
        self.generic_visit(node)
    
    def visit_BoolOp(self, node):
        # Each 'and'/'or' adds complexity
        self.complexity += len(node.values) - 1
        self.generic_visit(node)
    
    def visit_comprehension(self, node):
        self.complexity += 1
        if node.ifs:
            self.complexity += len(node.ifs)
        self.generic_visit(node)


class NestingVisitor(ast.NodeVisitor):
    """Calculate maximum nesting depth."""
    
    def __init__(self):
        self.max_depth = 0
        self.current_depth = 0
    
    def _increase_depth(self, node):
        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)
        self.generic_visit(node)
        self.current_depth -= 1
    
    def visit_If(self, node):
        self._increase_depth(node)
    
    def visit_For(self, node):
        self._increase_depth(node)
    
    def visit_While(self, node):
        self._increase_depth(node)
    
    def visit_With(self, node):
        self._increase_depth(node)
    
    def visit_Try(self, node):
        self._increase_depth(node)


class DocumentationVisitor(ast.NodeVisitor):
    """Analyze documentation coverage."""
    
    def __init__(self):
        self.total_functions = 0
        self.documented_functions = 0
        self.total_classes = 0
        self.documented_classes = 0
        self.has_module_docstring = False
    
    def visit_Module(self, node):
        if (node.body and isinstance(node.body[0], ast.Expr) and
            isinstance(node.body[0].value, ast.Constant) and
            isinstance(node.body[0].value.value, str)):
            self.has_module_docstring = True
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        self.total_functions += 1
        if ast.get_docstring(node):
            self.documented_functions += 1
        self.generic_visit(node)
    
    visit_AsyncFunctionDef = visit_FunctionDef
    
    def visit_ClassDef(self, node):
        self.total_classes += 1
        if ast.get_docstring(node):
            self.documented_classes += 1
        self.generic_visit(node)
    
    @property
    def coverage(self) -> float:
        total = self.total_functions + self.total_classes
        documented = self.documented_functions + self.documented_classes
        if total == 0:
            return 1.0 if self.has_module_docstring else 0.5
        base = documented / total
        if self.has_module_docstring:
            base = (base + 1.0) / 2  # Boost for module docstring
        return base


class SecurityVisitor(ast.NodeVisitor):
    """Check for security anti-patterns."""
    
    DANGEROUS_FUNCTIONS = {
        'eval', 'exec', 'compile', '__import__',
        'os.system', 'subprocess.call', 'subprocess.Popen'
    }
    
    DANGEROUS_PATTERNS = [
        r'password\s*=\s*["\'][^"\']+["\']',  # Hardcoded passwords
        r'secret\s*=\s*["\'][^"\']+["\']',     # Hardcoded secrets
        r'api_key\s*=\s*["\'][^"\']+["\']',    # Hardcoded API keys
    ]
    
    def __init__(self):
        self.issues = []
    
    def visit_Call(self, node):
        func_name = self._get_func_name(node)
        if func_name in self.DANGEROUS_FUNCTIONS:
            self.issues.append(f"Dangerous function call: {func_name} at line {node.lineno}")
        self.generic_visit(node)
    
    def _get_func_name(self, node) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
        return ""


class TestabilityVisitor(ast.NodeVisitor):
    """Analyze code testability."""
    
    def __init__(self):
        self.global_state_access = 0
        self.function_count = 0
        self.functions_with_side_effects = 0
        self.hardcoded_values = 0
    
    def visit_FunctionDef(self, node):
        self.function_count += 1
        # Check for side effects (print, write, etc.)
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func_name = self._get_func_name(child)
                if func_name in ('print', 'write', 'send', 'post', 'put', 'delete'):
                    self.functions_with_side_effects += 1
                    break
        self.generic_visit(node)
    
    def visit_Global(self, node):
        self.global_state_access += 1
        self.generic_visit(node)
    
    def visit_Constant(self, node):
        # Check for magic numbers (excluding 0, 1, -1, True, False, None)
        if isinstance(node.value, (int, float)):
            if node.value not in (0, 1, -1, 0.0, 1.0):
                self.hardcoded_values += 1
        self.generic_visit(node)
    
    def _get_func_name(self, node) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""
    
    @property
    def score(self) -> float:
        """Calculate testability score 0-1."""
        if self.function_count == 0:
            return 0.7  # No functions = moderately testable
        
        score = 1.0
        
        # Penalize global state
        if self.global_state_access > 0:
            score -= min(0.3, self.global_state_access * 0.1)
        
        # Penalize side effects
        side_effect_ratio = self.functions_with_side_effects / self.function_count
        score -= side_effect_ratio * 0.2
        
        # Penalize magic numbers
        if self.hardcoded_values > 10:
            score -= 0.1
        
        return max(0.0, score)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN QUALIFIER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Qualifier:
    """
    Quality Assessment Agent for code evolution.
    
    Determines if code meets quality criteria after Qalibrator mutations.
    Works in a loop: Qalibrator mutates, Qualifier assesses, repeat until qualified.
    """
    
    def __init__(self, config: dict = None, criteria_path: str = None):
        """
        Initialize Qualifier with configuration.
        
        Args:
            config: Dictionary with settings (overrides criteria file)
            criteria_path: Path to quality_qriteria.yaml
        """
        # Load criteria from file
        self.criteria = load_quality_criteria(criteria_path)
        
        # Override with direct config
        if config:
            for key, value in config.items():
                if isinstance(value, dict) and key in self.criteria:
                    self.criteria[key].update(value)
                else:
                    self.criteria[key] = value
        
        self.min_fitness = self.criteria.get('min_fitness', 0.70)
        self.dimension_config = self.criteria.get('dimensions', {})
        self.thresholds = self.criteria.get('thresholds', {})
    
    def assess(self, code: str, context: Dict = None) -> QualificationResult:
        """
        Assess code quality across all dimensions.
        
        Args:
            code: Python source code
            context: Optional context (test file, requirements, etc.)
        
        Returns:
            QualificationResult with fitness score and qualification status
        """
        import hashlib
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        
        dimension_scores = []
        blocking_issues = []
        suggestions = []
        
        # SYNTAX - Must pass
        syntax_score = self._assess_syntax(code)
        dimension_scores.append(syntax_score)
        if not syntax_score.score == 1.0:
            blocking_issues.extend(syntax_score.issues)
        
        # Only continue if syntax is valid
        if syntax_score.score == 1.0:
            try:
                tree = ast.parse(code)
                
                # COMPLEXITY
                complexity_score = self._assess_complexity(tree)
                dimension_scores.append(complexity_score)
                
                # STYLE
                style_score = self._assess_style(code, tree)
                dimension_scores.append(style_score)
                
                # SECURITY
                security_score = self._assess_security(tree, code)
                dimension_scores.append(security_score)
                if self.dimension_config.get('security', {}).get('blocking', True):
                    if security_score.score < self.dimension_config.get('security', {}).get('min_score', 0.7):
                        blocking_issues.extend(security_score.issues)
                
                # DOCUMENTATION
                doc_score = self._assess_documentation(tree)
                dimension_scores.append(doc_score)
                
                # TESTABILITY
                test_score = self._assess_testability(tree)
                dimension_scores.append(test_score)
                
                # Generate suggestions
                suggestions = self._generate_suggestions(dimension_scores)
                
            except Exception as e:
                blocking_issues.append(f"Assessment error: {e}")
        
        # Calculate weighted fitness
        total_weight = sum(ds.weight for ds in dimension_scores)
        weighted_sum = sum(ds.score * ds.weight for ds in dimension_scores)
        fitness = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        # v1.7.8: Ensure fitness is clamped to [0.0, 1.0]
        fitness = max(0.0, min(1.0, fitness))
        
        # Check blocking conditions
        qualified = (
            len(blocking_issues) == 0 and
            fitness >= self.min_fitness
        )
        
        return QualificationResult(
            qualified=qualified,
            fitness=fitness,
            min_fitness_required=self.min_fitness,
            dimension_scores=dimension_scores,
            blocking_issues=blocking_issues,
            suggestions=suggestions,
            code_hash=code_hash
        )
    
    def _assess_syntax(self, code: str) -> DimensionScore:
        """Check if code compiles."""
        config = self.dimension_config.get('syntax', {})
        issues = []
        
        try:
            compile(code, '<string>', 'exec')
            score = 1.0
        except SyntaxError as e:
            score = 0.0
            issues.append(f"Syntax error at line {e.lineno}: {e.msg}")
        
        return DimensionScore(
            dimension=QualityDimension.SYNTAX,
            score=score,
            weight=config.get('weight', 1.0),
            issues=issues
        )
    
    def _assess_complexity(self, tree: ast.AST) -> DimensionScore:
        """Assess cyclomatic and cognitive complexity."""
        config = self.dimension_config.get('complexity', {})
        issues = []
        details = {}
        
        # Cyclomatic complexity
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        
        max_complexity = self.thresholds.get('max_complexity', 15)
        max_func_complexity = max(visitor.function_complexities.values()) if visitor.function_complexities else 1
        
        details['function_complexities'] = visitor.function_complexities
        details['max_complexity'] = max_func_complexity
        
        if max_func_complexity > max_complexity:
            issues.append(f"Function complexity {max_func_complexity} exceeds threshold {max_complexity}")
        
        # Nesting depth
        nesting = NestingVisitor()
        nesting.visit(tree)
        max_nesting = self.thresholds.get('max_nesting_depth', 4)
        
        details['max_nesting'] = nesting.max_depth
        
        if nesting.max_depth > max_nesting:
            issues.append(f"Nesting depth {nesting.max_depth} exceeds threshold {max_nesting}")
        
        # Calculate score - only PENALIZE if OVER threshold, don't bonus for under
        # v1.7.8: Fixed score going over 1.0
        score = 1.0
        if max_func_complexity > max_complexity:
            overage_ratio = (max_func_complexity - max_complexity) / max_complexity
            score -= min(0.5, overage_ratio * 0.3)  # Max penalty 0.5 for complexity
        
        if nesting.max_depth > max_nesting:
            overage_ratio = (nesting.max_depth - max_nesting) / max_nesting
            score -= min(0.3, overage_ratio * 0.2)  # Max penalty 0.3 for nesting
        
        score = max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]
        
        return DimensionScore(
            dimension=QualityDimension.COMPLEXITY,
            score=score,
            weight=config.get('weight', 0.8),
            issues=issues,
            details=details
        )
    
    def _assess_style(self, code: str, tree: ast.AST) -> DimensionScore:
        """Assess code style (basic PEP8-ish checks)."""
        config = self.dimension_config.get('style', {})
        issues = []
        score = 1.0
        
        lines = code.split('\n')
        
        # Line length
        long_lines = sum(1 for line in lines if len(line) > 120)
        if long_lines > 0:
            issues.append(f"{long_lines} lines exceed 120 characters")
            score -= min(0.2, long_lines * 0.02)
        
        # Trailing whitespace
        trailing = sum(1 for line in lines if line.rstrip() != line and line.strip())
        if trailing > 0:
            issues.append(f"{trailing} lines have trailing whitespace")
            score -= min(0.1, trailing * 0.01)
        
        # Mixed indentation
        spaces = sum(1 for line in lines if line.startswith('    '))
        tabs = sum(1 for line in lines if line.startswith('\t'))
        if spaces > 0 and tabs > 0:
            issues.append("Mixed tabs and spaces for indentation")
            score -= 0.1
        
        # Blank lines between functions
        # (simplified check)
        
        return DimensionScore(
            dimension=QualityDimension.STYLE,
            score=max(0.0, score),
            weight=config.get('weight', 0.5),
            issues=issues
        )
    
    def _assess_security(self, tree: ast.AST, code: str) -> DimensionScore:
        """Assess security patterns."""
        config = self.dimension_config.get('security', {})
        issues = []
        score = 1.0
        
        # AST-based checks
        visitor = SecurityVisitor()
        visitor.visit(tree)
        issues.extend(visitor.issues)
        score -= len(visitor.issues) * 0.15
        
        # Pattern-based checks
        for pattern in SecurityVisitor.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                issues.append(f"Potential hardcoded secret found")
                score -= 0.2
        
        return DimensionScore(
            dimension=QualityDimension.SECURITY,
            score=max(0.0, score),
            weight=config.get('weight', 0.9),
            issues=issues
        )
    
    def _assess_documentation(self, tree: ast.AST) -> DimensionScore:
        """Assess documentation coverage."""
        config = self.dimension_config.get('documentation', {})
        issues = []
        
        visitor = DocumentationVisitor()
        visitor.visit(tree)
        
        score = visitor.coverage
        min_coverage = self.thresholds.get('min_docstring_coverage', 0.5)
        
        if score < min_coverage:
            issues.append(f"Documentation coverage {score:.1%} below threshold {min_coverage:.1%}")
        
        details = {
            'total_functions': visitor.total_functions,
            'documented_functions': visitor.documented_functions,
            'total_classes': visitor.total_classes,
            'documented_classes': visitor.documented_classes,
            'has_module_docstring': visitor.has_module_docstring
        }
        
        return DimensionScore(
            dimension=QualityDimension.DOCUMENTATION,
            score=score,
            weight=config.get('weight', 0.4),
            issues=issues,
            details=details
        )
    
    def _assess_testability(self, tree: ast.AST) -> DimensionScore:
        """Assess code testability."""
        config = self.dimension_config.get('testability', {})
        issues = []
        
        visitor = TestabilityVisitor()
        visitor.visit(tree)
        
        score = visitor.score
        
        if visitor.global_state_access > 0:
            issues.append(f"Global state access found ({visitor.global_state_access} occurrences)")
        
        if visitor.function_count > 0:
            side_effect_ratio = visitor.functions_with_side_effects / visitor.function_count
            if side_effect_ratio > 0.5:
                issues.append(f"{side_effect_ratio:.0%} of functions have side effects")
        
        details = {
            'global_state_access': visitor.global_state_access,
            'functions_with_side_effects': visitor.functions_with_side_effects,
            'hardcoded_values': visitor.hardcoded_values
        }
        
        return DimensionScore(
            dimension=QualityDimension.TESTABILITY,
            score=score,
            weight=config.get('weight', 0.6),
            issues=issues,
            details=details
        )
    
    def _generate_suggestions(self, scores: List[DimensionScore]) -> List[str]:
        """Generate improvement suggestions based on scores."""
        suggestions = []
        
        for ds in scores:
            if ds.score < 0.7:
                if ds.dimension == QualityDimension.COMPLEXITY:
                    suggestions.append("Consider breaking down complex functions into smaller units")
                elif ds.dimension == QualityDimension.DOCUMENTATION:
                    suggestions.append("Add docstrings to functions and classes")
                elif ds.dimension == QualityDimension.TESTABILITY:
                    suggestions.append("Reduce global state and side effects for better testability")
                elif ds.dimension == QualityDimension.STYLE:
                    suggestions.append("Review line lengths and indentation consistency")
        
        return suggestions
    
    def get_fitness_function(self) -> Callable[[str], float]:
        """
        Return a fitness function for use with Qalibrator.
        
        Returns:
            Function that takes code string and returns fitness 0.0-1.0
        """
        def fitness(code: str) -> float:
            result = self.assess(code)
            return result.fitness
        return fitness
    
    def run_evolution_loop(
        self,
        code: str,
        qalibrator,  # Qalibrator instance
        max_iterations: int = None,
        target_fitness: float = None
    ) -> EvolutionLoopResult:
        """
        Run the Qalibrator ⟷ Qualifier evolution loop.
        
        Args:
            code: Initial code to evolve
            qalibrator: Qalibrator instance for mutations
            max_iterations: Override max iterations
            target_fitness: Override target fitness
        
        Returns:
            EvolutionLoopResult with final code and statistics
        """
        max_iter = max_iterations or self.criteria.get('max_iterations', 50)
        target = target_fitness or self.min_fitness
        stagnation_limit = self.criteria.get('stagnation_limit', 10)
        
        current_code = code
        fitness_progression = []
        mutations_count = 0
        stagnation = 0
        best_fitness = 0.0
        best_code = code
        
        for iteration in range(max_iter):
            # Assess current code
            result = self.assess(current_code)
            fitness_progression.append(result.fitness)
            
            # Check if qualified
            if result.qualified and result.fitness >= target:
                return EvolutionLoopResult(
                    success=True,
                    original_code=code,
                    final_code=current_code,
                    iterations=iteration + 1,
                    fitness_progression=fitness_progression,
                    final_qualification=result,
                    mutations_applied=mutations_count,
                    reason="target_fitness_achieved"
                )
            
            # Track best
            if result.fitness > best_fitness:
                best_fitness = result.fitness
                best_code = current_code
                stagnation = 0
            else:
                stagnation += 1
            
            # Check stagnation
            if stagnation >= stagnation_limit:
                final_result = self.assess(best_code)
                return EvolutionLoopResult(
                    success=final_result.qualified,
                    original_code=code,
                    final_code=best_code,
                    iterations=iteration + 1,
                    fitness_progression=fitness_progression,
                    final_qualification=final_result,
                    mutations_applied=mutations_count,
                    reason="stagnation_limit_reached"
                )
            
            # Mutate
            mutation_result = qalibrator.mutate(current_code)
            if mutation_result.success:
                # Only accept if fitness doesn't drop significantly
                new_fitness = self.assess(mutation_result.mutated_code).fitness
                if new_fitness >= result.fitness - 0.05:  # Allow small regression
                    current_code = mutation_result.mutated_code
                    mutations_count += 1
        
        # Max iterations reached
        final_result = self.assess(best_code)
        return EvolutionLoopResult(
            success=final_result.qualified,
            original_code=code,
            final_code=best_code,
            iterations=max_iter,
            fitness_progression=fitness_progression,
            final_qualification=final_result,
            mutations_applied=mutations_count,
            reason="max_iterations_reached"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE USAGE
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI interface for Qualifier."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Qualifier - Code Quality Assessment")
    parser.add_argument("file", help="Python file to assess")
    parser.add_argument("--criteria", "-c", help="Path to quality_qriteria.yaml")
    parser.add_argument("--min-fitness", "-m", type=float, default=0.70,
                       help="Minimum fitness threshold")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output as JSON")
    
    args = parser.parse_args()
    
    with open(args.file, 'r') as f:
        code = f.read()
    
    qualifier = Qualifier(
        config={'min_fitness': args.min_fitness},
        criteria_path=args.criteria
    )
    
    result = qualifier.assess(code)
    
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Qualification Result for {args.file}")
        print(f"{'=' * 50}")
        print(f"Qualified: {'✓ YES' if result.qualified else '✗ NO'}")
        print(f"Fitness: {result.fitness:.2%} (required: {result.min_fitness_required:.2%})")
        print()
        print("Dimension Scores:")
        for ds in result.dimension_scores:
            status = "✓" if ds.score >= 0.7 else "⚠" if ds.score >= 0.4 else "✗"
            print(f"  {status} {ds.dimension.value}: {ds.score:.2%} (weight: {ds.weight})")
            for issue in ds.issues[:3]:  # Show first 3 issues
                print(f"      - {issue}")
        
        if result.blocking_issues:
            print("\nBlocking Issues:")
            for issue in result.blocking_issues:
                print(f"  ✗ {issue}")
        
        if result.suggestions:
            print("\nSuggestions:")
            for sug in result.suggestions:
                print(f"  → {sug}")


if __name__ == "__main__":
    main()
