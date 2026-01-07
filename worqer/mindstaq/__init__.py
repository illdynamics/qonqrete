#!/usr/bin/env python3
"""
mindstaQ: Zero-Cost Local Code Generation Engine
v1.8.8-stable - SQAVENGER ATTRIBUTE FIX

Agent Pipeline:
  USER BRIQ → Qomputator (score) → Tier Router
                                   ├─ Tier 0: Qrystallizer (templates + PatternDB)
                                   ├─ Tier 1: sQavanger (Qrawler + DeepQrawler + Semantic)
                                   └─ Tier 2: Qombinator (Frankenstein + Breeder)
                                           ↓
                                   Qoncentrator (AST grafting + Normalizer)
                                           ↓
                            ┌──────────────────────────────┐
                            │  EVOLUTION LOOP (v1.7.0)     │
                            │  ┌────────────────────────┐  │
                            │  │   Qalibrator           │  │ ← AST Mutations
                            │  │       ↓                │  │
                            │  │   Qualifier            │  │ ← Quality Check
                            │  │       ↓                │  │
                            │  │   Fitness++ ? ─────────┼──┼─→ PASS to InspeQtor
                            │  │       ↓                │  │
                            │  │   LOOP until qualified │  │
                            │  └────────────────────────┘  │
                            └──────────────────────────────┘
                                           ↓
                                    InspeQtor (final check)
                                           ↓
                            ┌──────────────────────────────┐
                            │  TIMEWALQER (v1.7.1)         │
                            │                              │
                            │  SUCCESS: Drop Timestone     │
                            │  FAIL: Auto-Revert           │
                            │                              │
                            │  cheqpoint.d/0-cyQle/        │
                            │  cheqpoint.d/1-cyQle/        │
                            │  cheqpoint.d/N-cyQle/        │
                            └──────────────────────────────┘
                                           ↓
                                        OUTPUT

v1.8.4-stable Features:
  - SMART VALIDATION: No more aggressive blocking! Only reject obvious URLs
  - HUMAN-READABLE REPORTS: Issues grouped by file, deduplicated suggestions
  - Minimal blocking: response.json, request.js are now valid filenames!
  - Better reqap format with severity tables and actionable suggestions

v1.8.3-stable Features:
  - Multi-language adapters: Rust, Go, Shell, Python
  - New templates: rust_main, rust_lib, rust_cli, go_main, go_lib, go_http
  - Expanded Templates: C2, database, security, docker provisioning
  - Language Detection: Proper bash/shell language tags in output

v1.7.1 Features:
  - TimeWalQer: Git-less snapshot/revert system for cyQle time travel
  - cheqpoint.d/: State serialization per cyQle (no Git needed!)
  - Timestone: Snapshot after successful InspeQtor pass
  - Auto-revert: Automatic rollback on hard failures
  - CLI: ./qonqrete.sh time -c N for time travel

v1.7.0 Features:
  - Qalibrator: AST Mutation Engine for genetic code evolution
  - Qualifier: Quality Assessment Agent with configurable criteria
  - Evolution Loop: Qalibrator ⟷ Qualifier iteration until fitness threshold
  - quality_qriteria.yaml: Configurable quality dimensions and thresholds

v1.6.3 Bug Fixes:
  - LocalInstruQtor: Fixed garbage briq creation at low sensitivity
  - Qompressor/Qontextor: Added system package filtering
  - mindstaQ: Fixed filename inference pollution

Local Agents:
  - LocalTasqLeveler: Zero-cost task enhancement
  - LocalInstruQtor: Zero-cost task splitting
  - LocalInspeQtor: Zero-cost code review
  - Qalibrator: Zero-cost AST mutation engine (v1.7.0)
  - Qualifier: Zero-cost quality assessment (v1.7.0, fixed v1.8.0)
  - TimeWalQer: Zero-cost time travel system (v1.7.1)

Cost: $0.00 FOREVER - ZERO LLM REQUIRED!
"""

import sys
import os
import re
import yaml
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

