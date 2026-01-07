#!/usr/bin/env python3
"""
sQavanger: Web Search Harvester Agent (Tier 1)
Part of mindstaQ - REAL web search for code harvesting

This is the REAL sQavanger that:
1. Takes a task/intent from Qomputator
2. Builds optimized search queries
3. Searches via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
4. Harvests REAL code snippets from search results
5. Ranks and filters snippets by relevance
6. Returns the best matching code for the task

v1.3.0 - REAL WEB SEARCH IMPLEMENTATION
"""

import asyncio
import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import sys

# Import Qrawler
try:
    from worqer.mindstaq.qrawler import Qrawler, QrawlerResult, CodeSnippet, CodeExtractor
    HAS_QRAWLER = True
except ImportError:
    try:
        from qrawler import Qrawler, QrawlerResult, CodeSnippet, CodeExtractor
        HAS_QRAWLER = True
    except ImportError:
        HAS_QRAWLER = False

# Import intent crystallizer for context
try:
    from worqer.mindstaq import CrystallizedIntent, ActionType, TargetType
    HAS_INTENT = True
except ImportError:
    HAS_INTENT = False


__version__ = '1.8.9-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HarvestedCode:
    """A harvested and processed code snippet ready for use."""
    code: str
    language: str
    source_url: str
    source_name: str
    relevance_score: float  # 0-1 how well it matches the task
    quality_score: float    # 0-1 code quality assessment
    upvotes: int = 0
    is_complete: bool = True  # False if snippet needs adaptation
    needs_imports: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SQavengerResult:
    """Result from sQavanger search and harvest."""
    task: str
    success: bool = False  # v1.8.9: Added default to fix instantiation error
    harvested_code: List[HarvestedCode] = field(default_factory=list)
    best_code: Optional[str] = None
    search_queries: List[str] = field(default_factory=list)
    total_snippets_found: int = 0
    search_time_ms: int = 0
    engines_used: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# CODE QUALITY ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class CodeQualityAnalyzer:
    """Analyze and score code quality without running it."""
    
    @classmethod
    def analyze_python(cls, code: str) -> Tuple[float, List[str]]:
        """
        Analyze Python code quality.
        Returns (score 0-1, list of warnings).
        """
        score = 1.0
        warnings = []
        
        # Check syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return 0.0, [f"Syntax error: {e}"]
        
        # Check for common issues
        code_lower = code.lower()
        
        # Hardcoded secrets (bad)
        if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', code, re.IGNORECASE):
            score -= 0.1
            warnings.append("Contains potential hardcoded secrets")
        
        # TODO/FIXME comments (incomplete)
        if re.search(r'#\s*(TODO|FIXME|HACK|XXX)', code, re.IGNORECASE):
            score -= 0.05
            warnings.append("Contains TODO/FIXME comments")
        
        # Pass/NotImplementedError (incomplete)
        if 'raise NotImplementedError' in code or re.search(r'^\s+pass\s*$', code, re.MULTILINE):
            score -= 0.2
            warnings.append("Contains stub implementations")
        
        # Check for docstrings (good)
        has_docstring = '"""' in code or "'''" in code
        if not has_docstring:
            score -= 0.05
            warnings.append("No docstrings found")
        
        # Check for type hints (good)
        has_type_hints = '->' in code or ': str' in code or ': int' in code or ': List' in code
        if not has_type_hints:
            score -= 0.05
        
        # Check for error handling
        has_try_except = 'try:' in code and 'except' in code
        if 'open(' in code or 'requests.' in code or 'http' in code.lower():
            if not has_try_except:
                score -= 0.1
                warnings.append("External operations without error handling")
        
        # Bonus for comprehensive code
        num_functions = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
        if num_functions >= 2:
            score = min(1.0, score + 0.05)
        
        return max(0.0, score), warnings
    
    @classmethod
    def analyze(cls, code: str, language: str) -> Tuple[float, List[str]]:
        """Analyze code quality for any supported language."""
        if language == 'python':
            return cls.analyze_python(code)
        elif language in ('yaml', 'json'):
            # Basic validation for config files
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
            # Basic shell script checks
            warnings = []
            score = 1.0
            if 'rm -rf' in code:
                score -= 0.2
                warnings.append("Contains dangerous rm -rf")
            if 'eval' in code:
                score -= 0.1
                warnings.append("Contains eval (security risk)")
            return score, warnings
        else:
            return 0.8, []  # Unknown language, assume okay


