#!/usr/bin/env python3
"""
TripleThreat: Parallel Multi-Tier Code Generation
v2.1.9-stable - FULL PIPELINE INTEGRATION EDITION! 🔥

THIS VERSION ACTUALLY WIRES IN THE MODULES!

Pipeline Order:
1. 🏺 Wisdom Pits (if enabled) - Tool-specific pre-built implementations
2. 📊 Dependency Graph - Multi-file architecture analysis  
3. 🎲 Parallel Tiers - Qrystallizer, SQavenger, Qombinator
4. 🧬 Darwinian Evolution - Novel algorithm synthesis
5. 🎮 MCTS (Monte Carlo Tree Search) - Strategic code optimization

v2.1.9 CRITICAL FIX:
  - Modules are now ACTUALLY CALLED in the pipeline!
  - Previously they existed but were never invoked during generation
  - This fix wires them into TripleThreatEngine.generate()

v2.1.8 Features (retained):
  - MCTS for strategic code generation
  - UCB1-based exploration vs exploitation

v2.1.7 Features (retained):
  - Wisdom Pits for tool-specific code
  - Darwinian Evolution for novel algorithms
  - Expanded boilerplate detection

Cost: $0.00 FOREVER - ZERO LLM REQUIRED!
"""

import concurrent.futures
import threading
import sys
from typing import Optional, List, Tuple, Any, Dict
from dataclasses import dataclass

__version__ = '2.2.8-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE IMPORTS WITH GRACEFUL FALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

# v2.1.7: Wisdom Pits - Tool-specific pre-built implementations
try:
    from .wisdom_pits import get_tool_code, search_wisdom, WisdomEntry
    WISDOM_PITS_AVAILABLE = True
except ImportError:
    WISDOM_PITS_AVAILABLE = False
    def get_tool_code(x): return None
    def search_wisdom(x, limit=5): return []
    class WisdomEntry:
        def matches_query(self, q): return 0.0
        code_template = ""

# v2.1.8: MCTS - Strategic code generation (like AlphaGo)
try:
    from .mcts_code import mcts_generate, mcts_improve_code, MCTSCodeGenerator
    MCTS_AVAILABLE = True
except ImportError:
    MCTS_AVAILABLE = False
    def mcts_generate(*args, **kwargs): return None, 0.0
    def mcts_improve_code(*args, **kwargs): return None, 0.0, 0.0

# v2.1.7: Darwinian Evolution - Genetic algorithm for novel code
try:
    from .darwinian import DarwinianEvolver, evolve_code
    DARWINIAN_AVAILABLE = True
except ImportError:
    DARWINIAN_AVAILABLE = False
    def evolve_code(*args, **kwargs): return None, 0.0

# v2.1.7: Dependency Graph - Multi-file architecture analysis
try:
    from .dependency_graph import DependencyAnalyzer, analyze_dependencies
    DEPENDENCY_GRAPH_AVAILABLE = True
except ImportError:
    DEPENDENCY_GRAPH_AVAILABLE = False
    def analyze_dependencies(*args, **kwargs): return {}


def _log(msg: str):
    """Safe logging that doesn't break the pipeline."""
    try:
        sys.stderr.write(f"[TripleThreat] {msg}\n")
        sys.stderr.flush()
    except:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# TIER RESULT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TierResult:
    """Result from a single tier's generation attempt."""
    tier_name: str
    code: Optional[str]
    success: bool
    latency_ms: float
    error: Optional[str] = None
    source: str = "tier"  # tier, wisdom_pits, darwinian, mcts


# ═══════════════════════════════════════════════════════════════════════════════
# WISDOM PITS - Check for pre-built tool implementations
# ═══════════════════════════════════════════════════════════════════════════════