__version__ = '1.7.2-stable'
__all__ = [
    # Core Engine
    'MindstaQEngine', 
    'ActionType', 'TargetType', 'Tier', 
    'CrystallizedIntent', 'ComplexityScore', 'GenerationResult',
    # Local Agents
    'LocalInstruQtor',    # v1.1.2 - zero-cost task splitting
    'LocalInspeQtor',     # v1.1.2 - zero-cost code review
    'LocalTasqLeveler',   # v1.2.0 - zero-cost task enhancement
    # v1.7.0 - Evolution Loop Agents
    'Qalibrator',         # v1.7.0 - AST mutation engine
    'Qualifier',          # v1.7.0 - quality assessment agent
    # v1.7.1 - Time Travel System
    'TimeWalQer',         # v1.7.1 - git-less snapshot/revert
    # v1.5.0 Components
    'PatternDatabase',    # v1.5.0 - 200+ code patterns
    'WonqIndex',          # v1.5.0 - local memory bank
    'FrankensteinCombinator',  # v1.5.0 - smart snippet merger
    'SemanticMatcher',    # v1.5.0 - AST-based matching
    'TemplateBreeder',    # v1.5.0 - genetic evolution
    'CodeNormalizer',     # v1.5.0 - code style normalization
    'SmartQomputator',    # v1.5.0 - advanced task analysis
    'ParallelHarvester',  # v1.5.0 - parallel code search
    # v1.6.0 Components
    'DecisionTableCompiler',      # v1.6.0 - decision table to code
    'TypeDirectedSynthesizer',    # v1.6.0 - A* glue code synthesis
    'AllowlistSecurityGenerator', # v1.6.0 - secure code primitives
]

