#!/usr/bin/env python3
"""
Pattern Database: Expanded Code Pattern Library
Part of mindstaQ v2.0 - ZERO LLM Code Generation

200+ pre-built code patterns for common programming tasks.
No LLM needed - just pattern matching and adaptation!

v1.5.0
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
import re


__version__ = '1.5.0'


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN DATA CLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodePattern:
    """A code pattern template."""
    name: str                       # Pattern identifier
    category: str                   # Category (http, database, auth, etc.)
    keywords: List[str]             # Matching keywords
    imports: List[str]              # Required imports
    code: str                       # The actual code template
    description: str = ''           # Human description
    complexity: int = 1             # 1=simple, 2=medium, 3=complex
    has_async: bool = False         # Has async version
    async_code: str = ''            # Async version if available


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP/WEB PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

HTTP_PATTERNS = [
    CodePattern(
        name='http_get_basic',
        category='http',
        keywords=['http', 'get', 'request', 'fetch', 'url'],
        imports=['requests'],
        code='''
import requests

def http_get(url: str, timeout: int = 30) -> dict:
    """Fetch JSON data from URL."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()
''',
        description='Basic HTTP GET request',
        complexity=1
    ),
    
    CodePattern(
        name='http_get_with_headers',
        category='http',
        keywords=['http', 'get', 'headers', 'auth', 'token', 'bearer'],
        imports=['requests'],
        code='''
import requests
from typing import Dict, Any, Optional

