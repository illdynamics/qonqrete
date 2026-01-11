#!/usr/bin/env python3
"""Qrystallizer: Template Engine Agent (Tier 0) - Pattern-based code generation"""

import re
from typing import List, Optional
from worqer.mindstaq import CrystallizedIntent, ActionType, TargetType


class Qrystallizer:
    """Template-based code generation for Tier 0."""
    
    TEMPLATES = {
        'validation_email': '''import re


def validate_email(email: str) -> bool:
    """Validate email address format."""
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$', email))
''',
        'validation_phone': '''import re


def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    cleaned = re.sub(r'[\\s\\-\\(\\)\\.]', '', phone)
    return bool(re.match(r'^\\+?[0-9]{10,15}$', cleaned))
''',
        'validation_url': '''import re


def validate_url(url: str) -> bool:
    """Validate URL format."""
    return bool(re.match(r'^https?://[a-zA-Z0-9.-]+(?:/[^\\s]*)?$', url))
''',
        'validation_uuid': '''import re


def validate_uuid(value: str) -> bool:
    """Validate UUID format."""
    return bool(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', value.lower()))
''',
        'validation_generic': '''def validate_{name}(value: str) -> bool:
    """Validate {name} value."""
    return bool(value and isinstance(value, str) and len(value.strip()) > 0)
''',
        'crud_create': '''import uuid
from datetime import datetime


def create_{entity}(data: dict) -> dict:
    """Create a new {entity}."""
    return {{'id': str(uuid.uuid4()), 'created_at': datetime.utcnow().isoformat(), **data}}
''',
        'crud_read': '''def get_{entity}({entity}_id: str) -> dict | None:
    """Retrieve a {entity} by ID."""
    return None  # TODO: Implement database lookup
''',
        'crud_update': '''def update_{entity}({entity}_id: str, data: dict) -> dict | None:
    """Update an existing {entity}."""
    from datetime import datetime
    {entity} = get_{entity}({entity}_id)
    if {entity} is None:
        return None
    {entity}.update(data)
    {entity}['updated_at'] = datetime.utcnow().isoformat()
    return {entity}
''',
        'crud_delete': '''def delete_{entity}({entity}_id: str) -> bool:
    """Delete a {entity} by ID."""
    return True  # TODO: Implement database deletion
''',
        'api_get': '''def get_{resource}(request):
    """GET endpoint for {resource}."""
    try:
        return {{'status': 'success', 'data': []}}
    except Exception as e:
        return {{'status': 'error', 'message': str(e)}}
''',
        'api_post': '''def create_{resource}(request):
    """POST endpoint for creating {resource}."""
    try:
        data = request.get_json()
        return {{'status': 'success', 'data': {{'id': 'new_id', **data}}}}, 201
    except Exception as e:
        return {{'status': 'error', 'message': str(e)}}, 400
''',
        'dataclass': '''from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class {class_name}:
    """{description}"""
    id: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {{'id': self.id, 'name': self.name, 'created_at': self.created_at.isoformat()}}
''',
        'file_reader': '''def read_{format}_file(file_path: str):
    """Read and parse a {format} file."""
    from pathlib import Path
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {{file_path}}")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
''',
        'file_writer': '''def write_{format}_file(file_path: str, data) -> bool:
    """Write data to a {format} file."""
    from pathlib import Path
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(str(data))
    return True
''',
        'json_handler': '''import json
from pathlib import Path
from typing import Any, Optional


def read_json(file_path: str) -> Optional[Any]:
    """Read and parse a JSON file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    """Write data to a JSON file."""
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
    """Read and parse a YAML file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_yaml(file_path: str, data: Any) -> bool:
    """Write data to a YAML file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return True
''',
        'jwt_auth': '''import jwt
import datetime
from typing import Dict, Any, Optional

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"


def create_jwt_token(payload: Dict[str, Any], expires_hours: int = 24) -> str:
    """Create a JWT token with expiration."""
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=expires_hours)
    token_payload = {**payload, 'exp': expiration, 'iat': datetime.datetime.utcnow()}
    return jwt.encode(token_payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None  # Token has expired
    except jwt.InvalidTokenError:
        return None  # Invalid token


def verify_jwt_token(token: str) -> bool:
    """Verify if a JWT token is valid."""
    return decode_jwt_token(token) is not None
''',
        'logger': '''import logging
from pathlib import Path


def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """Set up a logger with file and console handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger
''',
        'error_handler': '''from functools import wraps
from typing import Callable, TypeVar

T = TypeVar('T')


def handle_errors(default_return: T = None) -> Callable:
    """Decorator to handle exceptions gracefully."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"Error in {{func.__name__}}: {{e}}")
                return default_return
        return wrapper
    return decorator
''',
        'test_function': '''import pytest


class Test{class_name}:
    """Test suite for {class_name}."""
    
    def setup_method(self):
        pass
    
    def test_{function_name}_success(self):
        assert True
    
    def test_{function_name}_failure(self):
        with pytest.raises(Exception):
            pass
''',
        'config_loader': '''import os
import yaml
from pathlib import Path
from typing import Any, Dict


class Config:
    """Configuration loader with environment variable support."""
    _instance = None
    _config: Dict[str, Any] = {{}}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load(self, config_path: str = 'config.yaml') -> 'Config':
        path = Path(config_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {{}}
        return self
    
    def get(self, key: str, default: Any = None) -> Any:
        env_key = key.upper().replace('.', '_')
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return env_value
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
''',
        # v1.7.8: Security/Safety templates
        'safety_governor': '''"""Safety Governor - Enforces operational boundaries."""
from dataclasses import dataclass, field
from typing import Set, List, Optional
from datetime import datetime
import ipaddress
import logging

logger = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    """Safety configuration."""
    allowed_networks: Set[str] = field(default_factory=set)
    blocked_networks: Set[str] = field(default_factory=set)
    max_operations_per_minute: int = 60
    require_authorization: bool = True
    audit_all_operations: bool = True


class SafetyGovernor:
    """Enforces safety constraints on all operations."""
    
    def __init__(self, config: dict = None):
        self.config = SafetyConfig(**(config or {{}}))
        self._operation_count = 0
        self._last_reset = datetime.utcnow()
        logger.info("SafetyGovernor initialized")
    
    def check_scope(self, target: str) -> bool:
        """Check if target is within allowed scope."""
        try:
            ip = ipaddress.ip_address(target)
            for network in self.config.allowed_networks:
                if ip in ipaddress.ip_network(network, strict=False):
                    return True
            for network in self.config.blocked_networks:
                if ip in ipaddress.ip_network(network, strict=False):
                    logger.warning(f"Target {{target}} is in blocked network")
                    return False
        except ValueError:
            pass  # Not an IP address
        return True
    
    def authorize_operation(self, operation: str, operator: str) -> bool:
        """Authorize an operation."""
        self._check_rate_limit()
        if self.config.require_authorization:
            logger.info(f"Operation {{operation}} authorized for {{operator}}")
        return True
    
    def _check_rate_limit(self):
        """Check and update rate limit."""
        now = datetime.utcnow()
        if (now - self._last_reset).seconds >= 60:
            self._operation_count = 0
            self._last_reset = now
        self._operation_count += 1
        if self._operation_count > self.config.max_operations_per_minute:
            raise RuntimeError("Rate limit exceeded")
''',
        'redis_backend': '''"""Redis Backend - Pub/Sub and caching."""
from typing import Any, Optional, Callable, List
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


@dataclass  
class RedisConfig:
    """Redis connection configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    decode_responses: bool = True


class RedisBackend:
    """Redis backend for caching and pub/sub."""
    
    def __init__(self, config: dict = None):
        self.config = RedisConfig(**(config or {{}}))
        self._client = None
        self._pubsub = None
        self._subscribers: dict = {{}}
    
    @property
    def client(self):
        """Get or create Redis client."""
        if not HAS_REDIS:
            raise ImportError("redis package not installed")
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=self.config.decode_responses
            )
        return self._client
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = self.client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value in cache."""
        data = json.dumps(value) if not isinstance(value, str) else value
        if ttl:
            return bool(self.client.setex(key, ttl, data))
        return bool(self.client.set(key, data))
    
    def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel."""
        data = json.dumps(message) if not isinstance(message, str) else message
        return self.client.publish(channel, data)
    
    def subscribe(self, channel: str, callback: Callable):
        """Subscribe to channel."""
        if self._pubsub is None:
            self._pubsub = self.client.pubsub()
        self._pubsub.subscribe(**{{channel: callback}})
        logger.info(f"Subscribed to channel: {{channel}}")
''',
        'base_tool': '''"""Base Tool - Abstract wrapper for security tools."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import subprocess
import shlex
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    output: str = ""
    error: str = ""
    return_code: int = 0
    execution_time_ms: int = 0
    parsed_data: Dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for tool wrappers."""
    
    def __init__(self, config: dict = None):
        self.config = config or {{}}
        self.timeout = self.config.get("timeout", 300)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass
    
    @property
    def version(self) -> Optional[str]:
        """Get tool version."""
        return None
    
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        start = datetime.utcnow()
        try:
            cmd = self._build_command(**kwargs)
            self.logger.info(f"Executing: {{' '.join(cmd)}}")
            
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            result = ToolResult(
                success=proc.returncode == 0,
                output=proc.stdout,
                error=proc.stderr,
                return_code=proc.returncode
            )
            result.parsed_data = self._parse_output(proc.stdout)
            
        except subprocess.TimeoutExpired:
            result = ToolResult(success=False, error="Command timed out")
        except Exception as e:
            result = ToolResult(success=False, error=str(e))
        
        result.execution_time_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        return result
    
    @abstractmethod
    def _build_command(self, **kwargs) -> List[str]:
        """Build command line arguments."""
        pass
    
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse tool output. Override in subclass."""
        return {{"raw": output}}
''',
        'base_capability': '''"""Base AI Capability - Foundation for AI-driven operations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CapabilityType(Enum):
    """Types of AI capabilities."""
    RECON = "reconnaissance"
    EXPLOIT = "exploitation"
    POST_EXPLOIT = "post_exploitation"
    LATERAL = "lateral_movement"
    EXFIL = "exfiltration"


@dataclass
class CapabilityResult:
    """Result from capability execution."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class BaseCapability(ABC):
    """Abstract base for AI capabilities."""
    
    def __init__(self, config: dict = None):
        self.config = config or {{}}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @property
    @abstractmethod
    def capability_type(self) -> CapabilityType:
        """Type of capability."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Capability name."""
        pass
    
    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> CapabilityResult:
        """Execute the capability."""
        pass
    
    def validate_context(self, context: Dict[str, Any]) -> bool:
        """Validate execution context."""
        return True
''',
        # v1.7.8: Shell script templates
        'shell_provision': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
LOG_FILE="${{SCRIPT_DIR}}/provision_{name}.log"

log() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}}

