#!/usr/bin/env python3
"""
Qomputator: Complexity Scoring Agent (0-666 Scale - The Beast Number)
Part of mindstaQ - Routes tasks to appropriate tier based on complexity
"""

import re
from typing import Optional, Set, List
from worqer.mindstaq import CrystallizedIntent, ComplexityScore, Tier


class Qomputator:
    """Calculates task complexity on a 0-666 scale."""
    
    # Conditional logic keywords - add complexity
    CONDITIONAL_KEYWORDS: Set[str] = {
        'if', 'when', 'unless', 'except', 'while', 'until', 'whether', 
        'case', 'else', 'elif', 'otherwise', 'conditional', 'depending'
    }
    
    # Negation keywords - add complexity  
    NEGATION_KEYWORDS: Set[str] = {
        'not', 'never', 'without', 'no', 'none', 'neither', 'nor', 
        "don't", 'cannot', 'avoid', 'exclude', 'prevent', 'disable'
    }
    
    # Optimization keywords - reasoning complexity (use prefixes for substring match)
    OPTIMIZATION_KEYWORDS: Set[str] = {
        'optim', 'efficien', 'perform', 'fast', 'speed', 'cache', 
        'memo', 'lazy', 'batch', 'bulk', 'parallel', 'concurrent'
    }
    
    # Design/Architecture keywords - high reasoning
    DESIGN_KEYWORDS: Set[str] = {
        'architect', 'design', 'pattern', 'structure', 'system', 'framework',
        'abstract', 'interface', 'factory', 'singleton', 'strateg', 'observer',
        'decorator', 'adapter', 'facade', 'composite', 'bridge', 'proxy',
        'cqrs', 'event-driven', 'microservice', 'monolith', 'modular', 'plugin',
        'distribut', 'scalabl', 'resilien', 'fault-tolerant', 'eventual'
    }
    
    # Concurrency keywords - reasoning complexity
    CONCURRENCY_KEYWORDS: Set[str] = {
        'async', 'await', 'parallel', 'concurrent', 'thread', 'worker',
        'process', 'pool', 'queue', 'lock', 'mutex', 'semaphore',
        'race', 'deadlock', 'atomic', 'synchron', 'celery', 'background'
    }
    
    # Security keywords - high reasoning (use prefixes for substring match)
    SECURITY_KEYWORDS: Set[str] = {
        'secur', 'encrypt', 'auth', 'password', 'token', 'jwt', 'oauth',
        'hash', 'salt', 'permission', 'sanitiz', 'validat', 'credential',
        'session', 'cookie', 'csrf', 'xss', 'injection', 'firewall',
        'rate-limit', 'throttl', 'captcha', 'mfa', '2fa', 'rbac', 'acl'
    }
    
    # Known tech entities (case-insensitive patterns)
    TECH_KEYWORDS: Set[str] = {
        # API & Web
        'api', 'rest', 'graphql', 'grpc', 'websocket', 'http', 'https',
        'endpoint', 'route', 'handler', 'middleware', 'request', 'response',
        # Database
        'crud', 'database', 'sql', 'nosql', 'mongodb', 'postgres', 'mysql',
        'redis', 'elasticsearch', 'kafka', 'rabbitmq', 'queue', 'message',
        # Infrastructure
        'docker', 'kubernetes', 'k8s', 'container', 'microservice', 'service',
        # Auth
        'jwt', 'oauth', 'oauth2', 'openid', 'saml', 'ldap', 'sso',
        'authenticat', 'authoriz', 'credential', 'session', 'token',
        # Data formats
        'json', 'yaml', 'xml', 'csv', 'protobuf', 'avro', 'schema',
        # Testing
        'pytest', 'unittest', 'mock', 'fixture', 'coverage', 'test',
        # Frameworks
        'flask', 'fastapi', 'django', 'express', 'spring', 'rails',
        # Cloud
        'aws', 's3', 'lambda', 'ec2', 'rds', 'dynamodb', 'sqs', 'sns',
        'gcp', 'azure', 'cloudflare', 'nginx', 'apache', 'load', 'balancer',
        # DevOps
        'git', 'ci', 'cd', 'pipeline', 'deploy', 'rollback', 'helm', 'terraform',
        # Observability
        'logging', 'monitoring', 'metric', 'alert', 'trace', 'observ',
        # Integrations
        'stripe', 'paypal', 'twilio', 'sendgrid', 'mailgun', 'webhook',
        # Pagination/filtering
        'pagination', 'paginate', 'filter', 'sort', 'search', 'cursor',
        # Architecture patterns
        'event', 'driven', 'architect', 'layer', 'tier', 'component',
        'consistency', 'transaction', 'saga', 'repository', 'domain',
        'entity', 'aggregate', 'bounded', 'context', 'hexagonal', 'clean',
        # Caching
        'cache', 'memcache', 'varnish', 'cdn', 'ttl', 'invalidat',
        # Rate limiting
        'rate', 'limit', 'throttle', 'quota', 'bucket',
        # Concurrency (also in tech)
        'async', 'await', 'worker', 'pool', 'task', 'job', 'celery',
        'thread', 'process', 'parallel', 'concurrent', 'background',
        # Pub/Sub & Events
        'pub', 'sub', 'publish', 'subscribe', 'emit', 'listen', 'broadcast',
        'eventbus', 'eventdriven', 'cqrs', 'eventsourc',
    }
    
    # High-complexity action verbs
    COMPLEX_VERBS: Set[str] = {
        'implement', 'design', 'architect', 'build', 'create', 'develop',
        'integrat', 'migrat', 'refactor', 'optimiz', 'scale', 'deploy',
        'orchestrat', 'coordinat', 'synchroniz', 'distribut'
    }
    
    # Regex patterns for tech entities (original case)
    TECH_ENTITY_PATTERNS: List[str] = [
        r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # CamelCase: UserService
        r'\b[A-Z]{2,}\b',  # Acronyms: API, JWT, REST, CRUD
        r'\b[a-z]+_[a-z_]+\b',  # snake_case: user_service
        r'`[^`]+`',  # Backtick quoted: `function_name`
    ]
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        qomputator_cfg = self.config.get('qomputator', {})
        thresholds = qomputator_cfg.get('thresholds', {})
        self.tier_0_max = thresholds.get('tier_0_max', 85)
        self.tier_1_max = thresholds.get('tier_1_max', 400)
        
        weights = qomputator_cfg.get('weights', {})
        lexical = weights.get('lexical', {})
        self.word_count_multiplier = lexical.get('word_count_multiplier', 3)
        self.max_word_score = lexical.get('max_word_score', 60)
        
        technical = weights.get('technical', {})
        self.entity_weight = technical.get('entity_weight', 25)  # Increased from 20
        self.multi_entity_bonus = technical.get('multi_entity_bonus', 20)  # Increased from 15
        
        reasoning = weights.get('reasoning', {})
        self.optimization_weight = reasoning.get('optimization', 35)
        self.design_weight = reasoning.get('design', 50)
        self.concurrency_weight = reasoning.get('concurrency', 30)
        self.security_weight = reasoning.get('security', 40)
    
    def _substring_match_count(self, words: List[str], keyword_set: Set[str]) -> int:
        """Count words that contain any keyword (substring matching)."""
        count = 0
        for word in words:
            for keyword in keyword_set:
                if keyword in word:
                    count += 1
                    break
        return count
    
    def score(self, text: str, intent: Optional[CrystallizedIntent] = None) -> ComplexityScore:
        result = ComplexityScore()
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        word_count = len(words)
        
        # ═══════════════════════════════════════════════════════════════════
        # LEXICAL SCORE (0-100): Word count, conditionals, negations
        # ═══════════════════════════════════════════════════════════════════
        lex_score = min(self.max_word_score, word_count * self.word_count_multiplier)
        lex_score += min(30, self._substring_match_count(words, self.CONDITIONAL_KEYWORDS) * 8)
        lex_score += min(20, self._substring_match_count(words, self.NEGATION_KEYWORDS) * 6)
        
        # Boost for complex action verbs
        lex_score += min(20, self._substring_match_count(words, self.COMPLEX_VERBS) * 10)
        result.lexical = min(100, lex_score)
        
        # ═══════════════════════════════════════════════════════════════════
        # TECHNICAL SCORE (0-150): Tech entities, libraries, patterns
        # ═══════════════════════════════════════════════════════════════════
        # Count tech keywords (substring match)
        tech_keyword_count = self._substring_match_count(words, self.TECH_KEYWORDS)
        tech_score = tech_keyword_count * self.entity_weight
        
        # Find CamelCase and other patterns in original text
        entities = set()
        for pattern in self.TECH_ENTITY_PATTERNS:
            matches = re.findall(pattern, text)
            entities.update(m for m in matches if len(m) > 2)
        
        tech_score += len(entities) * 10
        
        # Multi-entity bonus
        total_entities = tech_keyword_count + len(entities)
        if total_entities > 3:
            tech_score += (total_entities - 3) * self.multi_entity_bonus
        
        # Intent-based library bonus
        if intent and intent.libraries:
            tech_score += len(intent.libraries) * 15
        
        result.technical = min(150, tech_score)
        
        # ═══════════════════════════════════════════════════════════════════
        # SEMANTIC SCORE (0-150): Task complexity, requirements, specificity
        # ═══════════════════════════════════════════════════════════════════
        # Base score from text length
        sem_score = min(40, len(text) // 15)
        
        # Requirement language patterns
        requirement_patterns = [
            r'\bmust\b', r'\bshould\b', r'\brequire', r'\bensure\b', 
            r'\bexactly\b', r'\bspecific', r'\bcustom\b', r'\bcomprehensive\b',
            r'\bincluding\b', r'\bwith\b.*\band\b', r'\bsupport\b'
        ]
        for pattern in requirement_patterns:
            if re.search(pattern, text_lower):
                sem_score += 12
        
        # Multiple clauses (commas, "and", lists)
        comma_count = text.count(',')
        and_count = text_lower.count(' and ')
        sem_score += min(30, (comma_count + and_count) * 8)
        
        # Code blocks indicate specific requirements
        if '```' in text:
            sem_score += 25
        
        # Intent-based bonuses
        if intent:
            if intent.domain and intent.domain not in ['general', '']:
                sem_score += 20
            if len(intent.keywords) > 10:
                sem_score += 30
            elif len(intent.keywords) > 5:
                sem_score += 15
        
        result.semantic = min(150, sem_score)
        
        # ═══════════════════════════════════════════════════════════════════
        # REASONING SCORE (0-116): Optimization, design, concurrency, security
        # ═══════════════════════════════════════════════════════════════════
        reason_score = 0
        
        opt_count = self._substring_match_count(words, self.OPTIMIZATION_KEYWORDS)
        reason_score += min(self.optimization_weight, opt_count * 12)
        
        design_count = self._substring_match_count(words, self.DESIGN_KEYWORDS)
        reason_score += min(self.design_weight, design_count * 15)
        
        concur_count = self._substring_match_count(words, self.CONCURRENCY_KEYWORDS)
        reason_score += min(self.concurrency_weight, concur_count * 12)
        
        sec_count = self._substring_match_count(words, self.SECURITY_KEYWORDS)
        reason_score += min(self.security_weight, sec_count * 12)
        
        result.reasoning = min(116, reason_score)
        
        # ═══════════════════════════════════════════════════════════════════
        # TOTAL & TIER ROUTING
        # ═══════════════════════════════════════════════════════════════════
        result.total = min(666, result.lexical + result.technical + result.semantic + result.reasoning)
        
        if result.total <= self.tier_0_max:
            result.tier = Tier.QRYSTALLIZER
        elif result.total <= self.tier_1_max:
            result.tier = Tier.SQAVANGER
        else:
            result.tier = Tier.QOMBINATOR
        
        return result
    
    def explain(self, text: str) -> str:
        """Return human-readable score breakdown."""
        score = self.score(text)
        return f"""Qomputator Analysis
═══════════════════════════════════════
Score: {score.total}/666 -> Tier: {score.tier.name}
├── Lexical:   {score.lexical}/100
├── Technical: {score.technical}/150
├── Semantic:  {score.semantic}/150
└── Reasoning: {score.reasoning}/116
═══════════════════════════════════════"""


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qomputator - Complexity Scorer')
    parser.add_argument('--text', '-t', type=str, help='Text to score')
    parser.add_argument('--explain', '-e', action='store_true', help='Show detailed breakdown')
    args = parser.parse_args()
    
    if args.text:
        qomp = Qomputator()
        if args.explain:
            print(qomp.explain(args.text))
        else:
            score = qomp.score(args.text)
            print(f"{score.total}/666 -> {score.tier.name}")