# ═══════════════════════════════════════════════════════════════════════════════
# RELEVANCE SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class RelevanceScorer:
    """Score how relevant a code snippet is to a task."""
    
    @classmethod
    def score(cls, code: str, task: str, context: dict = None) -> float:
        """
        Score relevance of code to task (0-1).
        
        Args:
            code: The code snippet
            task: The task description
            context: Optional context (entities, action, etc.)
        """
        context = context or {}
        score = 0.5  # Base score
        
        task_lower = task.lower()
        code_lower = code.lower()
        
        # Extract keywords from task
        keywords = set(re.findall(r'\b\w{3,}\b', task_lower))
        stopwords = {'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'are', 'was', 'were'}
        keywords = keywords - stopwords
        
        # Check keyword presence in code
        matches = 0
        for keyword in keywords:
            if keyword in code_lower:
                matches += 1
        
        if keywords:
            keyword_score = matches / len(keywords)
            score += keyword_score * 0.3
        
        # Check for entities from context
        entities = context.get('entities', [])
        entity_matches = 0
        for entity in entities:
            if entity.lower() in code_lower:
                entity_matches += 1
        if entities:
            entity_score = entity_matches / len(entities)
            score += entity_score * 0.2
        
        # Check for action type patterns
        action = context.get('action', '').lower()
        if action:
            if action in ('create', 'add', 'implement') and 'def ' in code:
                score += 0.1
            elif action in ('validate', 'check') and ('return' in code and ('True' in code or 'False' in code)):
                score += 0.1
            elif action == 'fix' and ('try:' in code or 'except' in code):
                score += 0.1
        
        # Bonus for complete-looking code
        if 'def ' in code and 'return' in code:
            score += 0.1
        if 'import ' in code:
            score += 0.05
        
        # Penalty for very short snippets
        if len(code) < 100:
            score -= 0.1
        
        # Penalty for very long snippets (might be too much)
        if len(code) > 2000:
            score -= 0.05
        
        return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════════════════════
# SQAVANGER MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class SQavenger:
    """
    sQavanger: Web Search Harvester Agent (Tier 1)
    
    Searches the web for REAL code snippets and harvests them.
    This is the brain that finds how to build things we don't have templates for!
    
    Process:
    1. Build search queries from task
    2. Search via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
    3. Extract and rank code snippets
    4. Return best matching code
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        sqavenger_cfg = self.config.get('sqavenger', self.config.get('mindstaq', {}))
        
        # Initialize Qrawler
        if HAS_QRAWLER:
            self.qrawler = Qrawler(self.config)
        else:
            self.qrawler = None
        
        # Configuration
        self.max_results = sqavenger_cfg.get('max_results', 10)
        self.min_relevance = sqavenger_cfg.get('min_relevance', 0.3)
        self.min_quality = sqavenger_cfg.get('min_quality', 0.5)
        self.target_languages = sqavenger_cfg.get('languages', ['python', 'yaml', 'json', 'bash', 'shell'])
        
        # Query templates for different task types
        self.query_templates = {
            'validate': '{lang} {entity} validation example',
            'create': '{lang} how to create {entity}',
            'add': '{lang} {entity} implementation example',
            'fix': '{lang} {entity} fix solution',
            'parse': '{lang} parse {entity} example',
            'convert': '{lang} convert {entity} example',
            'connect': '{lang} {entity} connection example',
            'default': '{lang} {entity} example code',
        }
    
    def _build_queries(self, task: str, context: dict = None) -> List[str]:
        """Build multiple search queries from a task."""
        context = context or {}
        queries = []
        
        lang = context.get('language', 'python')
        entities = context.get('entities', [])
        action = context.get('action', '').lower()
        
        # Get query template
        template = self.query_templates.get(action, self.query_templates['default'])
        
        # Build primary query
        entity_str = ' '.join(entities[:3]) if entities else task[:50]
        primary_query = template.format(lang=lang, entity=entity_str)
        queries.append(primary_query)
        
        # Build alternative queries
        # Direct task as query
        queries.append(f"{lang} {task[:60]}")
        
        # With "example" suffix
        if entities:
            queries.append(f"{lang} {entities[0]} example")
        
        # With "stackoverflow" for Q&A style
        queries.append(f"{lang} {entity_str} stackoverflow")
        
        # Deduplicate
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = ' '.join(q.split()).lower()
            if q_clean not in seen:
                seen.add(q_clean)
                unique_queries.append(q)
        
        return unique_queries[:4]  # Max 4 queries
    
    def _extract_imports(self, code: str) -> List[str]:
        """Extract required imports from code."""
        imports = []
        
        # Match import statements
        import_pattern = r'^(?:import|from)\s+[\w.]+'
        for line in code.split('\n'):
            line = line.strip()
            if re.match(import_pattern, line):
                imports.append(line)
        
        return imports
    
    def _process_snippets(self, snippets: List[CodeSnippet], task: str, context: dict) -> List[HarvestedCode]:
        """Process and rank code snippets."""
        harvested = []
        
        for snippet in snippets:
            # Filter by language
            if snippet.language not in self.target_languages and snippet.language != 'unknown':
                continue
            
            # Score relevance
            relevance = RelevanceScorer.score(snippet.code, task, context)
            if relevance < self.min_relevance:
                continue
            
            # Analyze quality
            quality, warnings = CodeQualityAnalyzer.analyze(snippet.code, snippet.language)
            if quality < self.min_quality:
                continue
            
            # Check completeness
            is_complete = True
            if 'raise NotImplementedError' in snippet.code:
                is_complete = False
            if re.search(r'^\s+pass\s*$', snippet.code, re.MULTILINE):
                is_complete = False
            
            # Extract imports
            imports = self._extract_imports(snippet.code)
            
            harvested.append(HarvestedCode(
                code=snippet.code,
                language=snippet.language,
                source_url=snippet.source_url,
                source_name=snippet.source_name,
                relevance_score=relevance,
                quality_score=quality,
                upvotes=snippet.score,
                is_complete=is_complete,
                needs_imports=imports,
                warnings=warnings
            ))
        
        # Sort by combined score
        harvested.sort(key=lambda h: (h.relevance_score * 0.5 + h.quality_score * 0.3 + min(h.upvotes / 100, 0.2)), reverse=True)
        
        return harvested
    
    async def harvest_async(self, task: str, context: dict = None) -> SQavengerResult:
        """
        Harvest code from the web for a task (async).
        
        Args:
            task: The task description (e.g., "add email validation")
            context: Optional context (language, entities, action, etc.)
        
        Returns:
            SQavengerResult with harvested code
        """
        context = context or {}
        start_time = datetime.utcnow()
        
        result = SQavengerResult(task=task)
        
        if not self.qrawler:
            result.error = "Qrawler not available (install aiohttp, beautifulsoup4)"
            result.success = False
            return result
        
        # Build search queries
        queries = self._build_queries(task, context)
        result.search_queries = queries
        
        # Search all queries
        all_snippets = []
        engines_used = set()
        
        for query in queries:
            try:
                qrawler_result = await self.qrawler.search(query, max_results=self.max_results)
                all_snippets.extend(qrawler_result.code_snippets)
                engines_used.update(qrawler_result.engines_used)
            except Exception as e:
                result.error = str(e)
        
        result.engines_used = list(engines_used)
        result.total_snippets_found = len(all_snippets)
        
        # Process and rank snippets
        harvested = self._process_snippets(all_snippets, task, context)
        result.harvested_code = harvested
        
        # Set best code
        if harvested:
            result.best_code = harvested[0].code
            result.success = True
        else:
            result.success = False
            if not result.error:
                result.error = "No suitable code found"
        
        result.search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return result
    
    def harvest(self, task: str, context: dict = None) -> SQavengerResult:
        """Synchronous wrapper for harvest_async."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.harvest_async(task, context))
    
    def generate(self, intent) -> Optional[str]:
        """
        Generate code for a crystallized intent.
        This is the interface called by MindstaQEngine.
        
        Args:
            intent: CrystallizedIntent from intent crystallizer
        
        Returns:
            Generated code string or None if not found
        
        v1.8.8 FIX: Use correct attribute names (keywords, raw_text)
        """
        # Build context from intent
        if HAS_INTENT and hasattr(intent, 'action'):
            context = {
                'action': intent.action.value if hasattr(intent.action, 'value') else str(intent.action),
                'entities': intent.keywords,  # v1.8.8: Fixed - was intent.entities
                'language': 'python',  # Default to Python
            }
            task = intent.raw_text  # v1.8.8: Fixed - was intent.raw_task
        else:
            # Fallback: treat intent as string
            context = {'language': 'python'}
            task = str(intent)
        
        # Harvest code
        result = self.harvest(task, context)
        
        if result.success and result.best_code:
            return result.best_code
        
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK PATTERNS (for offline mode)
# ═══════════════════════════════════════════════════════════════════════════════

# These are FALLBACK patterns used when web search is unavailable
OFFLINE_PATTERNS = {
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
}


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    async def test():
        print("=" * 70)
        print("SQAVANGER WEB HARVESTER TEST")
        print("=" * 70)
        
        sqavenger = SQavenger()
        
        # Test task
        task = "add email validation function"
        context = {
            'action': 'add',
            'entities': ['email', 'validation'],
            'language': 'python'
        }
        
        print(f"\nTask: {task}")
        print(f"Context: {context}")
        
        result = await sqavenger.harvest_async(task, context)
        
        print(f"\nResults:")
        print(f"  Success: {result.success}")
        print(f"  Search queries: {result.search_queries}")
        print(f"  Engines used: {result.engines_used}")
        print(f"  Snippets found: {result.total_snippets_found}")
        print(f"  Harvested: {len(result.harvested_code)}")
        print(f"  Search time: {result.search_time_ms}ms")
        
        if result.error:
            print(f"  Error: {result.error}")
        
        if result.harvested_code:
            print(f"\nBest Match:")
            best = result.harvested_code[0]
            print(f"  Source: {best.source_name}")
            print(f"  Relevance: {best.relevance_score:.2f}")
            print(f"  Quality: {best.quality_score:.2f}")
            print(f"  Upvotes: {best.upvotes}")
            print(f"  Complete: {best.is_complete}")
            print(f"\nCode:\n{best.code[:500]}...")
    
    asyncio.run(test())
