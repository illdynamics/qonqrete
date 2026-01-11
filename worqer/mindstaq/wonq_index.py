#!/usr/bin/env python3
"""
WoNQ Index: Local Memory Bank for Successful Code Patterns
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Stores and retrieves successful code patterns using keyword matching.
No vector DB, no embeddings - pure pattern matching!

v1.5.0
"""

import os
import re
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple
import ast


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class IndexEntry:
    """A single entry in the WoNQ Index."""
    name: str                           # Unique identifier
    keywords: List[str]                 # Search keywords
    imports: List[str]                  # Required imports
    code: str                           # The actual code
    score: int                          # WoNQ score (0-666)
    language: str = 'python'            # Programming language
    category: str = 'general'           # Category (http, database, auth, etc.)
    description: str = ''               # Human description
    source_url: str = ''                # Where it came from
    created_at: str = ''                # When it was added
    use_count: int = 0                  # How many times used
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'IndexEntry':
        return cls(**data)


@dataclass
class SearchMatch:
    """A match result from the WoNQ Index."""
    entry: IndexEntry
    relevance_score: float      # 0.0 - 1.0
    keyword_overlap: int        # Number of matching keywords
    import_overlap: int         # Number of matching imports
    
    @property
    def combined_score(self) -> float:
        """Combined score factoring in WoNQ score and relevance."""
        return (self.entry.score / 666.0) * 0.6 + self.relevance_score * 0.4


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Common programming keywords to extract
KEYWORD_PATTERNS = {
    # HTTP/Web
    'http': ['http', 'https', 'request', 'response', 'get', 'post', 'put', 'delete', 'api', 'rest', 'endpoint'],
    'web': ['web', 'server', 'client', 'url', 'uri', 'route', 'handler'],
    'async': ['async', 'await', 'asyncio', 'concurrent', 'parallel', 'coroutine'],
    
    # Database
    'database': ['database', 'db', 'sql', 'query', 'table', 'record', 'row', 'column'],
    'postgres': ['postgres', 'postgresql', 'psycopg', 'pg_'],
    'sqlite': ['sqlite', 'sqlite3'],
    'mysql': ['mysql', 'mariadb'],
    'mongodb': ['mongo', 'mongodb', 'pymongo', 'nosql'],
    'redis': ['redis', 'cache', 'memcache'],
    
    # Auth/Security
    'auth': ['auth', 'authentication', 'authorization', 'login', 'logout', 'session'],
    'jwt': ['jwt', 'token', 'bearer', 'jose'],
    'oauth': ['oauth', 'oauth2', 'openid'],
    'crypto': ['encrypt', 'decrypt', 'hash', 'hmac', 'aes', 'rsa', 'ssl', 'tls'],
    'password': ['password', 'bcrypt', 'argon', 'pbkdf'],
    
    # File/IO
    'file': ['file', 'read', 'write', 'open', 'close', 'path', 'directory', 'folder'],
    'json': ['json', 'loads', 'dumps', 'serialize', 'deserialize'],
    'yaml': ['yaml', 'yml'],
    'csv': ['csv', 'tsv', 'delimiter'],
    'xml': ['xml', 'parse', 'etree', 'lxml'],
    
    # CLI/System
    'cli': ['cli', 'command', 'argument', 'argparse', 'click', 'typer'],
    'process': ['process', 'subprocess', 'exec', 'spawn', 'shell'],
    'logging': ['log', 'logger', 'logging', 'debug', 'info', 'warning', 'error'],
    
    # Network
    'socket': ['socket', 'tcp', 'udp', 'port', 'bind', 'listen', 'connect'],
    'websocket': ['websocket', 'ws', 'wss', 'realtime'],
    
    # Data structures
    'list': ['list', 'array', 'append', 'extend', 'iterate'],
    'dict': ['dict', 'dictionary', 'map', 'key', 'value', 'mapping'],
    'class': ['class', 'object', 'instance', 'method', 'attribute', 'property'],
    
    # Testing
    'test': ['test', 'unittest', 'pytest', 'assert', 'mock', 'fixture'],
    
    # Frameworks
    'flask': ['flask', 'blueprint', 'jinja'],
    'django': ['django', 'model', 'view', 'template'],
    'fastapi': ['fastapi', 'pydantic', 'uvicorn'],
}