check_root() {{
    if [[ $EUID -ne 0 ]]; then
        log "ERROR: This script must be run as root"
        exit 1
    fi
}}

install_dependencies() {{
    log "Installing dependencies..."
    apt-get update -qq
    apt-get install -y -qq curl wget git
}}

main() {{
    log "Starting {name} provisioning..."
    check_root
    install_dependencies
    log "{name} provisioning complete!"
}}

main "$@"
''',
        'shell_setup': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0)

set -euo pipefail

echo "=== {name} Setup ==="

# Check prerequisites
command -v python3 >/dev/null 2>&1 || {{ echo "Python3 required but not installed."; exit 1; }}

# Create directories
mkdir -p config logs data

# Setup complete
echo "Setup complete!"
''',
        'shell_service': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0)

set -euo pipefail

SERVICE_NAME="{name}"
PID_FILE="/var/run/${{SERVICE_NAME}}.pid"

start() {{
    echo "Starting $SERVICE_NAME..."
    # TODO: Add start command
    echo "Started"
}}

stop() {{
    echo "Stopping $SERVICE_NAME..."
    if [[ -f "$PID_FILE" ]]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    echo "Stopped"
}}

status() {{
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "$SERVICE_NAME is running (PID: $(cat "$PID_FILE"))"
    else
        echo "$SERVICE_NAME is not running"
    fi
}}