def check_wisdom_pits(prompt: str, config: Dict = None) -> Optional[str]:
    """
    v2.1.9: Check Wisdom Pits for tool-specific implementations.
    
    If the prompt mentions a known tool (nmap, bloodhound, etc.),
    return the pre-built implementation instead of generating from scratch.
    
    Args:
        prompt: The user's request/briq content
        config: Configuration dict with 'enabled' key
        
    Returns:
        Pre-built code if found, None otherwise
    """
    config = config or {}
    if not config.get('enabled', False):
        return None
        
    if not WISDOM_PITS_AVAILABLE:
        _log("Wisdom Pits: Module not available")
        return None
    
    combined = prompt.lower()
    
    # Check common security tools
    tool_keywords = [
        'nmap', 'bloodhound', 'feroxbuster', 'masscan', 'nikto',
        'sqlmap', 'gobuster', 'dirb', 'hydra', 'nuclei', 'ffuf',
        'metasploit', 'burpsuite', 'wireshark', 'hashcat', 'john',
    ]
    
    for tool in tool_keywords:
        if tool in combined:
            # Check if we're asking for a wrapper
            if any(kw in combined for kw in ['wrapper', 'scanner', 'tool', 'implement', 'create']):
                code = get_tool_code(tool)
                if code:
                    _log(f"Wisdom Pits: Found pre-built implementation for '{tool}'")
                    return code
    
    # Search wisdom pits for relevant entries
    try:
        results = search_wisdom(combined, limit=1)
        if results and len(results) > 0:
            entry = results[0]
            if hasattr(entry, 'matches_query') and entry.matches_query(combined) > 0.5:
                _log(f"Wisdom Pits: Found matching entry (score > 0.5)")
                return entry.code_template
    except Exception as e:
        _log(f"Wisdom Pits search error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH - Multi-file architecture analysis
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_project_dependencies(
    prompt: str,
    context_files: List[str],
    qodeyard_path: str = None,
    config: Dict = None
) -> Dict:
    """
    v2.1.9: Analyze project dependencies for better code generation.
    
    Args:
        prompt: The user's request
        context_files: List of existing project files
        qodeyard_path: Path to the qodeyard directory
        config: Configuration dict with 'enabled' key
        
    Returns:
        Dict with dependency information
    """
    config = config or {}
    if not config.get('enabled', True):
        return {}
        
    if not DEPENDENCY_GRAPH_AVAILABLE:
        return {}
    
    try:
        deps = analyze_dependencies(
            files=context_files,
            root_path=qodeyard_path
        )
        if deps:
            _log(f"Dependency Graph: Analyzed {len(deps.get('nodes', []))} files")
        return deps
    except Exception as e:
        _log(f"Dependency Graph error: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# DARWINIAN EVOLUTION - Novel algorithm synthesis
# ═══════════════════════════════════════════════════════════════════════════════

def try_darwinian_evolution(
    prompt: str,
    base_code: str = None,
    test_cases: List[dict] = None,
    config: Dict = None
) -> Optional[str]:
    """
    v2.1.9: Try Darwinian evolution for novel algorithm synthesis.
    
    Best for:
    - Novel algorithms from scratch
    - No known solution exists
    - Open-ended problems with many valid solutions
    
    Args:
        prompt: The algorithm description
        base_code: Optional starting code to evolve from
        test_cases: Test cases for fitness evaluation
        config: Configuration dict
        
    Returns:
        Evolved code if successful, None otherwise
    """
    config = config or {}
    if not config.get('enabled', True):
        return None
        
    if not DARWINIAN_AVAILABLE:
        return None
    
    # Detect if this looks like a novel algorithm request
    algorithm_keywords = [
        'algorithm', 'implement', 'solve', 'calculate', 'compute',
        'optimize', 'search', 'sort', 'find', 'generate', 'convert',
        'transform', 'process', 'analyze', 'detect', 'classify',
    ]
    
    prompt_lower = prompt.lower()
    is_algorithm_request = any(kw in prompt_lower for kw in algorithm_keywords)
    
    if not is_algorithm_request:
        return None
    
    try:
        _log("Darwinian Evolution: Attempting novel algorithm synthesis...")
        
        evolved_code, fitness = evolve_code(
            description=prompt,
            initial_code=base_code,
            test_cases=test_cases or [],
            generations=config.get('max_generations', 50),
            population_size=config.get('population_size', 20),
        )
        
        if evolved_code and fitness > 0.5:
            _log(f"Darwinian Evolution: Success! Fitness={fitness:.2f}")
            return evolved_code
        else:
            _log(f"Darwinian Evolution: Fitness too low ({fitness:.2f})")
            
    except Exception as e:
        _log(f"Darwinian Evolution error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MCTS - Strategic code optimization
# ═══════════════════════════════════════════════════════════════════════════════

def try_mcts_improvement(
    code: str,
    test_cases: List[dict] = None,
    config: Dict = None
) -> Optional[str]:
    """
    v2.1.9: Try to improve code using MCTS (Monte Carlo Tree Search).
    
    Best for:
    - Optimizing existing code
    - Complex stateful logic with interdependent decisions
    - Known starting point, need to find BEST path
    
    Args:
        code: The code to improve
        test_cases: Test cases for fitness evaluation
        config: Configuration dict
        
    Returns:
        Improved code if successful, None otherwise
    """
    config = config or {}
    if not config.get('enabled', True):
        return None
        
    if not MCTS_AVAILABLE or not code:
        return None
    
    # Need test cases for MCTS to evaluate fitness
    if not test_cases:
        return None
    
    try:
        _log("MCTS: Attempting strategic code optimization...")
        
        improved_code, new_fitness, improvement = mcts_improve_code(
            code=code,
            test_cases=test_cases,
            iterations=config.get('iterations', 300),
            time_limit=config.get('time_limit', 30.0),
        )
        
        # Only use if significant improvement
        min_improvement = config.get('min_improvement', 0.1)
        min_fitness = config.get('min_fitness', 0.5)
        
        if improvement > min_improvement and new_fitness > min_fitness:
            _log(f"MCTS: Success! Improvement={improvement:.2f}, Fitness={new_fitness:.2f}")
            return improved_code
        else:
            _log(f"MCTS: Improvement too small ({improvement:.2f})")
            
    except Exception as e:
        _log(f"MCTS error: {e}")
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PARALLEL TIER EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

def run_tier_parallel(
    qrystallizer,
    sqavenger, 
    qombinator,
    intent,
    prompt: str,
    context_files: List[str],
    timeout_seconds: float = 30.0
) -> List[TierResult]:
    """
    Run all three tiers in parallel and collect results.
    
    Returns list of TierResults, one per tier that completed.
    """
    import time
    
    results = []
    lock = threading.Lock()
    
    def run_qrystallizer():
        start = time.time()
        try:
            code = qrystallizer.generate(intent, prompt, context_files)
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='QRYSTALLIZER',
                    code=code,
                    success=bool(code),
                    latency_ms=latency,
                    source='tier'
                ))
        except Exception as e:
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='QRYSTALLIZER',
                    code=None,
                    success=False,
                    latency_ms=latency,
                    error=str(e),
                    source='tier'
                ))
    
    def run_sqavenger():
        start = time.time()
        try:
            code = sqavenger.generate(intent)
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='SQAVENGER',
                    code=code,
                    success=bool(code),
                    latency_ms=latency,
                    source='tier'
                ))
        except Exception as e:
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='SQAVENGER',
                    code=None,
                    success=False,
                    latency_ms=latency,
                    error=str(e),
                    source='tier'
                ))
    
    def run_qombinator():
        start = time.time()
        try:
            code = qombinator.synthesize(intent, prompt, context_files)
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='QOMBINATOR',
                    code=code,
                    success=bool(code),
                    latency_ms=latency,
                    source='tier'
                ))
        except Exception as e:
            latency = (time.time() - start) * 1000
            with lock:
                results.append(TierResult(
                    tier_name='QOMBINATOR',
                    code=None,
                    success=False,
                    latency_ms=latency,
                    error=str(e),
                    source='tier'
                ))
    
    # Run all three in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(run_qrystallizer),
            executor.submit(run_sqavenger),
            executor.submit(run_qombinator),
        ]
        
        # Wait for all to complete (with timeout)
        concurrent.futures.wait(futures, timeout=timeout_seconds)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT COMBINATION AND SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def score_code_result(code: str, tier_name: str, config: Dict = None) -> float:
    """
    Score a code result based on quality metrics.
    
    v2.1.9: Enhanced boilerplate detection with HEAVY penalties.
    v2.2.4: WEB SEARCH (SQAVENGER) gets HIGHEST priority weight!
    """
    if not code:
        return 0.0
    
    config = config or {}
    
    # Base score = code length
    base_score = len(code)
    
    # v2.2.4: TIER WEIGHTS - WEB SEARCH IS KING! 👑
    # SQAVENGER does web search = HIGHEST weight because it's task-specific!
    tier_weights = {
        'SQAVENGER': config.get('web_priority_weight', 5.0),   # v2.2.4: BOOSTED! Web = gold
        'WISDOM_PITS': 2.5,    # Pre-built = good but generic
        'DARWINIAN': 2.0,      # Novel = experimental
        'MCTS': 1.8,           # Optimized = good
        'QOMBINATOR': 1.2,     # Templates = fallback
        'QRYSTALLIZER': 0.8,   # Basic templates = last resort
    }
    weight = tier_weights.get(tier_name, 1.0)
    
    # v2.1.9: EXPANDED boilerplate detection
    # v2.2.4: EVEN HEAVIER penalties for copypasta!
    # v2.2.8: Added Repository copypasta detection!
    # These patterns indicate generic template spam, NOT tool-specific code
    boilerplate_indicators = [
        # v2.1.6 original patterns
        'class SafetyGovernor',
        'class EventBus', 
        'class SafetyConfig',
        # v2.1.7 patterns
        'class ValidationResult',
        'class Validator',
        'class ConfigLoader',
        'EMAIL_RE = re.compile',
        'IP_RE = re.compile',
        # v2.1.9 NEW patterns
        'class BaseHandler',
        'class GenericWrapper',
        'class AbstractFactory',
        'class BaseModel',
        'def validate_email',
        'def validate_ip',
        'def get_config',
        '# Generic implementation',
        '# TODO: Implement',
        'raise NotImplementedError',
        # v2.2.4: MORE copypasta indicators
        'class NmapHost',        # Specific copypasta from v2.2.2
        'class NmapResult',      # Specific copypasta from v2.2.2
        '"""Discovered host from nmap',  # Copy signature
        # v2.2.8: Repository copypasta epidemic detection!
        'class Repository:',      # Generic CRUD - not tool-specific!
        'class Shared:',          # Generic shared class
        'class ERROR:',           # Generic error placeholder
        'class Config:',          # Another common copypasta
        'class Entity:',          # Generic entity
        'self._storage: Dict',    # In-memory storage (generic)
        'self._records: Dict',    # Generic records
        '"""Repository."""',      # Docstring-only classes
        '"""Create."""',          # One-word docstrings (stub indicator)
        '"""Get."""',
        '"""Update."""',
        '"""Delete."""',
    ]
    
    boilerplate_count = sum(1 for indicator in boilerplate_indicators if indicator in code)
    
    # Check for duplicate class definitions (strong copypasta signal)
    import re
    class_defs = re.findall(r'^class \w+', code, re.MULTILINE)
    unique_classes = len(set(class_defs))
    total_classes = len(class_defs)
    
    # v2.2.4: HEAVIER penalties for copypasta
    if total_classes > 0 and unique_classes < total_classes:
        weight *= 0.3  # 70% penalty for duplicate class definitions (was 50%)
    
    if boilerplate_count >= 4:
        weight *= 0.05  # 95% penalty for extreme copypasta (was 90%)
    elif boilerplate_count >= 3:
        weight *= 0.1   # 90% penalty for heavy copypasta (was 80%)
    elif boilerplate_count >= 2:
        weight *= 0.2   # 80% penalty for obvious copypasta (was 70%)
    elif boilerplate_count == 1:
        weight *= 0.5   # 50% penalty for single boilerplate (was 30%)
    
    # v2.2.4: BONUS for web-sourced code indicators
    # These indicate code came from actual GitHub/StackOverflow sources
    web_source_indicators = [
        '# Source:', '# From:', '# Adapted from',
        'github.com', 'stackoverflow.com',
        '# Copyright', '# License',
        '__author__', '__version__',
    ]
    web_source_count = sum(1 for ind in web_source_indicators if ind in code)
    if web_source_count > 0:
        weight *= 1.3  # 30% bonus for web-sourced code
    
    # v2.2.8: EXPANDED tool-specific code detection
    # These indicate REAL tool implementations, not generic patterns
    tool_indicators = [
        # Subprocess execution (actual tool wrapping)
        'subprocess.run', 'subprocess.Popen', 'subprocess.check_output',
        # CLI frameworks
        'argparse', 'click.command', '@click.option',
        # Network tools
        'socket.socket', 'requests.', 'aiohttp.',
        # v2.2.8: Security tool specific patterns
        'nmap.PortScanner', 'nmap.PortScannerAsync',  # python-nmap
        'bloodhound.', 'neo4j.', 'py2neo.',            # BloodHound/Neo4j
        'ldap3.', 'impacket.',                          # AD/SMB tools
        'feroxbuster', 'gobuster', 'ffuf',              # Web fuzzing
        'nuclei', 'httpx',                               # Vulnerability scanning
        'crackmapexec', 'cme.',                         # CrackMapExec
        'masscan.', 'rustscan',                         # Port scanning
        'hashcat', 'john',                               # Password cracking
        # Specific API patterns
        '-oX', '-oN', '-oG',                            # Nmap output formats
        'cypher_query', 'run_cypher',                   # Neo4j queries
        'ldap_search', 'kerberos',                      # AD protocols
        'smb.', 'ntlm.', 'spnego.',                     # Windows auth
    ]
    tool_count = sum(1 for indicator in tool_indicators if indicator.lower() in code.lower())
    if tool_count >= 3:
        weight *= 2.0  # 100% bonus for highly tool-specific code
    elif tool_count >= 2:
        weight *= 1.5  # 50% bonus for tool-specific code
    elif tool_count >= 1:
        weight *= 1.2  # 20% bonus for some tool indicators
    
    return base_score * weight