# Stop words to ignore
STOP_WORDS = {
    'the', 'a', 'an', 'to', 'for', 'and', 'or', 'in', 'on', 'at', 'is', 'are',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
    'this', 'that', 'these', 'those', 'it', 'its', 'of', 'with', 'as', 'by',
    'from', 'up', 'down', 'out', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now',
    'create', 'make', 'build', 'implement', 'write', 'code', 'function',
    'simple', 'basic', 'example', 'using', 'use', 'need', 'want', 'please',
}


def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    # Normalize
    text_lower = text.lower()
    
    # Remove special characters but keep underscores
    text_clean = re.sub(r'[^\w\s_]', ' ', text_lower)
    
    # Split into words
    words = text_clean.split()
    
    # Filter
    keywords = []
    for word in words:
        if len(word) < 2:
            continue
        if word in STOP_WORDS:
            continue
        if word.isdigit():
            continue
        keywords.append(word)
    
    # Also extract pattern-based keywords
    for category, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                if category not in keywords:
                    keywords.append(category)
                break
    
    return list(set(keywords))


def extract_imports_from_code(code: str) -> List[str]:
    """Extract import names from Python code."""
    imports = []
    
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split('.')[0])
    except SyntaxError:
        # Fallback: regex extraction
        import_pattern = r'^(?:from\s+(\w+)|import\s+(\w+))'
        for match in re.finditer(import_pattern, code, re.MULTILINE):
            name = match.group(1) or match.group(2)
            if name:
                imports.append(name)
    
    return list(set(imports))


# ═══════════════════════════════════════════════════════════════════════════════
# WONQ INDEX
# ═══════════════════════════════════════════════════════════════════════════════

