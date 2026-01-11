#!/usr/bin/env python3
"""
sQavenger: Search Harvester Agent (Tier 1)
Part of mindstaQ - REAL web search for code harvesting

v1.3.0 - REAL WEB SEARCH IMPLEMENTATION

This is the REAL sQavenger that:
1. Takes a task/intent from Qomputator
2. Builds optimized search queries
3. Searches via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
4. Harvests REAL code snippets from search results
5. Ranks and filters snippets by relevance
6. Returns the best matching code for the task

When web search is unavailable, falls back to local pattern library.
"""

import asyncio
import re
import ast
import sys
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

# Import CrystallizedIntent
try:
    from worqer.mindstaq import CrystallizedIntent, ActionType, TargetType
except ImportError:
    # Fallback definition
    class CrystallizedIntent:
        def __init__(self):
            self.action = None
            self.target_type = None
            self.target_name = ""
            self.raw_text = ""
            self.keywords = []
            self.entities = []

# Import Qrawler for web search
try:
    from worqer.mindstaq.qrawler import Qrawler, QrawlerResult, CodeSnippet
    HAS_QRAWLER = True
except ImportError:
    HAS_QRAWLER = False
    Qrawler = None


__version__ = '1.3.1'


# ═══════════════════════════════════════════════════════════════════════════════
# CODE QUALITY ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class CodeQualityAnalyzer:
    """Analyze and score code quality without running it."""
    
    @classmethod
    def analyze_python(cls, code: str) -> Tuple[float, List[str]]:
        """Analyze Python code quality. Returns (score 0-1, warnings)."""
        score = 1.0
        warnings = []
        
        # Check syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return 0.0, [f"Syntax error: {e}"]
        
        # Check for common issues
        if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', code, re.IGNORECASE):
            score -= 0.1
            warnings.append("Contains potential hardcoded secrets")
        
        if re.search(r'#\s*(TODO|FIXME|HACK|XXX)', code, re.IGNORECASE):
            score -= 0.05
            warnings.append("Contains TODO/FIXME comments")
        
        if 'raise NotImplementedError' in code or re.search(r'^\s+pass\s*$', code, re.MULTILINE):
            score -= 0.2
            warnings.append("Contains stub implementations")
        
        has_docstring = '"""' in code or "'''" in code
        if not has_docstring:
            score -= 0.05
        
        has_try_except = 'try:' in code and 'except' in code
        if 'open(' in code or 'requests.' in code:
            if not has_try_except:
                score -= 0.1
                warnings.append("External operations without error handling")
        
        return max(0.0, score), warnings
    
    @classmethod
    def analyze(cls, code: str, language: str) -> Tuple[float, List[str]]:
        """Analyze code quality for any supported language."""
        if language == 'python':
            return cls.analyze_python(code)
        elif language in ('yaml', 'json'):
            try:
                if language == 'yaml':
                    import yaml
                    yaml.safe_load(code)
                else:
                    import json
                    json.loads(code)
                return 1.0, []
            except Exception as e:
                return 0.0, [f"Parse error: {e}"]
        elif language in ('bash', 'shell'):
            warnings = []
            score = 1.0
            if 'rm -rf' in code:
                score -= 0.2
                warnings.append("Contains dangerous rm -rf")
            return score, warnings
        return 0.8, []


