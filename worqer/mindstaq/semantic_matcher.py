#!/usr/bin/env python3
"""
Semantic Matcher: AST-Based Code Similarity Without LLM
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Uses AST structure, keywords, and imports to find semantically similar code.
No embeddings, no vector DB, no LLM - pure pattern matching!

v1.5.0
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple
from collections import Counter
import math


__version__ = '1.5.0'


# ═══════════════════════════════════════════════════════════════════════════════
# AST PATTERN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ASTPattern:
    """Extracted AST pattern from code."""
    node_types: List[str]           # Types of nodes (FunctionDef, If, For, etc.)
    node_counts: Dict[str, int]     # Count of each node type
    depth: int                      # Maximum nesting depth
    has_classes: bool
    has_functions: bool
    has_async: bool
    has_decorators: bool
    has_comprehensions: bool
    has_generators: bool
    has_context_managers: bool
    has_exception_handling: bool
    imports: List[str]
    function_names: List[str]
    class_names: List[str]


def extract_ast_pattern(code: str) -> Optional[ASTPattern]:
    """Extract AST pattern from code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    
    node_types = []
    node_counts = Counter()
    max_depth = 0
    has_classes = False
    has_functions = False
    has_async = False
    has_decorators = False
    has_comprehensions = False
    has_generators = False
    has_context_managers = False
    has_exception_handling = False
    imports = []
    function_names = []
    class_names = []
    
    def walk_with_depth(node, depth=0):
        nonlocal max_depth, has_classes, has_functions, has_async
        nonlocal has_decorators, has_comprehensions, has_generators
        nonlocal has_context_managers, has_exception_handling
        
        max_depth = max(max_depth, depth)
        node_type = type(node).__name__
        node_types.append(node_type)
        node_counts[node_type] += 1
        
        if isinstance(node, ast.ClassDef):
            has_classes = True
            class_names.append(node.name)
            if node.decorator_list:
                has_decorators = True
        
        elif isinstance(node, ast.FunctionDef):
            has_functions = True
            function_names.append(node.name)
            if node.decorator_list:
                has_decorators = True
        
        elif isinstance(node, ast.AsyncFunctionDef):
            has_functions = True
            has_async = True
            function_names.append(node.name)
        
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
            has_comprehensions = True
        
        elif isinstance(node, ast.GeneratorExp):
            has_generators = True
        
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            has_context_managers = True
        
        elif isinstance(node, ast.Try):
            has_exception_handling = True
        
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split('.')[0])
        
        for child in ast.iter_child_nodes(node):
            walk_with_depth(child, depth + 1)
    
    walk_with_depth(tree)
    
    return ASTPattern(
        node_types=node_types,
        node_counts=dict(node_counts),
        depth=max_depth,
        has_classes=has_classes,
        has_functions=has_functions,
        has_async=has_async,
        has_decorators=has_decorators,
        has_comprehensions=has_comprehensions,
        has_generators=has_generators,
        has_context_managers=has_context_managers,
        has_exception_handling=has_exception_handling,
        imports=list(set(imports)),
        function_names=function_names,
        class_names=class_names
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Technical term mappings for semantic matching
SEMANTIC_GROUPS = {
    'http': {'http', 'https', 'request', 'response', 'api', 'rest', 'endpoint', 'url', 'get', 'post', 'put', 'delete', 'fetch', 'client'},
    'database': {'database', 'db', 'sql', 'query', 'table', 'record', 'insert', 'update', 'select', 'delete', 'connection', 'cursor'},
    'auth': {'auth', 'authentication', 'authorization', 'login', 'logout', 'session', 'token', 'jwt', 'oauth', 'password', 'credential'},
    'file': {'file', 'read', 'write', 'open', 'close', 'path', 'directory', 'folder', 'stream', 'buffer'},
    'async': {'async', 'await', 'asyncio', 'concurrent', 'parallel', 'coroutine', 'task', 'future', 'gather'},
    'network': {'socket', 'tcp', 'udp', 'port', 'connect', 'bind', 'listen', 'server', 'client', 'websocket'},
    'data': {'json', 'xml', 'yaml', 'csv', 'parse', 'serialize', 'deserialize', 'encode', 'decode'},
    'crypto': {'encrypt', 'decrypt', 'hash', 'hmac', 'sign', 'verify', 'key', 'cipher', 'ssl', 'tls'},
    'test': {'test', 'unittest', 'pytest', 'assert', 'mock', 'fixture', 'setup', 'teardown'},
    'error': {'error', 'exception', 'try', 'catch', 'raise', 'handle', 'fail', 'retry'},
}

# Import to semantic group mapping
IMPORT_SEMANTIC = {
    'requests': 'http',
    'aiohttp': 'http',
    'httpx': 'http',
    'urllib': 'http',
    'flask': 'http',
    'django': 'http',
    'fastapi': 'http',
    'sqlite3': 'database',
    'psycopg2': 'database',
    'pymongo': 'database',
    'sqlalchemy': 'database',
    'redis': 'database',
    'jwt': 'auth',
    'authlib': 'auth',
    'passlib': 'auth',
    'asyncio': 'async',
    'aiofiles': 'async',
    'socket': 'network',
    'websockets': 'network',
    'json': 'data',
    'yaml': 'data',
    'xml': 'data',
    'csv': 'data',
    'cryptography': 'crypto',
    'hashlib': 'crypto',
    'ssl': 'crypto',
    'pytest': 'test',
    'unittest': 'test',
}


def extract_semantic_keywords(text: str) -> Set[str]:
    """Extract semantic keywords from text."""
    text_lower = text.lower()
    words = set(re.findall(r'\b[a-z_][a-z0-9_]*\b', text_lower))
    
    keywords = set()
    
    for word in words:
        # Add the word itself if meaningful
        if len(word) >= 3:
            keywords.add(word)
        
        # Add semantic groups the word belongs to
        for group, terms in SEMANTIC_GROUPS.items():
            if word in terms:
                keywords.add(f"@{group}")  # Prefix with @ for semantic groups
    
    return keywords


def extract_code_keywords(code: str) -> Set[str]:
    """Extract keywords from code including identifiers."""
    keywords = extract_semantic_keywords(code)
    
    try:
        tree = ast.parse(code)
        
        for node in ast.walk(tree):
            # Function names
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                keywords.add(node.name.lower())
                # Split camelCase and snake_case
                parts = re.split(r'_|(?=[A-Z])', node.name)
                for part in parts:
                    if len(part) >= 3:
                        keywords.add(part.lower())
            
            # Class names
            elif isinstance(node, ast.ClassDef):
                keywords.add(node.name.lower())
            
            # Variable names (assignments)
            elif isinstance(node, ast.Name):
                if len(node.id) >= 3:
                    keywords.add(node.id.lower())
            
            # String literals (might contain useful terms)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if len(node.value) < 50:  # Skip long strings
                    str_keywords = extract_semantic_keywords(node.value)
                    keywords.update(str_keywords)
    
    except SyntaxError:
        pass
    
    return keywords


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC MATCHER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SemanticMatch:
    """Result of semantic matching."""
    code: str
    total_score: float          # Combined score 0-100
    keyword_score: float        # Keyword overlap score
    ast_score: float            # AST structure score
    import_score: float         # Import relevance score
    semantic_score: float       # Semantic group score
    matched_keywords: Set[str]
    matched_imports: Set[str]
    matched_groups: Set[str]


class SemanticMatcher:
    """
    Matches code snippets to queries using semantic analysis.
    
    Scoring components:
    1. Keyword overlap (40%): Direct word matching
    2. AST structure (20%): Similar code structure
    3. Import relevance (20%): Matching imports
    4. Semantic groups (20%): Conceptual similarity
    
    Usage:
        matcher = SemanticMatcher()
        
        candidates = [
            "def fetch(url): return requests.get(url)",
            "def read_file(path): return open(path).read()",
        ]
        
        matches = matcher.match("create http client", candidates)
        best = matches[0]  # Highest scoring match
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Score weights (must sum to 1.0)
        self.weights = {
            'keyword': 0.40,
            'ast': 0.20,
            'import': 0.20,
            'semantic': 0.20,
        }
    
    def _keyword_score(self, query_kw: Set[str], code_kw: Set[str]) -> Tuple[float, Set[str]]:
        """Calculate keyword overlap score."""
        # Filter out semantic group markers for this comparison
        query_words = {k for k in query_kw if not k.startswith('@')}
        code_words = {k for k in code_kw if not k.startswith('@')}
        
        if not query_words or not code_words:
            return 0.0, set()
        
        overlap = query_words & code_words
        
        # Jaccard similarity
        union = query_words | code_words
        score = len(overlap) / len(union) if union else 0.0
        
        return score, overlap
    
    def _ast_score(self, query_pattern: Optional[ASTPattern], code_pattern: Optional[ASTPattern]) -> float:
        """Calculate AST structure similarity."""
        if not query_pattern or not code_pattern:
            return 0.5  # Neutral score if can't compare
        
        score = 0.0
        
        # Node type distribution similarity
        query_counts = Counter(query_pattern.node_counts)
        code_counts = Counter(code_pattern.node_counts)
        
        all_types = set(query_counts.keys()) | set(code_counts.keys())
        if all_types:
            type_sim = 0
            for t in all_types:
                q = query_counts.get(t, 0)
                c = code_counts.get(t, 0)
                if q > 0 or c > 0:
                    type_sim += min(q, c) / max(q, c)
            type_sim /= len(all_types)
            score += type_sim * 0.4
        
        # Feature similarity
        features = [
            'has_classes', 'has_functions', 'has_async', 'has_decorators',
            'has_comprehensions', 'has_context_managers', 'has_exception_handling'
        ]
        
        feature_matches = 0
        for f in features:
            if getattr(query_pattern, f) == getattr(code_pattern, f):
                feature_matches += 1
        
        score += (feature_matches / len(features)) * 0.4
        
        # Depth similarity
        depth_diff = abs(query_pattern.depth - code_pattern.depth)
        depth_sim = 1.0 / (1.0 + depth_diff * 0.1)
        score += depth_sim * 0.2
        
        return score
    
    def _import_score(self, query_kw: Set[str], code_imports: List[str]) -> Tuple[float, Set[str]]:
        """Calculate import relevance score."""
        if not code_imports:
            return 0.0, set()
        
        # Get semantic groups from query
        query_groups = {k[1:] for k in query_kw if k.startswith('@')}
        query_words = {k for k in query_kw if not k.startswith('@')}
        
        matched = set()
        score = 0.0
        
        for imp in code_imports:
            imp_lower = imp.lower()
            
            # Direct import name match
            if imp_lower in query_words:
                matched.add(imp)
                score += 1.0
            
            # Semantic group match
            elif imp_lower in IMPORT_SEMANTIC:
                imp_group = IMPORT_SEMANTIC[imp_lower]
                if imp_group in query_groups or any(
                    term in query_words for term in SEMANTIC_GROUPS.get(imp_group, [])
                ):
                    matched.add(imp)
                    score += 0.7
        
        # Normalize by number of imports
        normalized = score / len(code_imports) if code_imports else 0.0
        
        return min(1.0, normalized), matched
    
    def _semantic_score(self, query_kw: Set[str], code_kw: Set[str]) -> Tuple[float, Set[str]]:
        """Calculate semantic group overlap score."""
        query_groups = {k for k in query_kw if k.startswith('@')}
        code_groups = {k for k in code_kw if k.startswith('@')}
        
        if not query_groups or not code_groups:
            return 0.0, set()
        
        overlap = query_groups & code_groups
        union = query_groups | code_groups
        
        score = len(overlap) / len(union) if union else 0.0
        
        return score, {g[1:] for g in overlap}  # Remove @ prefix
    
    def score_code(self, query: str, code: str) -> SemanticMatch:
        """Score a single code snippet against a query."""
        # Extract keywords
        query_kw = extract_semantic_keywords(query)
        code_kw = extract_code_keywords(code)
        
        # Extract AST patterns (for query, treat as pseudo-code description)
        query_pattern = extract_ast_pattern(code)  # Use code's AST as reference
        code_pattern = extract_ast_pattern(code)
        
        # Get imports
        code_imports = []
        if code_pattern:
            code_imports = code_pattern.imports
        
        # Calculate component scores
        kw_score, matched_kw = self._keyword_score(query_kw, code_kw)
        ast_sc = self._ast_score(query_pattern, code_pattern)
        imp_score, matched_imp = self._import_score(query_kw, code_imports)
        sem_score, matched_groups = self._semantic_score(query_kw, code_kw)
        
        # Combined score
        total = (
            kw_score * self.weights['keyword'] +
            ast_sc * self.weights['ast'] +
            imp_score * self.weights['import'] +
            sem_score * self.weights['semantic']
        ) * 100
        
        return SemanticMatch(
            code=code,
            total_score=total,
            keyword_score=kw_score * 100,
            ast_score=ast_sc * 100,
            import_score=imp_score * 100,
            semantic_score=sem_score * 100,
            matched_keywords=matched_kw,
            matched_imports=matched_imp,
            matched_groups=matched_groups
        )
    
    def match(
        self,
        query: str,
        candidates: List[str],
        min_score: float = 10.0,
        max_results: int = 10
    ) -> List[SemanticMatch]:
        """
        Match a query against multiple code candidates.
        
        Args:
            query: Natural language query or keywords
            candidates: List of code snippets to match
            min_score: Minimum score threshold (0-100)
            max_results: Maximum results to return
        
        Returns:
            List of SemanticMatch sorted by score descending
        """
        matches = []
        
        for code in candidates:
            if not code or not code.strip():
                continue
            
            match = self.score_code(query, code)
            
            if match.total_score >= min_score:
                matches.append(match)
        
        # Sort by score descending
        matches.sort(key=lambda m: m.total_score, reverse=True)
        
        return matches[:max_results]
    
    def rank_by_task(
        self,
        task_description: str,
        candidates: List[str],
        boost_features: Dict[str, float] = None
    ) -> List[SemanticMatch]:
        """
        Rank candidates with task-specific boosting.
        
        Args:
            task_description: Description of the task
            candidates: Code snippets to rank
            boost_features: Extra boosts for features
                e.g. {'async': 1.5, 'error_handling': 1.2}
        
        Returns:
            Ranked list of SemanticMatch
        """
        boost_features = boost_features or {}
        
        matches = self.match(task_description, candidates, min_score=0)
        
        # Apply boosts
        for match in matches:
            pattern = extract_ast_pattern(match.code)
            if not pattern:
                continue
            
            boost = 1.0
            
            if 'async' in boost_features and pattern.has_async:
                boost *= boost_features['async']
            
            if 'error_handling' in boost_features and pattern.has_exception_handling:
                boost *= boost_features['error_handling']
            
            if 'type_hints' in boost_features:
                # Check for type hints in code
                if ' -> ' in match.code or ': str' in match.code or ': int' in match.code:
                    boost *= boost_features['type_hints']
            
            match.total_score *= boost
        
        # Re-sort after boosting
        matches.sort(key=lambda m: m.total_score, reverse=True)
        
        return matches


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Semantic Matcher v{__version__}")
    print("=" * 60)
    
    matcher = SemanticMatcher()
    
    # Test candidates
    candidates = [
        '''
import requests

def fetch_url(url):
    response = requests.get(url)
    return response.json()
''',
        '''
def read_file(path):
    with open(path, 'r') as f:
        return f.read()
''',
        '''
import aiohttp

async def async_fetch(url, timeout=30):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
''',
        '''
import sqlite3

def query_database(db_path, sql):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()
''',
        '''
import jwt

def create_token(payload, secret):
    return jwt.encode(payload, secret, algorithm='HS256')
''',
    ]
    
    # Test queries
    queries = [
        "create http client to fetch json data",
        "read text from file",
        "async http request with timeout",
        "sql database query",
        "jwt token authentication",
    ]
    
    print("\n[1] Semantic Matching Tests")
    print("-" * 60)
    
    for query in queries:
        print(f"\nQuery: '{query}'")
        matches = matcher.match(query, candidates, min_score=5)
        
        for i, m in enumerate(matches[:2]):
            print(f"  #{i+1} Score: {m.total_score:.1f}")
            print(f"      Keywords: {m.keyword_score:.1f}, AST: {m.ast_score:.1f}")
            print(f"      Imports: {m.import_score:.1f}, Semantic: {m.semantic_score:.1f}")
            print(f"      Matched: {m.matched_imports or m.matched_keywords}")
            print(f"      Code: {m.code.strip()[:60]}...")
    
    print("\n" + "=" * 60)
    print("✅ Semantic Matcher working!")
