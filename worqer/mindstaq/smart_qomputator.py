#!/usr/bin/env python3
"""
Smart Qomputator: Advanced Task Complexity Analysis
Part of mindstaQ v2.0 - ZERO LLM Code Generation

Deep task understanding via patterns, dependency inference, and complexity scoring.
No LLM needed - pure pattern analysis!

v1.5.0
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple
from enum import Enum


__version__ = '1.5.0'


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLEXITY PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# Keyword-based complexity modifiers
COMPLEXITY_KEYWORDS = {
    # High complexity indicators (+40 to +80)
    'machine learning': 80,
    'neural network': 80,
    'deep learning': 80,
    'ml model': 75,
    'ai': 70,
    'websocket': 65,
    'real-time': 60,
    'realtime': 60,
    'distributed': 65,
    'microservice': 60,
    'kubernetes': 60,
    'blockchain': 70,
    'encryption': 55,
    'oauth2': 55,
    'oauth': 50,
    
    # Medium-high complexity (+30 to +50)
    'async': 50,
    'asynchronous': 50,
    'concurrent': 50,
    'parallel': 45,
    'authentication': 45,
    'authorization': 45,
    'database': 40,
    'postgres': 40,
    'mongodb': 40,
    'redis': 35,
    'queue': 40,
    'cache': 35,
    'api': 35,
    'rest api': 40,
    'graphql': 50,
    'jwt': 40,
    'security': 45,
    'crud': 35,
    
    # Medium complexity (+15 to +30)
    'flask': 30,
    'django': 35,
    'fastapi': 35,
    'web server': 30,
    'http': 25,
    'json': 20,
    'parser': 30,
    'scraper': 35,
    'crawler': 40,
    'file': 20,
    'csv': 20,
    'xml': 25,
    'yaml': 20,
    'config': 20,
    'cli': 25,
    'command line': 25,
    'argparse': 20,
    'logging': 15,
    'test': 25,
    'unittest': 25,
    'pytest': 25,
    
    # Low complexity indicators (-10 to -30)
    'simple': -30,
    'basic': -25,
    'hello world': -40,
    'example': -20,
    'demo': -15,
    'print': -20,
    'minimal': -25,
    'trivial': -35,
    'easy': -20,
    'beginner': -25,
}

# Task type patterns with base complexity
TASK_TYPE_PATTERNS = {
    'http_client': {
        'patterns': [r'http\s*(client|request)', r'fetch\s*url', r'api\s*call', r'requests?\s*get'],
        'base_complexity': 35,
        'dependencies': ['requests', 'aiohttp', 'httpx'],
    },
    'database': {
        'patterns': [r'database', r'sql\s*query', r'postgres', r'sqlite', r'mysql', r'mongodb'],
        'base_complexity': 45,
        'dependencies': ['sqlite3', 'psycopg2', 'pymongo', 'sqlalchemy'],
    },
    'auth': {
        'patterns': [r'authenticat', r'login', r'jwt', r'token', r'oauth', r'password'],
        'base_complexity': 50,
        'dependencies': ['jwt', 'bcrypt', 'passlib', 'authlib'],
    },
    'web_api': {
        'patterns': [r'rest\s*api', r'web\s*server', r'endpoint', r'flask', r'fastapi', r'django'],
        'base_complexity': 45,
        'dependencies': ['flask', 'fastapi', 'django', 'bottle'],
    },
    'file_io': {
        'patterns': [r'read\s*file', r'write\s*file', r'file\s*handl', r'csv', r'json\s*file'],
        'base_complexity': 25,
        'dependencies': ['json', 'csv', 'yaml', 'pathlib'],
    },
    'cli': {
        'patterns': [r'command\s*line', r'cli\s*tool', r'argparse', r'click', r'typer'],
        'base_complexity': 30,
        'dependencies': ['argparse', 'click', 'typer'],
    },
    'async': {
        'patterns': [r'async', r'await', r'asyncio', r'concurrent', r'parallel'],
        'base_complexity': 50,
        'dependencies': ['asyncio', 'aiohttp', 'aiofiles'],
    },
    'scraper': {
        'patterns': [r'scrape', r'crawl', r'beautifulsoup', r'selenium', r'playwright'],
        'base_complexity': 45,
        'dependencies': ['beautifulsoup4', 'selenium', 'playwright', 'scrapy'],
    },
    'data_processing': {
        'patterns': [r'data\s*process', r'transform', r'etl', r'pipeline', r'pandas'],
        'base_complexity': 40,
        'dependencies': ['pandas', 'numpy', 'polars'],
    },
    'testing': {
        'patterns': [r'unit\s*test', r'pytest', r'test\s*case', r'mock', r'fixture'],
        'base_complexity': 35,
        'dependencies': ['pytest', 'unittest', 'mock'],
    },
}

# Dependency graph for task types
DEPENDENCY_GRAPH = {
    'flask_api': ['http_client', 'database', 'auth', 'file_io'],
    'django_app': ['database', 'auth', 'web_api', 'file_io'],
    'fastapi_service': ['async', 'database', 'auth', 'web_api'],
    'cli_tool': ['file_io', 'cli'],
    'scraper': ['http_client', 'file_io', 'data_processing'],
    'microservice': ['web_api', 'database', 'async', 'auth'],
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class ComplexityLevel(Enum):
    """Task complexity levels."""
    TRIVIAL = "trivial"         # 0-20: Hello world, basic print
    SIMPLE = "simple"           # 21-40: Single function, basic file I/O
    MODERATE = "moderate"       # 41-60: Multiple functions, basic API
    COMPLEX = "complex"         # 61-80: Full module, database, auth
    VERY_COMPLEX = "very_complex"  # 81-100: Distributed, ML, real-time


@dataclass
class TaskAnalysis:
    """Complete analysis of a task."""
    raw_task: str
    complexity_score: int               # 0-100
    complexity_level: ComplexityLevel
    detected_types: List[str]           # Detected task types
    keywords_found: Dict[str, int]      # Keyword -> modifier
    inferred_dependencies: List[str]    # Likely required packages
    estimated_briqs: int                # Estimated number of briqs
    recommended_tier: int               # 0=templates, 1=search, 2=evolution
    confidence: float                   # 0-1 confidence in analysis
    suggestions: List[str]              # Improvement suggestions


# ═══════════════════════════════════════════════════════════════════════════════
# SMART QOMPUTATOR
# ═══════════════════════════════════════════════════════════════════════════════

class SmartQomputator:
    """
    Advanced task complexity analyzer for mindstaQ.
    
    Features:
    - Keyword-based complexity scoring
    - Task type detection via patterns
    - Dependency inference
    - Briq estimation
    - Tier recommendation
    
    Usage:
        qomputator = SmartQomputator()
        
        analysis = qomputator.analyze("Create an async HTTP client with retry logic")
        print(f"Complexity: {analysis.complexity_score}")
        print(f"Recommended tier: {analysis.recommended_tier}")
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        
        # Tier thresholds
        self.tier_thresholds = {
            0: 35,   # Tier 0 (templates) for scores <= 35
            1: 65,   # Tier 1 (search) for scores 36-65
            2: 100,  # Tier 2 (evolution) for scores > 65
        }
    
    def _extract_keywords(self, task: str) -> Dict[str, int]:
        """Extract complexity keywords from task."""
        task_lower = task.lower()
        found = {}
        
        # Sort by length descending to match longer phrases first
        sorted_keywords = sorted(COMPLEXITY_KEYWORDS.keys(), key=len, reverse=True)
        
        for keyword in sorted_keywords:
            if keyword in task_lower:
                found[keyword] = COMPLEXITY_KEYWORDS[keyword]
                # Avoid double-counting (e.g., "oauth" in "oauth2")
                task_lower = task_lower.replace(keyword, ' ' * len(keyword))
        
        return found
    
    def _detect_task_types(self, task: str) -> List[Tuple[str, float]]:
        """Detect task types with confidence scores."""
        task_lower = task.lower()
        detected = []
        
        for type_name, type_info in TASK_TYPE_PATTERNS.items():
            confidence = 0.0
            matches = 0
            
            for pattern in type_info['patterns']:
                if re.search(pattern, task_lower):
                    matches += 1
            
            if matches > 0:
                # Confidence based on number of pattern matches
                confidence = min(1.0, matches * 0.4)
                detected.append((type_name, confidence))
        
        # Sort by confidence
        detected.sort(key=lambda x: -x[1])
        return detected
    
    def _infer_dependencies(self, task_types: List[str]) -> List[str]:
        """Infer likely dependencies from task types."""
        deps = set()
        
        for task_type in task_types:
            if task_type in TASK_TYPE_PATTERNS:
                deps.update(TASK_TYPE_PATTERNS[task_type].get('dependencies', []))
            
            # Check dependency graph for composite types
            for composite, components in DEPENDENCY_GRAPH.items():
                if task_type in components:
                    for comp in components:
                        if comp in TASK_TYPE_PATTERNS:
                            deps.update(TASK_TYPE_PATTERNS[comp].get('dependencies', []))
        
        return sorted(deps)
    
    def _calculate_base_score(self, task_types: List[Tuple[str, float]]) -> int:
        """Calculate base complexity from task types."""
        if not task_types:
            return 30  # Default moderate score
        
        # Weighted average based on confidence
        total_weight = 0
        weighted_score = 0
        
        for type_name, confidence in task_types:
            if type_name in TASK_TYPE_PATTERNS:
                base = TASK_TYPE_PATTERNS[type_name]['base_complexity']
                weighted_score += base * confidence
                total_weight += confidence
        
        if total_weight > 0:
            return int(weighted_score / total_weight)
        return 30
    
    def _estimate_briqs(self, complexity_score: int, task_types: List[str]) -> int:
        """Estimate number of briqs needed."""
        # Base on complexity
        if complexity_score <= 20:
            briqs = 1
        elif complexity_score <= 40:
            briqs = 2
        elif complexity_score <= 60:
            briqs = 3
        elif complexity_score <= 80:
            briqs = 5
        else:
            briqs = 8
        
        # Add for multi-type tasks
        briqs += max(0, len(task_types) - 1)
        
        return min(15, briqs)  # Cap at 15
    
    def _recommend_tier(self, complexity_score: int, task_types: List[str]) -> int:
        """Recommend generation tier."""
        if complexity_score <= self.tier_thresholds[0]:
            return 0  # Templates
        elif complexity_score <= self.tier_thresholds[1]:
            return 1  # Search
        else:
            return 2  # Evolution
    
    def _generate_suggestions(self, task: str, analysis_data: dict) -> List[str]:
        """Generate improvement suggestions."""
        suggestions = []
        
        # Low confidence suggestions
        if analysis_data['confidence'] < 0.5:
            suggestions.append("Task description is vague. Consider adding specific requirements.")
        
        # High complexity suggestions
        if analysis_data['score'] > 70:
            suggestions.append("Consider breaking this into smaller sub-tasks.")
        
        # Missing context suggestions
        task_lower = task.lower()
        if 'api' in task_lower and 'endpoint' not in task_lower:
            suggestions.append("Specify API endpoints or routes needed.")
        
        if 'database' in task_lower and not any(
            db in task_lower for db in ['postgres', 'mysql', 'sqlite', 'mongo']
        ):
            suggestions.append("Specify which database type to use.")
        
        if 'auth' in task_lower and 'jwt' not in task_lower and 'oauth' not in task_lower:
            suggestions.append("Specify authentication method (JWT, OAuth, session, etc.).")
        
        return suggestions
    
    def _determine_complexity_level(self, score: int) -> ComplexityLevel:
        """Determine complexity level from score."""
        if score <= 20:
            return ComplexityLevel.TRIVIAL
        elif score <= 40:
            return ComplexityLevel.SIMPLE
        elif score <= 60:
            return ComplexityLevel.MODERATE
        elif score <= 80:
            return ComplexityLevel.COMPLEX
        else:
            return ComplexityLevel.VERY_COMPLEX
    
    def analyze(self, task: str) -> TaskAnalysis:
        """
        Perform complete task analysis.
        
        Args:
            task: Task description string
        
        Returns:
            TaskAnalysis with all computed metrics
        """
        # Extract keywords and their modifiers
        keywords_found = self._extract_keywords(task)
        
        # Detect task types
        task_types_with_conf = self._detect_task_types(task)
        task_types = [t[0] for t in task_types_with_conf]
        
        # Calculate confidence
        if task_types_with_conf:
            confidence = sum(c for _, c in task_types_with_conf) / len(task_types_with_conf)
        else:
            confidence = 0.3  # Low confidence for unknown tasks
        
        # Boost confidence if keywords found
        if keywords_found:
            confidence = min(1.0, confidence + 0.2)
        
        # Calculate base score from task types
        base_score = self._calculate_base_score(task_types_with_conf)
        
        # Apply keyword modifiers
        modifier_sum = sum(keywords_found.values())
        
        # Calculate final score (capped 0-100)
        final_score = max(0, min(100, base_score + modifier_sum))
        
        # Infer dependencies
        dependencies = self._infer_dependencies(task_types)
        
        # Estimate briqs
        estimated_briqs = self._estimate_briqs(final_score, task_types)
        
        # Recommend tier
        recommended_tier = self._recommend_tier(final_score, task_types)
        
        # Generate suggestions
        analysis_data = {'score': final_score, 'confidence': confidence}
        suggestions = self._generate_suggestions(task, analysis_data)
        
        return TaskAnalysis(
            raw_task=task,
            complexity_score=final_score,
            complexity_level=self._determine_complexity_level(final_score),
            detected_types=task_types,
            keywords_found=keywords_found,
            inferred_dependencies=dependencies,
            estimated_briqs=estimated_briqs,
            recommended_tier=recommended_tier,
            confidence=confidence,
            suggestions=suggestions
        )
    
    def quick_score(self, task: str) -> int:
        """Quick complexity score without full analysis."""
        keywords = self._extract_keywords(task)
        task_types = self._detect_task_types(task)
        
        base = self._calculate_base_score(task_types)
        modifier = sum(keywords.values())
        
        return max(0, min(100, base + modifier))
    
    def should_use_mindstaq(self, task: str) -> Tuple[bool, str]:
        """
        Determine if mindstaQ can handle this task.
        
        Returns:
            (can_handle, reason)
        """
        analysis = self.analyze(task)
        
        # mindstaQ works best for well-defined, pattern-matchable tasks
        if analysis.complexity_level == ComplexityLevel.TRIVIAL:
            return True, "Simple task - templates should handle this"
        
        if analysis.complexity_level == ComplexityLevel.SIMPLE:
            return True, "Basic task - search + templates"
        
        if analysis.complexity_level == ComplexityLevel.MODERATE:
            if analysis.confidence >= 0.5:
                return True, "Moderate task with good pattern match"
            else:
                return True, "Moderate task - may need multiple iterations"
        
        if analysis.complexity_level == ComplexityLevel.COMPLEX:
            if len(analysis.detected_types) <= 2:
                return True, "Complex but focused task - evolution tier"
            else:
                return True, "Complex multi-type task - break into briqs"
        
        # Very complex
        return True, "Very complex - will use all tiers + multiple briqs"


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print(f"Smart Qomputator v{__version__}")
    print("=" * 60)
    
    qomputator = SmartQomputator()
    
    # Test tasks
    test_tasks = [
        "print hello world",
        "read a json file",
        "create http client with retry",
        "build REST API with JWT authentication",
        "create async web scraper with database storage",
        "implement distributed machine learning pipeline",
    ]
    
    print("\n[1] Task Analysis:")
    print("-" * 60)
    
    for task in test_tasks:
        analysis = qomputator.analyze(task)
        
        print(f"\nTask: '{task}'")
        print(f"  Score: {analysis.complexity_score}/100 ({analysis.complexity_level.value})")
        print(f"  Types: {analysis.detected_types}")
        print(f"  Keywords: {list(analysis.keywords_found.keys())}")
        print(f"  Dependencies: {analysis.inferred_dependencies[:5]}")
        print(f"  Est. Briqs: {analysis.estimated_briqs}")
        print(f"  Tier: {analysis.recommended_tier}")
        print(f"  Confidence: {analysis.confidence:.2f}")
        if analysis.suggestions:
            print(f"  Suggestions: {analysis.suggestions[0]}")
    
    print("\n" + "=" * 60)
    print("✅ Smart Qomputator working!")