def combine_tier_results(
    results: List[TierResult],
    franqenstein_combine_func=None,
    config: Dict = None
) -> Tuple[Optional[str], str]:
    """
    Combine results from multiple tiers into the best possible output.
    
    v2.1.9 FIX: Now uses enhanced scoring with heavy boilerplate penalties.
    v2.2.8 FIX: Prefer SQAVENGER when web results contain tool-specific code!
    
    Returns: (combined_code, summary_string)
    """
    config = config or {}
    
    # Filter to successful results with code
    successful = [r for r in results if r.success and r.code]
    
    if not successful:
        failed_tiers = [r.tier_name for r in results]
        return None, f"All tiers failed: {', '.join(failed_tiers)}"
    
    if len(successful) == 1:
        r = successful[0]
        return r.code, f"Single source: {r.tier_name} ({r.latency_ms:.0f}ms)"
    
    # v2.2.8: CHECK FOR TOOL-SPECIFIC CODE IN SQAVENGER RESULT
    # If SQAVENGER has tool-specific code, USE IT DIRECTLY - don't let
    # Franqenstein dilute it with generic copypasta!
    sqavenger_result = next((r for r in successful if r.tier_name == 'SQAVENGER'), None)
    
    if sqavenger_result and sqavenger_result.code:
        code_lower = sqavenger_result.code.lower()
        
        # Tool-specific indicators (if present, SQAVENGER wins!)
        tool_indicators = [
            'subprocess.run', 'subprocess.popen', 'subprocess.check_output',
            'nmap', 'bloodhound', 'feroxbuster', 'masscan', 'hashcat',
            'neo4j', 'cypher', 'ldap3', 'impacket', 'kerberos',
            'socket.socket', 'requests.', 'aiohttp.',
            '-ox', '-on', '-og',  # nmap output formats
            'sharphound', 'crackmapexec', 'gobuster', 'nuclei',
        ]
        
        tool_count = sum(1 for ind in tool_indicators if ind in code_lower)
        
        # Also check for ABSENCE of copypasta
        copypasta_indicators = [
            'class repository:', '"""repository."""',
            'self._storage:', 'self._records:',
        ]
        copypasta_count = sum(1 for ind in copypasta_indicators if ind in code_lower)
        
        # If SQAVENGER has tool-specific code WITHOUT copypasta, USE IT DIRECTLY!
        if tool_count >= 2 and copypasta_count == 0:
            return sqavenger_result.code, f"Tool-specific SQAVENGER result (tools={tool_count})"
        elif tool_count >= 1 and copypasta_count == 0:
            return sqavenger_result.code, f"SQAVENGER result (tools={tool_count})"
    
    # Multiple succeeded - try to combine them
    codes = [r.code for r in successful]
    tier_names = [r.tier_name for r in successful]
    
    if franqenstein_combine_func:
        try:
            combined = franqenstein_combine_func(codes)
            if combined:
                return combined, f"Combined {len(successful)} sources: {', '.join(tier_names)}"
        except Exception:
            pass
    
    # Score and pick best
    def score_result(r: TierResult) -> float:
        return score_code_result(r.code, r.tier_name, config)
    
    best = max(successful, key=score_result)
    score = score_result(best)
    
    return best.code, f"Best of {len(successful)}: {best.tier_name} (score={score:.0f})"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class TripleThreatEngine:
    """
    v2.1.9: FULL PIPELINE INTEGRATION!
    
    Pipeline Order:
    1. 🏺 Wisdom Pits - Check for pre-built tool implementations
    2. 📊 Dependency Graph - Analyze project structure
    3. 🎲 Parallel Tiers - Run all tiers simultaneously
    4. 🧬 Darwinian - Try evolution if algorithm request
    5. 🎮 MCTS - Try optimization if test cases available
    6. 🔀 Combine - Pick best result with anti-copypasta scoring
    
    Usage:
        engine = TripleThreatEngine(qrystallizer, sqavenger, qombinator, config=config)
        code = engine.generate(intent, prompt, context_files)
    """
    
    def __init__(
        self, 
        qrystallizer, 
        sqavenger, 
        qombinator, 
        franqenstein=None,
        config: Dict = None
    ):
        self.qrystallizer = qrystallizer
        self.sqavenger = sqavenger
        self.qombinator = qombinator
        self.franqenstein = franqenstein
        self.config = config or {}
        
        # Stats tracking
        self.last_results = []
        self.last_summary = ""
        self.pipeline_log = []
    
    def generate(
        self, 
        intent, 
        prompt: str, 
        context_files: List[str] = None,
        timeout_seconds: float = 30.0,
        test_cases: List[dict] = None,
        qodeyard_path: str = None,
    ) -> Optional[str]:
        """
        v2.1.9: FULL PIPELINE with all modules ACTUALLY CALLED!
        
        Pipeline:
        1. Check Wisdom Pits for pre-built implementations
        2. Analyze dependencies for multi-file context
        3. Run all tiers in parallel
        4. Try Darwinian evolution if algorithm request
        5. Try MCTS optimization if test cases available
        6. Combine and score results (anti-copypasta)
        """
        import time
        start_time = time.time()
        
        context_files = context_files or []
        self.pipeline_log = []
        self.last_results = []
        
        def log(msg):
            self.pipeline_log.append(msg)
            _log(msg)
        
        log("=" * 50)
        log("TripleThreat v2.1.9 - FULL PIPELINE")
        log("=" * 50)
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 1: WISDOM PITS (Pre-built tool implementations)
        # ═══════════════════════════════════════════════════════════════════════
        wisdom_config = self.config.get('wisdom_pits', {})
        if wisdom_config.get('enabled', False):
            log("STEP 1: Checking Wisdom Pits...")
            wisdom_code = check_wisdom_pits(prompt, wisdom_config)
            if wisdom_code:
                log("  -> Found pre-built implementation!")
                self.last_results.append(TierResult(
                    tier_name='WISDOM_PITS',
                    code=wisdom_code,
                    success=True,
                    latency_ms=(time.time() - start_time) * 1000,
                    source='wisdom_pits'
                ))
                # Return immediately - pre-built is best!
                self.last_summary = "Wisdom Pits: Pre-built implementation"
                return wisdom_code
            else:
                log("  -> No pre-built match found")
        else:
            log("STEP 1: Wisdom Pits DISABLED")
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 2: DEPENDENCY GRAPH (Multi-file architecture)
        # ═══════════════════════════════════════════════════════════════════════
        dep_config = self.config.get('dependency_graph', {})
        if dep_config.get('enabled', True):
            log("STEP 2: Analyzing dependencies...")
            deps = analyze_project_dependencies(
                prompt, context_files, qodeyard_path, dep_config
            )
            if deps:
                log(f"  -> Found {len(deps.get('nodes', []))} dependency nodes")
        else:
            log("STEP 2: Dependency Graph DISABLED")
            deps = {}
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 3: PARALLEL TIERS (Qrystallizer, SQavenger, Qombinator)
        # ═══════════════════════════════════════════════════════════════════════
        log("STEP 3: Running parallel tiers...")
        tier_results = run_tier_parallel(
            self.qrystallizer,
            self.sqavenger,
            self.qombinator,
            intent,
            prompt,
            context_files,
            timeout_seconds
        )
        self.last_results.extend(tier_results)
        
        succeeded = sum(1 for r in tier_results if r.success)
        log(f"  -> {succeeded}/{len(tier_results)} tiers succeeded")
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 4: DARWINIAN EVOLUTION (Novel algorithms)
        # ═══════════════════════════════════════════════════════════════════════
        darwinian_config = self.config.get('darwinian', {})
        if darwinian_config.get('enabled', True):
            log("STEP 4: Trying Darwinian evolution...")
            
            # Get best tier result as starting point
            best_tier = None
            for r in tier_results:
                if r.success and r.code:
                    best_tier = r
                    break
            
            evolved_code = try_darwinian_evolution(
                prompt=prompt,
                base_code=best_tier.code if best_tier else None,
                test_cases=test_cases,
                config=darwinian_config
            )
            
            if evolved_code:
                log("  -> Evolution succeeded!")
                self.last_results.append(TierResult(
                    tier_name='DARWINIAN',
                    code=evolved_code,
                    success=True,
                    latency_ms=(time.time() - start_time) * 1000,
                    source='darwinian'
                ))
            else:
                log("  -> Evolution did not improve results")
        else:
            log("STEP 4: Darwinian DISABLED")
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 5: MCTS OPTIMIZATION (Strategic search)
        # ═══════════════════════════════════════════════════════════════════════
        mcts_config = self.config.get('mcts', {})
        if mcts_config.get('enabled', True) and test_cases:
            log("STEP 5: Trying MCTS optimization...")
            
            # Get best result so far
            best_so_far = None
            best_score = 0
            for r in self.last_results:
                if r.success and r.code:
                    score = score_code_result(r.code, r.tier_name, self.config)
                    if score > best_score:
                        best_score = score
                        best_so_far = r.code
            
            if best_so_far:
                mcts_code = try_mcts_improvement(
                    code=best_so_far,
                    test_cases=test_cases,
                    config=mcts_config
                )
                
                if mcts_code:
                    log("  -> MCTS improved the code!")
                    self.last_results.append(TierResult(
                        tier_name='MCTS',
                        code=mcts_code,
                        success=True,
                        latency_ms=(time.time() - start_time) * 1000,
                        source='mcts'
                    ))
                else:
                    log("  -> MCTS did not improve results")
            else:
                log("  -> No code to optimize")
        else:
            if not test_cases:
                log("STEP 5: MCTS SKIPPED (no test cases)")
            else:
                log("STEP 5: MCTS DISABLED")
        
        # ═══════════════════════════════════════════════════════════════════════
        # STEP 6: COMBINE RESULTS (Anti-copypasta scoring)
        # ═══════════════════════════════════════════════════════════════════════
        log("STEP 6: Combining results...")
        
        combine_func = None
        if self.franqenstein:
            combine_func = lambda codes: self.franqenstein.combine(codes).code if hasattr(self.franqenstein, 'combine') else None
        
        code, self.last_summary = combine_tier_results(
            self.last_results, 
            combine_func,
            self.config
        )
        
        total_time = (time.time() - start_time) * 1000
        log(f"  -> {self.last_summary}")
        log(f"COMPLETE: {total_time:.0f}ms total")
        log("=" * 50)
        
        return code
    
    def get_stats(self) -> dict:
        """Get statistics from the last generation."""
        return {
            'tiers_run': len(self.last_results),
            'tiers_succeeded': sum(1 for r in self.last_results if r.success),
            'total_latency_ms': sum(r.latency_ms for r in self.last_results),
            'summary': self.last_summary,
            'pipeline_log': self.pipeline_log,
            'results': [
                {
                    'tier': r.tier_name,
                    'success': r.success,
                    'latency_ms': r.latency_ms,
                    'code_length': len(r.code) if r.code else 0,
                    'source': r.source,
                    'error': r.error
                }
                for r in self.last_results
            ],
            'modules_available': {
                'wisdom_pits': WISDOM_PITS_AVAILABLE,
                'mcts': MCTS_AVAILABLE,
                'darwinian': DARWINIAN_AVAILABLE,
                'dependency_graph': DEPENDENCY_GRAPH_AVAILABLE,
            }
        }
