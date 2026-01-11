#!/usr/bin/env python3
"""
Qrawler: Web Search Engine Interface for mindstaQ
v2.2.6-stable - BULLETPROOF! Host Gateway + SSL Fix! 🔥

v2.2.6 CRITICAL FIX:
  - config.yaml now defaults to http://172.17.0.1:8888 (not localhost!)
  - localhost doesn't work from inside Docker container!
  - 172.17.0.1 is Docker's bridge gateway to host machine
  - SSL completely disabled with explicit ssl=False

v2.2.5 (retained):
  - Just use http://172.17.0.1:8888 directly
  - No docker network complexity

Supports multiple search backends:
- SearXNG (self-hosted, unlimited, RECOMMENDED)
- DuckDuckGo (no API key, rate limited fallback)

Configuration in config.yaml:
  qrawler:
    enabled: true
    searxng_url: "http://172.17.0.1:8888"  # NOT localhost!
    cache_dir: "/tmp/qrawler_cache"
    cache_ttl_hours: 24

Dependencies:
  pip install aiohttp beautifulsoup4 duckduckgo-search
"""

import asyncio
import re
import json
import os
import hashlib
import ssl
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse

__version__ = '2.2.8-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# GRACEFUL IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = None

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    BeautifulSoup = None

try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    DDGS = None

# Logging
try:
    from worqer.mindstaq.mindstaq_logger import mlog
except ImportError:
    mlog = None


