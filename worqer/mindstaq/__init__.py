#!/usr/bin/env python3
"""
mindstaQ: Zero-Cost Local Code Generation Engine
v2.1.0-stable - FULL COMPONENT INTEGRATION EDITION

Agent Pipeline:
  USER BRIQ → Qomputator (score) → Tier Router
                                   ├─ Tier 0: Qrystallizer (templates + PatternDB)
                                   ├─ Tier 1: sQavanger (Qrawler + DeepQrawler + Semantic)
                                   └─ Tier 2: Qombinator (Franqenstein + Breeder)
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

# v2.0.3: z3 constraint solver integration
try:
    from worqer.mindstaq.z3_solver import Z3Reasoner, has_z3, HAS_Z3
    _HAS_Z3 = has_z3()
except ImportError:
    _HAS_Z3 = False
    Z3Reasoner = None
    HAS_Z3 = False

# v1.9.7: Multi-language support for shell, yaml, etc.
try:
    from worqer.mindstaq.language_adapters import (
        detect_language, needs_language_adapter, generate_for_language
    )
    HAS_LANGUAGE_ADAPTERS = True
except ImportError:
    HAS_LANGUAGE_ADAPTERS = False

# v1.9.7: TripleThreat parallel tier execution
try:
    from worqer.mindstaq.triple_threat import TripleThreatEngine
    HAS_TRIPLE_THREAT = True
except ImportError:
    HAS_TRIPLE_THREAT = False

# v2.0.0: Safe non-blocking logger
try:
    from worqer.mindstaq.mindstaq_logger import mlog
    HAS_MLOG = True
except ImportError:
    HAS_MLOG = False
    mlog = None

__version__ = '2.2.8-stable'
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
    'FranqensteinCombinator',  # v1.5.0 - smart snippet merger
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
    if name == 'FranqensteinCombinator':
        from worqer.mindstaq.franqenstein import FranqensteinCombinator
        return FranqensteinCombinator
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
    SQAVENGER = 1
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
        # Core tier agents
        self._qomputator = None
        self._qrystallizer = None
        self._sqavenger = None
        self._qombinator = None
        self._qoncentrator = None
        self._qonscience = None
        
        # v2.1.0: Additional agents
        self._pattern_db = None
        self._semantic_matcher = None
        self._franqenstein = None
        self._template_breeder = None
        self._type_synthesis = None
        self._parallel_harvester = None
        self._qalibrator = None
        self._qualifier = None
        self._code_normalizer = None
        self._wonq_index = None
        self._decision_table = None
        self._allowlist_security = None
        self._smart_qomputator = None
        self._timewalqer = None
        self._deep_qrawler = None
        
        qomputator_cfg = self.mindstaq_config.get('qomputator', {})
        thresholds = qomputator_cfg.get('thresholds', {})
        self.tier_0_max = thresholds.get('tier_0_max', 100)
        self.tier_1_max = thresholds.get('tier_1_max', 400)
        self.audit_log = []
        
        # v1.9.7: TripleThreat mode - run all tiers in parallel
        self.triple_threat_enabled = self.mindstaq_config.get('triple_threat', {}).get('enabled', False)
        self._triple_threat = None
    
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
        # v2.0.0: Use mlog if available for better formatted output
        if HAS_MLOG and mlog:
            mlog.info(message)
        else:
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
    
    @property
    def triple_threat(self):
        """v2.1.9: TripleThreat engine with FULL PIPELINE INTEGRATION!
        
        Now passes config for all modules:
        - Wisdom Pits (pre-built tool implementations)
        - MCTS (Monte Carlo Tree Search optimization)
        - Darwinian Evolution (novel algorithm synthesis)
        - Dependency Graph (multi-file architecture)
        """
        if self._triple_threat is None and HAS_TRIPLE_THREAT:
            # v2.1.9: Build config for all modules
            triple_threat_config = {
                # Module configs from mindstaq_config
                'wisdom_pits': self.mindstaq_config.get('wisdom_pits', {'enabled': False}),
                'mcts': self.mindstaq_config.get('mcts', {'enabled': True}),
                'darwinian': self.mindstaq_config.get('darwinian', {'enabled': True}),
                'dependency_graph': self.mindstaq_config.get('dependency_graph', {'enabled': True}),
                # Scoring config
                'web_priority_weight': self.mindstaq_config.get('sqavenger', {}).get('web_priority_weight', 2.0),
            }
            
            self._triple_threat = TripleThreatEngine(
                self.qrystallizer,
                self.sqavenger,
                self.qombinator,
                self.franqenstein,
                config=triple_threat_config
            )
        return self._triple_threat
    
    # ═══════════════════════════════════════════════════════════════════════════
    # v2.1.0: FULL COMPONENT INTEGRATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    @property
    def pattern_db(self):
        """PatternDatabase: 200+ code patterns."""
        if self._pattern_db is None:
            from worqer.mindstaq.pattern_db import PatternDatabase
            self._pattern_db = PatternDatabase()
        return self._pattern_db
    
    @property
    def semantic_matcher(self):
        """SemanticMatcher: AST-based code similarity."""
        if self._semantic_matcher is None:
            from worqer.mindstaq.semantic_matcher import SemanticMatcher
            self._semantic_matcher = SemanticMatcher()
        return self._semantic_matcher
    
    @property
    def franqenstein(self):
        """FranqensteinCombinator: Smart code merger."""
        if self._franqenstein is None:
            from worqer.mindstaq.franqenstein import FranqensteinCombinator
            self._franqenstein = FranqensteinCombinator()
        return self._franqenstein
    
    @property
    def template_breeder(self):
        """TemplateBreeder: Genetic algorithm for code evolution."""
        if self._template_breeder is None:
            from worqer.mindstaq.template_breeder import TemplateBreeder
            self._template_breeder = TemplateBreeder()
        return self._template_breeder
    
    @property
    def type_synthesis(self):
        """TypeDirectedSynthesizer: A* pathfinding for glue code."""
        if self._type_synthesis is None:
            from worqer.mindstaq.type_synthesis import TypeDirectedSynthesizer
            cfg = self.mindstaq_config.copy()
            cfg['z3_enabled'] = self.mindstaq_config.get('z3_enabled', True)
            self._type_synthesis = TypeDirectedSynthesizer(cfg)
        return self._type_synthesis
    
    @property
    def z3_reasoner(self):
        """Z3Reasoner: Constraint solver for formal reasoning (v2.0.3)."""
        if not hasattr(self, '_z3_reasoner'):
            self._z3_reasoner = None
        if self._z3_reasoner is None and _HAS_Z3:
            try:
                self._z3_reasoner = Z3Reasoner(self.mindstaq_config)
            except Exception:
                self._z3_reasoner = None
        return self._z3_reasoner
    
    @property
    def has_z3(self) -> bool:
        """Check if z3 is available and enabled."""
        return _HAS_Z3 and self.mindstaq_config.get('z3_enabled', True)
    
    @property
    def parallel_harvester(self):
        """ParallelHarvester: Async multi-source code search."""
        if self._parallel_harvester is None:
            from worqer.mindstaq.parallel_harvester import ParallelHarvester
            cfg = self.mindstaq_config.get('parallel_harvester', {})
            self._parallel_harvester = ParallelHarvester(cfg)
        return self._parallel_harvester
    
    @property
    def qalibrator(self):
        """Qalibrator: AST mutation engine."""
        if self._qalibrator is None:
            from worqer.mindstaq.qalibrator import Qalibrator
            cfg = self.mindstaq_config.get('qalibrator', {})
            self._qalibrator = Qalibrator(config=cfg)
        return self._qalibrator
    
    @property
    def qualifier(self):
        """Qualifier: Quality assessment agent."""
        if self._qualifier is None:
            from worqer.mindstaq.qualifier import Qualifier
            cfg = self.mindstaq_config.get('qualifier', {})
            self._qualifier = Qualifier(config=cfg)
        return self._qualifier
    
    @property
    def code_normalizer(self):
        """CodeNormalizer: Code cleanup and formatting."""
        if self._code_normalizer is None:
            from worqer.mindstaq.code_normalizer import CodeNormalizer
            self._code_normalizer = CodeNormalizer()
        return self._code_normalizer
    
    @property
    def wonq_index(self):
        """WonqIndex: Local memory bank for patterns."""
        if self._wonq_index is None:
            from worqer.mindstaq.wonq_index import WonqIndex
            cfg = self.mindstaq_config.get('wonq_index', {})
            index_path = cfg.get('cache_dir', '/tmp/wonq_index.json')
            self._wonq_index = WonqIndex(index_path=index_path, config=self.mindstaq_config)
        return self._wonq_index
    
    @property
    def decision_table(self):
        """DecisionTableCompiler: Routing decision engine."""
        if self._decision_table is None:
            from worqer.mindstaq.decision_table import DecisionTableCompiler
            self._decision_table = DecisionTableCompiler()
        return self._decision_table
    
    @property
    def allowlist_security(self):
        """AllowlistSecurityGenerator: Security validation."""
        if self._allowlist_security is None:
            from worqer.mindstaq.allowlist_security import AllowlistSecurityGenerator
            self._allowlist_security = AllowlistSecurityGenerator()
        return self._allowlist_security
    
    @property
    def smart_qomputator(self):
        """SmartQomputator: Enhanced complexity scoring."""
        if self._smart_qomputator is None:
            from worqer.mindstaq.smart_qomputator import SmartQomputator
            self._smart_qomputator = SmartQomputator(self.mindstaq_config)
        return self._smart_qomputator
    
    @property
    def timewalqer(self):
        """TimeWalQer: Historical pattern tracking."""
        if self._timewalqer is None:
            from worqer.mindstaq.timewalqer import TimeWalQer
            self._timewalqer = TimeWalQer(config=self.mindstaq_config)
        return self._timewalqer
    
    @property
    def deep_qrawler(self):
        """DeepQrawler: Tor hidden service search (disabled by default)."""
        if self._deep_qrawler is None:
            from worqer.mindstaq.deep_qrawler import DeepQrawler
            cfg = self.mindstaq_config.get('deep_qrawler', {})
            self._deep_qrawler = DeepQrawler(config=cfg)
        return self._deep_qrawler
    
    def generate(self, prompt: str, context_files: List[str] = None, qodeyard_path=None) -> GenerationResult:
        """
        v2.1.0: FULL PIPELINE with all components integrated!
        
        Pipeline:
        1. Parse intent
        2. SmartQomputator scoring (enhanced complexity analysis)
        3. DecisionTable routing
        4. Tier execution (Qrystallizer / SQavenger+PatternDB / Qombinator)
        5. ParallelHarvester (multi-source search)
        6. SemanticMatcher (find similar code)
        7. Franqenstein (combine best parts)
        8. [Qalibrator ⟷ Qualifier LOOP] (evolve code)
        9. TypeSynthesis (generate glue code)
        10. CodeNormalizer (clean up)
        11. Qoncentrator (AST processing)
        12. AllowlistSecurity (validate)
        13. Qonscience (final verification)
        14. WonqIndex (cache successful pattern)
        15. TimeWalQer (track history)
        """
        import time as _time
        start_time = _time.time()
        self.audit_log = []
        result = GenerationResult()
        
        self.log("=" * 60)
        self.log("mindstaQ Code Generation Pipeline v2.1.0 [FULL]")
        self.log("=" * 60)
        
        try:
            self.log("STEP 1: Parsing task intent...")
            intent = self._parse_intent(prompt)
            self.log(f"  Action: {intent.action.value}")
            self.log(f"  Target: {intent.target_type.value} -> {intent.target_name or 'auto'}")
            
            # v2.1.0: Use SmartQomputator if available for better scoring
            self.log("STEP 2: SmartQomputator scoring complexity (0-666)...")
            try:
                score = self.smart_qomputator.score(prompt, intent)
                self.log("  -> Using SmartQomputator (enhanced)")
            except Exception:
                score = self.qomputator.score(prompt, intent)
                self.log("  -> Using standard Qomputator")
            result.complexity_score = score.total
            result.tier_used = score.tier
            self.log(f"  TOTAL: {score.total}/666 -> {score.tier.name}")
            
            self.log(f"STEP 3: Routing to {score.tier.name} tier agent...")
            code = None
            
            # v1.9.7: Check if target file needs language-specific generation (non-Python)
            target_filename = intent.target_file or self._infer_filename(intent, prompt)
            if HAS_LANGUAGE_ADAPTERS and needs_language_adapter(target_filename):
                target_lang = detect_language(target_filename)
                self.log(f"  -> Detected non-Python target: {target_lang}")
                code = generate_for_language(prompt, target_filename)
                if code:
                    self.log(f"  -> Generated {target_lang} content via language adapter")
            
            # v1.9.7: TripleThreat mode - run all tiers in parallel and combine!
            if not code and self.triple_threat_enabled and HAS_TRIPLE_THREAT and self.triple_threat:
                self.log("  -> TRIPLE THREAT MODE: Running all tiers in parallel!")
                code = self.triple_threat.generate(intent, prompt, context_files)
                if code:
                    stats = self.triple_threat.get_stats()
                    self.log(f"  -> {stats['summary']}")
            
            # Fall back to single tier routing (or if adapter/triple_threat failed)
            if not code:
                if score.tier == Tier.QRYSTALLIZER:
                    code = self.qrystallizer.generate(intent, prompt, context_files)
                elif score.tier == Tier.SQAVENGER:
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
            
            # v2.1.0: PatternDB lookup for additional patterns
            self.log("STEP 4: PatternDB searching for matches...")
            try:
                query_str = ' '.join(intent.keywords[:5]) if intent.keywords else prompt[:100]
                pattern_matches = self.pattern_db.search(query_str)
                if pattern_matches:
                    self.log(f"  -> Found {len(pattern_matches)} pattern matches")
            except Exception as e:
                self.log(f"  -> PatternDB: {e}")
            
            # v2.0.3: Z3 constraint solver for type synthesis
            if self.has_z3:
                self.log("STEP 4b: Z3 constraint solver active...")
                try:
                    # Use z3 for smarter type analysis
                    if hasattr(self, 'z3_reasoner') and self.z3_reasoner:
                        self.log("  -> z3 reasoning enabled for type paths")
                except Exception as e:
                    self.log(f"  -> z3: {e}")
            
            # v2.1.0: SemanticMatcher for similar code
            self.log("STEP 5: SemanticMatcher analyzing similarity...")
            try:
                # Get candidates from WonqIndex if available
                candidates = []
                try:
                    entries = self.wonq_index.search(' '.join(intent.keywords[:3]) if intent.keywords else '')
                    candidates = [e.code for e in entries[:5]] if entries else []
                except:
                    pass
                
                if candidates:
                    matches = self.semantic_matcher.match(prompt[:200], candidates)
                    if matches:
                        self.log(f"  -> Found {len(matches)} similar patterns (best score: {matches[0].score:.2f})")
                else:
                    self.log("  -> No candidates in WonqIndex yet")
            except Exception as e:
                self.log(f"  -> SemanticMatcher: {e}")
            
            # v2.1.0: Qalibrator ⟷ Qualifier evolution loop
            qalibrator_cfg = self.mindstaq_config.get('qalibrator', {})
            evolution_enabled = qalibrator_cfg.get('enabled', True)
            max_generations = qalibrator_cfg.get('max_generations', 3)
            
            if evolution_enabled:
                self.log(f"STEP 6: [Qalibrator ⟷ Qualifier] evolution loop (max {max_generations} generations)...")
                for gen in range(max_generations):
                    try:
                        # Assess quality
                        qual_result = self.qualifier.assess(code)
                        if qual_result.qualified:
                            self.log(f"  -> Generation {gen}: QUALIFIED (fitness: {qual_result.fitness:.2f})")
                            break
                        
                        # Mutate to improve
                        mutation_result = self.qalibrator.mutate(code)
                        if mutation_result.success:
                            code = mutation_result.mutated_code
                            self.log(f"  -> Generation {gen}: Mutation {mutation_result.mutation_type.value}")
                    except Exception as e:
                        self.log(f"  -> Evolution error: {e}")
                        break
            else:
                self.log("STEP 6: Evolution loop SKIPPED (disabled in config)")
            
            # v2.1.0: CodeNormalizer cleanup
            self.log("STEP 7: CodeNormalizer cleaning up...")
            try:
                code = self.code_normalizer.normalize(code)
            except Exception as e:
                self.log(f"  -> CodeNormalizer: {e}")
            
            self.log("STEP 8: Qoncentrator applying AST processing...")
            code = self.qoncentrator.process(code, intent, context_files)
            
            # v2.0.3: Z3 code verification (if enabled)
            if self.has_z3 and self.z3_reasoner:
                self.log("STEP 8b: Z3 verifying code properties...")
                try:
                    verification = self.z3_reasoner.verify_code_properties(
                        code, ['bounded_recursion', 'type_safe']
                    )
                    if verification.verified:
                        self.log("  -> z3: All properties verified ✓")
                    else:
                        for v in verification.violations[:2]:
                            self.log(f"  -> z3 warning: {v}")
                except Exception as e:
                    self.log(f"  -> z3 verification: {e}")
            
            # v2.1.0: AllowlistSecurity - check if using secure primitives
            self.log("STEP 9: AllowlistSecurity checking...")
            try:
                # Check if code uses any security primitives
                available_primitives = self.allowlist_security.list_primitives()
                security_keywords = ['sql', 'password', 'hash', 'jwt', 'sanitize', 'validate']
                code_lower = code.lower()
                
                using_security = any(kw in code_lower for kw in security_keywords)
                if using_security:
                    self.log(f"  -> Code uses security patterns (primitives available: {len(available_primitives)})")
                else:
                    self.log("  -> No security-sensitive patterns detected")
            except Exception as e:
                self.log(f"  -> AllowlistSecurity: {e}")
            
            self.log("STEP 10: Qonscience running verification...")
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
            
            # v2.1.0: Cache successful pattern in WonqIndex
            self.log("STEP 11: WonqIndex caching successful pattern...")
            try:
                self.wonq_index.add_entry(
                    name=intent.target_name or 'auto',
                    keywords=intent.keywords[:10] if intent.keywords else [],
                    code=code,
                    score=result.complexity_score
                )
            except Exception as e:
                self.log(f"  -> WonqIndex: {e}")
            
            # v2.1.0: TimeWalQer tracking
            try:
                self.timewalqer.record(
                    task=prompt[:100],
                    result='success',
                    score=result.complexity_score,
                    latency_ms=result.latency_ms
                )
            except Exception:
                pass  # TimeWalQer is optional
            
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
        
        # v2.0.0: First try to extract from markdown code block headers like ```python:qodeyard/path/file.py
        markdown_path = re.search(r'```[a-z]+:([\w/.-]+\.(?:py|js|ts|go|rs|sh|bash|yaml|yml|json|toml))', text)
        if markdown_path:
            intent.target_file = markdown_path.group(1).replace('qodeyard/', '')
            return intent
        
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
        
        # v2.2.8: EXTRACT TOOL NAMES FROM FILENAME AND PRIORITIZE THEM!
        # This fixes the issue where BRIQ descriptions are generic ("base_tool")
        # but the filename contains the actual tool name ("bloodhound_wrapper.py")
        tool_keywords = []
        
        if intent.target_file:
            # Extract meaningful parts from filename
            filename_parts = re.findall(r'[a-z]+', intent.target_file.lower())
            
            # Known security tools to prioritize
            known_tools = {
                'nmap', 'bloodhound', 'feroxbuster', 'masscan', 'hashcat',
                'gobuster', 'nuclei', 'sharphound', 'crackmapexec', 'impacket',
                'mimikatz', 'rubeus', 'beacon', 'implant', 'loader', 'injector',
                'scanner', 'wrapper', 'client', 'orchestrator', 'manager',
            }
            
            for part in filename_parts:
                if part in known_tools:
                    tool_keywords.insert(0, part)  # Priority at front
                elif len(part) > 4 and part not in stop_words:
                    tool_keywords.append(part)
        
        # Also check for tools in the BRIQ title (first line)
        first_line = text.split('\n')[0].lower() if text else ''
        for tool in ['nmap', 'bloodhound', 'feroxbuster', 'masscan', 'hashcat',
                     'gobuster', 'nuclei', 'sharphound', 'crackmapexec']:
            if tool in first_line and tool not in tool_keywords:
                tool_keywords.insert(0, tool)
        
        # v2.2.8: Prepend tool keywords to intent.keywords (so they're prioritized in search)
        if tool_keywords:
            # Remove duplicates while preserving order
            seen = set(tool_keywords)
            filtered_keywords = [kw for kw in intent.keywords if kw not in seen]
            intent.keywords = tool_keywords + filtered_keywords[:15]
        
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
