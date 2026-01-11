#!/usr/bin/env python3
"""
LocalInspeQtor: Zero-Cost Code Review Agent
Part of mindstaQ - Pure AST-based code analysis, NO LLM, NO API COST

Reviews code for:
- Syntax errors (via compile())
- Import issues (missing modules)
- Code quality (complexity, style, patterns)
- Security issues (hardcoded secrets, injection risks)
- Performance patterns (N+1, unbounded loops)
- Best practices (docstrings, type hints, error handling)

v1.2.2 - MODE SUPPORT:
- program: Focus on functionality - does the code work as intended?
- enterprise: Full review + logging, observability, error handling, docs
- innovative: All checks + suggestions for improvements and extensions

Usage:
  inspeqtor = LocalInspeQtor(config={'mode': 'enterprise'})
"""

import ast
import re
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple, Any
from pathlib import Path
from enum import Enum


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# REVIEW MODES
# ═══════════════════════════════════════════════════════════════════════════════

class ReviewMode(Enum):
    PROGRAM = "program"         # Focus on functionality
    ENTERPRISE = "enterprise"   # Full enterprise-grade review
    INNOVATIVE = "innovative"   # Suggest improvements and extensions


# ═══════════════════════════════════════════════════════════════════════════════
# SEVERITY LEVELS
# ═══════════════════════════════════════════════════════════════════════════════

class Severity(Enum):
    CRITICAL = "critical"  # Must fix - breaks execution
    ERROR = "error"        # Should fix - likely bugs
    WARNING = "warning"    # Consider fixing - code smells
    INFO = "info"          # Suggestions - improvements
    SUGGESTION = "suggest" # v1.2.2: Ideas for improvement (innovative mode)
    PASS = "pass"          # Check passed


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Issue:
    """A single code issue found during review."""
    category: str          # syntax, import, security, quality, performance, style
    severity: Severity
    message: str
    line: int = 0
    column: int = 0
    code_snippet: str = ""
    suggestion: str = ""
    rule_id: str = ""      # e.g., SEC001, PERF002