def _log(msg: str, level: str = "INFO"):
    """v2.2.1: REAL logging that shows what's happening!"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_msg = f"[QRAWLER {level}] {msg}"
    
    if mlog:
        if level == "ERROR":
            mlog.error(log_msg)
        elif level == "WARN":
            mlog.warn(log_msg)
        else:
            mlog.tier("QRAWLER", msg)
    
    # Always print to stderr
    sys.stderr.write(f"[{timestamp}] {log_msg}\n")
    sys.stderr.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodeSnippet:
    """A code snippet harvested from the web."""
    code: str
    language: str
    source_url: str
    source_name: str
    title: str = ""
    score: int = 0
    relevance: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __hash__(self):
        return hash(self.code[:100] + self.source_url)


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    source: str
    score: int = 0
    code_blocks: List[CodeSnippet] = field(default_factory=list)


@dataclass
class QrawlerResult:
    """Combined search results from all engines."""
    query: str
    results: List[SearchResult] = field(default_factory=list)
    code_snippets: List[CodeSnippet] = field(default_factory=list)
    total_found: int = 0
    search_time_ms: int = 0
    engines_used: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# CODE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class CodeExtractor:
    """Extract code snippets from HTML pages."""
    
    LANGUAGE_HINTS = {
        'python': ['python', 'py', 'python3', 'lang-python', 'language-python'],
        'javascript': ['javascript', 'js', 'lang-js', 'language-javascript'],
        'bash': ['bash', 'shell', 'sh', 'lang-bash', 'language-bash'],
        'yaml': ['yaml', 'yml', 'lang-yaml'],
        'json': ['json', 'lang-json'],
        'sql': ['sql', 'lang-sql'],
        'go': ['go', 'golang', 'lang-go'],
        'rust': ['rust', 'lang-rust'],
    }
    
    @classmethod
    def detect_language(cls, code: str, classes: List[str] = None) -> str:
        """Detect programming language."""
        classes = classes or []
        classes_lower = [c.lower() for c in classes]
        
        for lang, hints in cls.LANGUAGE_HINTS.items():
            for hint in hints:
                if any(hint in c for c in classes_lower):
                    return lang
        
        code_lower = code.lower()
        if 'def ' in code and ':' in code:
            return 'python'
        if 'import ' in code and ('from ' in code or 'as ' in code):
            return 'python'
        if 'function ' in code or 'const ' in code or 'let ' in code:
            return 'javascript'
        if code.strip().startswith('#!/bin/bash'):
            return 'bash'
        
        return 'unknown'
    
    @classmethod
    def extract_from_html(cls, html: str, source_url: str = "") -> List[CodeSnippet]:
        """Extract code snippets from HTML."""
        snippets = []
        
        if not HAS_BS4 or not html:
            return snippets
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Strategy 1: <pre><code> blocks
            for pre in soup.find_all('pre'):
                code_elem = pre.find('code')
                if code_elem:
                    code_text = code_elem.get_text(strip=True)
                    if len(code_text) > 20:
                        classes = code_elem.get('class', [])
                        if isinstance(classes, str):
                            classes = [classes]
                        
                        lang = cls.detect_language(code_text, classes)
                        snippets.append(CodeSnippet(
                            code=code_text,
                            language=lang,
                            source_url=source_url,
                            source_name=cls._get_source_name(source_url)
                        ))
            
            # Strategy 2: Highlight.js blocks
            for hljs in soup.find_all(class_=re.compile(r'hljs|highlight')):
                code_text = hljs.get_text(strip=True)
                if len(code_text) > 20:
                    classes = hljs.get('class', [])
                    if isinstance(classes, str):
                        classes = [classes]
                    
                    lang = cls.detect_language(code_text, classes)
                    if not any(s.code == code_text for s in snippets):
                        snippets.append(CodeSnippet(
                            code=code_text,
                            language=lang,
                            source_url=source_url,
                            source_name=cls._get_source_name(source_url)
                        ))
            
            _log(f"Extracted {len(snippets)} snippets from {source_url[:50]}...")
            
        except Exception as e:
            _log(f"HTML parsing error: {e}", "ERROR")
        
        return snippets
    
    @classmethod
    def extract_from_markdown(cls, text: str, source_url: str = "") -> List[CodeSnippet]:
        """Extract code from markdown."""
        snippets = []
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for lang, code in matches:
            code = code.strip()
            if len(code) > 20:
                if not lang:
                    lang = cls.detect_language(code)
                snippets.append(CodeSnippet(
                    code=code,
                    language=lang or 'unknown',
                    source_url=source_url,
                    source_name=cls._get_source_name(source_url)
                ))
        
        return snippets
    
    @classmethod
    def _get_source_name(cls, url: str) -> str:
        """Get source name from URL."""
        if not url:
            return 'unknown'
        
        domain = urlparse(url).netloc.lower()
        
        if 'stackoverflow.com' in domain:
            return 'stackoverflow'
        elif 'github.com' in domain:
            return 'github'
        elif 'realpython.com' in domain:
            return 'realpython'
        elif 'geeksforgeeks.org' in domain:
            return 'geeksforgeeks'
        else:
            return domain.split('.')[0]


# ═══════════════════════════════════════════════════════════════════════════════
# QRAWLER MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class Qrawler:
    """
    v2.2.1: Web Search with SSL FIX and Docker Networking!
    
    Fixes:
    - ssl=False explicitly in connectors
    - POST requests verified working
    
    v2.2.5: SIMPLIFIED! Just use host gateway port 8888 - no docker networking complexity!
    """
    
    def __init__(self, config: dict = None):
        config = config or {}
        qrawler_cfg = config.get('qrawler', config.get('mindstaq', {}).get('qrawler', {}))
        
        # v2.2.5: SIMPLE SearXNG configuration - host gateway port 8888!
        # Default to 172.17.0.1:8888 which is Docker's bridge gateway to host
        self.searxng_url = qrawler_cfg.get('searxng_url', 'http://172.17.0.1:8888')
        self.enabled = qrawler_cfg.get('enabled', True)
        
        # Cache configuration
        cache_dir = qrawler_cfg.get('cache_dir', '/tmp/qrawler_cache')
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = qrawler_cfg.get('cache_ttl_hours', 24)
        
        # Request configuration
        self.timeout = qrawler_cfg.get('timeout', 15)
        self.max_fetch = qrawler_cfg.get('max_fetch', 5)
        
        # Priority sites
        self.priority_sites = [
            'stackoverflow.com',
            'github.com',
            'realpython.com',
            'geeksforgeeks.org',
        ]
        
        _log(f"Qrawler v2.2.8: SearXNG={self.searxng_url}, enabled={self.enabled}")
    
    def _cache_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()
    
    def _get_cached(self, query: str) -> Optional[QrawlerResult]:
        """Get cached result if available."""
        cache_file = self.cache_dir / f"{self._cache_key(query)}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            cached_time = datetime.fromisoformat(data['timestamp'])
            if datetime.utcnow() - cached_time < timedelta(hours=self.cache_ttl):
                _log(f"Cache hit: {query[:30]}...")
                result = QrawlerResult(
                    query=data['query'],
                    total_found=data.get('total_found', 0),
                    engines_used=data.get('engines_used', ['cache'])
                )
                for snippet_data in data.get('code_snippets', []):
                    result.code_snippets.append(CodeSnippet(
                        code=snippet_data['code'],
                        language=snippet_data['language'],
                        source_url=snippet_data['source_url'],
                        source_name=snippet_data['source_name'],
                        score=snippet_data.get('score', 0)
                    ))
                return result
        except Exception as e:
            _log(f"Cache read error: {e}", "WARN")
        
        return None
    
    def _save_cache(self, result: QrawlerResult):
        """Save result to cache."""
        cache_file = self.cache_dir / f"{self._cache_key(result.query)}.json"
        
        try:
            data = {
                'query': result.query,
                'timestamp': datetime.utcnow().isoformat(),
                'total_found': result.total_found,
                'engines_used': result.engines_used,
                'code_snippets': [
                    {
                        'code': s.code,
                        'language': s.language,
                        'source_url': s.source_url,
                        'source_name': s.source_name,
                        'score': s.score
                    }
                    for s in result.code_snippets
                ]
            }
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            _log(f"Cache write error: {e}", "WARN")
    
    async def _search_searxng(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        v2.2.5: SIMPLIFIED! Search SearXNG using host gateway port 8888.
        No more docker networking complexity - just use the configured URL directly.
        """
        results = []
        
        if not HAS_AIOHTTP:
            _log("aiohttp not available", "ERROR")
            return results
        
        # v2.2.5: Use configured URL directly (defaults to 172.17.0.1:8888)
        search_url = f"{self.searxng_url}/search"
        _log(f"SearXNG POST to {search_url}: {query[:40]}...")
        
        try:
            # v2.2.1: CRITICAL - ssl=False in connector!
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            # POST with form data (verified working!)
            form_data = {
                'q': query,
                'format': 'json',
                'categories': 'it'
            }
            
            headers = {
                'User-Agent': 'QonQrete/2.2.7 (Code Search)',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(search_url, data=form_data, headers=headers) as response:
                    _log(f"SearXNG response: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        searxng_results = data.get('results', [])
                        _log(f"SearXNG returned {len(searxng_results)} results")
                        
                        for item in searxng_results[:max_results]:
                            url = item.get('url', '')
                            score = int(item.get('score', 0) * 100)
                            
                            # Boost priority sites
                            for i, site in enumerate(self.priority_sites):
                                if site in url:
                                    score += (len(self.priority_sites) - i) * 10
                                    break
                            
                            results.append(SearchResult(
                                title=item.get('title', ''),
                                url=url,
                                snippet=item.get('content', ''),
                                source='searxng',
                                score=score
                            ))
                    else:
                        text = await response.text()
                        _log(f"SearXNG error {response.status}: {text[:100]}", "ERROR")
        
        except asyncio.TimeoutError:
            _log(f"SearXNG timeout after {self.timeout}s", "WARN")
        except Exception as e:
            _log(f"SearXNG error: {type(e).__name__}: {e}", "ERROR")
        
        return results
    
    async def _search_duckduckgo(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """v2.2.1: DuckDuckGo fallback with proper error handling."""
        results = []
        
        if not HAS_DDGS:
            _log("duckduckgo-search not installed", "WARN")
            return results
        
        _log(f"DuckDuckGo query: {query[:40]}...")
        
        try:
            loop = asyncio.get_event_loop()
            ddg_results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=max_results))
            )
            
            _log(f"DuckDuckGo returned {len(ddg_results)} results")
            
            for item in ddg_results:
                url = item.get('href', '')
                score = 10
                
                for i, site in enumerate(self.priority_sites):
                    if site in url:
                        score += (len(self.priority_sites) - i) * 10
                        break
                
                results.append(SearchResult(
                    title=item.get('title', ''),
                    url=url,
                    snippet=item.get('body', ''),
                    source='duckduckgo',
                    score=score
                ))
        
        except Exception as e:
            _log(f"DuckDuckGo error: {type(e).__name__}: {e}", "ERROR")
        
        return results
    
    async def _fetch_page(self, url: str) -> Optional[str]:
        """v2.2.1: Fetch page with SSL disabled."""
        if not HAS_AIOHTTP:
            return None
        
        _log(f"Fetching: {url[:50]}...")
        
        try:
            # v2.2.1: SSL=False for all fetches
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=10)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' in content_type:
                            html = await response.text()
                            _log(f"Fetched {len(html)} bytes")
                            return html
                    else:
                        _log(f"Fetch failed {response.status}", "WARN")
        
        except asyncio.TimeoutError:
            _log(f"Fetch timeout: {url[:40]}", "WARN")
        except Exception as e:
            _log(f"Fetch error: {type(e).__name__}", "ERROR")
        
        return None
    
    async def _fetch_and_extract_code(self, results: List[SearchResult]) -> List[CodeSnippet]:
        """
        v2.2.1: Fetch pages and extract code.
        v2.2.8: Added DOMAIN FILTERING to skip non-Python sources!
        """
        snippets = []
        
        if not results:
            return snippets
        
        # v2.2.8: DOMAIN FILTERING!
        # These domains return garbage for Python code searches:
        # - MDN (Mozilla Developer Network) = JavaScript/HTML/CSS docs
        # - Docker Hub = Container images, not code
        # - Hackage = Haskell packages
        # - ArchWiki/Gentoo = Linux docs, not Python
        BLOCKED_DOMAINS = {
            'developer.mozilla.org',  # MDN - JS/HTML/CSS docs
            'hub.docker.com',         # Docker Hub - no code
            'hackage.haskell.org',    # Haskell - wrong language!
            'wiki.archlinux.org',     # Linux docs
            'wiki.gentoo.org',        # Linux docs  
            'docs.microsoft.com',     # Microsoft docs
            'learn.microsoft.com',    # Microsoft docs
            'npmjs.com',              # npm - JavaScript
            'www.npmjs.com',          # npm - JavaScript
            'crates.io',              # Rust packages
            'rubygems.org',           # Ruby gems
            'packagist.org',          # PHP packages
            'nuget.org',              # .NET packages
            'mvnrepository.com',      # Java/Maven
        }
        
        # v2.2.8: PRIORITIZE these domains for Python code:
        PRIORITY_DOMAINS = {
            'github.com': 10,           # Best source!
            'stackoverflow.com': 8,     # Good code examples
            'gitlab.com': 7,            # Code repos
            'bitbucket.org': 6,         # Code repos
            'realpython.com': 5,        # Python tutorials
            'docs.python.org': 5,       # Official Python docs
            'pypi.org': 4,              # Python packages
            'readthedocs.io': 4,        # Documentation
            'gist.github.com': 8,       # Code snippets
        }
        
        # Filter and re-score results
        filtered_results = []
        for result in results:
            try:
                domain = urlparse(result.url).netloc.lower()
                
                # Skip blocked domains
                if domain in BLOCKED_DOMAINS:
                    _log(f"BLOCKED: {domain} (non-Python source)")
                    continue
                
                # Boost priority domains
                for priority_domain, boost in PRIORITY_DOMAINS.items():
                    if priority_domain in domain:
                        result.score += boost
                        _log(f"BOOSTED: {domain} (+{boost})")
                        break
                
                filtered_results.append(result)
            except Exception:
                filtered_results.append(result)
        
        if not filtered_results:
            _log("All results filtered out - using original results")
            filtered_results = results
        
        sorted_results = sorted(filtered_results, key=lambda r: r.score, reverse=True)
        fetch_count = min(len(sorted_results), self.max_fetch)
        
        _log(f"Fetching top {fetch_count} pages (filtered from {len(results)})...")
        
        for result in sorted_results[:fetch_count]:
            html = await self._fetch_page(result.url)
            
            if html:
                page_snippets = CodeExtractor.extract_from_html(html, result.url)
                
                if 'github.com' in result.url:
                    md_snippets = CodeExtractor.extract_from_markdown(html, result.url)
                    page_snippets.extend(md_snippets)
                
                for snippet in page_snippets:
                    snippet.score = result.score
                    snippet.title = result.title
                
                snippets.extend(page_snippets[:3])
        
        _log(f"Total extracted: {len(snippets)} snippets")
        return snippets
    
    async def search(self, query: str, max_results: int = 10, use_cache: bool = True) -> QrawlerResult:
        """
        v2.2.1: Main search with SSL fix and Docker networking.
        """
        start_time = datetime.utcnow()
        
        if use_cache:
            cached = self._get_cached(query)
            if cached:
                return cached
        
        result = QrawlerResult(query=query)
        all_results: List[SearchResult] = []
        
        _log("=" * 50)
        _log(f"SEARCH: {query}")
        _log("=" * 50)
        
        # Try SearXNG first
        searxng_results = await self._search_searxng(query, max_results)
        if searxng_results:
            result.engines_used.append('searxng')
            all_results.extend(searxng_results)
        
        # Fallback to DuckDuckGo
        if len(all_results) < 3:
            _log("Trying DuckDuckGo fallback...")
            ddg_results = await self._search_duckduckgo(query, max_results)
            if ddg_results:
                result.engines_used.append('duckduckgo')
                all_results.extend(ddg_results)
        
        result.total_found = len(all_results)
        result.results = all_results
        
        if all_results:
            snippets = await self._fetch_and_extract_code(all_results)
            result.code_snippets = snippets
        else:
            result.errors.append("No results from any engine")
        
        result.search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        if result.code_snippets:
            self._save_cache(result)
        
        _log(f"DONE: {len(result.code_snippets)} snippets in {result.search_time_ms}ms")
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

async def test_qrawler():
    """Test Qrawler."""
    print("=" * 70)
    print("QRAWLER v2.2.1 TEST")
    print("=" * 70)
    
    qrawler = Qrawler()
    result = await qrawler.search("python nmap scanner subprocess")
    
    print(f"\nEngines: {result.engines_used}")
    print(f"Results: {result.total_found}")
    print(f"Snippets: {len(result.code_snippets)}")
    print(f"Time: {result.search_time_ms}ms")
    
    if result.code_snippets:
        print(f"\nTop snippet ({result.code_snippets[0].source_name}):")
        print(result.code_snippets[0].code[:200])


if __name__ == '__main__':
    asyncio.run(test_qrawler())
