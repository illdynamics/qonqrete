#!/usr/bin/env python3
"""
DeepQrawler: Tor Hidden Service Code Search Agent
Part of mindstaQ - Searches the deep web for code patterns

v1.4.0 - CIRCUIT ROTATION + TORCH + CODE ENDPOINT DETECTION

WARNING: This module requires Tor to be running and configured.
         Use responsibly and only for legitimate code research.

Search Sources:
- Ahmia (PRIMARY): Safe Tor search engine that filters illegal content
- Torch: Longstanding Tor search engine
- Known paste sites, git repos, forums
- Auto-discovery of git/gitea/cgit endpoints

Features:
- Circuit rotation to prevent rate limiting
- Resilience to timeouts and flaky connections
- Code endpoint auto-detection
- Smart query building for code discovery

Dependencies:
  pip install aiohttp aiohttp-socks
  # Tor must be running on localhost:9050
"""

import os
import re
import json
import hashlib
import asyncio
import random
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Set
from urllib.parse import quote_plus, urljoin, urlparse
import time

# Check for Tor/SOCKS support
try:
    import aiohttp
    import aiohttp_socks
    HAS_TOR_SUPPORT = True
except ImportError:
    HAS_TOR_SUPPORT = False
    aiohttp = None
    aiohttp_socks = None

# Import shared types from qrawler
try:
    from .qrawler import CodeSnippet, CodeExtractor, SearchResult
except ImportError:
    from qrawler import CodeSnippet, CodeExtractor, SearchResult


__version__ = '1.4.0'


# ═══════════════════════════════════════════════════════════════════════════════
# TOR SEARCH ENGINES
# ═══════════════════════════════════════════════════════════════════════════════

TOR_SEARCH_ENGINES = {
    'ahmia': {
        'name': 'Ahmia',
        'type': 'search_engine',
        'onion_url': 'http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion',
        'clearnet_url': 'https://ahmia.fi',
        'search_path': '/search/?q=',
        'enabled': True,
        'safe': True,  # Filters illegal content
    },
    'torch': {
        'name': 'Torch',
        'type': 'search_engine',
        'onion_url': 'http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion',
        'clearnet_url': None,
        'search_path': '/search?query=',
        'enabled': True,
        'safe': False,  # No filtering - be careful
    },
}

# Code-specific search keywords for seeding
CODE_SEARCH_KEYWORDS = [
    'git repo',
    'gitea',
    'cgit',
    'source code',
    'github mirror',
    'pastebin code',
    '.py python',
    'script',
    'exploit poc',
    'index of / git',
]