@dataclass 
class FileReview:
    """Review results for a single file."""
    filepath: str
    issues: List[Issue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    score: int = 100       # 0-100 quality score
    passed: bool = True
    
    def add_issue(self, issue: Issue):
        self.issues.append(issue)
        if issue.severity in (Severity.CRITICAL, Severity.ERROR):
            self.passed = False
        # Deduct points based on severity
        if issue.severity == Severity.CRITICAL:
            self.score = max(0, self.score - 25)
        elif issue.severity == Severity.ERROR:
            self.score = max(0, self.score - 10)
        elif issue.severity == Severity.WARNING:
            self.score = max(0, self.score - 5)


@dataclass
class ReviewReport:
    """Complete review report for multiple files."""
    files: List[FileReview] = field(default_factory=list)
    total_issues: int = 0
    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    overall_score: int = 100
    passed: bool = True
    
    def add_file(self, file_review: FileReview):
        self.files.append(file_review)
        for issue in file_review.issues:
            self.total_issues += 1
            if issue.severity == Severity.CRITICAL:
                self.critical_count += 1
            elif issue.severity == Severity.ERROR:
                self.error_count += 1
            elif issue.severity == Severity.WARNING:
                self.warning_count += 1
            elif issue.severity == Severity.INFO:
                self.info_count += 1
        
        if not file_review.passed:
            self.passed = False
        
        # Average score
        if self.files:
            self.overall_score = sum(f.score for f in self.files) // len(self.files)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

SECURITY_PATTERNS = [
    # Hardcoded secrets
    (r'(?:password|passwd|pwd|secret|token|api_key|apikey|auth)\s*=\s*["\'][^"\']{4,}["\']',
     'SEC001', 'Hardcoded secret detected', Severity.CRITICAL),
    
    # SQL injection risks
    (r'(?:execute|cursor\.execute)\s*\(\s*[f"\'].*%s.*[f"\']\s*%',
     'SEC002', 'Possible SQL injection (use parameterized queries)', Severity.ERROR),
    (r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE).*\{',
     'SEC003', 'SQL in f-string (use parameterized queries)', Severity.ERROR),
    
    # Command injection
    (r'os\.system\s*\(',
     'SEC004', 'os.system() is unsafe (use subprocess with shell=False)', Severity.WARNING),
    (r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True',
     'SEC005', 'subprocess with shell=True is risky', Severity.WARNING),
    
    # Eval/exec
    (r'\beval\s*\(',
     'SEC006', 'eval() is dangerous (avoid if possible)', Severity.ERROR),
    (r'\bexec\s*\(',
     'SEC007', 'exec() is dangerous (avoid if possible)', Severity.WARNING),
    
    # Pickle deserialization
    (r'pickle\.loads?\s*\(',
     'SEC008', 'pickle.load() can execute arbitrary code', Severity.WARNING),
    
    # Hardcoded IPs/URLs
    (r'(?:http://|https://)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
     'SEC009', 'Hardcoded IP address in URL', Severity.INFO),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

PERFORMANCE_PATTERNS = [
    # List comprehension in loop
    (r'for\s+\w+\s+in\s+\[.*for\s+.*\]',
     'PERF001', 'Nested comprehension may be slow', Severity.INFO),
    
    # String concatenation in loop
    (r'for\s+.*:\s*\n\s*\w+\s*\+=\s*["\']',
     'PERF002', 'String concatenation in loop (use join())', Severity.WARNING),
    
    # Global variable access in hot path
    (r'global\s+\w+',
     'PERF003', 'Global variable (consider passing as parameter)', Severity.INFO),
    
    # Repeated attribute access
    (r'self\.\w+\.\w+\.\w+\.\w+',
     'PERF004', 'Deep attribute chain (consider caching)', Severity.INFO),
]

# ═══════════════════════════════════════════════════════════════════════════════
# STYLE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

STYLE_PATTERNS = [
    # Very long lines
    (r'^.{121,}$',
     'STYLE001', 'Line exceeds 120 characters', Severity.INFO),
    
    # Multiple statements on one line
    (r';\s*\w+\s*=',
     'STYLE002', 'Multiple statements on one line', Severity.INFO),
    
    # TODO/FIXME/HACK comments
    (r'#\s*(?:TODO|FIXME|HACK|XXX):?',
     'STYLE003', 'TODO/FIXME comment found', Severity.INFO),
    
    # Print statements (should use logging)
    (r'\bprint\s*\(',
     'STYLE004', 'print() found (consider using logging)', Severity.INFO),
]


# ═══════════════════════════════════════════════════════════════════════════════
# ENTERPRISE PATTERNS (v1.2.2) - Extra checks for enterprise mode
# ═══════════════════════════════════════════════════════════════════════════════

ENTERPRISE_PATTERNS = [
    # Missing logging setup
    (r'^(?!.*import\s+logging)(?!.*from\s+logging)',
     'ENT001', 'No logging import found (enterprise apps should use logging)', Severity.WARNING),
    
    # Bare except clauses
    (r'except\s*:',
     'ENT002', 'Bare except clause (catch specific exceptions)', Severity.WARNING),
    
    # Missing error handling
    (r'open\s*\([^)]+\)(?!\s*as)',
     'ENT003', 'File open without context manager (use "with" statement)', Severity.WARNING),
    
    # No type hints on function
    (r'def\s+\w+\s*\([^)]*\)\s*:(?!\s*#)',
     'ENT004', 'Function without return type hint (add -> Type)', Severity.INFO),
    
    # Missing __all__ in module
    (r'^(?!.*__all__\s*=)',
     'ENT005', 'No __all__ defined (helps with explicit exports)', Severity.INFO),
    
    # No retry/timeout on network calls
    (r'requests\.(?:get|post|put|delete|patch)\s*\([^)]*\)(?!.*timeout)',
     'ENT006', 'HTTP request without timeout (add timeout parameter)', Severity.WARNING),
    
    # Missing docstring patterns  
    (r'class\s+\w+.*:\s*\n\s*(?!"""|\'\'\')def',
     'ENT007', 'Class without docstring', Severity.INFO),
]

# Suggestions for enterprise mode
ENTERPRISE_SUGGESTIONS = {
    'no_logging': "Add structured logging: `import logging; logger = logging.getLogger(__name__)`",
    'no_metrics': "Consider adding metrics: Prometheus, StatsD, or OpenTelemetry",
    'no_tracing': "Consider distributed tracing: OpenTelemetry or Jaeger",
    'no_health': "Add health check endpoint for observability",
    'no_retry': "Add retry logic for external service calls (tenacity library)",
    'no_circuit': "Consider circuit breaker pattern for resilience",
}


# ═══════════════════════════════════════════════════════════════════════════════
# INNOVATIVE PATTERNS (v1.2.2) - Suggestions for improvements
# ═══════════════════════════════════════════════════════════════════════════════

INNOVATIVE_SUGGESTIONS = [
    # Could be async
    (r'(?:requests|urllib)\.(?:get|post|put)',
     'INN001', 'Sync HTTP calls could be async (httpx, aiohttp)', 'Consider async/await for better concurrency'),
    
    # Could use dataclass
    (r'class\s+\w+:\s*\n\s*def\s+__init__\s*\(self[^)]*\):\s*\n(?:\s*self\.\w+\s*=\s*\w+\s*\n){3,}',
     'INN002', 'Class with many __init__ assignments', 'Consider using @dataclass for cleaner data containers'),
    
    # Could use pathlib
    (r'os\.path\.(?:join|dirname|basename|exists|isfile|isdir)',
     'INN003', 'Using os.path for path operations', 'Consider pathlib.Path for more Pythonic path handling'),
    
    # Could use f-strings
    (r'["\'].*%[sd].*["\']|\.format\s*\(',
     'INN004', 'Using % or .format() for string formatting', 'Consider f-strings for cleaner string formatting'),
    
    # Could use walrus operator
    (r'(\w+)\s*=\s*(\w+\([^)]*\))\s*\n\s*if\s+\1',
     'INN005', 'Assignment followed by condition check', 'Consider walrus operator (:=) for Python 3.8+'),
    
    # Could use typing
    (r'def\s+\w+\s*\([^:)]*\)\s*:',
     'INN006', 'Function without type hints', 'Add type hints for better IDE support and documentation'),
    
    # Could use enum
    (r'(?:STATUS_|TYPE_|MODE_)\w+\s*=\s*["\'][^"\']+["\']',
     'INN007', 'String constants detected', 'Consider using Enum for type-safe constants'),
    
    # Could add caching
    (r'def\s+\w+\s*\([^)]*\)\s*:\s*\n(?:[^#\n]*\n)*\s*return\s+\w+\([^)]*\)',
     'INN008', 'Pure function that could be cached', 'Consider @functools.lru_cache for memoization'),
]


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL INSPEQTOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class LocalInspeQtor:
    """
    Zero-cost code review using AST analysis and pattern matching.
    No LLM calls, just pure deterministic analysis.
    
    Modes (v1.2.2):
    - program: Focus on functionality (syntax, security, basic quality)
    - enterprise: Full review + logging, observability, error handling
    - innovative: All checks + suggestions for improvements
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        inspeqtor_cfg = self.config.get('local_inspeqtor', {})
        
        # v1.2.2: Mode configuration
        mode_str = inspeqtor_cfg.get('mode', self.config.get('mode', 'program'))
        try:
            self.mode = ReviewMode(mode_str.lower())
        except ValueError:
            self.mode = ReviewMode.PROGRAM
        
        # Configure severity thresholds
        self.fail_on_critical = inspeqtor_cfg.get('fail_on_critical', True)
        self.fail_on_error = inspeqtor_cfg.get('fail_on_error', True)
        self.fail_on_warning = inspeqtor_cfg.get('fail_on_warning', False)
        
        # Configure checks based on mode
        self.check_syntax = inspeqtor_cfg.get('check_syntax', True)
        self.check_imports = inspeqtor_cfg.get('check_imports', True)
        self.check_security = inspeqtor_cfg.get('check_security', True)
        self.check_performance = inspeqtor_cfg.get('check_performance', True)
        self.check_style = inspeqtor_cfg.get('check_style', True)
        self.check_quality = inspeqtor_cfg.get('check_quality', True)
        
        # v1.2.2: Mode-specific checks
        self.check_enterprise = inspeqtor_cfg.get('check_enterprise', self.mode in (ReviewMode.ENTERPRISE, ReviewMode.INNOVATIVE))
        self.check_innovative = inspeqtor_cfg.get('check_innovative', self.mode == ReviewMode.INNOVATIVE)
        
        # Minimum score to pass
        self.min_score = inspeqtor_cfg.get('min_score', 60)
    
    def review_file(self, filepath: str) -> FileReview:
        """Review a source file. Supports Python, Shell, Rust, Go.
        
        v1.8.3: Multi-language adapter support.
        """
        review = FileReview(filepath=filepath)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            review.add_issue(Issue(
                category='io',
                severity=Severity.CRITICAL,
                message=f"Cannot read file: {e}",
                rule_id='IO001'
            ))
            return review
        
        lines = content.split('\n')
        
        # v1.8.3: Detect language from file extension
        lang = self._detect_language(filepath)
        
        # Route to language-specific adapter
        if lang == 'python':
            return self._review_python(content, lines, filepath, review)
        elif lang == 'shell':
            return self._review_shell(content, lines, filepath, review)
        elif lang == 'rust':
            return self._review_rust(content, lines, filepath, review)
        elif lang == 'go':
            return self._review_go(content, lines, filepath, review)
        else:
            # Unknown language - do basic checks only
            return self._review_generic(content, lines, filepath, review)
    
    def _detect_language(self, filepath: str) -> str:
        """v1.8.3: Detect language from file extension."""
        ext_map = {
            '.py': 'python',
            '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell',
            '.rs': 'rust',
            '.go': 'go',
            '.js': 'javascript', '.ts': 'typescript',
            '.yaml': 'yaml', '.yml': 'yaml',
            '.json': 'json', '.toml': 'toml',
        }
        for ext, lang in ext_map.items():
            if filepath.endswith(ext):
                return lang
        return 'unknown'
    
    def _review_python(self, content: str, lines: List[str], filepath: str, review: FileReview) -> FileReview:
        """Python-specific review with full AST analysis."""
        # 1. Syntax check
        if self.check_syntax:
            self._check_syntax(content, review)
        
        # 2. AST-based analysis (only if syntax is valid)
        tree = None
        if review.passed:
            try:
                tree = ast.parse(content)
                if self.check_quality:
                    self._analyze_ast(tree, content, lines, review)
            except SyntaxError:
                pass  # Already caught above
        
        # 3. Pattern-based checks
        if self.check_security:
            self._check_patterns(lines, SECURITY_PATTERNS, review)
        
        if self.check_performance:
            self._check_patterns(lines, PERFORMANCE_PATTERNS, review)
        
        if self.check_style:
            self._check_patterns(lines, STYLE_PATTERNS, review)
        
        # 4. Import check
        if self.check_imports and tree:
            self._check_imports(tree, filepath, review)
        
        # 5. v1.2.2: Enterprise mode checks
        if self.check_enterprise:
            self._check_enterprise(content, lines, tree, review)
        
        # 6. v1.2.2: Innovative mode suggestions
        if self.check_innovative:
            self._check_innovative(content, lines, tree, review)
        
        # Calculate final pass/fail
        if review.score < self.min_score:
            review.passed = False
        
        return review
    
    def _review_shell(self, content: str, lines: List[str], filepath: str, review: FileReview) -> FileReview:
        """v1.8.3: Shell script review adapter.
        
        Checks for:
        - Valid shebang
        - Basic syntax (unclosed quotes, brackets)
        - Security patterns (eval, curl|bash)
        - Best practices (set -euo pipefail)
        """
        # Check for shebang
        if lines and not lines[0].startswith('#!'):
            review.add_issue(Issue(
                category='style',
                severity=Severity.WARNING,
                message="Shell script missing shebang (e.g., #!/bin/bash)",
                line=1,
                rule_id='SH001'
            ))
        
        # Check for set -e or set -euo pipefail (error handling)
        has_error_handling = any('set -e' in line or 'set -o errexit' in line for line in lines)
        if not has_error_handling:
            review.add_issue(Issue(
                category='quality',
                severity=Severity.INFO,
                message="Consider adding 'set -euo pipefail' for error handling",
                line=0,
                rule_id='SH002'
            ))
        
        # Security patterns for shell
        shell_security_patterns = [
            (r'\beval\s+', 'SH_SEC001', 'eval command found (potential code injection)', Severity.WARNING),
            (r'curl.*\|\s*bash', 'SH_SEC002', 'curl piped to bash (security risk)', Severity.WARNING),
            (r'wget.*\|\s*sh', 'SH_SEC003', 'wget piped to sh (security risk)', Severity.WARNING),
            (r'\$\([^)]+\)', 'SH_SEC004', 'Command substitution used (verify input)', Severity.INFO),
        ]
        self._check_patterns(lines, shell_security_patterns, review)
        
        # Check for unclosed quotes
        for i, line in enumerate(lines):
            # Skip comments
            if line.strip().startswith('#'):
                continue
            # Simple unbalanced quote check
            single_quotes = line.count("'") - line.count("\\'")
            double_quotes = line.count('"') - line.count('\\"')
            if single_quotes % 2 != 0:
                review.add_issue(Issue(
                    category='syntax',
                    severity=Severity.WARNING,
                    message="Possible unclosed single quote",
                    line=i + 1,
                    rule_id='SH_SYN001'
                ))
            if double_quotes % 2 != 0:
                review.add_issue(Issue(
                    category='syntax',
                    severity=Severity.WARNING,
                    message="Possible unclosed double quote",
                    line=i + 1,
                    rule_id='SH_SYN002'
                ))
        
        # Shell scripts pass by default (no compile check available)
        review.passed = not any(i.severity == Severity.CRITICAL for i in review.issues)
        return review
    
    def _review_rust(self, content: str, lines: List[str], filepath: str, review: FileReview) -> FileReview:
        """v1.8.3: Rust code review adapter.
        
        Checks for:
        - Basic structure (fn main, mod declarations)
        - Unsafe blocks
        - Common patterns
        """
        # Check for main function or lib.rs structure
        has_main = any('fn main()' in line or 'fn main(' in line for line in lines)
        is_lib = filepath.endswith('lib.rs') or 'mod ' in content
        
        if not has_main and not is_lib and not 'mod.rs' in filepath:
            review.add_issue(Issue(
                category='structure',
                severity=Severity.INFO,
                message="No fn main() found (expected for binary crates)",
                line=0,
                rule_id='RS001'
            ))
        
        # Security patterns for Rust
        rust_security_patterns = [
            (r'\bunsafe\s*\{', 'RS_SEC001', 'unsafe block found (verify safety)', Severity.WARNING),
            (r'\.unwrap\(\)', 'RS_SEC002', '.unwrap() used (consider ? operator or match)', Severity.INFO),
            (r'\.expect\(', 'RS_SEC003', '.expect() used (document panic conditions)', Severity.INFO),
            (r'\bpanic!\s*\(', 'RS_SEC004', 'panic! macro used (avoid in library code)', Severity.INFO),
        ]
        self._check_patterns(lines, rust_security_patterns, review)
        
        # Check for unclosed braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces != close_braces:
            review.add_issue(Issue(
                category='syntax',
                severity=Severity.WARNING,
                message=f"Unbalanced braces: {open_braces} open, {close_braces} close",
                line=0,
                rule_id='RS_SYN001'
            ))
        
        # Rust files pass by default (cargo check not available)
        review.passed = not any(i.severity == Severity.CRITICAL for i in review.issues)
        return review
    
    def _review_go(self, content: str, lines: List[str], filepath: str, review: FileReview) -> FileReview:
        """v1.8.3: Go code review adapter.
        
        Checks for:
        - Package declaration
        - Main function for main package
        - Common patterns
        """
        # Check for package declaration
        has_package = any(line.strip().startswith('package ') for line in lines)
        if not has_package:
            review.add_issue(Issue(
                category='syntax',
                severity=Severity.CRITICAL,
                message="Missing package declaration",
                line=1,
                rule_id='GO001'
            ))
        
        # Check main package has main function
        is_main_pkg = any('package main' in line for line in lines)
        has_main_func = any('func main()' in line for line in lines)
        
        if is_main_pkg and not has_main_func:
            review.add_issue(Issue(
                category='structure',
                severity=Severity.ERROR,
                message="package main requires func main()",
                line=0,
                rule_id='GO002'
            ))
        
        # Go patterns
        go_patterns = [
            (r'panic\s*\(', 'GO_SEC001', 'panic() used (prefer error returns)', Severity.INFO),
            (r'//\s*nolint', 'GO_SEC002', 'nolint comment found (document reason)', Severity.INFO),
            (r'fmt\.Print', 'GO_STYLE001', 'fmt.Print used (consider structured logging)', Severity.INFO),
        ]
        self._check_patterns(lines, go_patterns, review)
        
        # Check for unclosed braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces != close_braces:
            review.add_issue(Issue(
                category='syntax',
                severity=Severity.WARNING,
                message=f"Unbalanced braces: {open_braces} open, {close_braces} close",
                line=0,
                rule_id='GO_SYN001'
            ))
        
        # Go files pass unless critical issues
        review.passed = not any(i.severity == Severity.CRITICAL for i in review.issues)
        return review
    
    def _review_generic(self, content: str, lines: List[str], filepath: str, review: FileReview) -> FileReview:
        """v1.8.3: Generic file review for unknown languages."""
        # Just check for basic issues
        if not content.strip():
            review.add_issue(Issue(
                category='quality',
                severity=Severity.WARNING,
                message="Empty file",
                line=0,
                rule_id='GEN001'
            ))
        
        # Always passes for unknown languages
        review.passed = True
        return review
    
    def review_directory(self, dirpath: str, extensions: List[str] = None) -> ReviewReport:
        """Review all Python files in a directory."""
        extensions = extensions or ['.py']
        report = ReviewReport()
        
        for root, _, files in os.walk(dirpath):
            for filename in files:
                if any(filename.endswith(ext) for ext in extensions):
                    filepath = os.path.join(root, filename)
                    file_review = self.review_file(filepath)
                    report.add_file(file_review)
        
        return report
    
    def review_code(self, code: str, filename: str = "code.py") -> FileReview:
        """Review code string directly."""
        review = FileReview(filepath=filename)
        lines = code.split('\n')
        
        # 1. Syntax check
        if self.check_syntax:
            self._check_syntax(code, review)
        
        # 2. AST-based analysis
        tree = None
        if review.passed:
            try:
                tree = ast.parse(code)
                if self.check_quality:
                    self._analyze_ast(tree, code, lines, review)
            except SyntaxError:
                pass
        
        # 3. Pattern-based checks
        if self.check_security:
            self._check_patterns(lines, SECURITY_PATTERNS, review)
        
        if self.check_performance:
            self._check_patterns(lines, PERFORMANCE_PATTERNS, review)
        
        if self.check_style:
            self._check_patterns(lines, STYLE_PATTERNS, review)
        
        # 4. v1.2.2: Enterprise mode checks
        if self.check_enterprise:
            self._check_enterprise(code, lines, tree, review)
        
        # 5. v1.2.2: Innovative mode suggestions
        if self.check_innovative:
            self._check_innovative(code, lines, tree, review)
        
        # Calculate final pass/fail
        if review.score < self.min_score:
            review.passed = False
        
        return review
    
    def _check_syntax(self, code: str, review: FileReview):
        """Check Python syntax validity."""
        try:
            compile(code, review.filepath, 'exec')
        except SyntaxError as e:
            review.add_issue(Issue(
                category='syntax',
                severity=Severity.CRITICAL,
                message=f"Syntax error: {e.msg}",
                line=e.lineno or 0,
                column=e.offset or 0,
                code_snippet=e.text or "",
                rule_id='SYN001'
            ))
    
    def _check_imports(self, tree: ast.AST, filepath: str, review: FileReview):
        """Check if imports can be resolved."""
        import importlib.util
        
        # Get the directory of the file being reviewed
        file_dir = os.path.dirname(os.path.abspath(filepath))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if not self._can_import(module_name, file_dir):
                        review.add_issue(Issue(
                            category='import',
                            severity=Severity.WARNING,
                            message=f"Cannot resolve import: {alias.name}",
                            line=node.lineno,
                            rule_id='IMP001'
                        ))
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if not self._can_import(module_name, file_dir):
                        review.add_issue(Issue(
                            category='import',
                            severity=Severity.WARNING,
                            message=f"Cannot resolve import: from {node.module}",
                            line=node.lineno,
                            rule_id='IMP002'
                        ))
    
    def _can_import(self, module_name: str, file_dir: str = None) -> bool:
        """Check if a module can be imported."""
        import importlib.util
        
        # Standard library and common packages
        KNOWN_MODULES = {
            'os', 'sys', 're', 'ast', 'json', 'yaml', 'pathlib', 'typing',
            'dataclasses', 'collections', 'itertools', 'functools', 'operator',
            'datetime', 'time', 'math', 'random', 'hashlib', 'secrets',
            'logging', 'unittest', 'pytest', 'argparse', 'configparser',
            'subprocess', 'threading', 'multiprocessing', 'asyncio', 'concurrent',
            'http', 'urllib', 'requests', 'aiohttp', 'flask', 'fastapi', 'django',
            'sqlalchemy', 'redis', 'celery', 'pydantic', 'numpy', 'pandas',
            'gunicorn', 'uvicorn', 'werkzeug', 'jinja2', 'click', 'typer',
            'boto3', 'google', 'azure', 'cryptography', 'jwt', 'bcrypt',
            'marshmallow', 'sqlmodel', 'alembic', 'pymongo', 'motor',
            'httpx', 'starlette', 'tortoise', 'peewee', 'psycopg2',
            # QonQrete modules
            'worqer', 'qrane', 'lib_ai', 'lib_funqtions', 'lib_security',
        }
        
        if module_name in KNOWN_MODULES:
            return True
        
        # v1.6.1: Check for local project files
        # This handles imports like `from config import ...` where config.py is in the same directory
        if file_dir:
            local_module_path = os.path.join(file_dir, f"{module_name}.py")
            if os.path.isfile(local_module_path):
                return True
            
            # Also check for package (directory with __init__.py)
            local_package_path = os.path.join(file_dir, module_name)
            if os.path.isdir(local_package_path):
                init_path = os.path.join(local_package_path, '__init__.py')
                if os.path.isfile(init_path):
                    return True
            
            # Check parent directories (up to 3 levels) for the module
            parent_dir = file_dir
            for _ in range(3):
                parent_dir = os.path.dirname(parent_dir)
                if not parent_dir:
                    break
                local_module_path = os.path.join(parent_dir, f"{module_name}.py")
                if os.path.isfile(local_module_path):
                    return True
                local_package_path = os.path.join(parent_dir, module_name)
                if os.path.isdir(local_package_path) and os.path.isfile(os.path.join(local_package_path, '__init__.py')):
                    return True
        
        try:
            spec = importlib.util.find_spec(module_name)
            return spec is not None
        except (ModuleNotFoundError, ValueError):
            return False
    
    def _check_patterns(self, lines: List[str], patterns: List[Tuple], review: FileReview):
        """Check code against regex patterns."""
        for i, line in enumerate(lines, 1):
            for pattern, rule_id, message, severity in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    review.add_issue(Issue(
                        category=rule_id.split('0')[0].lower(),
                        severity=severity,
                        message=message,
                        line=i,
                        code_snippet=line.strip()[:80],
                        rule_id=rule_id
                    ))
    
    def _analyze_ast(self, tree: ast.AST, code: str, lines: List[str], review: FileReview):
        """Perform AST-based code quality analysis."""
        metrics = {
            'functions': 0,
            'classes': 0,
            'methods': 0,
            'lines': len(lines),
            'docstrings': 0,
            'type_hints': 0,
            'try_blocks': 0,
            'complexity': 0,
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                metrics['functions'] += 1
                self._analyze_function(node, review, metrics)
            
            elif isinstance(node, ast.ClassDef):
                metrics['classes'] += 1
                self._analyze_class(node, review, metrics)
            
            elif isinstance(node, ast.Try):
                metrics['try_blocks'] += 1
        
        review.metrics = metrics
        
        # Quality checks based on metrics
        if metrics['functions'] > 0:
            docstring_ratio = metrics['docstrings'] / metrics['functions']
            if docstring_ratio < 0.5:
                review.add_issue(Issue(
                    category='quality',
                    severity=Severity.INFO,
                    message=f"Low docstring coverage ({docstring_ratio:.0%})",
                    rule_id='QUAL001'
                ))
            
            type_hint_ratio = metrics['type_hints'] / metrics['functions']
            if type_hint_ratio < 0.3:
                review.add_issue(Issue(
                    category='quality',
                    severity=Severity.INFO,
                    message=f"Low type hint coverage ({type_hint_ratio:.0%})",
                    rule_id='QUAL002'
                ))
    
    def _analyze_function(self, node: ast.FunctionDef, review: FileReview, metrics: dict):
        """Analyze a function definition."""
        # Check for docstring
        if ast.get_docstring(node):
            metrics['docstrings'] += 1
        
        # Check for type hints
        if node.returns or any(arg.annotation for arg in node.args.args):
            metrics['type_hints'] += 1
        
        # Check function length
        func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
        if func_lines > 50:
            review.add_issue(Issue(
                category='quality',
                severity=Severity.WARNING,
                message=f"Function '{node.name}' is too long ({func_lines} lines)",
                line=node.lineno,
                suggestion="Consider breaking into smaller functions",
                rule_id='QUAL003'
            ))
        
        # Check parameter count
        param_count = len(node.args.args)
        if param_count > 7:
            review.add_issue(Issue(
                category='quality',
                severity=Severity.WARNING,
                message=f"Function '{node.name}' has too many parameters ({param_count})",
                line=node.lineno,
                suggestion="Consider using a config object or dataclass",
                rule_id='QUAL004'
            ))
        
        # Calculate cyclomatic complexity
        complexity = self._calculate_complexity(node)
        metrics['complexity'] += complexity
        
        if complexity > 10:
            review.add_issue(Issue(
                category='quality',
                severity=Severity.WARNING,
                message=f"Function '{node.name}' has high complexity ({complexity})",
                line=node.lineno,
                suggestion="Consider refactoring to reduce branching",
                rule_id='QUAL005'
            ))
    
    def _analyze_class(self, node: ast.ClassDef, review: FileReview, metrics: dict):
        """Analyze a class definition."""
        # Check for docstring
        if ast.get_docstring(node):
            metrics['docstrings'] += 1
        
        # Count methods
        method_count = sum(1 for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        metrics['methods'] += method_count
        
        # Check class size
        if method_count > 20:
            review.add_issue(Issue(
                category='quality',
                severity=Severity.WARNING,
                message=f"Class '{node.name}' has many methods ({method_count})",
                line=node.lineno,
                suggestion="Consider splitting into smaller classes",
                rule_id='QUAL006'
            ))
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
            elif isinstance(child, ast.Assert):
                complexity += 1
        
        return complexity
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ENTERPRISE MODE CHECKS (v1.2.2)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _check_enterprise(self, code: str, lines: List[str], tree: Optional[ast.AST], review: FileReview):
        """Enterprise mode: Check for production-readiness patterns."""
        full_text = '\n'.join(lines)
        
        # Check for logging
        has_logging = 'import logging' in code or 'from logging' in code
        if not has_logging and len(lines) > 20:
            review.add_issue(Issue(
                category='enterprise',
                severity=Severity.WARNING,
                message="No logging import found",
                suggestion=ENTERPRISE_SUGGESTIONS['no_logging'],
                rule_id='ENT001'
            ))
        
        # Check for bare except clauses
        for i, line in enumerate(lines, 1):
            if re.match(r'\s*except\s*:', line):
                review.add_issue(Issue(
                    category='enterprise',
                    severity=Severity.WARNING,
                    message="Bare except clause (catch specific exceptions)",
                    line=i,
                    suggestion="Use `except Exception as e:` or specific exceptions",
                    rule_id='ENT002'
                ))
        
        # Check for file operations without context manager
        for i, line in enumerate(lines, 1):
            if re.search(r'open\s*\([^)]+\)(?!\s*as)', line) and '=' in line:
                # Make sure it's not already in a with statement
                if i > 1 and 'with' not in lines[i-2]:
                    review.add_issue(Issue(
                        category='enterprise',
                        severity=Severity.WARNING,
                        message="File open without context manager",
                        line=i,
                        suggestion='Use `with open(path) as f:` for safe file handling',
                        rule_id='ENT003'
                    ))
        
        # Check for HTTP requests without timeout
        for i, line in enumerate(lines, 1):
            if re.search(r'requests\.(?:get|post|put|delete|patch)\s*\([^)]*\)', line):
                if 'timeout' not in line:
                    review.add_issue(Issue(
                        category='enterprise',
                        severity=Severity.WARNING,
                        message="HTTP request without timeout",
                        line=i,
                        suggestion="Add `timeout=30` parameter to prevent hanging",
                        rule_id='ENT006'
                    ))
        
        # Suggest observability patterns
        has_metrics = any(x in code for x in ['prometheus', 'statsd', 'metrics', 'counter', 'histogram'])
        has_tracing = any(x in code for x in ['opentelemetry', 'jaeger', 'trace', 'span'])
        
        if len(lines) > 50 and not has_metrics:
            review.add_issue(Issue(
                category='enterprise',
                severity=Severity.INFO,
                message="No metrics/monitoring found",
                suggestion=ENTERPRISE_SUGGESTIONS['no_metrics'],
                rule_id='ENT010'
            ))
        
        if len(lines) > 100 and not has_tracing:
            review.add_issue(Issue(
                category='enterprise',
                severity=Severity.INFO,
                message="No distributed tracing found",
                suggestion=ENTERPRISE_SUGGESTIONS['no_tracing'],
                rule_id='ENT011'
            ))
        
        # Check for retry logic on external calls
        has_retry = any(x in code for x in ['tenacity', 'retry', 'backoff', 'retrying'])
        if 'requests' in code and not has_retry:
            review.add_issue(Issue(
                category='enterprise',
                severity=Severity.INFO,
                message="External calls without retry logic",
                suggestion=ENTERPRISE_SUGGESTIONS['no_retry'],
                rule_id='ENT012'
            ))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # INNOVATIVE MODE SUGGESTIONS (v1.2.2)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _check_innovative(self, code: str, lines: List[str], tree: Optional[ast.AST], review: FileReview):
        """Innovative mode: Suggest improvements and extensions."""
        
        # Check for sync HTTP that could be async
        for i, line in enumerate(lines, 1):
            if re.search(r'(?:requests|urllib)\.(?:get|post|put)', line):
                review.add_issue(Issue(
                    category='innovation',
                    severity=Severity.SUGGESTION,
                    message="Synchronous HTTP call detected",
                    line=i,
                    suggestion="Consider async/await with httpx or aiohttp for better concurrency",
                    rule_id='INN001'
                ))
        
        # Check for classes that could be dataclasses
        if tree:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    init_assigns = 0
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef) and child.name == '__init__':
                            for stmt in ast.walk(child):
                                if isinstance(stmt, ast.Assign):
                                    for target in stmt.targets:
                                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                                            init_assigns += 1
                    
                    if init_assigns >= 4:
                        review.add_issue(Issue(
                            category='innovation',
                            severity=Severity.SUGGESTION,
                            message=f"Class '{node.name}' has many instance attributes",
                            line=node.lineno,
                            suggestion="Consider using @dataclass for cleaner data containers",
                            rule_id='INN002'
                        ))
        
        # Check for os.path usage
        for i, line in enumerate(lines, 1):
            if re.search(r'os\.path\.(?:join|dirname|basename|exists|isfile|isdir)', line):
                review.add_issue(Issue(
                    category='innovation',
                    severity=Severity.SUGGESTION,
                    message="Using os.path for path operations",
                    line=i,
                    suggestion="Consider pathlib.Path for more Pythonic path handling",
                    rule_id='INN003'
                ))
                break  # Only report once
        
        # Check for .format() or % formatting
        for i, line in enumerate(lines, 1):
            if '.format(' in line or re.search(r'%\s*[sd]', line):
                review.add_issue(Issue(
                    category='innovation',
                    severity=Severity.SUGGESTION,
                    message="Using .format() or % for string formatting",
                    line=i,
                    suggestion="Consider f-strings for cleaner string formatting",
                    rule_id='INN004'
                ))
                break  # Only report once
        
        # Suggest type hints for functions without them
        if tree:
            untyped_funcs = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.returns and node.name != '__init__':
                        untyped_funcs.append(node.name)
            
            if untyped_funcs and len(untyped_funcs) <= 5:
                for name in untyped_funcs[:3]:
                    review.add_issue(Issue(
                        category='innovation',
                        severity=Severity.SUGGESTION,
                        message=f"Function '{name}' lacks return type hint",
                        suggestion="Add type hints for better IDE support: `def {name}(...) -> ReturnType:`",
                        rule_id='INN006'
                    ))
        
        # Suggest potential extensions based on patterns
        if 'flask' in code.lower() or 'fastapi' in code.lower():
            if 'health' not in code.lower():
                review.add_issue(Issue(
                    category='innovation',
                    severity=Severity.SUGGESTION,
                    message="Web app without health check endpoint",
                    suggestion="Add `/health` endpoint for load balancer and monitoring",
                    rule_id='INN010'
                ))
            
            if 'openapi' not in code.lower() and 'swagger' not in code.lower():
                review.add_issue(Issue(
                    category='innovation',
                    severity=Severity.SUGGESTION,
                    message="API without OpenAPI/Swagger documentation",
                    suggestion="Add OpenAPI spec for API documentation and client generation",
                    rule_id='INN011'
                ))
    
    def format_report(self, report: ReviewReport) -> str:
        """Format review report as human-readable text."""
        mode_str = f" (Mode: {self.mode.value})" if hasattr(self, 'mode') else ""
        lines = [
            "═" * 70,
            f"LocalInspeQtor Code Review Report{mode_str}",
            "═" * 70,
            f"Files reviewed: {len(report.files)}",
            f"Overall score: {report.overall_score}/100",
            f"Status: {'PASSED ✓' if report.passed else 'FAILED ✗'}",
            "",
            f"Issues: {report.total_issues} total",
            f"  Critical: {report.critical_count}",
            f"  Errors: {report.error_count}",
            f"  Warnings: {report.warning_count}",
            f"  Info: {report.info_count}",
            "═" * 70,
        ]
        
        for file_review in report.files:
            if file_review.issues:
                lines.append(f"\n📄 {file_review.filepath} (Score: {file_review.score}/100)")
                for issue in file_review.issues:
                    icon = {
                        Severity.CRITICAL: "🔴",
                        Severity.ERROR: "🟠",
                        Severity.WARNING: "🟡",
                        Severity.INFO: "🔵",
                        Severity.SUGGESTION: "💡",  # v1.2.2: Innovation suggestions
                    }.get(issue.severity, "⚪")
                    
                    lines.append(f"  {icon} [{issue.rule_id}] Line {issue.line}: {issue.message}")
                    if issue.suggestion:
                        lines.append(f"      💡 {issue.suggestion}")
        
        return "\n".join(lines)
    
    def format_xml(self, report: ReviewReport) -> str:
        """Format review report as XML for InspeQtor integration."""
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append(f'<review passed="{str(report.passed).lower()}" score="{report.overall_score}">')
        
        for file_review in report.files:
            lines.append(f'  <file path="{file_review.filepath}" score="{file_review.score}">')
            for issue in file_review.issues:
                lines.append(f'    <issue severity="{issue.severity.value}" rule="{issue.rule_id}" line="{issue.line}">')
                lines.append(f'      <message>{issue.message}</message>')
                if issue.suggestion:
                    lines.append(f'      <suggestion>{issue.suggestion}</suggestion>')
                lines.append('    </issue>')
            lines.append('  </file>')
        
        lines.append('</review>')
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='LocalInspeQtor - Zero-Cost Code Review')
    parser.add_argument('path', nargs='?', help='File or directory to review')
    parser.add_argument('--code', '-c', type=str, help='Code string to review')
    parser.add_argument('--format', '-f', choices=['text', 'xml'], default='text', help='Output format')
    parser.add_argument('--min-score', '-s', type=int, default=60, help='Minimum passing score')
    args = parser.parse_args()
    
    inspeqtor = LocalInspeQtor()
    inspeqtor.min_score = args.min_score
    
    if args.code:
        review = inspeqtor.review_code(args.code)
        report = ReviewReport()
        report.add_file(review)
    elif args.path:
        path = Path(args.path)
        if path.is_file():
            review = inspeqtor.review_file(str(path))
            report = ReviewReport()
            report.add_file(review)
        else:
            report = inspeqtor.review_directory(str(path))
    else:
        # Read from stdin
        code = sys.stdin.read()
        review = inspeqtor.review_code(code)
        report = ReviewReport()
        report.add_file(review)
    
    if args.format == 'xml':
        print(inspeqtor.format_xml(report))
    else:
        print(inspeqtor.format_report(report))
    
    sys.exit(0 if report.passed else 1)