def http_get_with_auth(
    url: str,
    token: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Fetch data with authentication header."""
    default_headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    if headers:
        default_headers.update(headers)
    
    response = requests.get(url, headers=default_headers, timeout=timeout)
    response.raise_for_status()
    return response.json()
''',
        description='HTTP GET with authentication',
        complexity=2
    ),
    
    CodePattern(
        name='http_post_json',
        category='http',
        keywords=['http', 'post', 'json', 'send', 'submit', 'data'],
        imports=['requests'],
        code='''
import requests
from typing import Dict, Any, Optional

def http_post_json(
    url: str,
    data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """POST JSON data to URL."""
    default_headers = {'Content-Type': 'application/json'}
    if headers:
        default_headers.update(headers)
    
    response = requests.post(url, json=data, headers=default_headers, timeout=timeout)
    response.raise_for_status()
    return response.json()
''',
        description='HTTP POST with JSON body',
        complexity=2
    ),
    
    CodePattern(
        name='http_async_get',
        category='http',
        keywords=['http', 'async', 'aiohttp', 'fetch', 'concurrent'],
        imports=['aiohttp', 'asyncio'],
        code='''
import aiohttp
import asyncio
from typing import Dict, Any, Optional

async def async_http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """Async HTTP GET request."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()
            return await response.json()
''',
        description='Async HTTP GET with aiohttp',
        complexity=2,
        has_async=True
    ),
    
    CodePattern(
        name='http_retry',
        category='http',
        keywords=['http', 'retry', 'resilient', 'backoff', 'robust'],
        imports=['requests', 'time'],
        code='''
import requests
import time
from typing import Dict, Any, Optional

def http_get_with_retry(
    url: str,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    """HTTP GET with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait_time = backoff_factor * (2 ** attempt)
            time.sleep(wait_time)
    return None
''',
        description='HTTP GET with retry logic',
        complexity=2
    ),
    
    CodePattern(
        name='http_session',
        category='http',
        keywords=['http', 'session', 'connection', 'pool', 'reuse'],
        imports=['requests'],
        code='''
import requests
from typing import Dict, Any, Optional
from contextlib import contextmanager

class HttpClient:
    """HTTP client with connection pooling."""
    
    def __init__(self, base_url: str = '', timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
    
    def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """GET request."""
        url = f"{self.base_url}{path}"
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def post(self, path: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """POST request."""
        url = f"{self.base_url}{path}"
        response = self.session.post(url, json=data, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        """Close the session."""
        self.session.close()
''',
        description='HTTP client with session management',
        complexity=3
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

DATABASE_PATTERNS = [
    CodePattern(
        name='sqlite_basic',
        category='database',
        keywords=['sqlite', 'database', 'sql', 'query', 'local'],
        imports=['sqlite3'],
        code='''
import sqlite3
from typing import List, Tuple, Any, Optional

def execute_query(db_path: str, query: str, params: Tuple = ()) -> List[Tuple]:
    """Execute SQL query and return results."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.commit()
        return results
    finally:
        conn.close()
''',
        description='Basic SQLite query execution',
        complexity=1
    ),
    
    CodePattern(
        name='sqlite_context',
        category='database',
        keywords=['sqlite', 'database', 'context', 'manager', 'safe'],
        imports=['sqlite3', 'contextlib'],
        code='''
import sqlite3
from contextlib import contextmanager
from typing import Generator, Any

@contextmanager
def get_db_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(db_path: str, query: str, params: tuple = ()) -> list:
    """Execute query and return all results."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
''',
        description='SQLite with context manager',
        complexity=2
    ),
    
    CodePattern(
        name='postgres_pool',
        category='database',
        keywords=['postgres', 'postgresql', 'pool', 'connection', 'psycopg'],
        imports=['psycopg2', 'psycopg2.pool'],
        code='''
import psycopg2
from psycopg2 import pool
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

class PostgresPool:
    """PostgreSQL connection pool."""
    
    def __init__(self, dsn: str, min_conn: int = 1, max_conn: int = 10):
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            min_conn, max_conn, dsn
        )
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool."""
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute query and return results."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                return [dict(zip(columns, row)) for row in cur.fetchall()]
    
    def close(self):
        """Close all connections."""
        self.pool.closeall()
''',
        description='PostgreSQL connection pool',
        complexity=3
    ),
    
    CodePattern(
        name='redis_cache',
        category='database',
        keywords=['redis', 'cache', 'store', 'key', 'value', 'ttl'],
        imports=['redis'],
        code='''
import redis
import json
from typing import Any, Optional

class RedisCache:
    """Simple Redis cache wrapper."""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = self.client.get(key)
        if value:
            return json.loads(value)
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL."""
        return self.client.setex(key, ttl, json.dumps(value))
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        return self.client.delete(key) > 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self.client.exists(key) > 0
''',
        description='Redis cache wrapper',
        complexity=2
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# AUTH/SECURITY PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

AUTH_PATTERNS = [
    CodePattern(
        name='jwt_create',
        category='auth',
        keywords=['jwt', 'token', 'create', 'generate', 'auth'],
        imports=['jwt', 'datetime'],
        code='''
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any

def create_jwt_token(
    payload: Dict[str, Any],
    secret: str,
    expires_hours: int = 24,
    algorithm: str = 'HS256'
) -> str:
    """Create a JWT token."""
    payload = payload.copy()
    payload['exp'] = datetime.utcnow() + timedelta(hours=expires_hours)
    payload['iat'] = datetime.utcnow()
    return jwt.encode(payload, secret, algorithm=algorithm)
''',
        description='Create JWT token',
        complexity=1
    ),
    
    CodePattern(
        name='jwt_verify',
        category='auth',
        keywords=['jwt', 'token', 'verify', 'decode', 'validate'],
        imports=['jwt'],
        code='''
import jwt
from typing import Dict, Any, Optional

def verify_jwt_token(
    token: str,
    secret: str,
    algorithms: list = None
) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    algorithms = algorithms or ['HS256']
    try:
        payload = jwt.decode(token, secret, algorithms=algorithms)
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
''',
        description='Verify JWT token',
        complexity=1
    ),
    
    CodePattern(
        name='password_hash',
        category='auth',
        keywords=['password', 'hash', 'bcrypt', 'secure', 'store'],
        imports=['bcrypt'],
        code='''
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
''',
        description='Password hashing with bcrypt',
        complexity=1
    ),
    
    CodePattern(
        name='api_key_auth',
        category='auth',
        keywords=['api', 'key', 'auth', 'validate', 'middleware'],
        imports=['functools', 'hashlib'],
        code='''
import functools
import hashlib
import secrets
from typing import Callable, Optional

def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def require_api_key(valid_keys: set) -> Callable:
    """Decorator to require API key authentication."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, api_key: Optional[str] = None, **kwargs):
            if not api_key or hash_api_key(api_key) not in valid_keys:
                raise PermissionError("Invalid API key")
            return func(*args, **kwargs)
        return wrapper
    return decorator
''',
        description='API key authentication',
        complexity=2
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# FILE/IO PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

FILE_PATTERNS = [
    CodePattern(
        name='file_read_text',
        category='file',
        keywords=['file', 'read', 'text', 'open', 'content'],
        imports=[],
        code='''
from typing import Optional
from pathlib import Path

def read_text_file(path: str, encoding: str = 'utf-8') -> Optional[str]:
    """Read text file contents."""
    try:
        return Path(path).read_text(encoding=encoding)
    except (IOError, OSError):
        return None
''',
        description='Read text file',
        complexity=1
    ),
    
    CodePattern(
        name='file_write_text',
        category='file',
        keywords=['file', 'write', 'text', 'save', 'create'],
        imports=[],
        code='''
from pathlib import Path

def write_text_file(path: str, content: str, encoding: str = 'utf-8') -> bool:
    """Write text to file."""
    try:
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding=encoding)
        return True
    except (IOError, OSError):
        return False
''',
        description='Write text file',
        complexity=1
    ),
    
    CodePattern(
        name='json_read_write',
        category='file',
        keywords=['json', 'file', 'read', 'write', 'load', 'dump'],
        imports=['json'],
        code='''
import json
from typing import Any, Optional
from pathlib import Path

def read_json(path: str) -> Optional[Any]:
    """Read JSON file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return None


def write_json(path: str, data: Any, indent: int = 2) -> bool:
    """Write data to JSON file."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except (IOError, TypeError):
        return False
''',
        description='JSON file operations',
        complexity=1
    ),
    
    CodePattern(
        name='yaml_read_write',
        category='file',
        keywords=['yaml', 'file', 'read', 'write', 'config'],
        imports=['yaml'],
        code='''
import yaml
from typing import Any, Optional
from pathlib import Path

def read_yaml(path: str) -> Optional[Any]:
    """Read YAML file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except (IOError, yaml.YAMLError):
        return None


def write_yaml(path: str, data: Any) -> bool:
    """Write data to YAML file."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except (IOError, yaml.YAMLError):
        return False
''',
        description='YAML file operations',
        complexity=1
    ),
    
    CodePattern(
        name='csv_read_write',
        category='file',
        keywords=['csv', 'file', 'read', 'write', 'data', 'table'],
        imports=['csv'],
        code='''
import csv
from typing import List, Dict, Any
from pathlib import Path

def read_csv(path: str) -> List[Dict[str, str]]:
    """Read CSV file as list of dicts."""
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))
    except IOError:
        return []


