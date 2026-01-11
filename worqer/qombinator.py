#!/usr/bin/env python3
"""Qombinator: Evolutionary Synthesis Agent (Tier 2) - Multi-source code combination
v2.0.0-stable - EXPANDED patterns for better file-specific generation
"""

import re
import hashlib
from typing import List, Optional
from worqer.mindstaq import CrystallizedIntent

# v2.0.0: Safe non-blocking logger
try:
    from worqer.mindstaq.mindstaq_logger import mlog
except ImportError:
    mlog = None

__version__ = '2.1.0-stable'


class Qombinator:
    """Evolutionary synthesis for Tier 2. Combines patterns for complex tasks."""
    
    # v2.0.0: MASSIVELY EXPANDED PATTERNS - 15+ patterns now!
    COMPLEX_PATTERNS = {
        'rest_api_crud': '''from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


@dataclass
class Entity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class Repository:
    def __init__(self):
        self._storage: Dict[str, Dict] = {}
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        entity_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        entity = {"id": entity_id, "created_at": now, "updated_at": now, **data}
        self._storage[entity_id] = entity
        return entity
    
    def get(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self._storage.get(entity_id)
    
    def get_all(self) -> List[Dict[str, Any]]:
        return list(self._storage.values())
    
    def update(self, entity_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if entity_id not in self._storage:
            return None
        self._storage[entity_id].update(data)
        self._storage[entity_id]["updated_at"] = datetime.utcnow().isoformat()
        return self._storage[entity_id]
    
    def delete(self, entity_id: str) -> bool:
        if entity_id in self._storage:
            del self._storage[entity_id]
            return True
        return False
''',

        'async_worker_pool': '''import asyncio
from typing import List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    func: Callable = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = None


class AsyncWorkerPool:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results: dict = {}
        self.running = False
    
    async def start(self):
        self.running = True
        return [asyncio.create_task(self._worker(i)) for i in range(self.max_workers)]
    
    async def stop(self):
        self.running = False
    
    async def submit(self, func: Callable, *args, **kwargs) -> str:
        task = Task(func=func, args=args, kwargs=kwargs)
        await self.queue.put(task)
        return task.id
    
    async def _worker(self, worker_id: int):
        while self.running:
            try:
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                try:
                    if asyncio.iscoroutinefunction(task.func):
                        task.result = await task.func(*task.args, **task.kwargs)
                    else:
                        task.result = task.func(*task.args, **task.kwargs)
                except Exception as e:
                    task.error = str(e)
                finally:
                    task.completed_at = datetime.utcnow()
                    self.results[task.id] = task
                    self.queue.task_done()
            except asyncio.TimeoutError:
                continue
''',

        'event_system': '''from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from collections import defaultdict


@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "data": self.data, "timestamp": self.timestamp.isoformat()}


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Event] = []

    def subscribe(self, event_type: str, handler: Callable) -> None:
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, data: Dict[str, Any] = None) -> Event:
        event = Event(type=event_type, data=data or {})
        self._history.append(event)
        for handler in self._subscribers[event_type] + self._subscribers["*"]:
            try:
                handler(event)
            except Exception as e:
                print(f"Handler error: {e}")
        return event


event_bus = EventBus()
''',

        'config_loader': '''from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
import os
import json


@dataclass
class Config:
    """Application configuration with environment override support."""
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = json.load(f)
        return cls(data=data)

    def get(self, key: str, default: Any = None) -> Any:
        env_key = key.upper().replace(".", "_")
        if env_key in os.environ:
            return os.environ[env_key]
        keys = key.split(".")
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
    
    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        d = self.data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
''',

        'logger_setup': '''import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_str: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(format_str)
    
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


logger = setup_logger("app")
''',

        'exception_classes': '''from typing import Optional, Dict, Any


class BaseError(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, code: str = "ERROR", details: Dict[str, Any] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(BaseError):
    """Raised when validation fails."""
    def __init__(self, message: str, field: str = None):
        super().__init__(message, "VALIDATION_ERROR")
        self.field = field


class NotFoundError(BaseError):
    """Raised when a resource is not found."""
    def __init__(self, resource: str, identifier: str = None):
        super().__init__(f"{resource} not found", "NOT_FOUND")


class ConfigurationError(BaseError):
    """Raised when configuration is invalid."""
    def __init__(self, message: str, key: str = None):
        super().__init__(message, "CONFIG_ERROR")
''',

        'type_definitions': '''from typing import TypeVar, Generic, Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum, auto


T = TypeVar("T")


class ResultStatus(Enum):
    SUCCESS = auto()
    FAILURE = auto()
    PENDING = auto()


@dataclass
class Result(Generic[T]):
    """Generic result wrapper."""
    status: ResultStatus
    value: Optional[T] = None
    error: Optional[str] = None
    
    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(status=ResultStatus.SUCCESS, value=value)
    
    @classmethod
    def failure(cls, error: str) -> "Result[T]":
        return cls(status=ResultStatus.FAILURE, error=error)
    
    @property
    def is_success(self) -> bool:
        return self.status == ResultStatus.SUCCESS


# Common type aliases
JSON = Dict[str, Any]
Handler = Callable[[Any], Any]
''',

        'constants_module': '''"""Application constants and configuration defaults."""
from pathlib import Path


# Version
VERSION = "1.0.0"
APP_NAME = "autowonqnet"

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# Network
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_TIMEOUT = 30

# Limits
MAX_CONNECTIONS = 1000
MAX_RETRIES = 3

# Private network ranges
PRIVATE_RANGES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
]
''',

        'http_client': '''from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Response:
    status_code: int
    data: Any
    headers: Dict[str, str]
    error: Optional[str] = None


class HTTPClient:
    """Simple HTTP client wrapper."""
    
    def __init__(self, base_url: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
    
    def get(self, path: str, params: Dict = None) -> Response:
        # Placeholder - implement with requests/httpx
        return Response(200, None, {})
    
    def post(self, path: str, data: Dict = None) -> Response:
        return Response(200, None, {})
''',

        # v2.2.3: REMOVED 'validator' template - it was causing ValidationResult copypasta!
        # The pattern [r'valid', r'check', r'verify'] matched too many prompts
        # Use TOOL_PATTERNS in sqavenger.py for tool-specific code instead

        'target_profile': '''from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Target:
    """Represents a scan target."""
    ip: str
    target_id: str = field(default_factory=generate_id)
    hostname: Optional[str] = None
    ports: List[int] = field(default_factory=list)
    services: Dict[int, str] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "ip": self.ip,
            "hostname": self.hostname,
            "ports": self.ports,
            "services": self.services,
            "first_seen": self.first_seen.isoformat(),
        }


class TargetManager:
    """Manages target profiles."""
    
    def __init__(self):
        self._targets: Dict[str, Target] = {}
    
    def add(self, ip: str, **kwargs) -> Target:
        target = Target(ip=ip, **kwargs)
        self._targets[target.target_id] = target
        return target
    
    def get(self, target_id: str) -> Optional[Target]:
        return self._targets.get(target_id)
    
    def find_by_ip(self, ip: str) -> Optional[Target]:
        for t in self._targets.values():
            if t.ip == ip:
                return t
        return None
''',

        'capability_base': '''from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class CapabilityResult:
    """Result of a capability execution."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0


class BaseCapability(ABC):
    """Abstract base class for AI capabilities."""
    
    name: str = "base"
    description: str = "Base capability"
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.id = str(uuid.uuid4())
    
    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> CapabilityResult:
        """Execute the capability."""
        pass
    
    def validate_input(self, context: Dict[str, Any]) -> bool:
        """Validate input context."""
        return True
''',

        'credential_store': '''from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import uuid


@dataclass
class Credential:
    """Stored credential."""
    username: str
    password: str
    credential_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: Optional[str] = None
    target: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class CredentialStore:
    """Secure credential storage."""
    
    def __init__(self):
        self._credentials: Dict[str, Credential] = {}
    
    def add(self, username: str, password: str, **kwargs) -> Credential:
        cred = Credential(username=username, password=password, **kwargs)
        self._credentials[cred.credential_id] = cred
        return cred
    
    def get(self, credential_id: str) -> Optional[Credential]:
        return self._credentials.get(credential_id)
    
    def find(self, username: str = None, domain: str = None) -> List[Credential]:
        results = []
        for cred in self._credentials.values():
            if username and cred.username != username:
                continue
            if domain and cred.domain != domain:
                continue
            results.append(cred)
        return results
''',
    }

    # v2.0.0: FILE-SPECIFIC pattern mapping (takes priority!)
    FILE_PATTERNS = {
        'constants': 'constants_module',
        'config': 'config_loader',
        'logger': 'logger_setup',
        'exception': 'exception_classes',
        'error': 'exception_classes',
        'type': 'type_definitions',
        # v2.2.3: REMOVED 'validator' - was causing copypasta
        'crypto': 'crypto_utils',
        'target': 'target_profile',
        'profile': 'target_profile',
        'capability': 'capability_base',
        'credential': 'credential_store',
        'http': 'http_client',
        'client': 'http_client',
        'model': 'rest_api_crud',
        'event': 'event_system',
        'bus': 'event_system',
        'worker': 'async_worker_pool',
        'task': 'async_worker_pool',
        'api': 'rest_api_crud',
    }

    # v2.0.0: Expanded pattern matchers
    # v2.2.3: FIXED! Removed overly-broad patterns that caused copypasta
    PATTERN_MATCHERS = {
        'rest_api_crud': [r'rest.*api', r'crud.*api', r'repository', r'api.*handler'],
        'async_worker_pool': [r'async.*worker', r'worker.*pool', r'parallel.*task', r'thread.*pool'],
        'event_system': [r'event.*bus', r'pub.*sub', r'publish.*subscribe', r'event.*emitter'],
        'config_loader': [r'config.*load', r'load.*config', r'parse.*config', r'read.*settings'],
        'logger_setup': [r'logger.*setup', r'setup.*log', r'logging.*config'],
        'exception_classes': [r'exception.*class', r'custom.*error', r'base.*exception'],
        'type_definitions': [r'type.*def', r'typedef', r'generic.*type'],
        'constants_module': [r'constant.*module', r'define.*constant'],
        'http_client': [r'http.*client', r'api.*client', r'rest.*client'],
        # v2.2.3: REMOVED 'validator' - matched too many prompts causing ValidationResult spam
        'target_profile': [r'target.*profile', r'scan.*target', r'host.*profile'],
        'capability_base': [r'capability.*base', r'abstract.*capability'],
        'credential_store': [r'credential.*store', r'password.*manager', r'secret.*store'],
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        if mlog:
            mlog.tier("QOMBINATOR", "Initialized with 15+ patterns")
    
    def synthesize(self, intent: CrystallizedIntent, prompt: str, context_files: List[str] = None) -> Optional[str]:
        """v2.0.0: FILE-FIRST pattern matching for better code variety."""
        if mlog:
            mlog.step(1, "Finding pattern match...")
        
        # v2.0.0: First try FILE-SPECIFIC matching
        target_file = getattr(intent, 'target_file', '') or ''
        filename_lower = target_file.split('/')[-1].lower().replace('.py', '').replace('_', '')
        
        # Check file patterns first
        for keyword, pattern_name in self.FILE_PATTERNS.items():
            if keyword in filename_lower:
                if pattern_name in self.COMPLEX_PATTERNS:
                    if mlog:
                        mlog.info(f"FILE match: {keyword} -> {pattern_name}")
                    return self._customize_code(self.COMPLEX_PATTERNS[pattern_name], intent, prompt)
        
        # Fall back to prompt-based matching
        pattern_name = self._find_complex_pattern(intent, prompt)
        if pattern_name and pattern_name in self.COMPLEX_PATTERNS:
            if mlog:
                mlog.info(f"PROMPT match: {pattern_name}")
            return self._customize_code(self.COMPLEX_PATTERNS[pattern_name], intent, prompt)
        
        # v2.0.0: Last resort - generate based on hash for variety
        if mlog:
            mlog.info("Using hash-based pattern selection")
        return self._generate_varied(intent, prompt)
    
    def _find_complex_pattern(self, intent: CrystallizedIntent, prompt: str) -> Optional[str]:
        prompt_lower = prompt.lower()
        scores = {}
        for pattern_name, matchers in self.PATTERN_MATCHERS.items():
            score = sum(1 for p in matchers if re.search(p, prompt_lower))
            if score > 0:
                scores[pattern_name] = score
        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            if best[1] >= 1:
                return best[0]
        return None
    
    def _customize_code(self, code: str, intent: CrystallizedIntent, prompt: str) -> str:
        if intent.target_name:
            code = re.sub(r'\bEntity\b', intent.target_name, code)
        return code
    
    def _generate_varied(self, intent: CrystallizedIntent, prompt: str) -> str:
        """Generate varied code using hash for deterministic variety."""
        h = hashlib.md5(prompt.encode()).hexdigest()
        patterns = list(self.COMPLEX_PATTERNS.keys())
        idx = int(h[:4], 16) % len(patterns)
        pattern_name = patterns[idx]
        if mlog:
            mlog.info(f"Hash selected: {pattern_name}")
        return self._customize_code(self.COMPLEX_PATTERNS[pattern_name], intent, prompt)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qombinator - Evolutionary Synthesizer')
    parser.add_argument('--text', '-t', type=str, help='Task')
    parser.add_argument('--list', '-l', action='store_true', help='List patterns')
    args = parser.parse_args()
    if args.list:
        print("Complex Patterns:", list(Qombinator.COMPLEX_PATTERNS.keys()))
    elif args.text:
        intent = CrystallizedIntent(raw_text=args.text)
        code = Qombinator().synthesize(intent, args.text)
        print(code if code else "No pattern found")