case "${{1:-}}" in
    start)  start ;;
    stop)   stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "Usage: $0 {{start|stop|restart|status}}" ;;
esac
''',
        # v1.7.9: C2 Framework provisioning
        'shell_c2': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0) - C2 Framework Provisioning

set -euo pipefail

log() {{ echo "[$(date '+%H:%M:%S')] $1"; }}

install_sliver() {{
    log "Installing Sliver C2..."
    curl -sSL https://sliver.sh/install | bash || true
    log "Sliver installed"
}}

install_havoc() {{
    log "Installing Havoc C2..."
    git clone --depth 1 https://github.com/HavocFramework/Havoc.git /opt/c2/havoc 2>/dev/null || true
    log "Havoc installed"
}}

main() {{
    log "Starting C2 framework provisioning..."
    mkdir -p /opt/c2
    install_sliver
    install_havoc
    log "C2 provisioning complete!"
}}

main "$@"
''',
        # v1.7.9: Database setup provisioning
        'shell_database': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0) - Database Setup

set -euo pipefail

log() {{ echo "[$(date '+%H:%M:%S')] $1"; }}

setup_redis() {{
    log "Setting up Redis..."
    docker run -d --name redis -p 6379:6379 redis:alpine || true
}}

setup_postgres() {{
    log "Setting up PostgreSQL..."
    docker run -d --name postgres -e POSTGRES_PASSWORD=changeme -p 5432:5432 postgres:15-alpine || true
}}