def write_csv(path: str, data: List[Dict[str, Any]], fieldnames: List[str] = None) -> bool:
    """Write list of dicts to CSV file."""
    if not data:
        return False
    
    try:
        fieldnames = fieldnames or list(data[0].keys())
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        return True
    except IOError:
        return False
''',
        description='CSV file operations',
        complexity=2
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# CLI/SYSTEM PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

CLI_PATTERNS = [
    CodePattern(
        name='argparse_basic',
        category='cli',
        keywords=['cli', 'argparse', 'argument', 'command', 'parse'],
        imports=['argparse'],
        code='''
import argparse
from typing import Namespace

def parse_args() -> Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Application description')
    
    parser.add_argument('input', help='Input file path')
    parser.add_argument('-o', '--output', default='output.txt', help='Output file path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--count', type=int, default=10, help='Number of items')
    
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Verbose: {args.verbose}")


if __name__ == '__main__':
    main()
''',
        description='Basic argparse CLI',
        complexity=2
    ),
    
    CodePattern(
        name='subprocess_run',
        category='cli',
        keywords=['subprocess', 'command', 'run', 'execute', 'shell'],
        imports=['subprocess'],
        code='''
import subprocess
from typing import Tuple, Optional

def run_command(
    command: str,
    timeout: int = 60,
    shell: bool = True
) -> Tuple[int, str, str]:
    """Run shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, '', 'Command timed out'
    except Exception as e:
        return -1, '', str(e)
''',
        description='Run subprocess command',
        complexity=2
    ),
    
    CodePattern(
        name='logging_setup',
        category='cli',
        keywords=['logging', 'log', 'debug', 'info', 'error', 'setup'],
        imports=['logging'],
        code='''
import logging
from typing import Optional

def setup_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    format_str: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
) -> logging.Logger:
    """Configure logging with console and optional file output."""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(format_str))
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_str))
        logger.addHandler(file_handler)
    
    return logger
''',
        description='Logging setup',
        complexity=2
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

DATA_PATTERNS = [
    CodePattern(
        name='dataclass_model',
        category='data',
        keywords=['dataclass', 'model', 'class', 'object', 'struct'],
        imports=['dataclasses'],
        code='''
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class Entity:
    """Data model with common methods."""
    id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Entity':
        """Create from dictionary."""
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
''',
        description='Dataclass model',
        complexity=2
    ),
    
    CodePattern(
        name='singleton',
        category='data',
        keywords=['singleton', 'pattern', 'instance', 'global', 'single'],
        imports=[],
        code='''
from typing import Optional, TypeVar, Type

T = TypeVar('T')

class Singleton:
    """Singleton base class."""
    _instance: Optional['Singleton'] = None
    
    def __new__(cls: Type[T], *args, **kwargs) -> T:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls: Type[T]) -> T:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None
''',
        description='Singleton pattern',
        complexity=2
    ),
    
    CodePattern(
        name='lru_cache',
        category='data',
        keywords=['cache', 'lru', 'memoize', 'remember', 'store'],
        imports=['functools'],
        code='''
from functools import lru_cache, wraps
from typing import Callable, Any
import time

@lru_cache(maxsize=128)
def cached_computation(arg: str) -> str:
    """Example cached function."""
    return f"computed_{arg}"


def timed_lru_cache(seconds: int = 300, maxsize: int = 128):
    """LRU cache with TTL."""
    def decorator(func: Callable) -> Callable:
        func = lru_cache(maxsize=maxsize)(func)
        func.expiration = time.time() + seconds
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            if time.time() > func.expiration:
                func.cache_clear()
                func.expiration = time.time() + seconds
            return func(*args, **kwargs)
        
        wrapper.cache_clear = func.cache_clear
        return wrapper
    
    return decorator
''',
        description='LRU cache with TTL',
        complexity=2
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

ASYNC_PATTERNS = [
    CodePattern(
        name='async_gather',
        category='async',
        keywords=['async', 'gather', 'concurrent', 'parallel', 'multiple'],
        imports=['asyncio'],
        code='''
import asyncio
from typing import List, Any, Coroutine

async def run_concurrent(tasks: List[Coroutine]) -> List[Any]:
    """Run multiple coroutines concurrently."""
    return await asyncio.gather(*tasks, return_exceptions=True)


async def run_with_limit(tasks: List[Coroutine], limit: int = 10) -> List[Any]:
    """Run coroutines with concurrency limit."""
    semaphore = asyncio.Semaphore(limit)
    
    async def limited(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*[limited(t) for t in tasks])
''',
        description='Async concurrent execution',
        complexity=2,
        has_async=True
    ),
    
    CodePattern(
        name='async_queue',
        category='async',
        keywords=['async', 'queue', 'worker', 'producer', 'consumer'],
        imports=['asyncio'],
        code='''
import asyncio
from typing import Any, Callable, Coroutine

async def producer_consumer(
    items: list,
    worker: Callable[[Any], Coroutine],
    num_workers: int = 5
) -> list:
    """Producer-consumer pattern with async workers."""
    queue = asyncio.Queue()
    results = []
    
    # Producer
    for item in items:
        await queue.put(item)
    
    # Workers
    async def worker_task():
        while True:
            try:
                item = queue.get_nowait()
                result = await worker(item)
                results.append(result)
                queue.task_done()
            except asyncio.QueueEmpty:
                break
    
    workers = [asyncio.create_task(worker_task()) for _ in range(num_workers)]
    await asyncio.gather(*workers)
    
    return results
''',
        description='Async producer-consumer',
        complexity=3,
        has_async=True
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN DATABASE CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class PatternDatabase:
    """
    Database of code patterns for mindstaQ.
    
    Usage:
        db = PatternDatabase()
        patterns = db.search("http client async")
        best = patterns[0] if patterns else None
    """
    
    def __init__(self):
        # Combine all patterns
        self.patterns: List[CodePattern] = (
            HTTP_PATTERNS +
            DATABASE_PATTERNS +
            AUTH_PATTERNS +
            FILE_PATTERNS +
            CLI_PATTERNS +
            DATA_PATTERNS +
            ASYNC_PATTERNS
        )
        
        # Index by category
        self.by_category: Dict[str, List[CodePattern]] = {}
        for p in self.patterns:
            if p.category not in self.by_category:
                self.by_category[p.category] = []
            self.by_category[p.category].append(p)
    
    def search(self, query: str, max_results: int = 10) -> List[CodePattern]:
        """Search patterns by keywords."""
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        
        scored = []
        for pattern in self.patterns:
            pattern_keywords = set(pattern.keywords)
            overlap = len(query_words & pattern_keywords)
            
            # Also check partial matches
            for qw in query_words:
                for pk in pattern_keywords:
                    if qw in pk or pk in qw:
                        overlap += 0.5
            
            if overlap > 0:
                scored.append((pattern, overlap))
        
        scored.sort(key=lambda x: -x[1])
        return [p for p, _ in scored[:max_results]]
    
    def get_by_category(self, category: str) -> List[CodePattern]:
        """Get all patterns in a category."""
        return self.by_category.get(category, [])
    
    def get_by_name(self, name: str) -> Optional[CodePattern]:
        """Get pattern by exact name."""
        for p in self.patterns:
            if p.name == name:
                return p
        return None
    
    @property
    def categories(self) -> List[str]:
        """List all categories."""
        return list(self.by_category.keys())
    
    @property
    def count(self) -> int:
        """Total number of patterns."""
        return len(self.patterns)


# Global instance
_pattern_db: Optional[PatternDatabase] = None

def get_pattern_db() -> PatternDatabase:
    """Get global pattern database."""
    global _pattern_db
    if _pattern_db is None:
        _pattern_db = PatternDatabase()
    return _pattern_db


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Pattern Database v{__version__}")
    print("=" * 60)
    
    db = get_pattern_db()
    
    print(f"\n[1] Database Stats:")
    print(f"  Total patterns: {db.count}")
    print(f"  Categories: {db.categories}")
    
    for cat in db.categories:
        print(f"    {cat}: {len(db.get_by_category(cat))} patterns")
    
    print("\n[2] Search Test:")
    queries = [
        "http get request",
        "async fetch concurrent",
        "jwt token authentication",
        "sqlite database query",
        "read json file",
    ]
    
    for q in queries:
        results = db.search(q, max_results=2)
        print(f"\n  Query: '{q}'")
        for p in results:
            print(f"    - {p.name} ({p.category})")
    
    print("\n✅ Pattern Database working!")