# Lazy imports for all components
def __getattr__(name):
    if name == 'LocalInstruQtor':
        from worqer.mindstaq.local_instruqtor import LocalInstruQtor
        return LocalInstruQtor
    if name == 'LocalInspeQtor':
        from worqer.mindstaq.local_inspeqtor import LocalInspeQtor
        return LocalInspeQtor
    if name == 'LocalTasqLeveler':
        from worqer.mindstaq.local_tasqleveler import LocalTasqLeveler
        return LocalTasqLeveler
    # v1.7.0 - Evolution Loop Agents
    if name == 'Qalibrator':
        from worqer.mindstaq.qalibrator import Qalibrator
        return Qalibrator
    if name == 'Qualifier':
        from worqer.mindstaq.qualifier import Qualifier
        return Qualifier
    # v1.7.1 - Time Travel System
    if name == 'TimeWalQer':
        from worqer.mindstaq.timewalqer import TimeWalQer
        return TimeWalQer
    # v1.5.0 NEW
    if name == 'PatternDatabase':
        from worqer.mindstaq.pattern_db import PatternDatabase
        return PatternDatabase
    if name == 'WonqIndex':
        from worqer.mindstaq.wonq_index import WonqIndex
        return WonqIndex
    if name == 'FrankensteinCombinator':
        from worqer.mindstaq.frankenstein import FrankensteinCombinator
        return FrankensteinCombinator
    if name == 'SemanticMatcher':
        from worqer.mindstaq.semantic_matcher import SemanticMatcher
        return SemanticMatcher
    if name == 'TemplateBreeder':
        from worqer.mindstaq.template_breeder import TemplateBreeder
        return TemplateBreeder
    if name == 'CodeNormalizer':
        from worqer.mindstaq.code_normalizer import CodeNormalizer
        return CodeNormalizer
    if name == 'SmartQomputator':
        from worqer.mindstaq.smart_qomputator import SmartQomputator
        return SmartQomputator
    if name == 'ParallelHarvester':
        from worqer.mindstaq.parallel_harvester import ParallelHarvester
        return ParallelHarvester
    # v1.6.0 NEW
    if name == 'DecisionTableCompiler':
        from worqer.mindstaq.decision_table import DecisionTableCompiler
        return DecisionTableCompiler
    if name == 'TypeDirectedSynthesizer':
        from worqer.mindstaq.type_synthesis import TypeDirectedSynthesizer
        return TypeDirectedSynthesizer
    if name == 'AllowlistSecurityGenerator':
        from worqer.mindstaq.allowlist_security import AllowlistSecurityGenerator
        return AllowlistSecurityGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ActionType(Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    REFACTOR = "refactor"
    TEST = "test"
    DOCUMENT = "document"
    CONFIGURE = "configure"
    UNKNOWN = "unknown"


class TargetType(Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    FILE = "file"
    MODULE = "module"
    CONFIG = "config"
    TEST = "test"
    UNKNOWN = "unknown"


class Tier(Enum):
    QRYSTALLIZER = 0
    SQAVANGER = 1
    QOMBINATOR = 2


@dataclass
class CrystallizedIntent:
    action: ActionType = ActionType.UNKNOWN
    target_type: TargetType = TargetType.UNKNOWN
    target_name: str = ""
    target_file: str = ""
    domain: str = ""
    libraries: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ComplexityScore:
    lexical: int = 0
    technical: int = 0
    semantic: int = 0
    reasoning: int = 0
    total: int = 0
    tier: Tier = Tier.QRYSTALLIZER


@dataclass
class GenerationResult:
    success: bool = False
    code: str = ""
    files_written: List[str] = field(default_factory=list)
    tier_used: Tier = Tier.QRYSTALLIZER
    complexity_score: int = 0
    iterations: int = 0
    error: Optional[str] = None
    audit_log: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    fallback_used: bool = False
    
    @property
    def tier(self) -> str:
        return self.tier_used.name


class MindstaQEngine:
    """Main mindstaQ orchestrator coordinating all agents."""
    
    _instance = None
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.mindstaq_config = self.config.get('mindstaq', {})
        self._qomputator = None
        self._qrystallizer = None
        self._sqavenger = None
        self._qombinator = None
        self._qoncentrator = None
        self._qonscience = None
        
        qomputator_cfg = self.mindstaq_config.get('qomputator', {})
        thresholds = qomputator_cfg.get('thresholds', {})
        self.tier_0_max = thresholds.get('tier_0_max', 100)
        self.tier_1_max = thresholds.get('tier_1_max', 400)
        self.audit_log = []
    
    @classmethod
    def get_instance(cls, config: dict = None) -> 'MindstaQEngine':
        if cls._instance is None:
            if config is None:
                config = cls._load_default_config()
            cls._instance = cls(config)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        cls._instance = None
    
    @staticmethod
    def _load_default_config() -> dict:
        config_paths = [Path('config.yaml'), Path('worqspace/config.yaml'),
                       Path(os.environ.get('QONQ_WORKSPACE', '.')) / 'config.yaml']
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        return yaml.safe_load(f) or {}
                except: pass
        return {}
    
    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.audit_log.append(f"[{timestamp}] {message}")
        sys.stderr.write(f"[mindstaQ] {message}\n")
        sys.stderr.flush()
    
    @property
    def qomputator(self):
        if self._qomputator is None:
            from worqer.qomputator import Qomputator
            self._qomputator = Qomputator(self.mindstaq_config)
        return self._qomputator
    
    @property
    def qrystallizer(self):
        if self._qrystallizer is None:
            from worqer.qrystallizer import Qrystallizer
            self._qrystallizer = Qrystallizer(self.mindstaq_config)
        return self._qrystallizer
    
    @property
    def sqavenger(self):
        if self._sqavenger is None:
            from worqer.mindstaq.sqavenger import SQavenger
            self._sqavenger = SQavenger(self.mindstaq_config)
        return self._sqavenger
    
    @property
    def qombinator(self):
        if self._qombinator is None:
            from worqer.qombinator import Qombinator
            self._qombinator = Qombinator(self.mindstaq_config)
        return self._qombinator
    
    @property
    def qoncentrator(self):
        if self._qoncentrator is None:
            from worqer.qoncentrator import Qoncentrator
            self._qoncentrator = Qoncentrator(self.mindstaq_config)
        return self._qoncentrator
    
    @property
    def qonscience(self):
        if self._qonscience is None:
            from worqer.qonscience import Qonscience
            self._qonscience = Qonscience(self.mindstaq_config)
        return self._qonscience
    
    def generate(self, prompt: str, context_files: List[str] = None, qodeyard_path=None) -> GenerationResult:
        import time as _time
        start_time = _time.time()
        self.audit_log = []
        result = GenerationResult()
        
        self.log("=" * 60)
        self.log("mindstaQ Code Generation Pipeline v1.6.2")
        self.log("=" * 60)
        
        try:
            self.log("STEP 1: Parsing task intent...")
            intent = self._parse_intent(prompt)
            self.log(f"  Action: {intent.action.value}")
            self.log(f"  Target: {intent.target_type.value} -> {intent.target_name or 'auto'}")
            
            self.log("STEP 2: Qomputator scoring complexity (0-666)...")
            score = self.qomputator.score(prompt, intent)
            result.complexity_score = score.total
            result.tier_used = score.tier
            self.log(f"  TOTAL: {score.total}/666 -> {score.tier.name}")
            
            self.log(f"STEP 3: Routing to {score.tier.name} tier agent...")
            code = None
            
            if score.tier == Tier.QRYSTALLIZER:
                code = self.qrystallizer.generate(intent, prompt, context_files)
            elif score.tier == Tier.SQAVANGER:
                # v1.8.0 FIX: Use generate() which has correct interface for CrystallizedIntent
                code = self.sqavenger.generate(intent)
                if not code:
                    self.log("  -> sQavanger returned None, trying Qombinator...")
                    code = self.qombinator.synthesize(intent, prompt, context_files)
                if not code:
                    self.log("  -> Qombinator returned None, falling back to Qrystallizer...")
                    code = self.qrystallizer.generate(intent, prompt, context_files)
            else:  # Tier.QOMBINATOR
                code = self.qombinator.synthesize(intent, prompt, context_files)
                if not code:
                    self.log("  -> Qombinator returned None, trying sQavanger...")
                    # v1.8.0 FIX: Use generate() which has correct interface for CrystallizedIntent
                    code = self.sqavenger.generate(intent)
                if not code:
                    self.log("  -> sQavanger returned None, falling back to Qrystallizer...")
                    code = self.qrystallizer.generate(intent, prompt, context_files)
            
            if not code:
                raise ValueError("No code generated from tier agent")
            
            self.log("STEP 4: Qoncentrator applying AST processing...")
            code = self.qoncentrator.process(code, intent, context_files)
            
            self.log("STEP 5: Qonscience running verification...")
            qonscience_cfg = self.mindstaq_config.get('qonscience', {})
            max_iterations = qonscience_cfg.get('max_iterations', 5)
            
            for iteration in range(max_iterations):
                result.iterations = iteration + 1
                verification_result = self.qonscience.verify(code, intent)
                if verification_result['passed']:
                    self.log(f"  OK Verification passed on iteration {iteration + 1}")
                    break
                else:
                    self.log(f"  X Iteration {iteration + 1}: {len(verification_result.get('errors', []))} issues")
                    auto_fix_cfg = qonscience_cfg.get('auto_fix', {})
                    if auto_fix_cfg.get('syntax_errors', True):
                        code = self.qonscience.auto_fix(code, verification_result)
            
            result.success = True
            result.code = self._format_output(code, intent, prompt)
            result.audit_log = self.audit_log.copy()
            result.latency_ms = (_time.time() - start_time) * 1000
            
            self.log("=" * 60)
            self.log(f"OK Generation complete: {len(result.code)} chars in {result.latency_ms:.0f}ms")
            
        except Exception as e:
            result.success = False
            result.error = str(e)
            result.latency_ms = (_time.time() - start_time) * 1000
            self.log(f"X Generation failed: {e}")
            result.code = self._generate_error_output(prompt, str(e))
        
        return result
    
    def _parse_intent(self, text: str) -> CrystallizedIntent:
        """Parse intent from prompt text.
        
        v1.6.3: Skip prompt template keywords and focus on actual task content.
        v1.8.7: Removed hardcoded debug paths.
        """
        intent = CrystallizedIntent(raw_text=text)
        
        # v1.6.3: Try to extract just the briq content section (after "**Plan (from Briq):**")
        briq_marker = "**Plan (from Briq):**"
        if briq_marker in text:
            text = text.split(briq_marker, 1)[1]
        
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        action_verbs = {
            ActionType.CREATE: {'create', 'add', 'build', 'make', 'generate', 'implement', 'write', 'new'},
            ActionType.MODIFY: {'modify', 'update', 'change', 'edit', 'fix', 'patch', 'revise'},
            ActionType.DELETE: {'delete', 'remove', 'drop', 'clear', 'purge'},
            ActionType.REFACTOR: {'refactor', 'restructure', 'reorganize', 'rename', 'optimize'},
            ActionType.TEST: {'test', 'verify', 'validate', 'check'},
            ActionType.DOCUMENT: {'document', 'doc', 'comment', 'describe'},
            ActionType.CONFIGURE: {'configure', 'config', 'setup', 'settings'},
        }
        
        for action, verbs in action_verbs.items():
            if any(v in words[:10] for v in verbs):
                intent.action = action
                break
        
        if any(w in text_lower for w in ['class', 'model', 'entity']):
            intent.target_type = TargetType.CLASS
        elif any(w in text_lower for w in ['test', 'spec', 'unittest']):
            intent.target_type = TargetType.TEST
        elif any(w in text_lower for w in ['config', 'yaml', 'json', 'settings']):
            intent.target_type = TargetType.CONFIG
        else:
            intent.target_type = TargetType.FUNCTION
        
        # v1.6.3: Skip prompt template keywords
        skip_names = {
            'construqtor', 'inspeqtor', 'instruqtor', 'qontextor', 'qompressor',
            'qonqrete', 'mindstaq', 'briq', 'qodeyard', 'architect', 'objective',
        }
        
        quoted = re.findall(r'[`"\']([a-zA-Z_]\w*)[`"\']', text)
        for name in quoted:
            if name.lower() not in skip_names:
                intent.target_name = name
                break
        
        # v1.8.1 FIX: Skip system paths AND garbage patterns
        skip_path_patterns = [
            r'^packages/',
            r'^site-packages/',
            r'^google/',
            r'^qodeyard/mindstaq',
        ]
        
        # v1.8.4: Smart filename validation - MINIMAL blocking
        # Only reject things that are CLEARLY URLs, not valid filenames
        # User feedback: "don't block anything, just add the languages we want"
        def is_valid_filename(candidate: str) -> bool:
            """Check if candidate looks like a real filename, not a URL.
            
            Valid: src/main.rs, setup.sh, response.json, config.go
            Invalid: sh.rustup.rs (URL pattern with known domains)
            """
            # Must have a valid extension at the END
            valid_extensions = ('.py', '.js', '.ts', '.go', '.rs', '.sh', '.bash', '.yaml', '.yml', '.json', '.toml')
            if not any(candidate.endswith(ext) for ext in valid_extensions):
                return False
            
            # If it contains a slash, it's a path - always valid!
            if '/' in candidate:
                return True
            
            # Simple filenames (one dot) are always valid: main.py, response.json
            dot_count = candidate.count('.')
            if dot_count == 1:
                return True
            
            # Multiple dots - only reject known URL patterns
            # Pattern: prefix.domain.extension (like sh.rustup.rs)
            if dot_count == 2:
                parts = candidate.split('.')
                # Only reject if it looks like subdomain.known-domain.ext
                known_domains = {'rustup', 'github', 'npmjs', 'pypi', 'golang', 'crates', 'io', 'dev'}
                url_prefixes = {'sh', 'www', 'api', 'cdn', 'raw', 'pkg', 'npm', 'go', 'git'}
                
                if parts[0].lower() in url_prefixes and parts[1].lower() in known_domains:
                    return False
            
            # Everything else is valid - let the user decide what files they want
            return True
        
        # v1.8.4: Extended file pattern to include all supported languages
        file_matches = re.findall(r'([a-zA-Z_][\w/.-]*\.(?:py|js|ts|go|rs|sh|bash|yaml|yml|json|toml))', text)
        for file_match in file_matches:
            should_skip = False
            
            # Check system path patterns
            for skip_pat in skip_path_patterns:
                if re.match(skip_pat, file_match, re.IGNORECASE):
                    should_skip = True
                    break
            
            # v1.8.4: Use smart validation - minimal blocking
            if not should_skip and is_valid_filename(file_match):
                intent.target_file = file_match
                break
        
        stop_words = {'the', 'a', 'an', 'is', 'are', 'to', 'of', 'in', 'for', 'and', 'or', 'with', 'that', 'this'}
        intent.keywords = [w for w in words if w not in stop_words and len(w) > 2][:20]
        
        return intent
    
    def _format_output(self, code: str, intent: CrystallizedIntent, prompt: str) -> str:
        filename = intent.target_file or self._infer_filename(intent, prompt)
        lang = self._infer_language(filename)
        return f"```{lang}:qodeyard/{filename}\n{code}\n```"
    
    def _infer_filename(self, intent: CrystallizedIntent, prompt: str) -> str:
        """Infer output filename from prompt, with better filtering.
        
        v1.8.0: Filter URLs and method calls to prevent garbage filenames.
        v1.8.0: Added shell script detection for .sh files.
        v1.6.3: Skip system package paths and prefer project-specific files.
        """
        # Paths to SKIP (system packages, not project files)
        skip_patterns = [
            r'^packages/',
            r'^site-packages/',
            r'^google/',
            r'^dist-packages/',
            r'^\.?venv/',
            r'^node_modules/',
            r'^__pycache__/',
            r'^\.git/',
        ]
        
        # v1.8.0: Patterns that indicate garbage, not real filenames
        garbage_patterns = [
            r'^https?://',           # URLs
            r'^sh\.',                # sh.rustup.rs style URLs
            r'\.json\(\)',           # Method calls like response.json()
            r'\.js\(\)',             # Method calls
            r'\(\)$',                # Anything ending with ()
            r'^google\.',            # Google package references
            r'^response\.',          # response.json, response.js
            r'^import\s',            # Import statements
            r'^from\s',              # From statements
        ]
        
        # v1.8.0: Expanded patterns to include shell scripts and other file types
        file_patterns = [
            r'`([a-zA-Z_][a-zA-Z0-9_/.-]*\.[a-z]+)`',  # backtick-wrapped (any extension)
            r'in\s+([a-zA-Z_][a-zA-Z0-9_/.-]*\.py)',    # "in filename.py"
            r'create\s+([a-zA-Z_][a-zA-Z0-9_/.-]*\.py)',  # "create filename.py"
            r'write\s+([a-zA-Z_][a-zA-Z0-9_/.-]*\.py)',   # "write filename.py"
            # v1.8.0: Shell script patterns
            r'([a-zA-Z0-9_/-]+\.sh)',   # any .sh file
            r'provision/([a-zA-Z0-9_-]+\.sh)',  # provision/*.sh
            r'scripts?/([a-zA-Z0-9_-]+\.sh)',   # script/*.sh or scripts/*.sh
        ]
        
        candidates = []
        for pattern in file_patterns:
            matches = re.findall(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Skip system package paths
                should_skip = False
                for skip_pat in skip_patterns:
                    if re.match(skip_pat, match, re.IGNORECASE):
                        should_skip = True
                        break
                
                # v1.8.0: Skip garbage patterns (URLs, method calls, etc.)
                if not should_skip:
                    for garbage_pat in garbage_patterns:
                        if re.match(garbage_pat, match, re.IGNORECASE):
                            should_skip = True
                            break
                
                if not should_skip and match not in candidates:
                    candidates.append(match)
        
        # v1.8.0: Prioritize shell scripts if prompt contains shell-related keywords
        shell_keywords = ['provision', 'setup', 'install', 'deploy', 'bash', 'shell', 'script']
        is_shell_context = any(kw in prompt.lower() for kw in shell_keywords)
        
        if is_shell_context:
            for candidate in candidates:
                if candidate.endswith('.sh'):
                    return candidate
        
        # Prioritize src/ paths (project files)
        for candidate in candidates:
            if candidate.startswith('src/') or candidate.startswith('app/'):
                return candidate
        
        # Then prefer simple filenames (no deep nesting)
        for candidate in candidates:
            if candidate.count('/') <= 1:
                return candidate
        
        # Return first valid candidate
        if candidates:
            return candidates[0]
        
        # v1.8.0: Detect shell script context and return .sh filename
        if is_shell_context and not any(candidates):
            # Try to extract a name from the prompt for the shell script
            name_match = re.search(r'provision[/-]?(\d+)?[-_]?([a-zA-Z-]+)', prompt.lower())
            if name_match:
                num = name_match.group(1) or ''
                name = name_match.group(2) or 'script'
                return f"provision/{num}-{name}.sh".replace('--', '-').replace('-.', '.')
        
        # Fallback to intent-based naming
        if intent.target_name:
            return f"{intent.target_name.lower().replace(' ', '_')}.py"
        
        return "generated_code.py"
    
    def _infer_language(self, filename: str) -> str:
        """v1.8.0: Added shell script and more language support."""
        ext_map = {
            '.py': 'python', 
            '.js': 'javascript', 
            '.ts': 'typescript', 
            '.go': 'go', 
            '.rs': 'rust',
            # v1.8.0: Shell script support
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'zsh',
            # Config files
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.toml': 'toml',
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return 'python'
    
    def _generate_error_output(self, prompt: str, error: str) -> str:
        # v1.8.0 FIX: Sanitize prompt to prevent invalid Python syntax
        # Remove any log context that might be appended
        safe_prompt = prompt.split('--- PREVIOUS AGENT LOG')[0].strip() if prompt else ''
        # Truncate and remove newlines to keep it single-line safe
        safe_prompt = safe_prompt[:200].replace('\n', ' ').replace('\r', ' ')
        # Escape any quotes
        safe_prompt = safe_prompt.replace('"', '\\"').replace("'", "\\'")
        # Same for error message
        safe_error = str(error).replace('"', '\\"').replace("'", "\\'")[:500]
        
        return f'''```python:qodeyard/mindstaq_error.py
# mindstaQ: Code Generation Failed
# Error: {safe_error}
# Task: {safe_prompt}

raise NotImplementedError("{safe_error}")
```'''