main() {{
    log "Starting database setup..."
    setup_redis
    setup_postgres
    log "Database setup complete!"
}}

main "$@"
''',
        # v1.7.9: Security tools provisioning
        'shell_security': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0) - Security Tools

set -euo pipefail

TOOLS_DIR="/opt/tools"

log() {{ echo "[$(date '+%H:%M:%S')] $1"; }}

install_tool() {{
    local name="$1"
    local repo="$2"
    log "Installing $name..."
    git clone --depth 1 "$repo" "$TOOLS_DIR/$name" 2>/dev/null || git -C "$TOOLS_DIR/$name" pull
}}

main() {{
    log "Installing security tools..."
    mkdir -p "$TOOLS_DIR"
    
    # Common security tools
    install_tool "SecLists" "https://github.com/danielmiessler/SecLists.git"
    
    log "Security tools installed!"
}}

main "$@"
''',
        # v1.7.9: Docker setup provisioning
        'shell_docker': '''#!/bin/bash
# {description}
# Generated by Qrystallizer (mindstaQ Tier 0) - Docker Setup

set -euo pipefail

log() {{ echo "[$(date '+%H:%M:%S')] $1"; }}

install_docker() {{
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh || true
    systemctl enable docker
    systemctl start docker
}}

install_compose() {{
    log "Installing Docker Compose..."
    apt-get install -y docker-compose-plugin || true
}}

main() {{
    log "Starting Docker setup..."
    install_docker
    install_compose
    log "Docker setup complete!"
}}

main "$@"
''',
        # v1.7.9: Improved fallback with actual structure
        'fallback': '''# Generated by Qrystallizer (mindstaQ Tier 0)
# Task: {task}

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class {class_name}:
    """{description}"""
    id: str = ""
    name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {{
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "{class_name}":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            metadata=data.get("metadata", {{}})
        )


class {class_name}Manager:
    """Manager for {class_name} operations."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {{}}
        self._items: Dict[str, {class_name}] = {{}}
        logger.info(f"{class_name}Manager initialized")
    
    def create(self, data: Dict[str, Any]) -> {class_name}:
        """Create a new {class_name}."""
        import uuid
        item = {class_name}.from_dict(data)
        item.id = str(uuid.uuid4())
        self._items[item.id] = item
        logger.info(f"Created {class_name}: {{item.id}}")
        return item
    
    def get(self, item_id: str) -> Optional[{class_name}]:
        """Get {class_name} by ID."""
        return self._items.get(item_id)
    
    def update(self, item_id: str, data: Dict[str, Any]) -> Optional[{class_name}]:
        """Update {class_name}."""
        item = self._items.get(item_id)
        if item:
            for key, value in data.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            logger.info(f"Updated {class_name}: {{item_id}}")
        return item
    
    def delete(self, item_id: str) -> bool:
        """Delete {class_name}."""
        if item_id in self._items:
            del self._items[item_id]
            logger.info(f"Deleted {class_name}: {{item_id}}")
            return True
        return False
    
    def list_all(self) -> List[{class_name}]:
        """List all items."""
        return list(self._items.values())
''',
        # v1.8.3: Rust templates
        'rust_main': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Rust