# Patterns to detect code hosting endpoints
CODE_ENDPOINT_PATTERNS = {
    'git': [
        r'/git/',
        r'\.git',
        r'/\.git/config',
        r'/refs/heads/',
    ],
    'gitea': [
        r'/api/v1/repos',
        r'gitea',
        r'/user/login',
        r'/explore/repos',
    ],
    'cgit': [
        r'cgit\.cgi',
        r'/cgit/',
        r'<div id="cgit">',
    ],
    'gitlab': [
        r'gitlab',
        r'/api/v4/',
        r'/users/sign_in',
    ],
    'raw_code': [
        r'/raw/',
        r'/blob/',
        r'/plain/',
        r'\.py$',
        r'\.sh$',
        r'\.c$',
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN HIDDEN SERVICES FOR CODE
# ═══════════════════════════════════════════════════════════════════════════════

# These are well-known hidden services that host code content
# Most are paste sites or forums with code sections
# IMPORTANT: These addresses change frequently and may become stale

KNOWN_CODE_SERVICES = [
    # Paste sites (most reliable for code)
    {
        'name': 'stronghold_paste',
        'type': 'paste',
        'base_url': 'http://strongerw2ise74v3duebgsvug4mehyhlpa7f6kfwnas7zofs3daq7bad.onion',
        'search_path': '/paste/',
        'enabled': True,
    },
    {
        'name': 'zeropaste',
        'type': 'paste', 
        'base_url': 'http://zerobinftagjpeep.onion',
        'search_path': '/',
        'enabled': True,
    },
    # Code repositories
    {
        'name': 'git_onion',
        'type': 'git',
        'base_url': 'http://gitweb5j4uu5llvmqgzazlsw4bjrv7bxwyliqxrtqrtqsrf.onion',
        'search_path': '/search',
        'enabled': True,
    },
    # Forum code sections
    {
        'name': 'dread_code',
        'type': 'forum',
        'base_url': 'http://dreadytofatroptsdj6io7l3xptbet6onoyno2yv7jicoxknyazubrad.onion',
        'search_path': '/d/programming',
        'enabled': True,
    },
]


@dataclass
class DeepSearchResult:
    """Result from a deep web search."""
    title: str
    url: str
    snippet: str
    source: str  # Service name
    service_type: str  # paste, git, forum
    timestamp: Optional[datetime] = None
    code_blocks: List[CodeSnippet] = field(default_factory=list)
    reliability_score: float = 0.0  # 0-1, how likely this is real code


@dataclass
class DeepQrawlerResult:
    """Combined results from deep web search."""
    query: str
    results: List[DeepSearchResult] = field(default_factory=list)
    code_snippets: List[CodeSnippet] = field(default_factory=list)
    services_queried: List[str] = field(default_factory=list)
    services_failed: List[str] = field(default_factory=list)
    search_time_ms: int = 0
    tor_connected: bool = False
    errors: List[str] = field(default_factory=list)


class DeepQrawler:
    """
    DeepQrawler: Searches Tor hidden services for code.
    
    v1.4.0 Features:
    - Circuit rotation to prevent rate limiting
    - Ahmia + Torch search engines
    - Code endpoint auto-detection (git, gitea, cgit)
    - Resilient to timeouts and flaky connections
    
    Requirements:
    - Tor running locally (default: 127.0.0.1:9050)
    - aiohttp + aiohttp-socks installed
    - Tor control port (9051) for circuit rotation (optional)
    
    Usage:
        qrawler = DeepQrawler()
        if qrawler.is_available:
            result = await qrawler.search("python exploit framework")
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        deep_cfg = self.config.get('deep_qrawler', {})
        
        # Tor SOCKS proxy configuration
        self.tor_host = deep_cfg.get('tor_host', '127.0.0.1')
        self.tor_port = deep_cfg.get('tor_port', 9050)
        self.tor_control_port = deep_cfg.get('tor_control_port', 9051)
        self.tor_control_password = deep_cfg.get('tor_control_password', '')
        self.tor_url = f"socks5://{self.tor_host}:{self.tor_port}"
        
        # Circuit rotation settings
        self.circuit_rotation_enabled = deep_cfg.get('circuit_rotation', True)
        self.requests_before_rotation = deep_cfg.get('requests_before_rotation', 5)
        self.request_count = 0
        self.last_rotation = time.time()
        
        # Search engines
        self.ahmia_enabled = deep_cfg.get('ahmia', {}).get('enabled', True)
        self.torch_enabled = deep_cfg.get('torch', {}).get('enabled', True)
        self.ahmia_prefer_onion = deep_cfg.get('ahmia', {}).get('prefer_onion', True)
        
        # Timeouts (Tor is slow)
        self.connect_timeout = deep_cfg.get('connect_timeout', 30)
        self.request_timeout = deep_cfg.get('request_timeout', 60)
        self.retry_count = deep_cfg.get('retry_count', 3)
        self.retry_delay = deep_cfg.get('retry_delay', 2)
        
        # Cache configuration
        self.cache_dir = Path(deep_cfg.get('cache_dir', '/tmp/deep_qrawler_cache'))
        self.cache_ttl = deep_cfg.get('cache_ttl_hours', 48)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Target languages
        self.target_languages = deep_cfg.get('languages', ['python', 'bash', 'shell', 'c', 'cpp'])
        
        # Enabled services
        self.enabled_services = deep_cfg.get('enabled_services', None)
        
        # Safety settings
        self.max_results_per_service = deep_cfg.get('max_results', 10)
        self.skip_suspicious = deep_cfg.get('skip_suspicious', True)
        
        # Discovered endpoints (auto-populated during crawling)
        self.discovered_endpoints: Set[str] = set()
        
        # Status
        self._tor_checked = False
        self._tor_available = False
        self._control_available = False
    
    @property
    def is_available(self) -> bool:
        """Check if DeepQrawler can operate (has Tor + dependencies)."""
        if not HAS_TOR_SUPPORT:
            return False
        if not self._tor_checked:
            self._check_tor_sync()
        return self._tor_available
    
    @property
    def has_dependencies(self) -> bool:
        """Check if required packages are installed."""
        return HAS_TOR_SUPPORT
    
    def _check_tor_sync(self):
        """Synchronously check if Tor is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.tor_host, self.tor_port))
            sock.close()
            self._tor_available = (result == 0)
            
            # Also check control port for circuit rotation
            if self.circuit_rotation_enabled:
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock2.settimeout(5)
                ctrl_result = sock2.connect_ex((self.tor_host, self.tor_control_port))
                sock2.close()
                self._control_available = (ctrl_result == 0)
        except Exception:
            self._tor_available = False
            self._control_available = False
        self._tor_checked = True
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CIRCUIT ROTATION - Prevent rate limiting
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def rotate_circuit(self) -> bool:
        """
        Request a new Tor circuit to get a new exit IP.
        This helps avoid rate limiting on search engines.
        
        Requires Tor control port (9051) with authentication.
        """
        if not self._control_available:
            return False
        
        try:
            reader, writer = await asyncio.open_connection(
                self.tor_host, self.tor_control_port
            )
            
            # Authenticate (empty password or configured)
            if self.tor_control_password:
                writer.write(f'AUTHENTICATE "{self.tor_control_password}"\r\n'.encode())
            else:
                writer.write(b'AUTHENTICATE\r\n')
            await writer.drain()
            
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            if not response.startswith(b'250'):
                writer.close()
                return False
            
            # Request new circuit
            writer.write(b'SIGNAL NEWNYM\r\n')
            await writer.drain()
            
            response = await asyncio.wait_for(reader.readline(), timeout=5)
            writer.close()
            
            if response.startswith(b'250'):
                self.last_rotation = time.time()
                self.request_count = 0
                # Wait for new circuit to establish
                await asyncio.sleep(1)
                return True
                
        except Exception:
            pass
        
        return False
    
    async def _maybe_rotate_circuit(self):
        """Rotate circuit if we've made enough requests."""
        if not self.circuit_rotation_enabled:
            return
        
        self.request_count += 1
        
        if self.request_count >= self.requests_before_rotation:
            await self.rotate_circuit()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CODE ENDPOINT DETECTION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def detect_code_endpoint(self, url: str, html: str = '') -> Optional[str]:
        """
        Detect if a URL/page is a code hosting endpoint.
        
        Returns endpoint type: 'git', 'gitea', 'cgit', 'gitlab', 'raw_code', or None
        """
        url_lower = url.lower()
        html_lower = html.lower() if html else ''
        
        for endpoint_type, patterns in CODE_ENDPOINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower) or (html and re.search(pattern, html_lower)):
                    return endpoint_type
        
        return None
    
    def extract_onion_urls(self, html: str) -> List[str]:
        """Extract all .onion URLs from HTML content."""
        pattern = r'https?://[a-z2-7]{56}\.onion[^\s"\'<>]*'
        urls = re.findall(pattern, html, re.IGNORECASE)
        return list(set(urls))
    
    async def crawl_for_code_endpoints(self, base_url: str, depth: int = 1) -> List[str]:
        """
        Crawl a page to discover code hosting endpoints.
        
        Looks for git, gitea, cgit, etc. patterns.
        """
        if depth < 0:
            return []
        
        endpoints = []
        html = await self._fetch_with_tor(base_url)
        
        if not html:
            return []
        
        # Check if this page itself is a code endpoint
        endpoint_type = self.detect_code_endpoint(base_url, html)
        if endpoint_type:
            endpoints.append(base_url)
            self.discovered_endpoints.add(base_url)
        
        # Extract onion URLs for further crawling
        if depth > 0:
            onion_urls = self.extract_onion_urls(html)
            for url in onion_urls[:10]:  # Limit to avoid explosion
                if url not in self.discovered_endpoints:
                    sub_endpoints = await self.crawl_for_code_endpoints(url, depth - 1)
                    endpoints.extend(sub_endpoints)
        
        return endpoints
    
    async def check_tor(self) -> bool:
        """Check if Tor is running and accessible."""
        if not HAS_TOR_SUPPORT:
            return False
        
        try:
            connector = aiohttp_socks.ProxyConnector.from_url(self.tor_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                # Test with check.torproject.org
                async with session.get(
                    'https://check.torproject.org/api/ip',
                    timeout=aiohttp.ClientTimeout(total=self.connect_timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._tor_available = data.get('IsTor', False)
                        return self._tor_available
        except Exception:
            pass
        
        self._tor_available = False
        return False
    
    def _cache_key(self, query: str) -> str:
        """Generate cache key for a query."""
        return hashlib.md5(f"deep:{query}".encode()).hexdigest()
    
    def _get_cached(self, query: str) -> Optional[DeepQrawlerResult]:
        """Get cached result if available and not expired."""
        cache_file = self.cache_dir / f"{self._cache_key(query)}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                cached_time = datetime.fromisoformat(data.get('timestamp', '2000-01-01'))
                if datetime.utcnow() - cached_time < timedelta(hours=self.cache_ttl):
                    result = DeepQrawlerResult(
                        query=data['query'],
                        services_queried=data.get('services_queried', []),
                        search_time_ms=0,
                        tor_connected=True
                    )
                    for snippet_data in data.get('code_snippets', []):
                        result.code_snippets.append(CodeSnippet(
                            code=snippet_data['code'],
                            language=snippet_data['language'],
                            source_url=snippet_data.get('source_url', ''),
                            source_name=snippet_data.get('source_name', 'deep'),
                            title=snippet_data.get('title', ''),
                            score=snippet_data.get('score', 0)
                        ))
                    return result
            except Exception:
                pass
        return None
    
    def _save_cache(self, result: DeepQrawlerResult):
        """Save result to cache."""
        cache_file = self.cache_dir / f"{self._cache_key(result.query)}.json"
        try:
            data = {
                'query': result.query,
                'timestamp': datetime.utcnow().isoformat(),
                'services_queried': result.services_queried,
                'code_snippets': [
                    {
                        'code': s.code,
                        'language': s.language,
                        'source_url': s.source_url,
                        'source_name': s.source_name,
                        'title': s.title,
                        'score': s.score
                    }
                    for s in result.code_snippets
                ]
            }
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass
    
    def _get_enabled_services(self) -> List[Dict]:
        """Get list of enabled hidden services."""
        services = []
        for svc in KNOWN_CODE_SERVICES:
            if not svc.get('enabled', True):
                continue
            if self.enabled_services and svc['name'] not in self.enabled_services:
                continue
            services.append(svc)
        return services
    
    def _build_search_queries(self, base_query: str) -> List[str]:
        """Build optimized search queries for deep web."""
        queries = [base_query]
        
        # Add language prefixes
        lower = base_query.lower()
        if 'python' not in lower and 'py' not in lower:
            if any(kw in lower for kw in ['script', 'code', 'function', 'class']):
                queries.append(f"python {base_query}")
        
        # Add exploit/security keywords for relevant queries
        security_keywords = ['exploit', 'vulnerability', 'bypass', 'injection', 'payload']
        if any(kw in lower for kw in security_keywords):
            queries.append(f"{base_query} poc")
            queries.append(f"{base_query} github")
        
        return queries[:3]  # Limit to avoid overload
    
    async def _fetch_with_tor(self, url: str, retries: int = None) -> Optional[str]:
        """
        Fetch a URL through Tor with retry logic and circuit rotation.
        
        Features:
        - Automatic retries on failure
        - Circuit rotation to prevent rate limiting
        - Graceful timeout handling
        """
        if not HAS_TOR_SUPPORT:
            return None
        
        retries = retries if retries is not None else self.retry_count
        
        for attempt in range(retries):
            try:
                # Maybe rotate circuit before request
                await self._maybe_rotate_circuit()
                
                connector = aiohttp_socks.ProxyConnector.from_url(self.tor_url)
                timeout = aiohttp.ClientTimeout(
                    total=self.request_timeout,
                    connect=self.connect_timeout
                )
                
                async with aiohttp.ClientSession(connector=connector) as session:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:102.0) Gecko/20100101 Firefox/102.0',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                    }
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:
                            # Rate limited - rotate circuit
                            await self.rotate_circuit()
                        elif response.status >= 500:
                            # Server error - retry
                            pass
                            
            except asyncio.TimeoutError:
                # Timeout - try again with potentially new circuit
                await self.rotate_circuit()
            except Exception:
                pass
            
            # Delay before retry
            if attempt < retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TORCH SEARCH ENGINE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def _search_torch(self, query: str, max_results: int = 10) -> List[DeepSearchResult]:
        """
        Search Torch - longstanding Tor search engine.
        
        WARNING: Torch doesn't filter content like Ahmia.
        Results are processed carefully.
        """
        results = []
        
        if not self.torch_enabled:
            return results
        
        if not HAS_TOR_SUPPORT:
            return results
        
        try:
            torch_cfg = TOR_SEARCH_ENGINES['torch']
            search_url = f"{torch_cfg['onion_url']}{torch_cfg['search_path']}{quote_plus(query)}"
            
            html = await self._fetch_with_tor(search_url)
            
            if html:
                results.extend(self._parse_torch_results(html, query, max_results))
                
        except Exception:
            pass
        
        return results
    
    def _parse_torch_results(self, html: str, query: str, max_results: int) -> List[DeepSearchResult]:
        """Parse Torch search results."""
        results = []
        
        try:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Torch results are usually in dt/dd pairs or specific divs
                # Structure varies - try multiple patterns
                
                # Pattern 1: Look for links with .onion
                for link in soup.find_all('a', href=True)[:max_results * 2]:
                    href = link.get('href', '')
                    if '.onion' in href:
                        title = link.get_text(strip=True) or 'Untitled'
                        
                        # Skip obviously problematic titles
                        if self.skip_suspicious:
                            bad_keywords = ['hack', 'card', 'drug', 'weapon']
                            if any(kw in title.lower() for kw in bad_keywords):
                                continue
                        
                        # Check if code-related
                        code_indicators = ['git', 'code', 'script', 'source', 'repo', 'paste', 'python']
                        is_code = any(ind in title.lower() or ind in href.lower() 
                                     for ind in code_indicators)
                        
                        results.append(DeepSearchResult(
                            title=title[:200],
                            url=href,
                            snippet='',
                            source='torch',
                            service_type='search_engine',
                            reliability_score=0.6 if is_code else 0.3
                        ))
                        
                        if len(results) >= max_results:
                            break
                            
            except ImportError:
                # Fallback regex parsing
                pattern = r'href=["\']?(http[s]?://[a-z2-7]{56}\.onion[^"\'<>\s]*)'
                matches = re.findall(pattern, html, re.IGNORECASE)
                
                for url in matches[:max_results]:
                    results.append(DeepSearchResult(
                        title=f"Torch: {url[:50]}...",
                        url=url,
                        snippet='',
                        source='torch',
                        service_type='search_engine',
                        reliability_score=0.4
                    ))
                    
        except Exception:
            pass
        
        return results
    
    async def _search_ahmia(self, query: str, max_results: int = 10) -> List[DeepSearchResult]:
        """
        Search Ahmia - the safe Tor search engine.
        
        Ahmia filters out illegal content, making it safe to query.
        Returns onion links to code resources.
        """
        results = []
        
        if not self.ahmia_enabled:
            return results
        
        if not HAS_TOR_SUPPORT:
            return results
        
        # Build search URL
        # Ahmia search format: /search/?q=<query>
        encoded_query = quote_plus(query)
        
        # Choose onion or clearnet
        if self.ahmia_prefer_onion:
            base_url = self.ahmia_onion_url
        else:
            base_url = self.ahmia_clearnet_url
        
        search_url = f"{base_url}/search/?q={encoded_query}"
        
        try:
            html = await self._fetch_with_tor(search_url)
            
            if not html:
                # Fallback to clearnet if onion fails
                if self.ahmia_prefer_onion:
                    search_url = f"{self.ahmia_clearnet_url}/search/?q={encoded_query}"
                    # For clearnet, we can use regular aiohttp without Tor
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                                if response.status == 200:
                                    html = await response.text()
                    except Exception:
                        pass
            
            if not html:
                return results
            
            # Parse Ahmia search results
            # Ahmia returns HTML with search results in a specific format
            # Results are typically in <li class="result"> elements
            results.extend(self._parse_ahmia_results(html, query, max_results))
            
        except Exception as e:
            # Ahmia might be down or Tor unavailable
            pass
        
        return results
    
    def _parse_ahmia_results(self, html: str, query: str, max_results: int) -> List[DeepSearchResult]:
        """Parse Ahmia search results HTML."""
        results = []
        
        try:
            # Try BeautifulSoup if available
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ahmia results are in <li class="result"> elements
                result_items = soup.find_all('li', class_='result')
                
                for item in result_items[:max_results]:
                    try:
                        # Get title and URL
                        title_elem = item.find('a')
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True)
                        url = title_elem.get('href', '')
                        
                        # Get snippet/description
                        desc_elem = item.find('p') or item.find('span', class_='desc')
                        snippet = desc_elem.get_text(strip=True) if desc_elem else ''
                        
                        # Skip non-onion results
                        if '.onion' not in url:
                            continue
                        
                        # Check if it looks like a code resource
                        code_indicators = ['github', 'git', 'code', 'script', '.py', 'source', 
                                          'paste', 'repo', 'exploit', 'tool']
                        is_code_related = any(ind in title.lower() or ind in snippet.lower() 
                                             for ind in code_indicators)
                        
                        # Create result
                        result = DeepSearchResult(
                            title=title,
                            url=url,
                            snippet=snippet[:500],
                            source='ahmia',
                            service_type='search_engine',
                            reliability_score=0.8 if is_code_related else 0.5
                        )
                        results.append(result)
                        
                    except Exception:
                        continue
                        
            except ImportError:
                # Fallback to regex parsing
                # Pattern for Ahmia result links
                link_pattern = r'<a[^>]+href=["\']([^"\']*\.onion[^"\']*)["\'][^>]*>([^<]+)</a>'
                matches = re.findall(link_pattern, html, re.IGNORECASE)
                
                for url, title in matches[:max_results]:
                    if '.onion' in url:
                        results.append(DeepSearchResult(
                            title=title.strip(),
                            url=url,
                            snippet='',
                            source='ahmia',
                            service_type='search_engine',
                            reliability_score=0.6
                        ))
                        
        except Exception:
            pass
        
        return results
    
    async def _fetch_and_extract_code(self, url: str) -> List[CodeSnippet]:
        """Fetch an onion URL and extract code from it."""
        snippets = []
        
        try:
            html = await self._fetch_with_tor(url)
            if html:
                # Extract code blocks
                extracted = CodeExtractor.extract_from_html(html)
                
                for snippet in extracted:
                    # Tag with source URL
                    snippet.source_url = url
                    snippet.source_name = 'ahmia'
                    snippets.append(snippet)
                    
        except Exception:
            pass
        
        return snippets
    
    async def _search_paste_service(self, service: Dict, query: str) -> List[DeepSearchResult]:
        """Search a paste-type service."""
        results = []
        
        # Paste sites usually don't have search, we'd need to crawl recent
        # For now, return empty - this is a placeholder for future expansion
        # Real implementation would:
        # 1. Fetch recent pastes list
        # 2. Download and grep for query terms
        # 3. Extract code blocks
        
        return results
    
    async def _search_git_service(self, service: Dict, query: str) -> List[DeepSearchResult]:
        """Search a git-type service."""
        results = []
        
        base_url = service['base_url']
        search_path = service['search_path']
        
        # Try search endpoint
        search_url = f"{base_url}{search_path}?q={query.replace(' ', '+')}"
        html = await self._fetch_with_tor(search_url)
        
        if html:
            snippets = CodeExtractor.extract_from_html(html)
            for snippet in snippets[:self.max_results_per_service]:
                results.append(DeepSearchResult(
                    title=f"Git result: {query}",
                    url=search_url,
                    snippet=snippet.code[:200],
                    source=service['name'],
                    service_type='git',
                    code_blocks=[snippet],
                    reliability_score=0.7  # Git services are relatively reliable
                ))
        
        return results
    
    async def _search_forum_service(self, service: Dict, query: str) -> List[DeepSearchResult]:
        """Search a forum-type service."""
        results = []
        
        # Forums usually have search functionality
        base_url = service['base_url']
        search_path = service['search_path']
        
        # Construct search URL (varies by forum software)
        search_url = f"{base_url}/search?q={query.replace(' ', '+')}"
        html = await self._fetch_with_tor(search_url)
        
        if html:
            snippets = CodeExtractor.extract_from_html(html)
            for snippet in snippets[:self.max_results_per_service]:
                # Skip very short or suspicious content
                if len(snippet.code) < 30:
                    continue
                if self.skip_suspicious:
                    suspicious_patterns = ['rm -rf /', 'format c:', 'dd if=/dev/zero']
                    if any(p in snippet.code.lower() for p in suspicious_patterns):
                        continue
                
                results.append(DeepSearchResult(
                    title=f"Forum: {query}",
                    url=search_url,
                    snippet=snippet.code[:200],
                    source=service['name'],
                    service_type='forum',
                    code_blocks=[snippet],
                    reliability_score=0.5  # Forum code is less reliable
                ))
        
        return results
    
    async def search(self, query: str, use_cache: bool = True) -> DeepQrawlerResult:
        """
        Search deep web services for code.
        
        v1.4.0 Search order:
        1. Ahmia (PRIMARY) - Safe Tor search engine
        2. Torch - Secondary Tor search engine  
        3. Known services (paste sites, git repos, forums)
        4. Auto-discovered code endpoints
        
        Features:
        - Circuit rotation for rate limiting prevention
        - Retry logic for flaky connections
        - Code endpoint auto-detection
        
        Args:
            query: Search query
            use_cache: Whether to use cached results
        
        Returns:
            DeepQrawlerResult with aggregated code snippets
        """
        start_time = datetime.utcnow()
        
        result = DeepQrawlerResult(query=query)
        
        # Check cache first
        if use_cache:
            cached = self._get_cached(query)
            if cached:
                cached.search_time_ms = 0
                return cached
        
        # Check Tor availability
        if not self.is_available:
            result.errors.append("Tor not available (install aiohttp-socks and run Tor)")
            return result
        
        tor_ok = await self.check_tor()
        result.tor_connected = tor_ok
        
        if not tor_ok:
            result.errors.append("Cannot connect to Tor network")
            return result
        
        # Build queries
        queries = self._build_search_queries(query)
        
        all_results: List[DeepSearchResult] = []
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Search Ahmia (PRIMARY - safe Tor search engine)
        # ═══════════════════════════════════════════════════════════════════
        if self.ahmia_enabled:
            try:
                for q in queries:
                    code_queries = [q]
                    if 'code' not in q.lower() and 'source' not in q.lower():
                        code_queries.append(f"{q} source code")
                    
                    for cq in code_queries:
                        ahmia_results = await self._search_ahmia(cq, self.max_results_per_service)
                        all_results.extend(ahmia_results)
                
                if all_results:
                    result.services_queried.append('ahmia')
                    
            except Exception as e:
                result.errors.append(f"ahmia: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: Search Torch (SECONDARY - more results, less safe)
        # ═══════════════════════════════════════════════════════════════════
        if self.torch_enabled:
            try:
                for q in queries:
                    torch_results = await self._search_torch(q, self.max_results_per_service)
                    all_results.extend(torch_results)
                
                if torch_results:
                    result.services_queried.append('torch')
                    
            except Exception as e:
                result.errors.append(f"torch: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 3: Fetch code from promising results
        # ═══════════════════════════════════════════════════════════════════
        for r in all_results[:8]:  # Top 8 results
            if r.reliability_score >= 0.5:
                try:
                    snippets = await self._fetch_and_extract_code(r.url)
                    r.code_blocks.extend(snippets)
                    
                    # Check if it's a code endpoint for future reference
                    endpoint_type = self.detect_code_endpoint(r.url)
                    if endpoint_type:
                        self.discovered_endpoints.add(r.url)
                except Exception:
                    pass
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Search known services (paste sites, git repos, forums)
        # ═══════════════════════════════════════════════════════════════════
        services = self._get_enabled_services()
        
        for service in services:
            try:
                svc_type = service['type']
                
                for q in queries:
                    if svc_type == 'paste':
                        results = await self._search_paste_service(service, q)
                    elif svc_type == 'git':
                        results = await self._search_git_service(service, q)
                    elif svc_type == 'forum':
                        results = await self._search_forum_service(service, q)
                    else:
                        continue
                    
                    all_results.extend(results)
                
                result.services_queried.append(service['name'])
                
            except Exception as e:
                result.services_failed.append(service['name'])
                result.errors.append(f"{service['name']}: {str(e)}")
        
        # Aggregate code snippets
        result.results = all_results
        for r in all_results:
            for snippet in r.code_blocks:
                # Tag with deep source
                snippet.source_name = f"deep:{r.source}"
                result.code_snippets.append(snippet)
        
        result.total_found = len(result.code_snippets)
        
        # Calculate search time
        result.search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Cache results
        if result.code_snippets:
            self._save_cache(result)
        
        return result
    
    def search_sync(self, query: str, use_cache: bool = True) -> DeepQrawlerResult:
        """Synchronous wrapper for search."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.search(query, use_cache))


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"DeepQrawler v{__version__}")
    print(f"Tor support: {HAS_TOR_SUPPORT}")
    
    qrawler = DeepQrawler()
    print(f"Is available: {qrawler.is_available}")
    print(f"Enabled services: {[s['name'] for s in qrawler._get_enabled_services()]}")