# ═══════════════════════════════════════════════════════════════════════════════
# RELEVANCE SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class RelevanceScorer:
    """Score how relevant a code snippet is to a task."""
    
    @classmethod
    def score(cls, code: str, task: str, keywords: List[str] = None) -> float:
        """Score relevance of code to task (0-1)."""
        score = 0.5
        
        task_lower = task.lower()
        code_lower = code.lower()
        
        # Extract keywords from task
        task_keywords = set(re.findall(r'\b\w{3,}\b', task_lower))
        stopwords = {'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'are'}
        task_keywords = task_keywords - stopwords
        
        # Add provided keywords
        if keywords:
            task_keywords.update(k.lower() for k in keywords)
        
        # Check keyword presence
        matches = sum(1 for kw in task_keywords if kw in code_lower)
        if task_keywords:
            score += (matches / len(task_keywords)) * 0.3
        
        # Bonus for complete code
        if 'def ' in code and 'return' in code:
            score += 0.1
        if 'import ' in code:
            score += 0.05
        
        # Penalty for short snippets
        if len(code) < 100:
            score -= 0.1
        
        return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK PATTERNS (offline mode)
# ═══════════════════════════════════════════════════════════════════════════════

PATTERNS = {
    'http_get': '''import requests
from typing import Optional, Dict, Any


def fetch_data(url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Fetch data from a URL using GET request."""
    try:
        response = requests.get(url, headers=headers or {}, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
''',
    'http_post': '''import requests
from typing import Optional, Dict, Any


def post_data(url: str, data: Dict[str, Any], headers: Dict[str, str] = None) -> Optional[Dict]:
    """Send data to a URL using POST request."""
    default_headers = {'Content-Type': 'application/json'}
    if headers:
        default_headers.update(headers)
    try:
        response = requests.post(url, json=data, headers=default_headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
''',
    'json_handler': '''import json
from pathlib import Path
from typing import Any, Optional


def read_json(file_path: str) -> Optional[Any]:
    """Read JSON from file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    """Write JSON to file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    return True
''',
    'yaml_handler': '''import yaml
from pathlib import Path
from typing import Any, Optional


def read_yaml(file_path: str) -> Optional[Any]:
    """Read YAML from file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_yaml(file_path: str, data: Any) -> bool:
    """Write YAML to file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return True
''',
    'csv_handler': '''import csv
from pathlib import Path
from typing import List, Dict, Any


def read_csv(file_path: str) -> List[Dict[str, Any]]:
    """Read CSV file as list of dictionaries."""
    path = Path(file_path)
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(file_path: str, data: List[Dict[str, Any]], fieldnames: List[str] = None) -> bool:
    """Write list of dictionaries to CSV file."""
    if not data:
        return False
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fieldnames or list(data[0].keys())
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    return True
''',
    'logging_setup': '''import logging
import sys
from pathlib import Path


def setup_logging(
    name: str = __name__,
    level: int = logging.INFO,
    log_file: str = None,
    format_string: str = None
) -> logging.Logger:
    """Set up a logger with console and optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
''',
    'retry': '''import time
from functools import wraps
from typing import Callable, Type, Tuple


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """Decorator to retry a function on failure with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception
        return wrapper
    return decorator
''',
    'async_http': '''import asyncio
import aiohttp
from typing import Dict, Any, Optional, List


async def fetch_url(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> Optional[Dict]:
    """Fetch JSON from a URL asynchronously."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None


async def fetch_all(urls: List[str]) -> List[Optional[Dict]]:
    """Fetch multiple URLs concurrently."""
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(*[fetch_url(session, url) for url in urls])
''',
    'db_connection': '''import sqlite3
from contextlib import contextmanager
from typing import Generator, Any, List, Dict


@contextmanager
def get_db_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def execute_query(db_path: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a query and return results as list of dicts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def execute_write(db_path: str, query: str, params: tuple = ()) -> int:
    """Execute a write query and return affected rows."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount
''',
}

# Pattern matchers for fallback
PATTERN_MATCHERS = {
    'http_get': [r'http.*get', r'fetch.*url', r'request.*get', r'api.*get'],
    'http_post': [r'http.*post', r'send.*data', r'request.*post', r'api.*post'],
    'json_handler': [r'json.*file', r'read.*json', r'write.*json', r'load.*json'],
    'yaml_handler': [r'yaml.*file', r'read.*yaml', r'write.*yaml', r'config.*yaml'],
    'csv_handler': [r'csv.*file', r'read.*csv', r'write.*csv', r'parse.*csv'],
    'logging_setup': [r'setup.*log', r'create.*log', r'init.*log', r'configure.*log'],
    'retry': [r'retry', r'backoff', r'attempt', r'resilient'],
    'async_http': [r'async.*http', r'concurrent.*request', r'parallel.*fetch'],
    'db_connection': [r'database', r'sqlite', r'sql.*connect', r'db.*connection'],
}


# ═══════════════════════════════════════════════════════════════════════════════
# SQAVENGER MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class SQavenger:
    """
    sQavenger: Web Search Harvester Agent (Tier 1)
    
    Searches the web for REAL code snippets and harvests them.
    Falls back to local pattern library when web search unavailable.
    
    Process:
    1. Try web search via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
    2. If web search unavailable or no results, use local patterns
    3. Rank and filter results by relevance and quality
    4. Return best matching code
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        sqavenger_cfg = self.config.get('sqavenger', self.config.get('mindstaq', {}))
        qrawler_cfg = self.config.get('qrawler', sqavenger_cfg.get('qrawler', {}))
        
        # Qrawler configuration
        self.qrawler_enabled = qrawler_cfg.get('enabled', True)  # Enabled by default!
        self.qrawler_url = qrawler_cfg.get('url', 'http://172.17.0.1:8888')
        
        # Initialize Qrawler
        self.qrawler = None
        if HAS_QRAWLER and self.qrawler_enabled:
            try:
                self.qrawler = Qrawler(self.config)
            except Exception as e:
                sys.stderr.write(f"[sQavenger] Qrawler init failed: {e}\n")
        
        # Configuration
        self.max_results = sqavenger_cfg.get('max_results', 10)
        self.min_relevance = sqavenger_cfg.get('min_relevance', 0.3)
        self.min_quality = sqavenger_cfg.get('min_quality', 0.5)
        
        # Search query templates
        self.query_templates = {
            'create': 'python how to {task} example code',
            'add': 'python {task} implementation',
            'validate': 'python {task} validation',
            'parse': 'python parse {task}',
            'connect': 'python {task} connection',
            'default': 'python {task} example',
        }
    
    def harvest(self, intent: CrystallizedIntent, prompt: str, context_files: List[str] = None) -> Optional[str]:
        """
        Harvest code for a task - main interface called by MindstaQEngine.
        
        Args:
            intent: CrystallizedIntent from intent parsing
            prompt: Raw task prompt
            context_files: Optional list of context file paths
        
        Returns:
            Generated/harvested code string or None
        """
        # Try web search first
        if self.qrawler:
            code = self._search_web(intent, prompt)
            if code:
                return code
        
        # Fallback to local patterns
        return self._search_patterns(intent, prompt)
    
    def _build_search_query(self, intent: CrystallizedIntent, prompt: str) -> str:
        """Build optimized search query from intent and prompt."""
        # Get action type
        action = 'default'
        if hasattr(intent, 'action') and intent.action:
            action_str = intent.action.value if hasattr(intent.action, 'value') else str(intent.action)
            action = action_str.lower()
        
        # Clean prompt for query
        task = re.sub(r'[^\w\s]', ' ', prompt.lower())[:60]
        
        # Get template
        template = self.query_templates.get(action, self.query_templates['default'])
        query = template.format(task=task)
        
        return query
    
    def _search_web(self, intent: CrystallizedIntent, prompt: str) -> Optional[str]:
        """Search the web for code via Qrawler."""
        if not self.qrawler:
            return None
        
        try:
            # Build search query
            query = self._build_search_query(intent, prompt)
            sys.stderr.write(f"[sQavenger] Web search: {query[:50]}...\n")
            
            # Search
            result = self.qrawler.search_sync(query, max_results=self.max_results)
            
            if not result.code_snippets:
                sys.stderr.write(f"[sQavenger] No code snippets found\n")
                return None
            
            sys.stderr.write(f"[sQavenger] Found {len(result.code_snippets)} snippets from {result.engines_used}\n")
            
            # Get keywords from intent
            keywords = []
            if hasattr(intent, 'keywords'):
                keywords = intent.keywords
            
            # Score and filter snippets
            scored = []
            for snippet in result.code_snippets:
                # Score relevance
                relevance = RelevanceScorer.score(snippet.code, prompt, keywords)
                if relevance < self.min_relevance:
                    continue
                
                # Score quality
                quality, warnings = CodeQualityAnalyzer.analyze(snippet.code, snippet.language)
                if quality < self.min_quality:
                    continue
                
                # Combined score
                combined = relevance * 0.5 + quality * 0.3 + min(snippet.score / 100, 0.2)
                scored.append((snippet, combined, relevance, quality))
            
            if not scored:
                sys.stderr.write(f"[sQavenger] No snippets passed quality/relevance threshold\n")
                return None
            
            # Sort by score
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0]
            
            sys.stderr.write(f"[sQavenger] Best match: relevance={best[2]:.2f}, quality={best[3]:.2f}\n")
            
            return best[0].code
            
        except Exception as e:
            sys.stderr.write(f"[sQavenger] Web search error: {e}\n")
            return None
    
    def _search_patterns(self, intent: CrystallizedIntent, prompt: str) -> Optional[str]:
        """Fallback: Search local pattern library."""
        prompt_lower = prompt.lower()
        
        # Score each pattern
        scores = {}
        for pattern_name, matchers in PATTERN_MATCHERS.items():
            score = sum(1 for p in matchers if re.search(p, prompt_lower))
            if score > 0:
                scores[pattern_name] = score
        
        # Add keyword matches
        if hasattr(intent, 'keywords'):
            for keyword in intent.keywords:
                keyword_lower = keyword.lower()
                for pattern_name, matchers in PATTERN_MATCHERS.items():
                    for matcher in matchers:
                        if re.search(matcher, keyword_lower):
                            scores[pattern_name] = scores.get(pattern_name, 0) + 0.5
        
        if not scores:
            return None
        
        # Get best match
        best = max(scores.items(), key=lambda x: x[1])
        if best[1] >= 1 and best[0] in PATTERNS:
            code = PATTERNS[best[0]]
            return self._customize_pattern(code, intent)
        
        return None
    
    def _customize_pattern(self, code: str, intent: CrystallizedIntent) -> str:
        """Customize pattern code with intent details."""
        if hasattr(intent, 'target_name') and intent.target_name:
            code = re.sub(r'\bMyClass\b', intent.target_name, code)
            code = re.sub(r'\bmy_function\b', intent.target_name.lower(), code)
        return code


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='sQavenger - Search Harvester Agent')
    parser.add_argument('--text', '-t', type=str, help='Task description')
    parser.add_argument('--list', '-l', action='store_true', help='List available patterns')
    parser.add_argument('--search', '-s', action='store_true', help='Force web search')
    args = parser.parse_args()
    
    if args.list:
        print("Available patterns:")
        for name in PATTERNS.keys():
            print(f"  - {name}")
    elif args.text:
        intent = CrystallizedIntent()
        intent.raw_text = args.text
        
        sqavenger = SQavenger()
        code = sqavenger.harvest(intent, args.text)
        
        if code:
            print("=" * 60)
            print("HARVESTED CODE:")
            print("=" * 60)
            print(code)
        else:
            print("No code found for task")