use std::io::{{self, Write}};

fn main() {{
    println!("Starting {name}...");
    
    if let Err(e) = run() {{
        eprintln!("Error: {{}}", e);
        std::process::exit(1);
    }}
}}

fn run() -> Result<(), Box<dyn std::error::Error>> {{
    // TODO: Implement {name} logic
    println!("{name} completed successfully");
    Ok(())
}}
''',
        'rust_lib': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Rust Library

pub mod {name} {{
    use std::error::Error;
    
    /// Configuration for {class_name}
    #[derive(Debug, Clone)]
    pub struct Config {{
        pub name: String,
        pub enabled: bool,
    }}
    
    impl Default for Config {{
        fn default() -> Self {{
            Config {{
                name: String::from("{name}"),
                enabled: true,
            }}
        }}
    }}
    
    /// Main {class_name} struct
    pub struct {class_name} {{
        config: Config,
    }}
    
    impl {class_name} {{
        pub fn new(config: Config) -> Self {{
            Self {{ config }}
        }}
        
        pub fn run(&self) -> Result<(), Box<dyn Error>> {{
            println!("Running {{}}...", self.config.name);
            Ok(())
        }}
    }}
}}
''',
        'rust_cli': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Rust CLI

use std::env;
use std::process;

fn main() {{
    let args: Vec<String> = env::args().collect();
    
    if args.len() < 2 {{
        eprintln!("Usage: {} <command>", args[0]);
        process::exit(1);
    }}
    
    match args[1].as_str() {{
        "run" => run_command(),
        "help" | "-h" | "--help" => print_help(),
        _ => {{
            eprintln!("Unknown command: {{}}", args[1]);
            process::exit(1);
        }}
    }}
}}

fn run_command() {{
    println!("Running {name}...");
    // TODO: Implement {name} logic
}}

fn print_help() {{
    println!("{name} - {description}");
    println!();
    println!("Commands:");
    println!("  run    Run the {name}");
    println!("  help   Show this help message");
}}
''',
        # v1.8.3: Go templates
        'go_main': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Go

package main

import (
    "fmt"
    "os"
)

func main() {{
    fmt.Println("Starting {name}...")
    
    if err := run(); err != nil {{
        fmt.Fprintf(os.Stderr, "Error: %v\\n", err)
        os.Exit(1)
    }}
}}

func run() error {{
    // TODO: Implement {name} logic
    fmt.Println("{name} completed successfully")
    return nil
}}
''',
        'go_lib': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Go Package

package {name}

import (
    "errors"
    "fmt"
)

// Config holds configuration for {class_name}
type Config struct {{
    Name    string
    Enabled bool
}}

// {class_name} is the main struct
type {class_name} struct {{
    config Config
}}

// New creates a new {class_name} instance
func New(config Config) *{class_name} {{
    return &{class_name}{{config: config}}
}}

// Run executes the main logic
func (c *{class_name}) Run() error {{
    if !c.config.Enabled {{
        return errors.New("{name} is disabled")
    }}
    fmt.Printf("Running %s...\\n", c.config.Name)
    return nil
}}
''',
        'go_http': '''// {description}
