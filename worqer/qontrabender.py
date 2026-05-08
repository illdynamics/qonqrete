#!/usr/bin/env python3
# worqer/qontrabender.py
"""
QonQrete Qontrabender - The Cache Bender 🌀 (Enhanced Edition v0.8.0)

Policy-driven hybrid caching with Variable Fidelity and schema validation.

Features:
- Policy-based configuration via caching_policy.yaml
- Multiple operational modes (local_fast, local_smart, cyber_bedrock, etc.)
- Improved volatile detection (cycle-based, diff-based, git diff, mtime fallback)
- Fidelity rules engine with configurable thresholds
- Schema validation to prevent bad YAML from bricking the flow
- Full audit logging in debug_repro mode

The "Compositor" Pattern:
- Qompressor handles Syntax (AST stripping)
- Qontextor handles structural context (symbols, relationships, dependencies)
- Qontrabender handles Logistics (what goes to cloud, at what fidelity)

Usage:
    python qontrabender.py                    # Check if sync needed
    python qontrabender.py --mode local_smart # Use specific mode
    python qontrabender.py --sync             # Prepare payload for sync
    python qontrabender.py --status           # Show current cache status
    python qontrabender.py --analyze          # Show file fidelity decisions
    python qontrabender.py --validate         # Validate policy file only
"""

import os
import sys
import json
import yaml
import ast
import sqlite3
import hashlib
import argparse
import subprocess
import fnmatch
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple, Set

try:
    from path_hygiene import INFRA_DIR_NAMES, is_generated_output_dir, is_source_junk_file
except ImportError:
    INFRA_DIR_NAMES = frozenset({
        ".git",
        ".venv",
        ".test_venv",
        "node_modules",
        ".gradle",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".validation-env-cache",
        "__MACOSX",
    })

    def is_generated_output_dir(path: Path) -> bool:
        return path.name == "out" and path.parent.name == "vscode-extension"

    def is_source_junk_file(path: Path) -> bool:
        return path.name == ".DS_Store" or path.name.startswith("._") or path.suffix == ".pyc"

try:
    from worqer.context_bundle import (
        FULL_HOTSET,
        FULL_NEIGHBOR,
        MISSING_NEW_FILE_TARGET,
        QONTEXT,
        SKELETON,
        ContextBundleItem,
        build_context_bundle,
        resolve_qontrabender_cache_backend,
        validate_bundle_invariants,
        write_context_bundle_manifest,
        get_context_strategy_config,
    )