class WonqIndex:
    """
    WoNQ Index: Local Memory Bank for successful code patterns.
    
    Features:
    - Keyword-based search (no embeddings!)
    - Import-based matching
    - Score-based ranking
    - Persistent JSON storage
    - Auto-update on successful generations
    
    Usage:
        index = WonqIndex()
        
        # Add entry
        index.add_entry(
            name='http_client_basic',
            code='def fetch(url): ...',
            keywords=['http', 'client', 'request'],
            imports=['requests'],
            score=620
        )
        
        # Search
        matches = index.search("create http client")
        best_match = matches[0] if matches else None
    """
    
    def __init__(self, index_path: str = None, config: dict = None):
        self.config = config or {}
        
        # Index storage path
        if index_path:
            self.index_path = Path(index_path)
        else:
            default_path = self.config.get('wonq_index', {}).get(
                'path', 
                os.path.expanduser('~/.qonqrete/wonq_index.json')
            )
            self.index_path = Path(default_path)
        
        # Ensure directory exists
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory index
        self.entries: Dict[str, IndexEntry] = {}
        
        # Settings
        self.min_score_to_store = self.config.get('wonq_index', {}).get('min_score', 400)
        self.max_entries = self.config.get('wonq_index', {}).get('max_entries', 1000)
        
        # Load existing index
        self._load()
    
    def _load(self):
        """Load index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, 'r') as f:
                    data = json.load(f)
                    for name, entry_data in data.get('entries', {}).items():
                        self.entries[name] = IndexEntry.from_dict(entry_data)
            except Exception:
                pass
    
    def _save(self):
        """Save index to disk."""
        try:
            data = {
                'version': __version__,
                'updated_at': datetime.utcnow().isoformat(),
                'entries': {name: entry.to_dict() for name, entry in self.entries.items()}
            }
            with open(self.index_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _generate_name(self, keywords: List[str], code: str) -> str:
        """Generate a unique name for an entry."""
        # Use keywords + hash of code
        kw_part = '_'.join(sorted(keywords[:3]))
        code_hash = hashlib.md5(code.encode()).hexdigest()[:8]
        return f"{kw_part}_{code_hash}"
    
    def add_entry(
        self,
        code: str,
        keywords: List[str] = None,
        imports: List[str] = None,
        score: int = 500,
        name: str = None,
        category: str = 'general',
        description: str = '',
        source_url: str = '',
        language: str = 'python'
    ) -> Optional[IndexEntry]:
        """
        Add a new entry to the index.
        
        Args:
            code: The code to store
            keywords: Search keywords (auto-extracted if not provided)
            imports: Required imports (auto-extracted if not provided)
            score: WoNQ score (0-666)
            name: Unique name (auto-generated if not provided)
            category: Category for grouping
            description: Human description
            source_url: Origin URL
            language: Programming language
        
        Returns:
            IndexEntry if added, None if rejected
        """
        # Check minimum score
        if score < self.min_score_to_store:
            return None
        
        # Auto-extract keywords if not provided
        if not keywords:
            keywords = extract_keywords(description or code)
        
        # Auto-extract imports if not provided
        if not imports:
            imports = extract_imports_from_code(code)
        
        # Generate name if not provided
        if not name:
            name = self._generate_name(keywords, code)
        
        # Check for duplicates (similar code)
        code_hash = hashlib.md5(code.encode()).hexdigest()
        for existing in self.entries.values():
            existing_hash = hashlib.md5(existing.code.encode()).hexdigest()
            if existing_hash == code_hash:
                # Update score if better
                if score > existing.score:
                    existing.score = score
                    self._save()
                return existing
        
        # Create entry
        entry = IndexEntry(
            name=name,
            keywords=keywords,
            imports=imports,
            code=code,
            score=score,
            language=language,
            category=category,
            description=description,
            source_url=source_url
        )
        
        # Add to index
        self.entries[name] = entry
        
        # Enforce max entries (remove lowest scores)
        if len(self.entries) > self.max_entries:
            sorted_entries = sorted(self.entries.items(), key=lambda x: x[1].score)
            to_remove = sorted_entries[:len(self.entries) - self.max_entries]
            for name_to_remove, _ in to_remove:
                del self.entries[name_to_remove]
        
        # Save
        self._save()
        
        return entry
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        min_relevance: float = 0.1,
        category: str = None,
        required_imports: List[str] = None
    ) -> List[SearchMatch]:
        """
        Search the index for matching entries.
        
        Args:
            query: Search query (natural language or keywords)
            max_results: Maximum results to return
            min_relevance: Minimum relevance score (0-1)
            category: Filter by category
            required_imports: Filter by required imports
        
        Returns:
            List of SearchMatch sorted by combined score
        """
        # Extract keywords from query
        query_keywords = set(extract_keywords(query))
        
        if not query_keywords:
            return []
        
        matches = []
        
        for entry in self.entries.values():
            # Filter by category
            if category and entry.category != category:
                continue
            
            # Filter by imports
            if required_imports:
                if not set(required_imports).issubset(set(entry.imports)):
                    continue
            
            # Calculate keyword overlap
            entry_keywords = set(entry.keywords)
            keyword_overlap = len(query_keywords & entry_keywords)
            
            if keyword_overlap == 0:
                continue
            
            # Calculate relevance score
            max_keywords = max(len(query_keywords), len(entry_keywords))
            relevance = keyword_overlap / max_keywords if max_keywords > 0 else 0
            
            # Import overlap bonus
            query_lower = query.lower()
            import_overlap = 0
            for imp in entry.imports:
                if imp.lower() in query_lower:
                    import_overlap += 1
            
            # Boost relevance with import overlap
            if import_overlap > 0:
                relevance = min(1.0, relevance + 0.1 * import_overlap)
            
            if relevance < min_relevance:
                continue
            
            matches.append(SearchMatch(
                entry=entry,
                relevance_score=relevance,
                keyword_overlap=keyword_overlap,
                import_overlap=import_overlap
            ))
        
        # Sort by combined score
        matches.sort(key=lambda m: m.combined_score, reverse=True)
        
        return matches[:max_results]
    
    def get_by_name(self, name: str) -> Optional[IndexEntry]:
        """Get entry by exact name."""
        return self.entries.get(name)
    
    def get_by_category(self, category: str) -> List[IndexEntry]:
        """Get all entries in a category."""
        return [e for e in self.entries.values() if e.category == category]
    
    def update_score(self, name: str, new_score: int):
        """Update the score of an entry."""
        if name in self.entries:
            self.entries[name].score = new_score
            self._save()
    
    def increment_use_count(self, name: str):
        """Increment the use count of an entry."""
        if name in self.entries:
            self.entries[name].use_count += 1
            self._save()
    
    def remove_entry(self, name: str) -> bool:
        """Remove an entry by name."""
        if name in self.entries:
            del self.entries[name]
            self._save()
            return True
        return False
    
    def get_stats(self) -> dict:
        """Get index statistics."""
        if not self.entries:
            return {
                'total_entries': 0,
                'avg_score': 0,
                'categories': {},
                'top_keywords': []
            }
        
        scores = [e.score for e in self.entries.values()]
        categories = {}
        all_keywords = []
        
        for entry in self.entries.values():
            cat = entry.category
            categories[cat] = categories.get(cat, 0) + 1
            all_keywords.extend(entry.keywords)
        
        # Count keywords
        keyword_counts = {}
        for kw in all_keywords:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        top_keywords = sorted(keyword_counts.items(), key=lambda x: -x[1])[:20]
        
        return {
            'total_entries': len(self.entries),
            'avg_score': sum(scores) / len(scores),
            'max_score': max(scores),
            'min_score': min(scores),
            'categories': categories,
            'top_keywords': top_keywords
        }
    
    def export_for_training(self) -> List[dict]:
        """Export entries in a format suitable for pattern training."""
        return [
            {
                'keywords': entry.keywords,
                'imports': entry.imports,
                'code': entry.code,
                'category': entry.category
            }
            for entry in self.entries.values()
            if entry.score >= 500  # Only high-quality entries
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

_global_index: Optional[WonqIndex] = None


def get_wonq_index(config: dict = None) -> WonqIndex:
    """Get the global WoNQ Index instance."""
    global _global_index
    if _global_index is None:
        _global_index = WonqIndex(config=config)
    return _global_index


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"WoNQ Index v{__version__}")
    print("=" * 60)
    
    # Test keyword extraction
    test_queries = [
        "create an HTTP client with async support",
        "implement JWT authentication for Flask API",
        "write a PostgreSQL database connection pool",
    ]
    
    print("\n[1] Keyword Extraction Test")
    for query in test_queries:
        keywords = extract_keywords(query)
        print(f"  Query: {query}")
        print(f"  Keywords: {keywords}")
        print()
    
    # Test index
    print("[2] Index Test")
    index = WonqIndex(index_path='/tmp/test_wonq_index.json')
    
    # Add test entries
    index.add_entry(
        code='''
import requests

def http_get(url, timeout=30):
    """Fetch URL with timeout."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
''',
        keywords=['http', 'get', 'request', 'json'],
        imports=['requests'],
        score=620,
        category='http',
        description='Simple HTTP GET client'
    )
    
    index.add_entry(
        code='''
import jwt
from datetime import datetime, timedelta

def create_jwt_token(payload, secret, expires_hours=24):
    """Create a JWT token."""
    payload['exp'] = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode(payload, secret, algorithm='HS256')
''',
        keywords=['jwt', 'token', 'auth', 'authentication'],
        imports=['jwt', 'datetime'],
        score=640,
        category='auth',
        description='JWT token creation'
    )
    
    # Search test
    print("\n[3] Search Test")
    results = index.search("create http client request")
    print(f"  Query: 'create http client request'")
    print(f"  Found: {len(results)} matches")
    for match in results:
        print(f"    - {match.entry.name}: score={match.entry.score}, relevance={match.relevance_score:.2f}")
    
    # Stats
    print("\n[4] Index Stats")
    stats = index.get_stats()
    print(f"  Total entries: {stats['total_entries']}")
    print(f"  Avg score: {stats['avg_score']:.1f}")
    print(f"  Categories: {stats['categories']}")
    
    print("\n✅ WoNQ Index working!")