// Generated by Qrystallizer (mindstaQ Tier 0) - Go HTTP Server

package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
)

func main() {{
    http.HandleFunc("/", homeHandler)
    http.HandleFunc("/health", healthHandler)
    http.HandleFunc("/api/{name}", apiHandler)
    
    fmt.Println("Starting {name} server on :8080...")
    log.Fatal(http.ListenAndServe(":8080", nil))
}}

func homeHandler(w http.ResponseWriter, r *http.Request) {{
    fmt.Fprintf(w, "Welcome to {name}")
}}

func healthHandler(w http.ResponseWriter, r *http.Request) {{
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{{"status": "healthy"}})
}}

func apiHandler(w http.ResponseWriter, r *http.Request) {{
    w.Header().Set("Content-Type", "application/json")
    response := map[string]interface{}{{
        "name": "{name}",
        "status": "ok",
    }}
    json.NewEncoder(w).Encode(response)
}}
''',
    }
    
    TEMPLATE_MATCHERS = {
        'validation_email': [r'email', r'e-mail', r'mail.*valid'],
        'validation_phone': [r'phone', r'telephone', r'mobile.*valid'],
        'validation_url': [r'url', r'uri', r'link.*valid'],
        'validation_uuid': [r'uuid', r'guid'],
        'validation_generic': [r'valid'],
        'crud_create': [r'create(?!.*(?:file|reader|writer|jwt|token))', r'add(?!.*(?:file|jwt|token|auth))', r'new(?!.*file)', r'insert'],
        'crud_read': [r'get(?!.*file)', r'fetch', r'retrieve', r'find'],
        'crud_update': [r'update', r'modify', r'edit', r'patch'],
        'crud_delete': [r'delete', r'remove', r'destroy'],
        'api_get': [r'get.*endpoint', r'api.*get', r'rest.*get'],
        'api_post': [r'post.*endpoint', r'api.*post', r'rest.*create'],
        'dataclass': [r'dataclass', r'data.*class', r'model', r'entity'],
        'file_reader': [r'read.*file', r'load.*file', r'parse.*file', r'file.*reader', r'json.*reader', r'yaml.*reader', r'csv.*reader', r'read.*json', r'read.*yaml', r'read.*csv'],
        'file_writer': [r'write.*file', r'save.*file', r'export.*file', r'file.*writer'],
        'json_handler': [r'json.*(?:file|handler|load|read|write|parse)', r'(?:read|write|parse).*json'],
        'yaml_handler': [r'yaml.*(?:file|handler|load|read|write|parse)', r'(?:read|write|parse).*yaml'],
        'jwt_auth': [r'jwt', r'json.*web.*token', r'auth.*token', r'token.*auth', r'bearer'],
        'logger': [r'log', r'logger', r'logging'],
        'error_handler': [r'error.*handl', r'exception.*handl'],
        'test_function': [r'test', r'unittest', r'pytest'],
        'config_loader': [r'config', r'configuration', r'settings'],
        # v1.7.8: Security/Safety matchers
        # v2.1.6 FIX: REMOVED specific tool names (nmap, masscan, nuclei, etc.) from matchers!
        # These were causing template copypasta instead of letting web search find REAL implementations.
        # Only match when user EXPLICITLY asks for base/generic versions.
        'safety_governor': [r'generic.*safety', r'base.*governor', r'template.*safety'],
        'redis_backend': [r'generic.*redis', r'template.*redis', r'base.*cache'],
        'base_tool': [r'generic.*tool.*wrapper', r'base.*tool.*template', r'tool.*skeleton'],
        'base_capability': [r'generic.*capability', r'base.*capability.*template'],
        # v1.7.9: Enhanced shell script matchers
        'shell_provision': [r'provision', r'provisioning', r'\.sh.*provision', r'setup.*server', r'install.*package'],
        'shell_setup': [r'setup\.sh', r'install\.sh', r'init\.sh', r'bootstrap'],
        'shell_service': [r'service.*script', r'daemon', r'systemd', r'start.*stop', r'init\.d'],
        'shell_c2': [r'c2.*framework', r'sliver', r'havoc', r'mythic', r'covenant', r'03.*c2', r'c2-framework'],
        'shell_database': [r'database.*setup', r'02.*database', r'redis', r'postgres', r'mysql', r'db.*setup'],
        'shell_security': [r'security.*tool', r'04.*security', r'pentest', r'evasion', r'07.*evasion', r'seclist'],
        'shell_docker': [r'docker.*setup', r'01.*docker', r'container.*setup', r'compose'],
        # v1.8.3: Rust template matchers
        'rust_main': [r'\.rs.*main', r'rust.*main', r'fn\s+main', r'rust.*binary', r'rust.*exec'],
        'rust_lib': [r'\.rs.*lib', r'rust.*lib', r'rust.*module', r'rust.*crate', r'pub\s+mod'],
        'rust_cli': [r'rust.*cli', r'rust.*command', r'clap', r'structopt', r'rust.*arg'],
        # v1.8.3: Go template matchers
        'go_main': [r'\.go.*main', r'go.*main', r'func\s+main', r'go.*binary', r'go.*exec'],
        'go_lib': [r'\.go.*lib', r'go.*package', r'go.*module', r'go.*pkg'],
        'go_http': [r'go.*http', r'go.*server', r'go.*api', r'net/http', r'gin', r'echo', r'chi'],
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.min_similarity = self.config.get('qrystallizer', {}).get('min_similarity', 0.85)
    
    def generate(self, intent: CrystallizedIntent, prompt: str, context_files: List[str] = None) -> str:
        # v1.8.7: Removed hardcoded debug paths
        template_name = self._find_best_template(intent, prompt)
        if template_name and template_name in self.TEMPLATES:
            return self._fill_slots(self.TEMPLATES[template_name], intent, prompt)
        return self._fill_slots(self.TEMPLATES['fallback'], intent, prompt)
    
    def _find_best_template(self, intent: CrystallizedIntent, prompt: str) -> Optional[str]:
        """Find the best matching template for the given intent and prompt.
        
        v1.8.7: Removed hardcoded debug file paths.
        v1.8.3: Language-specific template routing based on target file extension.
        """
        prompt_lower = prompt.lower()
        scores = {}
        for template_name, patterns in self.TEMPLATE_MATCHERS.items():
            score = sum(1 for p in patterns if re.search(p, prompt_lower))
            if score > 0:
                scores[template_name] = score

        # v1.8.3: Check target file extension FIRST to route to correct language templates
        target_file = intent.target_file or ''
        is_python_target = target_file.endswith('.py')
        is_shell_target = target_file.endswith('.sh') or target_file.endswith('.bash')
        is_rust_target = target_file.endswith('.rs')
        is_go_target = target_file.endswith('.go')

        # v1.8.3: Boost language-specific templates based on target file
        if is_rust_target:
            for key in list(scores.keys()):
                if key.startswith('rust_'):
                    scores[key] = scores.get(key, 0) + 10  # Strong boost
            # Filter to only Rust templates
            scores = {k: v for k, v in scores.items() if k.startswith('rust_') or k == 'fallback'}
            if not any(k.startswith('rust_') for k in scores):
                scores['rust_main'] = 5  # Default Rust template
        
        elif is_go_target:
            for key in list(scores.keys()):
                if key.startswith('go_'):
                    scores[key] = scores.get(key, 0) + 10  # Strong boost
            # Filter to only Go templates
            scores = {k: v for k, v in scores.items() if k.startswith('go_') or k == 'fallback'}
            if not any(k.startswith('go_') for k in scores):
                scores['go_main'] = 5  # Default Go template
        
        elif is_shell_target:
            for key in list(scores.keys()):
                if key.startswith('shell_'):
                    scores[key] = scores.get(key, 0) + 10  # Strong boost
            # Filter to only shell templates
            scores = {k: v for k, v in scores.items() if k.startswith('shell_') or k == 'fallback'}
            if not any(k.startswith('shell_') for k in scores):
                scores['shell_provision'] = 5  # Default shell template
        
        elif is_python_target:
            # v1.8.2 FIX: If targeting Python file, remove non-Python templates
            scores = {k: v for k, v in scores.items() 
                     if not k.startswith(('shell_', 'rust_', 'go_'))}
        
        # v1.7.9: Boost shell script detection when .sh files are mentioned (for unknown targets)
        elif not target_file and ('.sh' in prompt_lower or 'provision/' in prompt_lower):
            for key in list(scores.keys()):
                if key.startswith('shell_'):
                    scores[key] = scores.get(key, 0) + 5
            if not any(k.startswith('shell_') for k in scores):
                scores['shell_provision'] = 3
        
        if intent.domain == 'validation':
            for key in scores:
                if key.startswith('validation_'):
                    scores[key] = scores.get(key, 0) + 2
        if intent.target_type == TargetType.TEST:
            scores['test_function'] = scores.get('test_function', 0) + 3
        if intent.target_type == TargetType.CLASS:
            scores['dataclass'] = scores.get('dataclass', 0) + 2
        
        if scores:
            best_template = max(scores.items(), key=lambda x: x[1])[0]
            return best_template
        return None
    
    def _fill_slots(self, template: str, intent: CrystallizedIntent, prompt: str) -> str:
        # v1.8.2 FIX: Sanitize prompt to remove garbage before template insertion
        # The prompt often contains "--- PREVIOUS AGENT LOG ---" which should NOT
        # be inserted into generated code templates
        clean_prompt = prompt.split('--- PREVIOUS AGENT LOG')[0].strip() if prompt else ''
        # Also remove any other common garbage patterns
        clean_prompt = re.sub(r'---\s*Architect analyzing.*?---', '', clean_prompt, flags=re.DOTALL)
        clean_prompt = re.sub(r'\[CONFI.*?\]', '', clean_prompt)
        clean_prompt = clean_prompt.strip()
        
        # v1.8.2: Ensure description/task are single-line safe for template comments
        clean_desc = clean_prompt[:100].replace('\n', ' ').replace('\r', ' ')
        clean_task = clean_prompt[:200].replace('\n', ' ').replace('\r', ' ')
        
        name = intent.target_name or self._extract_name(clean_prompt)
        replacements = {
            '{name}': name.lower(), '{entity}': name.lower(), '{resource}': name.lower(),
            '{class_name}': self._to_pascal_case(name), '{function_name}': self._to_snake_case(name),
            '{description}': clean_desc, '{task}': clean_task, '{params}': '', '{format}': self._extract_format(clean_prompt),
        }
        code = template
        for slot, value in replacements.items():
            code = code.replace(slot, value)
        return code
    
    def _extract_name(self, prompt: str) -> str:
        quoted = re.findall(r'[`"\']([a-zA-Z_]\w*)[`"\']', prompt)
        if quoted: return quoted[0]
        camel = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', prompt)
        if camel: return camel[0]
        return 'item'
    
    def _extract_format(self, prompt: str) -> str:
        for fmt, pattern in {'json': r'\bjson\b', 'yaml': r'\byaml\b', 'csv': r'\bcsv\b'}.items():
            if re.search(pattern, prompt.lower()):
                return fmt
        return 'text'
    
    def _to_pascal_case(self, name: str) -> str:
        words = re.findall(r'[a-zA-Z][a-z]*', name)
        return ''.join(word.capitalize() for word in words) or 'Item'
    
    def _to_snake_case(self, name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Qrystallizer - Template Engine')
    parser.add_argument('--text', '-t', type=str, help='Task')
    parser.add_argument('--list', '-l', action='store_true', help='List templates')
    args = parser.parse_args()
    if args.list:
        print("Templates:", list(Qrystallizer.TEMPLATES.keys()))
    elif args.text:
        intent = CrystallizedIntent(raw_text=args.text)
        print(Qrystallizer().generate(intent, args.text))