except ImportError:
    from context_bundle import (  # type: ignore
        FULL_HOTSET,
        FULL_NEIGHBOR,
        MISSING_NEW_FILE_TARGET,
        QONTEXT,
        SKELETON,
        ContextBundleItem,
        build_context_bundle,
        resolve_qontrabender_cache_backend,
        validate_bundle_invariants,
        write_context_bundle_manifest,
        get_context_strategy_config,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

POLICY_SCHEMA = {
    'version': {'type': int, 'required': True},
    'defaults': {
        'type': dict,
        'required': True,
        'children': {
            'qache_dir': {'type': str, 'required': False, 'default': 'qache.d'},
            'volatile_detection': {'type': dict, 'required': False},
            'budgets': {'type': dict, 'required': False},
            'file_limits': {'type': dict, 'required': False},
            'truncation': {'type': dict, 'required': False},
            'render': {'type': dict, 'required': False},
            'classification': {'type': dict, 'required': False},
            'paths': {'type': dict, 'required': False},
            'logging': {'type': dict, 'required': False},
        }
    },
    'modes': {
        'type': dict,
        'required': True,
        'children': {}  # Dynamic - each mode has its own structure
    },
    'qontext_schema': {'type': dict, 'required': False},
}

class PolicyValidationError(Exception):
    """Raised when policy file fails validation"""
    pass


class PolicyValidator:
    """Validates caching_policy.yaml against expected schema"""
    
    REQUIRED_MODE_FIELDS = ['description']
    VALID_FIDELITY_VALUES = ['full', 'skeleton', 'diff', 'summary', 'omit']
    VALID_TRUNCATION_STRATEGIES = ['head', 'tail', 'middle']
    VALID_RENDER_FORMATS = ['xml', 'markdown']
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate(self, policy: dict) -> Tuple[bool, List[str], List[str]]:
        """
        Validate the policy dictionary.
        Returns: (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        
        # Check version
        if 'version' not in policy:
            self.errors.append("Missing required field: 'version'")
        elif not isinstance(policy['version'], int):
            self.errors.append(f"'version' must be an integer, got {type(policy['version']).__name__}")
        
        # Check defaults
        if 'defaults' not in policy:
            self.errors.append("Missing required field: 'defaults'")
        elif not isinstance(policy['defaults'], dict):
            self.errors.append("'defaults' must be a dictionary")
        else:
            self._validate_defaults(policy['defaults'])
        
        # Check modes
        if 'modes' not in policy:
            self.errors.append("Missing required field: 'modes'")
        elif not isinstance(policy['modes'], dict):
            self.errors.append("'modes' must be a dictionary")
        elif len(policy['modes']) == 0:
            self.errors.append("'modes' must contain at least one mode")
        else:
            for mode_name, mode_config in policy['modes'].items():
                self._validate_mode(mode_name, mode_config)
        
        # Check qontext_schema (optional)
        if 'qontext_schema' in policy and not isinstance(policy['qontext_schema'], dict):
            self.errors.append("'qontext_schema' must be a dictionary")
        
        return len(self.errors) == 0, self.errors, self.warnings
    
    def _validate_defaults(self, defaults: dict):
        """Validate the defaults section"""
        # Validate budgets
        if 'budgets' in defaults:
            budgets = defaults['budgets']
            for key in ['cached_max_chars', 'cached_target_chars', 'hotset_max_chars', 'hotset_target_chars']:
                if key in budgets and not isinstance(budgets[key], (int, float)):
                    self.errors.append(f"defaults.budgets.{key} must be a number")
        
        # Validate truncation
        if 'truncation' in defaults:
            trunc = defaults['truncation']
            if 'strategy' in trunc and trunc['strategy'] not in self.VALID_TRUNCATION_STRATEGIES:
                self.errors.append(f"defaults.truncation.strategy must be one of: {self.VALID_TRUNCATION_STRATEGIES}")
        
        # Validate render
        if 'render' in defaults:
            render = defaults['render']
            if 'file_wrapper' in render and render['file_wrapper'] not in self.VALID_RENDER_FORMATS:
                self.errors.append(f"defaults.render.file_wrapper must be one of: {self.VALID_RENDER_FORMATS}")
        
        # Validate volatile_detection
        if 'volatile_detection' in defaults:
            vd = defaults['volatile_detection']
            if 'mtime_minutes' in vd:
                if not isinstance(vd['mtime_minutes'], (int, float)) or vd['mtime_minutes'] < 0:
                    self.errors.append("defaults.volatile_detection.mtime_minutes must be a positive number")
        
        # Validate paths
        if 'paths' in defaults:
            paths = defaults['paths']
            for key in ['exclude_globs', 'prefer_docs_globs', 'generated_globs']:
                if key in paths and not isinstance(paths[key], list):
                    self.errors.append(f"defaults.paths.{key} must be a list")
    
    def _validate_mode(self, mode_name: str, mode_config: dict):
        """Validate a single mode configuration"""
        if not isinstance(mode_config, dict):
            self.errors.append(f"Mode '{mode_name}' must be a dictionary")
            return
        
        # Check description
        if 'description' not in mode_config:
            self.warnings.append(f"Mode '{mode_name}' is missing 'description'")
        
        # Validate remote_cache
        if 'remote_cache' in mode_config:
            rc = mode_config['remote_cache']
            if not isinstance(rc, dict):
                self.errors.append(f"Mode '{mode_name}'.remote_cache must be a dictionary")
            else:
                if 'enabled' in rc and not isinstance(rc['enabled'], bool):
                    self.errors.append(f"Mode '{mode_name}'.remote_cache.enabled must be a boolean")
                if 'ttl_minutes' in rc and not isinstance(rc['ttl_minutes'], (int, float)):
                    self.errors.append(f"Mode '{mode_name}'.remote_cache.ttl_minutes must be a number")
        
        # Validate fidelity rules
        if 'fidelity' in mode_config and 'rules' in mode_config['fidelity']:
            rules = mode_config['fidelity']['rules']
            if not isinstance(rules, list):
                self.errors.append(f"Mode '{mode_name}'.fidelity.rules must be a list")
            else:
                for i, rule in enumerate(rules):
                    if 'use' in rule and rule['use'] not in self.VALID_FIDELITY_VALUES:
                        self.errors.append(
                            f"Mode '{mode_name}'.fidelity.rules[{i}].use must be one of: {self.VALID_FIDELITY_VALUES}"
                        )


def validate_policy_file(policy_path: Path) -> Tuple[bool, dict, List[str], List[str]]:
    """
    Load and validate a policy file.
    Returns: (is_valid, policy_dict, errors, warnings)
    """
    errors = []
    warnings = []
    
    if not policy_path.exists():
        return False, {}, [f"Policy file not found: {policy_path}"], []
    
    try:
        with open(policy_path, 'r', encoding='utf-8') as f:
            policy = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return False, {}, [f"YAML parsing error: {e}"], []
    
    if policy is None:
        return False, {}, ["Policy file is empty"], []
    
    validator = PolicyValidator()
    is_valid, errors, warnings = validator.validate(policy)
    
    return is_valid, policy, errors, warnings


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

class Fidelity:
    FULL = "full"
    SKELETON = "skeleton"
    DIFF = "diff"
    SUMMARY = "summary"
    OMIT = "omit"
    VOLATILE = "volatile"


@dataclass
class FileDecision:
    """Decision about how to handle a file in the cache"""
    path: str
    fidelity: str
    reason: str
    rule_name: str
    token_estimate: int
    dependency_count: int
    core_score: float
    file_chars: int
    is_volatile: bool
    last_modified: float


@dataclass
class CacheEntry:
    """Represents a single cache entry in the ledger"""
    payload_hash: str
    cache_id: Optional[str]
    version: int
    token_count: int
    created_at: str
    expires_at: Optional[str]
    status: str
    mode: str
    fidelity_mix: Dict[str, int]
    qache_id: Optional[str] = None  # The qage-based cache identifier


@dataclass
class Manifest:
    """Local truth of cache state"""
    qage_id: str
    qache_id: str  # Base qache identifier: qache_{qage_id}
    policy_version: int
    active_mode: str
    last_sync: Optional[str]
    active_cache: Optional[Dict[str, Any]]
    current_version: int
    fidelity_stats: Dict[str, Any]
    created_at: str  # When this qage's cache was first created
    
    @classmethod
    def default(cls, qage_id: str) -> 'Manifest':
        """
        Generate qache_id from qage_id.
        
        Format: qache_{sanitized_qage_id}
        
        Examples:
            qage_20251222_143522 -> qache_qage_20251222_143522
            my-project           -> qache_my-project_20251222_143522
        """
        # Sanitize qage_id for use in cache name (keep alphanumeric, underscore, hyphen)
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', qage_id)
        
        # Check if qage_id already has a timestamp pattern (YYYYMMDD or similar)
        has_timestamp = bool(re.search(r'\d{8}', qage_id))
        
        if has_timestamp:
            # qage_id already has timestamp, use directly
            qache_id = f"qache_{sanitized}"
        else:
            # Add timestamp for uniqueness
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            qache_id = f"qache_{sanitized}_{timestamp}"
        
        return cls(
            qage_id=qage_id,
            qache_id=qache_id,
            policy_version=1,
            active_mode='local_smart',
            last_sync=None,
            active_cache=None,
            current_version=0,
            fidelity_stats={},
            created_at=datetime.now(timezone.utc).isoformat()
        )
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Manifest':
        # Handle backwards compatibility for older manifests
        if 'qache_id' not in data:
            sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', data.get('qage_id', 'unknown'))
            data['qache_id'] = f"qache_{sanitized}"
        if 'created_at' not in data:
            data['created_at'] = datetime.now(timezone.utc).isoformat()
        return cls(**data)


# ═══════════════════════════════════════════════════════════════════════════════
# SQLITE LEDGER
# ═══════════════════════════════════════════════════════════════════════════════

class CacheLedger:
    """SQLite-backed ledger for cache ID tracking"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_hash TEXT UNIQUE NOT NULL,
                cache_id TEXT,
                qache_id TEXT,
                version INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                status TEXT NOT NULL,
                mode TEXT,
                fidelity_mix TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payload_hash ON cache_entries(payload_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON cache_entries(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_qache_id ON cache_entries(qache_id)')
        
        # Add qache_id column if it doesn't exist (migration)
        try:
            cursor.execute('ALTER TABLE cache_entries ADD COLUMN qache_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.commit()
        conn.close()
    
    def get_by_hash(self, payload_hash: str) -> Optional[CacheEntry]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT payload_hash, cache_id, version, token_count, created_at, expires_at, status, mode, fidelity_mix, qache_id '
            'FROM cache_entries WHERE payload_hash = ?',
            (payload_hash,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            fidelity_mix = json.loads(row[8]) if row[8] else {}
            return CacheEntry(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7] or '', fidelity_mix, row[9])
        return None
    
    def get_active(self) -> Optional[CacheEntry]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT payload_hash, cache_id, version, token_count, created_at, expires_at, status, mode, fidelity_mix, qache_id '
            'FROM cache_entries WHERE status = "synced" ORDER BY version DESC LIMIT 1'
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            fidelity_mix = json.loads(row[8]) if row[8] else {}
            return CacheEntry(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7] or '', fidelity_mix, row[9])
        return None
    
    def insert(self, entry: CacheEntry):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO cache_entries 
            (payload_hash, cache_id, qache_id, version, token_count, created_at, expires_at, status, mode, fidelity_mix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry.payload_hash, entry.cache_id, entry.qache_id, entry.version, entry.token_count,
            entry.created_at, entry.expires_at, entry.status, entry.mode, json.dumps(entry.fidelity_mix)
        ))
        conn.commit()
        conn.close()
    
    def update_status(self, payload_hash: str, status: str, cache_id: str = None, expires_at: str = None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if cache_id and expires_at:
            cursor.execute(
                'UPDATE cache_entries SET status = ?, cache_id = ?, expires_at = ? WHERE payload_hash = ?',
                (status, cache_id, expires_at, payload_hash)
            )
        else:
            cursor.execute('UPDATE cache_entries SET status = ? WHERE payload_hash = ?', (status, payload_hash))
        conn.commit()
        conn.close()
    
    def supersede_all_except(self, current_hash: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE cache_entries SET status = "superseded" WHERE status = "synced" AND payload_hash != ?',
            (current_hash,)
        )
        conn.commit()
        conn.close()
    
    def get_history(self, limit: int = 10) -> List[CacheEntry]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT payload_hash, cache_id, version, token_count, created_at, expires_at, status, mode, fidelity_mix, qache_id '
            'FROM cache_entries ORDER BY version DESC LIMIT ?',
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        entries = []
        for row in rows:
            fidelity_mix = json.loads(row[8]) if row[8] else {}
            entries.append(CacheEntry(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7] or '', fidelity_mix, row[9] if len(row) > 9 else None))
        return entries


# ═══════════════════════════════════════════════════════════════════════════════
# SYNC LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

class SyncLogger:
    def __init__(self, log_path: Path, verbose: bool = False):
        self.log_path = log_path
        self.verbose = verbose
    
    def log(self, action: str, details: str = ""):
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"[{timestamp}] {action}"
        if details:
            entry += f" | {details}"
        entry += "\n"
        
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(entry)
        
        if self.verbose:
            print(f"  [LOG] {action}: {details}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# VOLATILE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class VolatileDetector:
    """
    Detects volatile files using multiple signals:
    1. Changed files manifest (from current cycle)
    2. Git diff
    3. Briq targets
    4. Mtime fallback
    """
    
    def __init__(self, worqspace: Path, config: dict):
        self.worqspace = worqspace
        self.config = config
        self._volatile_set: Optional[Set[str]] = None
    
    def _get_changed_files_from_manifest(self) -> Set[str]:
        """Get files from changed files manifest (e.g., exeq.d/*_changed.md)"""
        changed = set()
        pattern = self.config.get('changed_files_pattern', 'exeq.d/*_changed.md')
        
        for manifest_path in self.worqspace.glob(pattern):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Extract file paths from backticks or common patterns
                matches = re.findall(r'`([^`]+\.[a-zA-Z0-9]+)`', content)
                for match in matches:
                    changed.add(match)
            except Exception:
                pass
        
        return changed
    
    def _get_changed_files_from_git(self) -> Set[str]:
        """Get files from git diff"""
        changed = set()
        base = self.config.get('git_diff_base', 'HEAD')
        
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', base],
                cwd=str(self.worqspace / 'qodeyard'),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        changed.add(line)
        except Exception:
            pass
        
        return changed
    
    def _get_briq_targets(self) -> Set[str]:
        """Get files targeted by current briq"""
        targets = set()
        pattern = self.config.get('briq_pattern', 'briq.d/*.md')
        
        for briq_path in self.worqspace.glob(pattern):
            try:
                with open(briq_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Extract file paths
                matches = re.findall(r'(?:create|modify|edit|update|fix)\s+[`"]?([^`"\s]+\.[a-zA-Z0-9]+)', content, re.IGNORECASE)
                for match in matches:
                    targets.add(match)
            except Exception:
                pass
        
        return targets
    
    def _build_volatile_set(self) -> Set[str]:
        """Build the complete set of volatile files"""
        volatile = set()
        
        if self.config.get('use_changed_files_manifest', True):
            volatile.update(self._get_changed_files_from_manifest())
        
        if self.config.get('use_git_diff_if_available', True):
            volatile.update(self._get_changed_files_from_git())
        
        if self.config.get('use_briq_targets', True):
            volatile.update(self._get_briq_targets())
        
        return volatile
    
    def is_volatile(self, file_path: Path, rel_path: str) -> Tuple[bool, str]:
        """
        Check if a file is volatile.
        Returns: (is_volatile, reason)
        """
        # Build volatile set on first call
        if self._volatile_set is None:
            self._volatile_set = self._build_volatile_set()
        
        # Check against volatile set
        if rel_path in self._volatile_set:
            return True, "In changed files manifest"
        
        # Check path components
        for vol_path in self._volatile_set:
            if vol_path in rel_path or rel_path.endswith(vol_path):
                return True, "Matches changed file pattern"
        
        # Mtime fallback
        if self.config.get('use_mtime_fallback', True):
            mtime_minutes = self.config.get('mtime_minutes', 15)
            try:
                mtime = file_path.stat().st_mtime
                mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                threshold = datetime.now(timezone.utc) - timedelta(minutes=mtime_minutes)
                if mtime_dt > threshold:
                    return True, f"Modified within last {mtime_minutes} minutes"
            except Exception:
                pass
        
        return False, ""


# ═══════════════════════════════════════════════════════════════════════════════
# FIDELITY RULES ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class FidelityRulesEngine:
    """Evaluates fidelity rules from policy to decide file treatment"""
    
    def __init__(self, rules: List[dict], defaults: dict):
        self.rules = rules
        self.defaults = defaults
    
    def evaluate(self, file_info: dict) -> Tuple[str, str]:
        """
        Evaluate rules against file info.
        Returns: (fidelity, rule_name)
        """
        for rule in self.rules:
            rule_name = rule.get('name', 'unnamed')
            conditions = rule.get('when', {})
            
            if self._matches_conditions(file_info, conditions):
                return rule.get('use', Fidelity.SKELETON), rule_name
        
        # Default fallback
        return Fidelity.SKELETON, 'default_fallback'
    
    def _matches_conditions(self, file_info: dict, conditions: dict) -> bool:
        """Check if file_info matches all conditions"""
        if not conditions:
            return True  # Empty conditions = match all
        
        for key, expected in conditions.items():
            actual = file_info.get(key)
            
            # Handle comparison operators
            if key.endswith('_gte'):
                actual_key = key[:-4]
                actual = file_info.get(actual_key, 0)
                if actual < expected:
                    return False
            elif key.endswith('_lte'):
                actual_key = key[:-4]
                actual = file_info.get(actual_key, float('inf'))
                if actual > expected:
                    return False
            elif key.endswith('_gt'):
                actual_key = key[:-3]
                actual = file_info.get(actual_key, 0)
                if actual <= expected:
                    return False
            elif key.endswith('_lt'):
                actual_key = key[:-3]
                actual = file_info.get(actual_key, float('inf'))
                if actual >= expected:
                    return False
            else:
                # Exact match
                if actual != expected:
                    return False
        
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# CORE QONTRABENDER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

# Constants
QACHE_DIR = "qache.d"
PAYLOADS_DIR = "payloads"
MANIFEST_FILE = "manifest.json"
LEDGER_DB = "ledger.db"
SYNC_LOG = "sync.log"
ACTIVE_CACHE_FILE = ".active_cache_id"
DECISIONS_LOG = "decisions.log"
CHARS_PER_TOKEN = 4

CODE_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.h', '.cpp', '.cs', '.rb', '.php'}
CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.xml'}
DOC_EXTENSIONS = {'.md', '.txt', '.rst'}
SPECIAL_FILES = {'Dockerfile', 'Makefile', 'docker-compose.yml', 'docker-compose.yaml'}


class Qontrabender:
    """
    The Cache Bender - Policy-Driven Variable Fidelity Compositor
    
    Enhanced with:
    - Policy file support (caching_policy.yaml)
    - Multiple operational modes
    - Improved volatile detection
    - Fidelity rules engine
    - Schema validation
    """
    
    def __init__(self, worqspace_path: Path, mode: str = None,
                 qodeyard_path: Path = None, bloq_path: Path = None, 
                 qontext_path: Path = None, qache_path: Path = None):
        self.worqspace = worqspace_path
        self.requested_mode = mode
        
        # Load policy first
        self.policy = self._load_policy()
        self.mode = mode or self._get_default_mode()
        self.mode_config = self._get_mode_config()
        
        # Set up paths - use explicit if provided, otherwise derive from worqspace
        if qache_path:
            self.qache_path = Path(qache_path)
        else:
            qache_dir = self.policy.get('defaults', {}).get('qache_dir', QACHE_DIR)
            self.qache_path = worqspace_path / qache_dir
        
        self.payloads_path = self.qache_path / PAYLOADS_DIR
        self.manifest_path = self.qache_path / MANIFEST_FILE
        self.ledger_path = self.qache_path / LEDGER_DB
        self.log_path = self.qache_path / SYNC_LOG
        self.active_cache_path = self.qache_path / ACTIVE_CACHE_FILE
        self.decisions_log_path = self.qache_path / DECISIONS_LOG
        
        # Source directories - use explicit if provided
        self.qodeyard_path = Path(qodeyard_path) if qodeyard_path else worqspace_path / "qodeyard"
        self.bloq_path = Path(bloq_path) if bloq_path else worqspace_path / "bloq.d"
        self.qontext_path = Path(qontext_path) if qontext_path else worqspace_path / "qontext.d"
        
        # Initialize components
        self._ensure_structure()
        self.manifest = self._load_manifest()
        self.ledger = CacheLedger(self.ledger_path)
        
        # Get logging config
        logging_config = self._get_merged_config('logging', {})
        self.verbose = logging_config.get('verbose_decisions', False)
        self.logger = SyncLogger(self.log_path, self.verbose)
        
        # Initialize volatile detector
        volatile_config = self._get_merged_config('volatile_detection', {})
        self.volatile_detector = VolatileDetector(worqspace_path, volatile_config)
        
        # Initialize fidelity rules engine
        fidelity_config = self.mode_config.get('fidelity', {})
        rules = fidelity_config.get('rules', [{'name': 'default', 'when': {}, 'use': 'skeleton'}])
        self.fidelity_engine = FidelityRulesEngine(rules, self.policy.get('defaults', {}))
    
    def _load_policy(self) -> dict:
        """Load and validate policy file"""
        # Try to find policy file
        policy_paths = [
            self.worqspace / 'caching_policy.yaml',
            self.worqspace / '.qonqrete' / 'caching_policy.yaml',
        ]
        
        # Also check config.yaml for custom path
        config_path = self.worqspace / 'config.yaml'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                custom_path = config.get('agents', {}).get('qontrabender', {}).get('policy_file')
                if custom_path:
                    policy_paths.insert(0, self.worqspace / custom_path)
            except Exception:
                pass
        
        for policy_path in policy_paths:
            if policy_path.exists():
                is_valid, policy, errors, warnings = validate_policy_file(policy_path)
                
                if warnings:
                    for w in warnings:
                        print(f"  [WARN] Policy: {w}", flush=True)
                
                if not is_valid:
                    print(f"  [ERROR] Policy validation failed:", flush=True)
                    for e in errors:
                        print(f"    - {e}", flush=True)
                    print(f"  [INFO] Using built-in defaults", flush=True)
                    return self._get_builtin_policy()
                
                return policy
        
        # No policy file found - use built-in defaults
        return self._get_builtin_policy()
    
    def _get_builtin_policy(self) -> dict:
        """Return built-in default policy"""
        return {
            'version': 1,
            'defaults': {
                'qache_dir': QACHE_DIR,
                'volatile_detection': {
                    # Conservative defaults for local-first operation
                    # Files just built are STABLE, not volatile
                    'use_changed_files_manifest': False,  # Don't mark just-built files as volatile
                    'use_git_diff_if_available': False,   # Enable for cyber_* modes
                    'use_mtime_fallback': False,          # Causes empty caches post-build
                    'mtime_minutes': 5,
                    'use_briq_targets': True,             # Only files ABOUT TO change are volatile
                },
                'budgets': {
                    'cached_max_chars': 1800000,
                    'cached_target_chars': 1200000,
                },
                'classification': {
                    'thresholds': {
                        'core_score_min': 0.65,
                        'massive_chars_min': 220000,
                    }
                },
                'paths': {
                    'exclude_globs': ['**/.git/**', '**/__pycache__/**', '**/node_modules/**'],
                }
            },
            'modes': {
                'local_smart': {
                    'description': 'Default mode with variable fidelity',
                    'remote_cache': {'enabled': False},
                    'fidelity': {
                        'rules': [
                            {'name': 'stable_core_full', 'when': {'volatile': False, 'core_score_gte': 0.65, 'file_chars_lte': 200000}, 'use': 'full'},
                            {'name': 'massive_skeleton', 'when': {'file_chars_gte': 220000}, 'use': 'skeleton'},
                            {'name': 'default', 'when': {}, 'use': 'skeleton'},
                        ]
                    }
                }
            }
        }
    
    def _get_default_mode(self) -> str:
        """Get default mode from config or policy"""
        # Check config.yaml first
        config_path = self.worqspace / 'config.yaml'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                mode = config.get('agents', {}).get('qontrabender', {}).get('mode')
                if mode:
                    return mode
            except Exception:
                pass
        
        # Return first mode in policy
        modes = self.policy.get('modes', {})
        if modes:
            return list(modes.keys())[0]
        
        return 'local_smart'
    
    def _get_mode_config(self) -> dict:
        """Get configuration for current mode"""
        modes = self.policy.get('modes', {})
        if self.mode in modes:
            return modes[self.mode]
        
        # Fallback to first mode
        if modes:
            first_mode = list(modes.keys())[0]
            print(f"  [WARN] Mode '{self.mode}' not found, using '{first_mode}'", flush=True)
            self.mode = first_mode
            return modes[first_mode]
        
        return {}
    
    def _get_merged_config(self, key: str, default: Any = None) -> Any:
        """Get config value, merging mode overrides with defaults"""
        defaults = self.policy.get('defaults', {})
        mode_value = self.mode_config.get(key)
        default_value = defaults.get(key, default)
        
        if mode_value is None:
            return default_value
        
        if isinstance(mode_value, dict) and isinstance(default_value, dict):
            merged = default_value.copy()
            merged.update(mode_value)
            return merged
        
        return mode_value
    
    def _ensure_structure(self):
        """Ensure qache.d directory structure exists"""
        self.qache_path.mkdir(parents=True, exist_ok=True)
        self.payloads_path.mkdir(exist_ok=True)
    
    def _load_manifest(self) -> Manifest:
        """Load or create manifest"""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return Manifest.from_dict(data)
            except Exception:
                pass
        
        qage_id = self.worqspace.name
        return Manifest.default(qage_id)
    
    def _save_manifest(self):
        """Save manifest to disk"""
        self.manifest.active_mode = self.mode
        self.manifest.policy_version = self.policy.get('version', 1)
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest.to_dict(), f, indent=2)
    
    def _estimate_tokens(self, content: str) -> int:
        return len(content) // CHARS_PER_TOKEN
    
    def _hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _matches_glob(self, path: str, globs: List[str]) -> bool:
        """Check if path matches any of the glob patterns"""
        for pattern in globs:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False
    
    def _should_exclude(self, rel_path: str) -> bool:
        """Check if file should be excluded based on path patterns"""
        paths_config = self._get_merged_config('paths', {})
        exclude_globs = paths_config.get('exclude_globs', [])
        return self._matches_glob(rel_path, exclude_globs)
    
    def _load_qontext_intelligence(self, rel_path: str) -> Dict[str, Any]:
        """Load structural context intelligence from qontext.d"""
        qontext_schema = self.policy.get('qontext_schema', {})
        symbols_key = qontext_schema.get('symbols_key', 'symbols')
        deps_key = qontext_schema.get('deps_key', 'dependencies')
        inbound_refs_key = qontext_schema.get('inbound_refs_key', 'inbound_refs')
        
        possible_names = [
            self.qontext_path / f"{rel_path}.q.yaml",
            self.qontext_path / f"{Path(rel_path).name}.q.yaml",
        ]
        
        for qontext_file in possible_names:
            if qontext_file.exists():
                try:
                    with open(qontext_file, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                    
                    symbols = data.get(symbols_key, [])
                    if not isinstance(symbols, list):
                        symbols = []

                    total_deps = 0
                    for symbol in symbols:
                        if not isinstance(symbol, dict):
                            continue
                        deps = symbol.get(deps_key, [])
                        if isinstance(deps, list):
                            total_deps += len(deps)
                    top_level_deps = data.get(deps_key, [])
                    if isinstance(top_level_deps, list):
                        total_deps += len(top_level_deps)

                    inbound_refs_raw = data.get(inbound_refs_key, [])
                    inbound_refs_count = 0
                    if isinstance(inbound_refs_raw, list):
                        inbound_refs_count = len([item for item in inbound_refs_raw if str(item).strip()])
                    elif isinstance(inbound_refs_raw, (int, float)):
                        inbound_refs_count = max(0, int(inbound_refs_raw))

                    return {
                        'dependency_count': total_deps,
                        'symbol_count': len(symbols),
                        'inbound_refs': inbound_refs_count,
                        'has_qontext': True
                    }
                except Exception:
                    pass
        
        return {'dependency_count': 0, 'symbol_count': 0, 'inbound_refs': 0, 'has_qontext': False}
    
    def _calculate_core_score(self, file_info: dict) -> float:
        """Calculate core utility score for a file"""
        classification = self._get_merged_config('classification', {})
        signals = classification.get('signals', {})
        
        dep_weight = signals.get('dependency_rank_weight', 0.50)
        sym_weight = signals.get('symbol_count_weight', 0.20)
        ref_weight = signals.get('inbound_refs_weight', 0.20)
        doc_weight = signals.get('doc_presence_weight', 0.10)
        
        # Normalize values (assuming max values for scoring)
        dep_score = min(file_info.get('dependency_count', 0) / 20.0, 1.0)
        sym_score = min(file_info.get('symbol_count', 0) / 50.0, 1.0)
        ref_score = min(file_info.get('inbound_refs', 0) / 10.0, 1.0)
        doc_score = 1.0 if file_info.get('has_docstrings', False) else 0.0
        
        return (dep_score * dep_weight + sym_score * sym_weight + 
                ref_score * ref_weight + doc_score * doc_weight)
    
    def _should_include_file(self, file_path: Path) -> bool:
        """Check if a file should be considered for caching"""
        if is_source_junk_file(file_path):
            return False
        if any(part in INFRA_DIR_NAMES for part in file_path.parts):
            return False
        if any(part.startswith('.') for part in file_path.parts):
            return False
        
        suffix = file_path.suffix.lower()
        name = file_path.name
        
        return (suffix in CODE_EXTENSIONS or 
                suffix in CONFIG_EXTENSIONS or 
                suffix in DOC_EXTENSIONS or 
                name in SPECIAL_FILES)
    
    def analyze_files(self) -> List[FileDecision]:
        """Analyze all files and decide their fidelity levels"""
        decisions = []
        
        if not self.qodeyard_path.exists():
            print(f"  [ERROR] qodeyard not found: {self.qodeyard_path}", flush=True)
            return decisions
        
        print(f"  - Analyzing files (mode: {self.mode})...", flush=True)
        
        for root, dirs, files in os.walk(self.qodeyard_path):
            dirs[:] = [
                d for d in dirs
                if d not in INFRA_DIR_NAMES and not is_generated_output_dir(Path(root) / d)
            ]
            for file in files:
                file_path = Path(root) / file
                
                if not self._should_include_file(file_path):
                    continue
                
                rel_path = str(file_path.relative_to(self.qodeyard_path))
                
                if self._should_exclude(rel_path):
                    continue
                
                decision = self._decide_fidelity(file_path, rel_path)
                decisions.append(decision)
        
        return decisions
    
    def _has_docstrings(self, content: str, suffix: str) -> bool:
        """Detect doc presence conservatively; never assume unknown content is documented."""
        if not content:
            return False
        
        if suffix == '.py':
            try:
                tree = ast.parse(content)
            except Exception:
                return False

            if ast.get_docstring(tree):
                return True
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if ast.get_docstring(node):
                        return True
            return False
        
        if suffix in {'.js', '.ts', '.java', '.c', '.cpp', '.cs'}:
            return bool(re.search(r'/\*\*[\s\S]*?\*/', content))
        
        if suffix in {'.md', '.rst', '.txt'}:
            # Documentation files count only when they contain meaningful prose.
            return bool(re.search(r'[A-Za-z]{4,}', content))
            
        return False

    def _decide_fidelity(self, file_path: Path, rel_path: str) -> FileDecision:
        """Decide fidelity for a single file using the rules engine"""
        # Get file metadata
        try:
            mtime = file_path.stat().st_mtime
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            file_chars = len(content)
            token_est = self._estimate_tokens(content)
            has_docstrings = self._has_docstrings(content, file_path.suffix.lower())
        except Exception:
            mtime = 0.0
            file_chars = 0
            token_est = 0
            has_docstrings = False
        
        # Check volatility
        is_volatile, volatile_reason = self.volatile_detector.is_volatile(file_path, rel_path)
        
        # Load qontext intelligence
        intel = self._load_qontext_intelligence(rel_path)
        dep_count = intel['dependency_count']
        sym_count = intel['symbol_count']
        inbound_refs = intel.get('inbound_refs', 0)
        
        # Calculate core score
        file_info = {
            'dependency_count': dep_count,
            'symbol_count': sym_count,
            'inbound_refs': inbound_refs,
            'has_docstrings': has_docstrings,
        }
        core_score = self._calculate_core_score(file_info)
        
        # Check if volatile (always exclude from cache)
        if is_volatile:
            return FileDecision(
                path=rel_path,
                fidelity=Fidelity.VOLATILE,
                reason=volatile_reason,
                rule_name='volatile_check',
                token_estimate=token_est,
                dependency_count=dep_count,
                core_score=core_score,
                file_chars=file_chars,
                is_volatile=True,
                last_modified=mtime
            )
        
        # Build file info for rules engine
        rules_info = {
            'volatile': False,
            'file_chars': file_chars,
            'core_score': core_score,
            'dependency_count': dep_count,
            'symbol_count': sym_count,
            'tier': 'stable',  # Non-volatile = stable
        }
        
        # Evaluate rules
        fidelity, rule_name = self.fidelity_engine.evaluate(rules_info)
        
        # Determine reason based on fidelity
        if fidelity == Fidelity.FULL:
            reason = f"Core logic (score={core_score:.2f}, deps={dep_count})"
        elif fidelity == Fidelity.SKELETON:
            if file_chars > 200000:
                reason = f"Massive file ({file_chars:,} chars)"
            else:
                reason = "Default skeleton fidelity"
        else:
            reason = f"Rule: {rule_name}"
        
        return FileDecision(
            path=rel_path,
            fidelity=fidelity,
            reason=reason,
            rule_name=rule_name,
            token_estimate=token_est,
            dependency_count=dep_count,
            core_score=core_score,
            file_chars=file_chars,
            is_volatile=False,
            last_modified=mtime
        )
    
    def assemble_payload(self) -> Tuple[str, str, int, Dict[str, int]]:
        """Assemble cache payload with variable fidelity"""
        decisions = self.analyze_files()
        
        if not decisions:
            return None, None, 0, {}
        
        payload_parts = []
        fidelity_mix = {'full': 0, 'skeleton': 0, 'volatile': 0}
        total_tokens = 0
        
        render_config = self._get_merged_config('render', {})
        file_wrapper = render_config.get('file_wrapper', 'xml')
        
        # Header
        payload_parts.append(f"<!-- QonQrete Cache Payload - Mode: {self.mode} -->")
        payload_parts.append(f"<!-- Generated: {datetime.now(timezone.utc).isoformat()} -->")
        payload_parts.append(f"<!-- Qage: {self.manifest.qage_id} -->")
        payload_parts.append(f"<!-- Policy Version: {self.policy.get('version', 1)} -->")
        payload_parts.append("")
        
        # Separate by fidelity
        full_files = [d for d in decisions if d.fidelity == Fidelity.FULL]
        skeleton_files = [d for d in decisions if d.fidelity == Fidelity.SKELETON]
        volatile_files = [d for d in decisions if d.fidelity == Fidelity.VOLATILE]
        
        # Log volatile files
        if volatile_files:
            payload_parts.append("<!-- VOLATILE FILES (excluded - sent fresh via stdin): -->")
            for d in volatile_files:
                payload_parts.append(f"<!--   - {d.path} ({d.reason}) -->")
                fidelity_mix['volatile'] += 1
            payload_parts.append("")
        
        # FULL FIDELITY FILES
        if full_files:
            payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
            payload_parts.append("<!-- FULL FIDELITY (Complete Implementation from qodeyard)  -->")
            payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
            payload_parts.append("")
            
            for d in sorted(full_files, key=lambda x: -x.core_score):
                source_path = self.qodeyard_path / d.path
                if not source_path.exists():
                    continue
                
                try:
                    with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    tokens = self._estimate_tokens(content)
                    total_tokens += tokens
                    fidelity_mix['full'] += 1
                    
                    if file_wrapper == 'xml':
                        payload_parts.append(f'<file path="{d.path}" fidelity="full" score="{d.core_score:.2f}" deps="{d.dependency_count}">')
                        payload_parts.append(content)
                        payload_parts.append('</file>')
                    else:
                        payload_parts.append(f"### FILE: {d.path} (full, score={d.core_score:.2f})")
                        payload_parts.append("```")
                        payload_parts.append(content)
                        payload_parts.append("```")
                    payload_parts.append("")
                    
                except Exception as e:
                    payload_parts.append(f"<!-- ERROR reading {d.path}: {e} -->")
        
        # SKELETON FIDELITY FILES
        if skeleton_files:
            payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
            payload_parts.append("<!-- SKELETON FIDELITY (Signatures Only from bloq.d)        -->")
            payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
            payload_parts.append("")
            
            for d in sorted(skeleton_files, key=lambda x: x.path):
                skeleton_path = self.bloq_path / d.path
                source_path = skeleton_path if skeleton_path.exists() else self.qodeyard_path / d.path
                
                if not source_path.exists():
                    continue
                
                try:
                    with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    tokens = self._estimate_tokens(content)
                    total_tokens += tokens
                    fidelity_mix['skeleton'] += 1
                    
                    if file_wrapper == 'xml':
                        payload_parts.append(f'<skeleton path="{d.path}" fidelity="skeleton" reason="{d.reason}">')
                        payload_parts.append(content)
                        payload_parts.append('</skeleton>')
                    else:
                        payload_parts.append(f"### SKELETON: {d.path}")
                        payload_parts.append("```")
                        payload_parts.append(content)
                        payload_parts.append("```")
                    payload_parts.append("")
                    
                except Exception as e:
                    payload_parts.append(f"<!-- ERROR reading {d.path}: {e} -->")
        
        # Footer
        payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
        payload_parts.append(f"<!-- STATS: {fidelity_mix['full']} full, {fidelity_mix['skeleton']} skeleton, {fidelity_mix['volatile']} volatile -->")
        payload_parts.append(f"<!-- TOKENS: ~{total_tokens:,} -->")
        payload_parts.append(f"<!-- MODE: {self.mode} -->")
        payload_parts.append("<!-- ═══════════════════════════════════════════════════════ -->")
        
        payload_content = "\n".join(payload_parts)
        payload_hash = self._hash_content(payload_content)
        
        # Update manifest stats
        self.manifest.fidelity_stats = {
            'full_files': fidelity_mix['full'],
            'skeleton_files': fidelity_mix['skeleton'],
            'volatile_files': fidelity_mix['volatile'],
            'total_tokens': total_tokens,
            'mode': self.mode
        }
        
        print(f"  - Payload assembled: {total_tokens:,} tokens (hash: {payload_hash[:12]}...)", flush=True)
        print(f"    └─ 🥩 FULL: {fidelity_mix['full']} files", flush=True)
        print(f"    └─ 🦴 SKELETON: {fidelity_mix['skeleton']} files", flush=True)
        print(f"    └─ ⚡ VOLATILE: {fidelity_mix['volatile']} files (excluded)", flush=True)
        
        # Log decisions if verbose
        if self.verbose:
            self._log_decisions(decisions)
        
        return payload_content, payload_hash, total_tokens, fidelity_mix
    
    def _log_decisions(self, decisions: List[FileDecision]):
        """Log detailed decisions to file"""
        with open(self.decisions_log_path, 'w', encoding='utf-8') as f:
            f.write(f"# Qontrabender Decisions Log\n")
            f.write(f"# Mode: {self.mode}\n")
            f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n\n")
            
            for d in sorted(decisions, key=lambda x: x.path):
                f.write(f"## {d.path}\n")
                f.write(f"  Fidelity: {d.fidelity}\n")
                f.write(f"  Rule: {d.rule_name}\n")
                f.write(f"  Reason: {d.reason}\n")
                f.write(f"  Core Score: {d.core_score:.2f}\n")
                f.write(f"  Dependencies: {d.dependency_count}\n")
                f.write(f"  Size: {d.file_chars:,} chars (~{d.token_estimate:,} tokens)\n")
                f.write(f"  Volatile: {d.is_volatile}\n\n")
    
    def check_sync_needed(self) -> Tuple[bool, str, str]:
        """Check if a sync is needed"""
        payload_content, payload_hash, token_count, _ = self.assemble_payload()
        
        if not payload_hash:
            return False, "No payload could be assembled", None
        
        existing = self.ledger.get_by_hash(payload_hash)
        if existing:
            if existing.status == 'synced':
                if existing.expires_at:
                    expires = datetime.fromisoformat(existing.expires_at.replace('Z', '+00:00'))
                    rc = self.mode_config.get('remote_cache', {})
                    keepalive = rc.get('keepalive', {})
                    threshold_mins = keepalive.get('refresh_when_remaining_minutes_lte', 15)
                    threshold = timedelta(minutes=threshold_mins)
                    if datetime.now(timezone.utc) > expires - threshold:
                        return True, "Cache TTL expiring soon", payload_hash
                return False, f"Payload unchanged (v{existing.version}, synced)", payload_hash
            elif existing.status == 'local':
                return True, "Payload assembled but not synced", payload_hash
        
        return True, "New payload - content changed", payload_hash
    
    def get_qache_id(self) -> str:
        """Get the qache_id for this qage (one cache per qage)"""
        return self.manifest.qache_id
    
    def generate_versioned_qache_id(self, version: int) -> str:
        """Generate a versioned qache_id for a specific payload version"""
        # Format: qache_{qage_name}_{timestamp}_v{version}
        return f"{self.manifest.qache_id}_v{version}"
    
    def save_payload(self, payload_content: str, payload_hash: str, token_count: int, fidelity_mix: Dict[str, int]) -> int:
        """Save payload to disk"""
        self.manifest.current_version += 1
        version = self.manifest.current_version
        
        # Generate versioned qache_id for this payload
        qache_id = self.generate_versioned_qache_id(version)
        
        payload_file = self.payloads_path / f"payload_v{version}.txt"
        with open(payload_file, 'w', encoding='utf-8') as f:
            f.write(payload_content)
        
        entry = CacheEntry(
            payload_hash=payload_hash,
            cache_id=None,  # Will be set when synced to remote
            version=version,
            token_count=token_count,
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=None,
            status='local',
            mode=self.mode,
            fidelity_mix=fidelity_mix,
            qache_id=qache_id
        )
        self.ledger.insert(entry)
        self._save_manifest()
        
        self.logger.log("PAYLOAD_SAVED", f"qache={qache_id} mode={self.mode} hash={payload_hash[:12]}... tokens={token_count:,}")
        
        print(f"  - Payload saved: {qache_id} -> {payload_file.name}", flush=True)
        return version
    
    def mark_synced(self, payload_hash: str, cache_id: str = None, ttl_minutes: int = None):
        """
        Mark a payload as synced with remote cache.
        
        If cache_id is not provided, uses the qache_id from the entry.
        This allows one cache per qage, updated on cycles.
        """
        if ttl_minutes is None:
            rc = self.mode_config.get('remote_cache', {})
            ttl_minutes = rc.get('ttl_minutes', 60)
        
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
        
        # Get the entry to retrieve qache_id
        entry = self.ledger.get_by_hash(payload_hash)
        if not entry:
            print(f"  [ERROR] No entry found for hash: {payload_hash[:12]}...", flush=True)
            return
        
        # Use provided cache_id or fall back to qache_id
        effective_cache_id = cache_id or entry.qache_id or self.generate_versioned_qache_id(entry.version)
        
        self.ledger.update_status(payload_hash, 'synced', effective_cache_id, expires_at)
        self.ledger.supersede_all_except(payload_hash)
        
        self.manifest.active_cache = {
            'cache_id': effective_cache_id,
            'qache_id': entry.qache_id,
            'payload_hash': payload_hash,
            'payload_version': entry.version,
            'token_count': entry.token_count,
            'expires_at': expires_at,
            'mode': self.mode,
            'fidelity_mix': entry.fidelity_mix
        }
        self.manifest.last_sync = datetime.now(timezone.utc).isoformat()
        self._save_manifest()
        
        with open(self.active_cache_path, 'w') as f:
            f.write(effective_cache_id)
        
        self.logger.log("SYNC_COMPLETE", f"qache={effective_cache_id} mode={self.mode} expires={expires_at}")
        print(f"  - Marked as synced: {effective_cache_id}", flush=True)
    
    def get_active_cache_id(self) -> Optional[str]:
        """Get active cache ID"""
        if self.active_cache_path.exists():
            with open(self.active_cache_path, 'r') as f:
                return f.read().strip()
        if self.manifest.active_cache:
            return self.manifest.active_cache.get('cache_id')
        return None
    
    def get_status(self) -> dict:
        """Get current cache status"""
        active = self.ledger.get_active()
        history = self.ledger.get_history(5)
        
        rc = self.mode_config.get('remote_cache', {})
        
        return {
            'qage_id': self.manifest.qage_id,
            'qache_id': self.manifest.qache_id,
            'created_at': self.manifest.created_at,
            'last_sync': self.manifest.last_sync,
            'policy_version': self.policy.get('version', 1),
            'active_mode': self.mode,
            'mode_description': self.mode_config.get('description', ''),
            'remote_cache_enabled': rc.get('enabled', False),
            'current_version': self.manifest.current_version,
            'fidelity_stats': self.manifest.fidelity_stats,
            'active_cache': {
                'cache_id': active.cache_id,
                'qache_id': active.qache_id,
                'version': active.version,
                'token_count': active.token_count,
                'expires_at': active.expires_at,
                'mode': active.mode,
                'fidelity_mix': active.fidelity_mix,
                'hash': active.payload_hash[:12] + '...'
            } if active else None,
            'available_modes': list(self.policy.get('modes', {}).keys()),
            'history': [{
                'version': e.version,
                'qache_id': e.qache_id,
                'status': e.status,
                'tokens': e.token_count,
                'mode': e.mode,
                'fidelity': e.fidelity_mix,
                'created': e.created_at[:19]
            } for e in history]
        }
    
    def get_payload_for_sync(self) -> Optional[Tuple[str, str, int]]:
        """Get payload for syncing"""
        payload_content, payload_hash, token_count, fidelity_mix = self.assemble_payload()
        
        if not payload_hash:
            return None
        
        existing = self.ledger.get_by_hash(payload_hash)
        if existing and existing.status == 'synced':
            payload_file = self.payloads_path / f"payload_v{existing.version}.txt"
            if payload_file.exists():
                with open(payload_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, existing.payload_hash, existing.version
        
        version = self.save_payload(payload_content, payload_hash, token_count, fidelity_mix)
        return payload_content, payload_hash, version
    
    def generate_sync_instructions(self) -> str:
        """Generate sync instructions"""
        payload_info = self.get_payload_for_sync()
        
        if not payload_info:
            return "No payload available for sync."
        
        content, payload_hash, version = payload_info
        payload_file = self.payloads_path / f"payload_v{version}.txt"
        fidelity = self.manifest.fidelity_stats
        rc = self.mode_config.get('remote_cache', {})
        qache_id = self.generate_versioned_qache_id(version)
        
        return f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           QONTRABENDER SYNC INSTRUCTIONS (Enhanced v0.8.0)                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Qage:    {self.manifest.qage_id:<30}                          ║
║  Qache:   {qache_id:<50}     ║
║                                                                              ║
║  Mode: {self.mode:<20} Remote Cache: {'ENABLED' if rc.get('enabled') else 'DISABLED':<10}             ║
║  Payload: v{version:<5}  Hash: {payload_hash[:20]}...                ║
║  File: {payload_file.name:<30}                              ║
║                                                                              ║
║  FIDELITY MIX:                                                               ║
║    🥩 FULL (meat):     {fidelity.get('full_files', 0):>4} files  (complete implementation)       ║
║    🦴 SKELETON (bones): {fidelity.get('skeleton_files', 0):>4} files  (signatures only)            ║
║    ⚡ VOLATILE:         {fidelity.get('volatile_files', 0):>4} files  (excluded, via stdin)        ║
║    📊 TOTAL TOKENS:    ~{fidelity.get('total_tokens', 0):>6,}                                    ║
║                                                                              ║
║  To sync with Gemini Context Caching:                                        ║
║  1. Upload payload file to Google File API or GCS                            ║
║  2. Create CachedContent resource with name: {qache_id:<20}      ║
║  3. Run: python qontrabender.py --mark-synced                                ║
║     (or: python qontrabender.py --mark-synced <provider_cache_id>)           ║
║                                                                              ║
║  NOTE: One qache per qage - cache is updated on cycles when content changes  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def print_status(qb: Qontrabender):
    """Print formatted status"""
    status = qb.get_status()
    
    print("\n" + "═" * 75)
    print(f"  QONTRABENDER STATUS: {status['qage_id']} (v0.8.0)")
    print("═" * 75)
    print(f"  Qache ID           : {status['qache_id']}")
    print(f"  Created            : {status['created_at'][:19]}")
    print(f"  Last Sync          : {status['last_sync'][:19] if status['last_sync'] else 'Never'}")
    print(f"  Policy Version     : {status['policy_version']}")
    print(f"  Active Mode        : {status['active_mode']}")
    print(f"  Mode Description   : {status['mode_description'][:50]}...")
    print(f"  Remote Cache       : {'ENABLED' if status['remote_cache_enabled'] else 'DISABLED'}")
    print(f"  Payload Version    : {status['current_version']}")
    print(f"  Available Modes    : {', '.join(status['available_modes'])}")
    
    fs = status.get('fidelity_stats', {})
    if fs:
        print(f"\n  FIDELITY STATS:")
        print(f"    🥩 Full files      : {fs.get('full_files', 0)}")
        print(f"    🦴 Skeleton files  : {fs.get('skeleton_files', 0)}")
        print(f"    ⚡ Volatile files  : {fs.get('volatile_files', 0)}")
        print(f"    📊 Total tokens   : {fs.get('total_tokens', 0):,}")
    
    if status['active_cache']:
        ac = status['active_cache']
        print(f"\n  ACTIVE CACHE:")
        print(f"    Qache   : {ac.get('qache_id', ac['cache_id'])}")
        print(f"    Version : v{ac['version']}")
        print(f"    Tokens  : {ac['token_count']:,}")
        print(f"    Mode    : {ac['mode']}")
        print(f"    Expires : {ac['expires_at'][:19] if ac['expires_at'] else 'N/A'}")
    else:
        print(f"\n  ACTIVE CACHE: None (run --sync to create)")
    
    if status['history']:
        print(f"\n  HISTORY:")
        for h in status['history']:
            mix = h['fidelity']
            mix_str = f"F:{mix.get('full', 0)} S:{mix.get('skeleton', 0)}" if mix else "N/A"
            qache_short = h.get('qache_id', '')[-15:] if h.get('qache_id') else 'N/A'
            print(f"    v{h['version']:3d} | {h['status']:10s} | {h['tokens']:>8,} tok | {qache_short}")
    
    print("═" * 75 + "\n")


def print_analysis(qb: Qontrabender):
    """Print file analysis"""
    print("\n" + "═" * 75)
    print(f"  QONTRABENDER FILE ANALYSIS (Mode: {qb.mode})")
    print("═" * 75)
    
    decisions = qb.analyze_files()
    
    full = [d for d in decisions if d.fidelity == Fidelity.FULL]
    skeleton = [d for d in decisions if d.fidelity == Fidelity.SKELETON]
    volatile = [d for d in decisions if d.fidelity == Fidelity.VOLATILE]
    
    print(f"\n  🥩 FULL FIDELITY ({len(full)} files):")
    for d in sorted(full, key=lambda x: -x.core_score)[:15]:
        print(f"    {d.path:<45} score={d.core_score:.2f} deps={d.dependency_count:<3} ~{d.token_estimate:,} tok")
    if len(full) > 15:
        print(f"    ... and {len(full) - 15} more")
    
    print(f"\n  🦴 SKELETON FIDELITY ({len(skeleton)} files):")
    for d in sorted(skeleton, key=lambda x: x.path)[:15]:
        print(f"    {d.path:<45} {d.reason[:30]}")
    if len(skeleton) > 15:
        print(f"    ... and {len(skeleton) - 15} more")
    
    print(f"\n  ⚡ VOLATILE ({len(volatile)} files - excluded):")
    for d in volatile[:15]:
        print(f"    {d.path:<45} {d.reason}")
    if len(volatile) > 15:
        print(f"    ... and {len(volatile) - 15} more")
    
    print("═" * 75 + "\n")


def print_modes(policy: dict):
    """Print available modes"""
    print("\n" + "═" * 75)
    print("  AVAILABLE MODES")
    print("═" * 75)
    
    modes = policy.get('modes', {})
    for name, config in modes.items():
        rc = config.get('remote_cache', {})
        rc_str = "☁️  Remote" if rc.get('enabled') else "💾 Local"
        desc = config.get('description', 'No description')
        print(f"\n  {name}")
        print(f"    {rc_str}")
        print(f"    {desc}")
    
    print("\n" + "═" * 75 + "\n")


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_rel_path(value: str | None) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("qodeyard/"):
        text = text[len("qodeyard/"):]
    return text


def _safe_read_text(path: Path, max_chars: int = 120000) -> str:
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated]"
    return text


def _extract_repair_targets_from_plan(repair_plan_path: str | None) -> list[str]:
    if not repair_plan_path:
        return []
    try:
        payload = json.loads(Path(repair_plan_path).read_text(encoding='utf-8'))
    except Exception:
        return []
    targets: set[str] = set()
    if isinstance(payload, dict):
        for key in ("target_files", "validation_scope_files", "allowed_edit_paths"):
            for value in payload.get(key, []) or []:
                rel = _normalize_rel_path(str(value))
                if rel:
                    targets.add(rel)
        escalation = payload.get("repair_escalation")
        if isinstance(escalation, dict):
            for value in escalation.get("target_files", []) or []:
                rel = _normalize_rel_path(str(value))
                if rel:
                    targets.add(rel)
    return sorted(targets)


def _extract_briq_targets_from_cycle(worqspace: Path, cycle_num: str) -> list[str]:
    briq_dir = worqspace / "briq.d"
    if not briq_dir.exists():
        return []
    targets: set[str] = set()
    pattern = f"cyqle{cycle_num}_*.md" if str(cycle_num or "").strip() else "*.md"
    for briq in sorted(briq_dir.glob(pattern)):
        text = _safe_read_text(briq, max_chars=250000)
        for token in re.findall(r'`([^`]+)`', text):
            rel = _normalize_rel_path(token)
            if not rel:
                continue
            if rel.startswith("/") or rel.startswith("../"):
                continue
            if "/" in rel or "." in Path(rel).name:
                targets.add(rel)
    return sorted(targets)


def _read_support_artifact(path: Path, heading: str, max_chars: int = 60000) -> str:
    if not path.exists():
        return ""
    content = _safe_read_text(path, max_chars=max_chars).strip()
    if not content:
        return ""
    return f"{heading}\nFILE: {path.name}\n```\n{content}\n```\n"


def _render_provider_aware_payloads(
    *,
    worqspace: Path,
    qodeyard_path: Path,
    bundle: list[ContextBundleItem],
    provider: str,
    model: str,
    cache_backend: str,
    pass_kind: str,
    repair_mode: bool,
    repair_plan_path: str | None,
) -> tuple[str, str]:
    stable_lines: list[str] = [
        "CACHED STABLE CONTEXT",
        f"PROVIDER: {provider}",
        f"MODEL: {model or '(unset)'}",
        f"CACHE_BACKEND: {cache_backend}",
        "BACKGROUND ONLY. If this conflicts with full hotset context, hotset wins.",
        "",
        "STRUCTURAL CONTEXT",
        "Skeletons/qontexts are navigation-only and not enough to edit from.",
        "",
    ]
    hotset_lines: list[str] = [
        "HOTSET CONTEXT",
        f"PASS_KIND: {pass_kind}",
        f"REPAIR_MODE: {'1' if repair_mode else '0'}",
        "Includes authoritative editable targets and volatile execution evidence.",
        "",
    ]

    sorted_bundle = sorted(bundle, key=lambda item: (item.fidelity, item.rel_path, item.source))
    for item in sorted_bundle:
        path_obj = Path(item.actual_path) if item.actual_path else None
        if item.fidelity in {SKELETON, QONTEXT}:
            if path_obj and path_obj.exists():
                stable_text = _safe_read_text(path_obj, max_chars=90000)
            else:
                stable_text = ""
            stable_lines.append(
                f"FILE: {item.rel_path}\nSOURCE: {item.source}\nFIDELITY: {item.fidelity}\nREASON: {item.reason}"
            )
            if stable_text:
                stable_lines.append("```")
                stable_lines.append(stable_text)
                stable_lines.append("```")
            stable_lines.append("")
            continue

        if item.fidelity in {FULL_HOTSET, FULL_NEIGHBOR, MISSING_NEW_FILE_TARGET}:
            hotset_lines.append(
                f"FILE: {item.rel_path}\nSOURCE: qodeyard\nFIDELITY: {item.fidelity}\nREASON: {item.reason}\nEDITABLE: {str(item.editable).lower()}"
            )
            if path_obj and path_obj.exists():
                hotset_lines.append("```")
                hotset_lines.append(_safe_read_text(path_obj, max_chars=120000))
                hotset_lines.append("```")
            else:
                hotset_lines.append("MISSING: true")
            hotset_lines.append("")

    if repair_plan_path:
        plan_block = _read_support_artifact(Path(repair_plan_path), "REPAIR PLAN", max_chars=120000)
        if plan_block:
            hotset_lines.append(plan_block)

    for artifact in (
        worqspace / "exeq.d" / "latest_validation.md",
        worqspace / "exeq.d" / "latest_changed.md",
    ):
        block = _read_support_artifact(artifact, "RECENT EXECUTION EVIDENCE", max_chars=60000)
        if block:
            hotset_lines.append(block)

    changed_candidates = sorted((worqspace / "exeq.d").glob("cyqle*_changed.md")) if (worqspace / "exeq.d").exists() else []
    summary_candidates = sorted((worqspace / "exeq.d").glob("cyqle*_summary.md")) if (worqspace / "exeq.d").exists() else []
    if changed_candidates:
        hotset_lines.append(_read_support_artifact(changed_candidates[-1], "CHANGED DIFF SUMMARY", max_chars=80000))
    if summary_candidates:
        hotset_lines.append(_read_support_artifact(summary_candidates[-1], "LATEST BUILD SUMMARY", max_chars=80000))

    # Deterministic project map in stable payload.
    project_map: list[str] = ["PROJECT MAP (qodeyard)"]
    for file_path in sorted(qodeyard_path.rglob("*")):
        if file_path.is_file():
            project_map.append(str(file_path.relative_to(qodeyard_path).as_posix()))
        if len(project_map) >= 600:
            project_map.append("... [truncated]")
            break
    stable_lines.extend(project_map)
    stable_lines.append("")

    return "\n".join(stable_lines).strip() + "\n", "\n".join(hotset_lines).strip() + "\n"


def _run_provider_aware_pipeline_bundle(qb: Qontrabender) -> tuple[bool, str]:
    provider = str(os.environ.get("QONQ_CONSTRUQTOR_PROVIDER", "") or "").strip().lower()
    model = str(os.environ.get("QONQ_CONSTRUQTOR_MODEL", "") or "").strip()
    pass_kind = str(os.environ.get("QONQ_PASS_KIND", "build") or "build").strip().lower()
    repair_mode = _is_truthy(os.environ.get("QONQ_REPAIR_MODE"))
    repair_plan_path = os.environ.get("QONQ_REPAIR_PLAN_PATH")
    cycle_num = str(os.environ.get("CYCLE_NUM", "") or "").strip()

    try:
        with open(qb.worqspace / "config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}
    options = cfg.get("options", {}) if isinstance(cfg, dict) else {}
    strategy_cfg = cfg.get("context_strategy", {}) if isinstance(cfg, dict) else {}
    if not isinstance(strategy_cfg, dict):
        strategy_cfg = {}
    if not provider:
        provider = str((cfg.get("agents", {}).get("construqtor", {}) or {}).get("provider", "local")).strip().lower()
    if not model:
        model = str((cfg.get("agents", {}).get("construqtor", {}) or {}).get("model", "")).strip()

    policy_provider_cache = (((qb.policy or {}).get("defaults") or {}).get("provider_cache") or {})
    cfg_provider_cache = (((cfg.get("agents", {}) or {}).get("qontrabender", {}) or {}).get("provider_cache") or {})
    provider_cache_cfg = dict(policy_provider_cache) if isinstance(policy_provider_cache, dict) else {}
    if isinstance(cfg_provider_cache, dict):
        provider_cache_cfg.update(cfg_provider_cache)

    cache_backend = resolve_qontrabender_cache_backend(
        provider=provider,
        provider_cache_cfg=provider_cache_cfg,
    )
    cache_backend_reason = "provider mapping"
    if provider in {"gemini", "google"} and cache_backend == "stable_prefix_auto":
        cache_backend_reason = "Gemini explicit cache is disabled because no real SDK-backed CachedContent path is implemented/enabled."
    elif cache_backend == "stable_prefix_auto":
        cache_backend_reason = "Provider uses stable-prefix automatic cache behavior."
    elif cache_backend == "anthropic_cache_control":
        cache_backend_reason = "Anthropic cache_control enabled for stable prefix only."
    elif cache_backend == "local_only":
        cache_backend_reason = "Provider is local or explicit provider caching is not harmless."

    repair_targets = _extract_repair_targets_from_plan(repair_plan_path) if repair_mode else []
    editable_targets = list(repair_targets)
    if not editable_targets:
        editable_targets = _extract_briq_targets_from_cycle(qb.worqspace, cycle_num)

    context_strategy = str(
        strategy_cfg.get("repair" if repair_mode else "normal", "repair_truth" if repair_mode else "hybrid_fidelity")
    ).strip().lower()
    max_neighbor_chars = int(strategy_cfg.get("direct_dependencies_full_if_small_max_chars", 90000) or 90000)
    max_full_neighbors = int(strategy_cfg.get("max_full_neighbors", 24) or 24)
    max_indirect_neighbors = int(strategy_cfg.get("max_indirect_neighbors", 40) or 40)
    try:
        repair_level = int(os.environ.get("QONQ_REPAIR_LEVEL") or 1) if repair_mode else None
    except Exception:
        repair_level = 1 if repair_mode else None

    bundle = build_context_bundle(
        qodeyard_path=qb.qodeyard_path,
        bloq_path=qb.bloq_path,
        qontext_path=qb.qontext_path,
        editable_targets=editable_targets,
        repair_targets=repair_targets,
        use_qompressor=bool(options.get("use_qompressor", True)),
        use_qontextor=bool(options.get("use_qontextor", True)),
        context_strategy=context_strategy,
        max_neighbor_full_chars=max_neighbor_chars,
        max_full_neighbors=max_full_neighbors,
        max_indirect=max_indirect_neighbors,
        repair_level=repair_level,
    )
    validate_bundle_invariants(
        bundle=bundle,
        qodeyard_path=qb.qodeyard_path,
        repair_targets=repair_targets,
    )
    if repair_targets:
        hotset_files = {
            item.rel_path
            for item in bundle
            if item.fidelity == FULL_HOTSET
        }
        missing_from_hotset = sorted(
            rel
            for rel in repair_targets
            if rel not in hotset_files and not any(
                item.rel_path == rel and item.reason == "new_file_target" for item in bundle
            )
        )
        if missing_from_hotset:
            return False, (
                "repair targets missing from hotset bundle: " + ", ".join(missing_from_hotset)
            )

    qb.qache_path.mkdir(parents=True, exist_ok=True)
    cached_payload, hotset_payload = _render_provider_aware_payloads(
        worqspace=qb.worqspace,
        qodeyard_path=qb.qodeyard_path,
        bundle=bundle,
        provider=provider,
        model=model,
        cache_backend=cache_backend,
        pass_kind=pass_kind,
        repair_mode=repair_mode,
        repair_plan_path=repair_plan_path,
    )
    (qb.qache_path / "cached_payload.txt").write_text(cached_payload, encoding="utf-8")
    (qb.qache_path / "hotset_payload.txt").write_text(hotset_payload, encoding="utf-8")
    write_context_bundle_manifest(
        qache_dir=qb.qache_path,
        provider=provider,
        model=model,
        cache_backend=cache_backend,
        cache_backend_reason=cache_backend_reason,
        pass_kind=pass_kind,
        repair_mode=repair_mode,
        bundle=bundle,
        cycle_num=cycle_num,
        build_pass_index=int(os.environ.get("QONQ_BUILD_PASS_INDEX") or 0),
        repair_pass_index=int(os.environ.get("QONQ_REPAIR_PASS_INDEX") or 0),
        target_files=editable_targets,
        repair_targets=repair_targets,
        qodeyard_path=qb.qodeyard_path,
    )

    # provider_cache.json is only emitted when we actually have a provider cache id/object.
    provider_cache_path = qb.qache_path / "provider_cache.json"
    active_cache_id = qb.get_active_cache_id()
    if cache_backend == "gemini_explicit" and active_cache_id:
        provider_cache_path.write_text(
            json.dumps(
                {
                    "provider": provider,
                    "backend": cache_backend,
                    "cache_id": active_cache_id,
                    "qache_id": qb.get_qache_id(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    elif provider_cache_path.exists():
        try:
            provider_cache_path.unlink()
        except Exception:
            pass

    return True, cache_backend


def main():
    parser = argparse.ArgumentParser(
        description="Qontrabender - The Cache Bender 🌀 (Enhanced v0.8.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  local_fast       Ultra-fast, skeleton only, no remote cache
  local_smart      Default - variable fidelity, local only
  cyber_bedrock    Remote cache for stable bedrock
  cyber_aggressive Aggressive remote caching
  paranoid_mincloud Minimal cloud exposure
  debug_repro      Maximum audit logging

Examples:
  python qontrabender.py                         # Check with default mode
  python qontrabender.py --mode local_smart      # Use specific mode
  python qontrabender.py --status                # Show status
  python qontrabender.py --analyze               # Show fidelity decisions
  python qontrabender.py --sync                  # Prepare for sync
  python qontrabender.py --validate              # Validate policy only
  python qontrabender.py --modes                 # List available modes
  
Pipeline Usage (called by qrane.py):
  python qontrabender.py bloq.d/ qodeyard/ qontext.d/ qache.d/
        """
    )
    
    # Positional arguments for pipeline integration
    parser.add_argument('inputs', nargs='*', default=[], 
                        help='Input directories (bloq.d, qodeyard, qontext.d) and output (qache.d)')
    
    parser.add_argument('--mode', '-m', help='Operational mode')
    parser.add_argument('--status', action='store_true', help='Show cache status')
    parser.add_argument('--analyze', action='store_true', help='Analyze files')
    parser.add_argument('--sync', action='store_true', help='Prepare for sync')
    parser.add_argument('--mark-synced', nargs='?', const='', metavar='CACHE_ID', 
                        help='Mark as synced (uses qache_id if no CACHE_ID provided)')
    parser.add_argument('--check', action='store_true', help='Check if sync needed')
    parser.add_argument('--get-cache-id', action='store_true', help='Print active cache ID')
    parser.add_argument('--get-qache-id', action='store_true', help='Print qache ID for this qage')
    parser.add_argument('--validate', action='store_true', help='Validate policy file')
    parser.add_argument('--modes', action='store_true', help='List available modes')
    
    args = parser.parse_args()
    
    # Determine worqspace based on inputs or cwd
    if args.inputs and len(args.inputs) >= 4:
        # Pipeline mode: inputs are bloq.d, qodeyard, qontext.d, qache.d
        # Derive worqspace from output path (qache.d is at qage root level)
        output_path = Path(args.inputs[-1])
        if output_path.name == 'qache.d':
            worqspace = output_path.parent  # Go up one level to qage root
        else:
            worqspace = output_path.parent
    else:
        worqspace = Path(os.getcwd())
    
    # Validate only
    if args.validate:
        policy_path = worqspace / 'caching_policy.yaml'
        is_valid, policy, errors, warnings = validate_policy_file(policy_path)
        
        print(f"\n  Validating: {policy_path}")
        if warnings:
            print(f"\n  Warnings:")
            for w in warnings:
                print(f"    ⚠️  {w}")
        
        if is_valid:
            print(f"\n  ✅ Policy file is valid!")
            print(f"  Version: {policy.get('version')}")
            print(f"  Modes: {', '.join(policy.get('modes', {}).keys())}")
        else:
            print(f"\n  ❌ Policy file has errors:")
            for e in errors:
                print(f"    - {e}")
        return
    
    # List modes
    if args.modes:
        policy_path = worqspace / 'caching_policy.yaml'
        if policy_path.exists():
            _, policy, _, _ = validate_policy_file(policy_path)
            print_modes(policy)
        else:
            print("  No caching_policy.yaml found")
        return
    
    print(f"--- Qontrabender v0.8.0: Initializing in {worqspace} ---", flush=True)
    
    # Create Qontrabender with explicit paths if provided (pipeline mode)
    if args.inputs and len(args.inputs) >= 4:
        # Pipeline mode: inputs are bloq.d, qodeyard, qontext.d, qache.d
        bloq_path = Path(args.inputs[0])
        qodeyard_path = Path(args.inputs[1])
        qontext_path = Path(args.inputs[2])
        qache_path = Path(args.inputs[3])
        
        print(f"  Pipeline mode - explicit paths:", flush=True)
        print(f"    bloq.d:    {bloq_path}", flush=True)
        print(f"    qodeyard:  {qodeyard_path}", flush=True)
        print(f"    qontext.d: {qontext_path}", flush=True)
        print(f"    qache.d:   {qache_path}", flush=True)
        
        qb = Qontrabender(
            worqspace, 
            mode=args.mode,
            qodeyard_path=qodeyard_path,
            bloq_path=bloq_path,
            qontext_path=qontext_path,
            qache_path=qache_path
        )
    else:
        qb = Qontrabender(worqspace, mode=args.mode)
    
    if args.status:
        print_status(qb)
        return
    
    if args.analyze:
        print_analysis(qb)
        return
    
    if args.get_cache_id:
        cache_id = qb.get_active_cache_id()
        if cache_id:
            print(cache_id)
        else:
            print(f"# No active cache. Base qache_id: {qb.manifest.qache_id}")
        return
    
    if args.get_qache_id:
        print(qb.manifest.qache_id)
        return
    
    if args.mark_synced is not None:
        _, payload_hash, _, _ = qb.assemble_payload()
        if payload_hash:
            # Use provided cache_id or None (will use qache_id)
            cache_id = args.mark_synced if args.mark_synced else None
            qb.mark_synced(payload_hash, cache_id)
            effective_id = cache_id or qb.get_active_cache_id()
            print(f"  ✓ Marked as synced: {effective_id}", flush=True)
        else:
            print("  [ERROR] No payload to mark", flush=True)
        return
    
    if args.sync:
        print(qb.generate_sync_instructions())
        return

    if args.check:
        # --check now runs provider-aware pipeline when in pipeline/worqspace mode
        if args.inputs and len(args.inputs) >= 4:
            print(f"\n  Running --check in pipeline mode...", flush=True)
            ok, backend_or_error = _run_provider_aware_pipeline_bundle(qb)
            if not ok:
                print(f"  [ERROR] Provider-aware bundle assembly failed: {backend_or_error}", flush=True)
                sys.exit(1)
            print(f"  Cache backend: {backend_or_error}", flush=True)
            print(f"  Wrote: qache.d/cached_payload.txt", flush=True)
            print(f"  Wrote: qache.d/hotset_payload.txt", flush=True)
            print(f"  Wrote: qache.d/context_bundle_manifest.json", flush=True)
            print("\n--- Qontrabender: Complete ---", flush=True)
            return
        else:
            # Legacy --check: run sync-need check
            needs_sync, reason, payload_hash = qb.check_sync_needed()
            print(f"\n  Qache: {qb.manifest.qache_id}")
            print(f"  Mode: {qb.mode}")
            print(f"  Sync needed: {'YES' if needs_sync else 'NO'}")
            print(f"  Reason: {reason}")
            if needs_sync:
                print(f"\n  Run 'python qontrabender.py --sync' for instructions")
                print(f"  Run 'python qontrabender.py --analyze' for decisions")
            print("\n--- Qontrabender: Complete ---", flush=True)
            return
    
    # Default behavior depends on mode
    if args.inputs and len(args.inputs) >= 4:
        # Pipeline mode: provider-aware context bundle assembly for ConstruQtor.
        print(f"\n  Running in pipeline mode...", flush=True)
        ok, backend_or_error = _run_provider_aware_pipeline_bundle(qb)
        if not ok:
            print(f"  [ERROR] Provider-aware bundle assembly failed: {backend_or_error}", flush=True)
            sys.exit(1)
        print(f"  Cache backend: {backend_or_error}", flush=True)
        print(f"  Wrote: qache.d/cached_payload.txt", flush=True)
        print(f"  Wrote: qache.d/hotset_payload.txt", flush=True)
        print(f"  Wrote: qache.d/context_bundle_manifest.json", flush=True)
        print("\n--- Qontrabender: Complete ---", flush=True)
        return
    
    # Interactive mode: check
    needs_sync, reason, payload_hash = qb.check_sync_needed()
    
    print(f"\n  Qache: {qb.manifest.qache_id}")
    print(f"  Mode: {qb.mode}")
    print(f"  Sync needed: {'YES' if needs_sync else 'NO'}")
    print(f"  Reason: {reason}")
    
    if needs_sync:
        print(f"\n  Run 'python qontrabender.py --sync' for instructions")
        print(f"  Run 'python qontrabender.py --analyze' for decisions")
    
    print("\n--- Qontrabender: Complete ---", flush=True)


if __name__ == "__main__":
    main()
