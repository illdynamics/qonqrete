# AutoWonqNet v3.0 - Parrot Security Adversary Platform

> AI-Orchestrated Red Team Infrastructure on Parrot Security Linux
> Mode: Program | For v1.0.0-stable Briq Enforcement Validation

---

## 🦜 Project Overview

Build a **complete AI-orchestrated adversary emulation platform** based on **Parrot Security Linux**. This transforms a Parrot container into a fully autonomous red team workstation with multi-framework C2 integration, traffic obfuscation, and AI-driven decision making.

**Core Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PARROT SECURITY BASE CONTAINER                          │
│  ┌─────────────────────────────────────────────────────────────────────────┤
│  │  🧠 AI ORCHESTRATION LAYER (MCP/API Interface)                          │
│  │  ├── Decision Engine (task routing, priority, autonomy levels)          │
│  │  ├── Context Manager (session state, target intel, op history)          │
│  │  └── Safety Governor (geofence, timebomb, killswitch enforcement)       │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │  🎯 C2 FRAMEWORK LAYER                                                  │
│  │  ├── Sliver (gRPC native)                                               │
│  │  ├── Havoc (REST API)                                                   │
│  │  ├── Covenant (.NET/REST)                                               │
│  │  └── Mythic (GraphQL) [NEW]                                             │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │  🔧 TOOLCHAIN LAYER (Pre-installed in Parrot)                           │
│  │  ├── Metasploit, Nmap, Burp, SQLMap, Nikto, etc.                       │
│  │  ├── Custom: Donut, LLVM-Obfuscator, osslsigncode                       │
│  │  └── AI Wrappers: Tool invocation via natural language                  │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │  🌐 TRAFFIC LAYER                                                       │
│  │  ├── Domain Fronting, DGA, Jitter, Synthetic Noise                     │
│  │  ├── Tor/I2P Integration                                                │
│  │  └── Malleable C2 Profile Engine                                        │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │  📊 INTEL & PERSISTENCE                                                 │
│  │  ├── Redis (session/command queue)                                      │
│  │  ├── PostgreSQL (op intel database)                                     │
│  │  └── Elasticsearch (log aggregation)                                    │
│  └─────────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- **AI-First**: Every component exposes an API for AI orchestration
- **Parrot-Native**: Leverage Parrot's pre-installed security tools
- **Autonomous Operations**: AI can plan and execute attack chains
- **Safety-Gated**: All destructive actions require safety checks
- **Ephemeral**: Infrastructure is disposable and rebuildable

---

## 🎯 Global Success Criteria

Before ANY cycle is marked SUCCESS:
1. All Python files pass `python -m py_compile <file>`
2. All imports resolve within the project structure
3. No circular import dependencies
4. All classes instantiable with mock/test configs
5. All Dockerfiles pass syntax validation
6. AI interface classes have standardized method signatures

---

## 📦 Dependency Graph (STRICTLY ENFORCED)

```
src/
├── __init__.py
│
├── shared/                         # LAYER 0: No external src imports
│   ├── __init__.py
│   ├── constants.py               # Pure Python constants
│   ├── exceptions.py              # Custom exception hierarchy
│   ├── logger.py                  # Logging setup (only: logging, os)
│   ├── config_loader.py           # YAML config (only: yaml, os, pathlib)
│   └── types.py                   # Shared dataclasses/types
│
├── ai/                             # LAYER 1: AI Orchestration (shared only)
│   ├── __init__.py
│   ├── base_capability.py         # ABC for all AI-callable capabilities
│   ├── decision_engine.py         # Task routing and prioritization
│   ├── context_manager.py         # Session state and intel tracking
│   ├── prompt_templates.py        # Structured prompts for AI reasoning
│   ├── tool_registry.py           # Registry of AI-callable tools
│   └── mcp_interface.py           # Model Context Protocol server
│
├── safety/                         # LAYER 2: Safety Controls (shared only)
│   ├── __init__.py
│   ├── crypto_auth.py             # GPG authorization
│   ├── geofencing.py              # IP/geo restrictions
│   ├── timebomb.py                # Time-based expiration
│   ├── killswitch.py              # Emergency shutdown
│   └── safety_governor.py         # Unified safety enforcement
│
├── traffic/                        # LAYER 3: Traffic Obfuscation (shared only)
│   ├── __init__.py
│   ├── jitter.py                  # Timing randomization
│   ├── dga.py                     # Domain generation algorithm
│   ├── synthetic.py               # Decoy traffic generation
│   ├── domain_fronting.py         # CDN fronting
│   ├── malleable_profiles.py      # C2 profile generation
│   └── tor_controller.py          # Tor circuit management [NEW]
│
├── c2/                             # LAYER 4: C2 Clients (shared, traffic)
│   ├── __init__.py
│   ├── base_client.py             # ABC for C2 implementations
│   ├── sliver_client.py           # Sliver gRPC client
│   ├── havoc_client.py            # Havoc REST client
│   ├── covenant_client.py         # Covenant REST client
│   ├── mythic_client.py           # Mythic GraphQL client [NEW]
│   └── unified_c2.py              # Multi-framework facade [NEW]
│
├── tools/                          # LAYER 5: Tool Wrappers (shared, ai)
│   ├── __init__.py
│   ├── base_tool.py               # ABC for tool wrappers
│   ├── nmap_wrapper.py            # Nmap AI interface
│   ├── metasploit_wrapper.py      # MSF RPC interface
│   ├── burp_wrapper.py            # Burp REST API
│   ├── sqlmap_wrapper.py          # SQLMap automation
│   ├── crackmapexec_wrapper.py    # CME automation [NEW]
│   └── bloodhound_wrapper.py      # BloodHound ingestor [NEW]
│
├── agent/                          # LAYER 6: Agent Factory (shared, c2)
│   ├── __init__.py
│   ├── factory.py                 # Implant builder
│   ├── donut_converter.py         # Shellcode conversion
│   ├── signer.py                  # Binary signing
│   ├── obfuscator.py              # Obfuscation pipeline
│   └── loader_generator.py        # Custom loader generation [NEW]
│
├── intel/                          # LAYER 7: Intelligence (shared) [NEW]
│   ├── __init__.py
│   ├── target_profile.py          # Target data model
│   ├── credential_store.py        # Credential management
│   ├── network_map.py             # Network topology tracking
│   └── attack_graph.py            # Attack path visualization
│
└── orchestration/                  # LAYER 8: Mass Ops (all layers)
    ├── __init__.py
    ├── redis_backend.py           # Redis pub/sub
    ├── postgres_backend.py        # PostgreSQL intel store [NEW]
    ├── mass_beacon.py             # Multi-session orchestration
    ├── event_handler.py           # Event-driven actions
    ├── scheduler.py               # Business hours scheduling
    └── campaign_manager.py        # Full campaign orchestration [NEW]
```

---

## 🧪 Mock Infrastructure (REQUIRED)

### Mock Server Framework

**Deliverables:**
- `tests/__init__.py`
- `tests/conftest.py` (pytest fixtures)
- `tests/mocks/__init__.py`
- `tests/mocks/mock_c2_server.py`
- `tests/mocks/mock_tool_output.py`
- `tests/mocks/mock_ai_response.py`

```python
# tests/mocks/mock_c2_server.py
"""Mock C2 servers for testing without real infrastructure."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import uuid
import time

@dataclass
class MockSession:
    id: str
    remote_address: str
    hostname: str
    username: str
    os: str
    arch: str
    last_checkin: float = field(default_factory=time.time)
    
@dataclass
class MockBeacon:
    id: str
    remote_address: str
    interval: int = 60
    jitter: int = 10
    last_checkin: float = field(default_factory=time.time)

class MockC2Server:
    """Base mock C2 for all framework implementations."""
    
    def __init__(self):
        self.sessions: Dict[str, MockSession] = {}
        self.beacons: Dict[str, MockBeacon] = {}
        self.command_queue: Dict[str, List[str]] = {}
        self._connected = False
    
    def add_mock_session(self, **kwargs) -> MockSession:
        session = MockSession(
            id=kwargs.get('id', str(uuid.uuid4())),
            remote_address=kwargs.get('remote_address', '10.0.0.1'),
            hostname=kwargs.get('hostname', 'WORKSTATION-01'),
            username=kwargs.get('username', 'testuser'),
            os=kwargs.get('os', 'windows'),
            arch=kwargs.get('arch', 'amd64')
        )
        self.sessions[session.id] = session
        return session
    
    def connect(self) -> bool:
        self._connected = True
        return True
    
    def disconnect(self):
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected


class MockSliverServer(MockC2Server):
    """Mock Sliver for SliverClient testing."""
    
    def get_sessions(self) -> List[MockSession]:
        return list(self.sessions.values())
    
    def execute_command(self, session_id: str, command: str) -> str:
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        mock_outputs = {
            'whoami': 'DOMAIN\\testuser',
            'hostname': 'WORKSTATION-01',
            'pwd': 'C:\\Users\\testuser',
        }
        return mock_outputs.get(command.split()[0], f"Mock: {command}")
    
    def generate_implant(self, config: dict) -> bytes:
        return b"MOCK_SLIVER_IMPLANT_" + str(config).encode()[:50]


class MockHavocServer(MockC2Server):
    """Mock Havoc for HavocClient testing."""
    
    def get_demons(self) -> List[MockSession]:
        return list(self.sessions.values())
    
    def execute_task(self, demon_id: str, task: str) -> str:
        return f"Task '{task}' queued for {demon_id}"


class MockMythicServer(MockC2Server):
    """Mock Mythic for MythicClient testing."""
    
    def __init__(self):
        super().__init__()
        self.callbacks: Dict[str, MockSession] = self.sessions
        self.payloads: List[dict] = []
    
    def get_callbacks(self) -> List[MockSession]:
        return list(self.callbacks.values())
    
    def create_payload(self, config: dict) -> dict:
        payload = {'id': str(uuid.uuid4()), 'config': config}
        self.payloads.append(payload)
        return payload
    
    def execute_task(self, callback_id: str, command: str) -> dict:
        return {'task_id': str(uuid.uuid4()), 'status': 'queued'}
```

```python
# tests/mocks/mock_tool_output.py
"""Mock outputs for Parrot Security tools."""

MOCK_NMAP_OUTPUT = """
Starting Nmap 7.94 ( https://nmap.org )
Nmap scan report for 10.0.0.1
Host is up (0.0010s latency).
PORT     STATE SERVICE
22/tcp   open  ssh
80/tcp   open  http
443/tcp  open  https
3389/tcp open  ms-wbt-server
"""

MOCK_BLOODHOUND_OUTPUT = {
    "users": [
        {"name": "admin@domain.local", "enabled": True, "adminCount": True},
        {"name": "user1@domain.local", "enabled": True, "adminCount": False}
    ],
    "computers": [
        {"name": "DC01.domain.local", "os": "Windows Server 2019"},
        {"name": "WS01.domain.local", "os": "Windows 10"}
    ],
    "paths_to_da": 3
}

MOCK_CME_OUTPUT = """
SMB         10.0.0.1        445    DC01             [*] Windows Server 2019 Build 17763 x64
SMB         10.0.0.1        445    DC01             [+] domain.local\\admin:Password123! (Pwn3d!)
"""
```

---

## Phase 1: Parrot Security Base Image

### 1.1 Parrot Security Dockerfile

**Deliverables:**
- `infra/docker/parrot-base/Dockerfile`

```dockerfile
# infra/docker/parrot-base/Dockerfile
# AutoWonqNet v3 - Parrot Security Base Image
FROM parrotsec/security:latest

LABEL maintainer="WonQmeistah <wonq@autowonqnet.local>"
LABEL version="3.0.0"
LABEL description="AI-Orchestrated Adversary Platform on Parrot Security"

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Update and install additional requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python ecosystem
    python3-pip \
    python3-venv \
    python3-dev \
    # Build tools
    build-essential \
    cmake \
    golang-go \
    # C2 dependencies
    mingw-w64 \
    mono-complete \
    # Networking
    tor \
    proxychains4 \
    # Database clients
    redis-tools \
    postgresql-client \
    # Binary analysis
    upx-ucl \
    osslsigncode \
    # Additional security tools
    crackmapexec \
    bloodhound \
    neo4j \
    responder \
    impacket-scripts \
    evil-winrm \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Donut for shellcode conversion
RUN git clone https://github.com/TheWover/donut.git /opt/donut \
    && cd /opt/donut \
    && make \
    && cp donut /usr/local/bin/

# Install Sliver C2
RUN curl https://sliver.sh/install | bash

# Create non-root operator user
RUN useradd -m -s /bin/bash operator \
    && usermod -aG sudo operator \
    && echo "operator ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create application directories
RUN mkdir -p /opt/autowonqnet/{src,config,data,logs} \
    && chown -R operator:operator /opt/autowonqnet

# Set working directory
WORKDIR /opt/autowonqnet

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=operator:operator . .

# Expose ports
# 8080: AI MCP Interface
# 8443: HTTPS C2 Listener
# 31337: gRPC (Sliver)
# 6379: Redis
# 5432: PostgreSQL
EXPOSE 8080 8443 31337 6379 5432

# Switch to non-root user
USER operator

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "from src.shared.config_loader import ConfigLoader; print('OK')" || exit 1

# Default command: Start AI orchestration interface
CMD ["python3", "main.py", "--mode", "ai-server"]
```

### 1.2 Extended Requirements

**Deliverables:**
- `requirements.txt`

```
# Core Framework
pyyaml>=6.0
redis>=4.5.0
requests>=2.28.0
aiohttp>=3.8.0
asyncio>=3.4.3

# C2 Integration
sliver-py>=0.0.18
gql>=3.4.0  # GraphQL for Mythic
websockets>=10.0

# Security & Crypto
python-gnupg>=0.5.0
cryptography>=40.0.0
pyjwt>=2.6.0

# Database
psycopg2-binary>=2.9.0
sqlalchemy>=2.0.0

# AI/MCP Interface
fastapi>=0.95.0
uvicorn>=0.21.0
pydantic>=1.10.0

# Traffic & Network
scapy>=2.5.0
stem>=1.8.0  # Tor controller
dnspython>=2.3.0

# Tool Integration
python-nmap>=0.7.1
pymetasploit3>=1.0.3

# Testing
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
httpx>=0.24.0  # Async test client
```

### 1.3 Project Structure & Entry Point

**Deliverables:**
- `README.md`
- `main.py`
- `config.yaml.example`
- `.gitignore`
- `src/__init__.py`

```python
# main.py
"""
AutoWonqNet v3.0 - AI-Orchestrated Adversary Platform
Entry point for all operation modes.
"""
import argparse
import sys
import asyncio
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(
        description="AutoWonqNet v3.0 - AI-Orchestrated Adversary Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--mode', 
        choices=['ai-server', 'cli', 'campaign', 'health-check'],
        default='cli',
        help='Operation mode'
    )
    parser.add_argument(
        '--config', 
        type=Path, 
        default=Path('config.yaml'),
        help='Configuration file path'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='AI server port (ai-server mode only)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Import here to catch import errors gracefully
    try:
        from src.shared.config_loader import ConfigLoader
        from src.shared.logger import get_logger
    except ImportError as e:
        print(f"[ERROR] Failed to import core modules: {e}")
        sys.exit(1)
    
    logger = get_logger("main", debug=args.debug)
    logger.info(f"AutoWonqNet v3.0 starting in {args.mode} mode")
    
    # Load configuration
    config_loader = ConfigLoader(args.config)
    config = config_loader.load()
    
    if args.mode == 'ai-server':
        from src.ai.mcp_interface import start_mcp_server
        logger.info(f"Starting AI MCP server on port {args.port}")
        asyncio.run(start_mcp_server(config, port=args.port))
        
    elif args.mode == 'cli':
        from src.orchestration.campaign_manager import CampaignCLI
        cli = CampaignCLI(config)
        cli.run()
        
    elif args.mode == 'campaign':
        from src.orchestration.campaign_manager import CampaignManager
        manager = CampaignManager(config)
        asyncio.run(manager.run_campaign())
        
    elif args.mode == 'health-check':
        from src.shared.health import run_health_checks
        success = run_health_checks(config)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

**🎯 Golden Path Test:**
```python
# This MUST work after phase completion
import yaml
from pathlib import Path
from main import main, parse_args

# Args parseable
args = parse_args()
assert args.mode in ['ai-server', 'cli', 'campaign', 'health-check']

# Config loadable
with open('config.yaml.example', 'r') as f:
    config = yaml.safe_load(f)
assert isinstance(config, dict)
```

---

## Phase 2: Shared Foundation Layer

### 2.1 Core Shared Modules

**Deliverables:**
- `src/shared/__init__.py`
- `src/shared/constants.py`
- `src/shared/exceptions.py`
- `src/shared/types.py`
- `src/shared/logger.py`
- `src/shared/config_loader.py`
- `src/shared/health.py`

```python
# src/shared/types.py
"""Shared type definitions for AutoWonqNet."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class OperationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"

class C2Framework(Enum):
    SLIVER = "sliver"
    HAVOC = "havoc"
    COVENANT = "covenant"
    MYTHIC = "mythic"

@dataclass
class Session:
    """Unified session representation across C2 frameworks."""
    id: str
    framework: C2Framework
    remote_address: str
    hostname: str
    username: str
    os: str
    arch: str
    last_checkin: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CommandResult:
    """Unified command result."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0

@dataclass
class Target:
    """Target system profile."""
    ip: str
    hostname: Optional[str] = None
    os: Optional[str] = None
    ports: List[int] = field(default_factory=list)
    services: Dict[int, str] = field(default_factory=dict)
    credentials: List[Dict[str, str]] = field(default_factory=list)
    notes: str = ""

@dataclass
class AITaskRequest:
    """Request structure for AI-initiated tasks."""
    task_type: str
    target: Optional[Target] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, 10 = highest
    safety_override: bool = False  # Requires confirmation
```

**🎯 Golden Path Test:**
```python
from src.shared.config_loader import ConfigLoader
from src.shared.logger import get_logger
from src.shared.exceptions import ConfigurationError, SafetyViolation
from src.shared.types import Session, C2Framework, Target

# Logger works
logger = get_logger("test")
logger.info("Test message")

# Types instantiable
session = Session(
    id="test-123",
    framework=C2Framework.SLIVER,
    remote_address="10.0.0.1",
    hostname="TEST-PC",
    username="admin",
    os="windows",
    arch="amd64"
)
assert session.framework == C2Framework.SLIVER

# Exceptions raisable
try:
    raise SafetyViolation("Geofence violation")
except SafetyViolation:
    pass
```

---

## Phase 3: AI Orchestration Layer

### 3.1 AI Base Capability Interface

**Deliverables:**
- `src/ai/__init__.py`
- `src/ai/base_capability.py`
- `src/ai/tool_registry.py`
- `src/ai/prompt_templates.py`

```python
# src/ai/base_capability.py
"""
Base class for all AI-callable capabilities.
Every tool/action that AI can invoke must inherit from this.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class CapabilityResult:
    """Standardized result from any capability execution."""
    success: bool
    data: Any
    error: Optional[str] = None
    suggestions: List[str] = None  # AI can use these for next steps

class BaseCapability(ABC):
    """
    Abstract base for AI-callable capabilities.
    
    All tools, C2 actions, and operations inherit from this
    to ensure consistent interface for AI orchestration.
    """
    
    # Capability metadata for AI reasoning
    name: str = "base_capability"
    description: str = "Base capability - override this"
    requires_safety_check: bool = True
    autonomy_level: int = 1  # 1-5, 5 = fully autonomous
    
    @abstractmethod
    def execute(self, **kwargs) -> CapabilityResult:
        """Execute the capability with given parameters."""
        pass
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return JSON schema for expected parameters."""
        pass
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate parameters against schema."""
        schema = self.get_parameters_schema()
        required = schema.get('required', [])
        return all(key in params for key in required)
    
    def to_ai_description(self) -> Dict[str, Any]:
        """Generate AI-friendly capability description."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
            "requires_safety_check": self.requires_safety_check,
            "autonomy_level": self.autonomy_level
        }
```

### 3.2 Decision Engine & Context Manager

**Deliverables:**
- `src/ai/decision_engine.py`
- `src/ai/context_manager.py`

```python
# src/ai/decision_engine.py
"""
AI Decision Engine - Routes tasks and manages execution flow.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from src.shared.types import AITaskRequest, OperationStatus
from src.shared.logger import get_logger
from src.ai.base_capability import BaseCapability, CapabilityResult
from src.ai.tool_registry import ToolRegistry

class DecisionMode(Enum):
    MANUAL = "manual"           # All actions require confirmation
    SEMI_AUTO = "semi_auto"     # Low-risk actions auto-approved
    AUTONOMOUS = "autonomous"   # Full autonomy within safety bounds

@dataclass
class ExecutionPlan:
    """Plan for executing a complex task."""
    steps: List[Dict[str, Any]]
    estimated_time: float
    risk_level: int  # 1-10
    requires_confirmation: bool

class DecisionEngine:
    """
    Core AI decision-making component.
    
    Responsibilities:
    - Route tasks to appropriate capabilities
    - Build execution plans for complex operations
    - Enforce safety checks before execution
    - Track operation history for learning
    """
    
    def __init__(self, config: dict, mode: DecisionMode = DecisionMode.SEMI_AUTO):
        self.config = config
        self.mode = mode
        self.logger = get_logger("decision_engine")
        self.registry = ToolRegistry()
        self.execution_history: List[Dict[str, Any]] = []
    
    def plan_task(self, request: AITaskRequest) -> ExecutionPlan:
        """
        Generate execution plan for a task request.
        """
        self.logger.info(f"Planning task: {request.task_type}")
        
        # Find relevant capabilities
        capabilities = self.registry.find_capabilities(request.task_type)
        
        steps = []
        for cap in capabilities:
            steps.append({
                "capability": cap.name,
                "parameters": request.parameters,
                "requires_safety": cap.requires_safety_check
            })
        
        risk_level = self._assess_risk(request, capabilities)
        
        return ExecutionPlan(
            steps=steps,
            estimated_time=len(steps) * 30.0,  # Rough estimate
            risk_level=risk_level,
            requires_confirmation=(risk_level > 5 or self.mode == DecisionMode.MANUAL)
        )
    
    def execute_plan(self, plan: ExecutionPlan) -> List[CapabilityResult]:
        """Execute an approved plan."""
        results = []
        for step in plan.steps:
            cap = self.registry.get(step["capability"])
            if cap:
                result = cap.execute(**step["parameters"])
                results.append(result)
                if not result.success:
                    self.logger.warning(f"Step failed: {step['capability']}")
                    break
        return results
    
    def _assess_risk(self, request: AITaskRequest, capabilities: List[BaseCapability]) -> int:
        """Assess risk level of a task (1-10)."""
        base_risk = 3
        
        # Increase risk for certain task types
        high_risk_keywords = ["delete", "destroy", "exfil", "persist", "lateral"]
        if any(kw in request.task_type.lower() for kw in high_risk_keywords):
            base_risk += 3
        
        # Increase for low autonomy capabilities
        if any(cap.autonomy_level < 3 for cap in capabilities):
            base_risk += 2
        
        return min(10, base_risk)
```

### 3.3 MCP Interface Server

**Deliverables:**
- `src/ai/mcp_interface.py`

```python
# src/ai/mcp_interface.py
"""
Model Context Protocol (MCP) server for AI integration.
Exposes AutoWonqNet capabilities via standardized API.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uvicorn

from src.shared.logger import get_logger
from src.ai.decision_engine import DecisionEngine, DecisionMode
from src.ai.tool_registry import ToolRegistry
from src.shared.types import AITaskRequest

app = FastAPI(
    title="AutoWonqNet AI Interface",
    description="MCP-compatible interface for AI-orchestrated red team operations",
    version="3.0.0"
)

logger = get_logger("mcp_interface")

# Global instances (initialized on startup)
decision_engine: Optional[DecisionEngine] = None
tool_registry: Optional[ToolRegistry] = None


class TaskRequest(BaseModel):
    """API request model for task execution."""
    task_type: str
    target_ip: Optional[str] = None
    parameters: Dict[str, Any] = {}
    priority: int = 5


class CapabilityInfo(BaseModel):
    """API response model for capability info."""
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    requires_safety_check: bool
    autonomy_level: int


@app.get("/capabilities", response_model=List[CapabilityInfo])
async def list_capabilities():
    """List all available AI-callable capabilities."""
    if not tool_registry:
        raise HTTPException(status_code=503, detail="Registry not initialized")
    
    return [
        CapabilityInfo(
            name=cap.name,
            description=cap.description,
            parameters_schema=cap.get_parameters_schema(),
            requires_safety_check=cap.requires_safety_check,
            autonomy_level=cap.autonomy_level
        )
        for cap in tool_registry.list_all()
    ]


@app.post("/execute")
async def execute_task(request: TaskRequest):
    """Execute an AI-requested task."""
    if not decision_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    logger.info(f"Received task request: {request.task_type}")
    
    # Convert to internal format
    ai_request = AITaskRequest(
        task_type=request.task_type,
        parameters=request.parameters,
        priority=request.priority
    )
    
    # Plan and execute
    plan = decision_engine.plan_task(ai_request)
    
    if plan.requires_confirmation:
        return {
            "status": "confirmation_required",
            "plan": {
                "steps": plan.steps,
                "risk_level": plan.risk_level,
                "estimated_time": plan.estimated_time
            }
        }
    
    results = decision_engine.execute_plan(plan)
    return {
        "status": "completed",
        "results": [{"success": r.success, "data": r.data} for r in results]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "3.0.0"}


async def start_mcp_server(config: dict, port: int = 8080):
    """Start the MCP interface server."""
    global decision_engine, tool_registry
    
    logger.info(f"Initializing AI interface on port {port}")
    
    tool_registry = ToolRegistry()
    decision_engine = DecisionEngine(config, mode=DecisionMode.SEMI_AUTO)
    
    # Register all capabilities
    tool_registry.auto_discover()
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
```

**🎯 Golden Path Test:**
```python
from src.ai.base_capability import BaseCapability, CapabilityResult
from src.ai.decision_engine import DecisionEngine, DecisionMode
from src.ai.tool_registry import ToolRegistry
from src.shared.types import AITaskRequest

# Base capability subclassable
class TestCapability(BaseCapability):
    name = "test_cap"
    description = "Test capability"
    
    def execute(self, **kwargs) -> CapabilityResult:
        return CapabilityResult(success=True, data="test")
    
    def get_parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}}

cap = TestCapability()
result = cap.execute()
assert result.success == True

# Decision engine instantiable
engine = DecisionEngine(config={}, mode=DecisionMode.MANUAL)
assert engine is not None
```

---

## Phase 4: Safety Controls Layer

### 4.1 Safety Modules

**Deliverables:**
- `src/safety/__init__.py`
- `src/safety/crypto_auth.py`
- `src/safety/geofencing.py`
- `src/safety/timebomb.py`
- `src/safety/killswitch.py`
- `src/safety/safety_governor.py`

```python
# src/safety/safety_governor.py
"""
Unified Safety Governor - Enforces all safety controls.
All destructive/risky operations MUST pass through this.
"""
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from src.shared.logger import get_logger
from src.shared.exceptions import SafetyViolation
from src.safety.geofencing import Geofencing
from src.safety.timebomb import TimeBomb
from src.safety.crypto_auth import CryptoAuthorization

@dataclass
class SafetyCheckResult:
    """Result of safety validation."""
    allowed: bool
    reason: str
    violations: list

class SafetyGovernor:
    """
    Central safety enforcement for all operations.
    
    Checks:
    1. Geofencing - Is target IP in allowed ranges?
    2. TimeBomb - Has operation window expired?
    3. CryptoAuth - Is operator authorized?
    4. Rate limiting - Too many operations too fast?
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = get_logger("safety_governor")
        
        # Initialize safety modules
        safety_config = config.get('safety', {})
        
        self.geofencing = Geofencing(
            allowed_cidrs=safety_config.get('allowed_cidrs', ['10.0.0.0/8', '192.168.0.0/16'])
        )
        
        kill_date = safety_config.get('kill_date')
        if kill_date:
            self.timebomb = TimeBomb(kill_date=datetime.fromisoformat(kill_date))
        else:
            self.timebomb = None
        
        self.crypto_auth = CryptoAuthorization(
            public_key_path=safety_config.get('operator_key_path')
        )
        
        self._operation_count = 0
        self._rate_limit = safety_config.get('rate_limit', 100)  # ops per minute
    
    def check(self, target_ip: Optional[str] = None, 
              require_auth: bool = False) -> SafetyCheckResult:
        """
        Run all safety checks for an operation.
        
        Args:
            target_ip: Target IP to validate against geofence
            require_auth: Whether crypto authorization is required
            
        Returns:
            SafetyCheckResult with allowed status and details
        """
        violations = []
        
        # Check timebomb
        if self.timebomb and self.timebomb.is_expired():
            violations.append("Operation window has expired (timebomb)")
        
        # Check geofencing
        if target_ip and not self.geofencing.is_authorized(target_ip):
            violations.append(f"Target {target_ip} outside allowed ranges")
        
        # Check authorization
        if require_auth and not self.crypto_auth.is_authorized():
            violations.append("Operator not authorized (crypto auth failed)")
        
        # Check rate limit
        if self._operation_count >= self._rate_limit:
            violations.append("Rate limit exceeded")
        
        if violations:
            self.logger.warning(f"Safety check failed: {violations}")
            return SafetyCheckResult(
                allowed=False,
                reason="Safety violations detected",
                violations=violations
            )
        
        self._operation_count += 1
        return SafetyCheckResult(allowed=True, reason="All checks passed", violations=[])
    
    def enforce(self, target_ip: Optional[str] = None, 
                require_auth: bool = False) -> None:
        """
        Enforce safety checks - raises exception if failed.
        """
        result = self.check(target_ip, require_auth)
        if not result.allowed:
            raise SafetyViolation(f"Safety violation: {result.violations}")
```

**🎯 Golden Path Test:**
```python
from src.safety.geofencing import Geofencing
from src.safety.timebomb import TimeBomb
from src.safety.safety_governor import SafetyGovernor
from datetime import datetime, timedelta

# Geofencing
geo = Geofencing(allowed_cidrs=['10.0.0.0/8', '192.168.0.0/16'])
assert geo.is_authorized('10.0.0.1') == True
assert geo.is_authorized('8.8.8.8') == False

# Timebomb
future = datetime.now() + timedelta(days=30)
bomb = TimeBomb(kill_date=future)
assert bomb.is_expired() == False

# Safety Governor
governor = SafetyGovernor(config={'safety': {'allowed_cidrs': ['10.0.0.0/8']}})
result = governor.check(target_ip='10.0.0.1')
assert result.allowed == True

result = governor.check(target_ip='8.8.8.8')
assert result.allowed == False
```

---

## Phase 5: C2 Framework Layer

### 5.1 Base Client & Unified Interface

**Deliverables:**
- `src/c2/__init__.py`
- `src/c2/base_client.py`
- `src/c2/unified_c2.py`

```python
# src/c2/base_client.py
"""Abstract base class for C2 client implementations."""
from abc import ABC, abstractmethod
from typing import List, Optional
from src.shared.types import Session, CommandResult

class BaseC2Client(ABC):
    """
    Abstract base for all C2 framework clients.
    Ensures consistent interface for AI orchestration.
    """
    
    framework_name: str = "base"
    
    def __init__(self, config: dict):
        self.config = config
        self._connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to C2 server."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass
    
    @abstractmethod
    def get_sessions(self) -> List[Session]:
        """Get all active sessions."""
        pass
    
    @abstractmethod
    def execute_command(self, session_id: str, command: str) -> CommandResult:
        """Execute command on session."""
        pass
    
    def is_connected(self) -> bool:
        return self._connected
```

```python
# src/c2/unified_c2.py
"""
Unified C2 interface - Facade for all C2 frameworks.
AI interacts with this, not individual clients.
"""
from typing import Dict, List, Optional
from src.shared.types import Session, CommandResult, C2Framework
from src.shared.logger import get_logger
from src.c2.base_client import BaseC2Client

class UnifiedC2:
    """
    Unified interface across all C2 frameworks.
    
    Provides:
    - Single API for all C2 operations
    - Automatic framework detection
    - Session aggregation
    - Command routing
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = get_logger("unified_c2")
        self.clients: Dict[C2Framework, BaseC2Client] = {}
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize configured C2 clients."""
        c2_config = self.config.get('c2', {})
        
        if 'sliver' in c2_config:
            from src.c2.sliver_client import SliverClient
            self.clients[C2Framework.SLIVER] = SliverClient(c2_config['sliver'])
        
        if 'havoc' in c2_config:
            from src.c2.havoc_client import HavocClient
            self.clients[C2Framework.HAVOC] = HavocClient(c2_config['havoc'])
        
        if 'covenant' in c2_config:
            from src.c2.covenant_client import CovenantClient
            self.clients[C2Framework.COVENANT] = CovenantClient(c2_config['covenant'])
        
        if 'mythic' in c2_config:
            from src.c2.mythic_client import MythicClient
            self.clients[C2Framework.MYTHIC] = MythicClient(c2_config['mythic'])
    
    def connect_all(self) -> Dict[C2Framework, bool]:
        """Connect to all configured C2 servers."""
        results = {}
        for framework, client in self.clients.items():
            try:
                results[framework] = client.connect()
                self.logger.info(f"Connected to {framework.value}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {framework.value}: {e}")
                results[framework] = False
        return results
    
    def get_all_sessions(self) -> List[Session]:
        """Get sessions from all connected C2 frameworks."""
        all_sessions = []
        for framework, client in self.clients.items():
            if client.is_connected():
                try:
                    sessions = client.get_sessions()
                    all_sessions.extend(sessions)
                except Exception as e:
                    self.logger.error(f"Failed to get sessions from {framework.value}: {e}")
        return all_sessions
    
    def execute_on_session(self, session_id: str, command: str) -> CommandResult:
        """Execute command on any session, auto-routing to correct framework."""
        # Find which framework owns this session
        for framework, client in self.clients.items():
            if client.is_connected():
                sessions = client.get_sessions()
                if any(s.id == session_id for s in sessions):
                    return client.execute_command(session_id, command)
        
        return CommandResult(success=False, output="", error=f"Session {session_id} not found")
    
    def broadcast_command(self, command: str, filter_os: Optional[str] = None) -> Dict[str, CommandResult]:
        """Broadcast command to all sessions (with optional OS filter)."""
        results = {}
        for session in self.get_all_sessions():
            if filter_os and session.os.lower() != filter_os.lower():
                continue
            result = self.execute_on_session(session.id, command)
            results[session.id] = result
        return results
```

### 5.2 Framework Clients

**Deliverables:**
- `src/c2/sliver_client.py`
- `src/c2/havoc_client.py`
- `src/c2/covenant_client.py`
- `src/c2/mythic_client.py`

**🎯 Golden Path Test:**
```python
from src.c2.base_client import BaseC2Client
from src.c2.sliver_client import SliverClient
from src.c2.havoc_client import HavocClient
from src.c2.mythic_client import MythicClient
from src.c2.unified_c2 import UnifiedC2

# All clients inherit from base
assert issubclass(SliverClient, BaseC2Client)
assert issubclass(HavocClient, BaseC2Client)
assert issubclass(MythicClient, BaseC2Client)

# Clients instantiable
sliver = SliverClient(config={'config_path': '/tmp/test.cfg'})
assert hasattr(sliver, 'get_sessions')

# Unified C2 instantiable
unified = UnifiedC2(config={})
assert hasattr(unified, 'get_all_sessions')
assert hasattr(unified, 'broadcast_command')
```

---

## Phase 6: Tool Wrappers Layer

### 6.1 Base Tool & Parrot Tool Wrappers

**Deliverables:**
- `src/tools/__init__.py`
- `src/tools/base_tool.py`
- `src/tools/nmap_wrapper.py`
- `src/tools/metasploit_wrapper.py`
- `src/tools/crackmapexec_wrapper.py`
- `src/tools/bloodhound_wrapper.py`

```python
# src/tools/base_tool.py
"""Base class for Parrot Security tool wrappers."""
from abc import abstractmethod
from typing import Dict, Any, Optional
import subprocess
import shlex

from src.ai.base_capability import BaseCapability, CapabilityResult
from src.shared.logger import get_logger

class BaseTool(BaseCapability):
    """
    Base class for wrapping Parrot Security tools.
    Inherits from BaseCapability for AI integration.
    """
    
    tool_binary: str = ""  # e.g., "nmap", "msfconsole"
    
    def __init__(self):
        self.logger = get_logger(self.name)
    
    def _run_command(self, args: list, timeout: int = 300) -> tuple[int, str, str]:
        """Execute tool command and return (returncode, stdout, stderr)."""
        cmd = [self.tool_binary] + args
        self.logger.debug(f"Executing: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    @abstractmethod
    def execute(self, **kwargs) -> CapabilityResult:
        pass
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        pass
```

```python
# src/tools/nmap_wrapper.py
"""Nmap wrapper for AI-driven network scanning."""
from typing import Dict, Any, List
from src.tools.base_tool import BaseTool
from src.ai.base_capability import CapabilityResult

class NmapWrapper(BaseTool):
    """AI-callable Nmap wrapper."""
    
    name = "nmap_scan"
    description = "Network scanner for host discovery and service enumeration"
    tool_binary = "nmap"
    requires_safety_check = True
    autonomy_level = 3
    
    def execute(self, target: str, scan_type: str = "quick", 
                ports: str = None, **kwargs) -> CapabilityResult:
        """
        Execute nmap scan.
        
        Args:
            target: IP or CIDR to scan
            scan_type: quick, full, stealth, vuln
            ports: Specific ports (e.g., "22,80,443" or "1-1000")
        """
        args = self._build_args(target, scan_type, ports)
        
        returncode, stdout, stderr = self._run_command(args, timeout=600)
        
        if returncode == 0:
            parsed = self._parse_output(stdout)
            return CapabilityResult(
                success=True,
                data=parsed,
                suggestions=self._generate_suggestions(parsed)
            )
        else:
            return CapabilityResult(
                success=False,
                data=None,
                error=stderr or "Nmap scan failed"
            )
    
    def _build_args(self, target: str, scan_type: str, ports: str) -> List[str]:
        args = []
        
        if scan_type == "quick":
            args.extend(["-sV", "-T4", "-F"])
        elif scan_type == "full":
            args.extend(["-sV", "-sC", "-A", "-p-"])
        elif scan_type == "stealth":
            args.extend(["-sS", "-T2", "-Pn"])
        elif scan_type == "vuln":
            args.extend(["-sV", "--script=vuln"])
        
        if ports:
            args.extend(["-p", ports])
        
        args.append(target)
        return args
    
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse nmap output into structured data."""
        # Simplified parser - in production, use python-nmap
        return {
            "raw_output": output,
            "hosts_found": output.count("Host is up"),
            "open_ports": output.count("open")
        }
    
    def _generate_suggestions(self, data: Dict[str, Any]) -> List[str]:
        """Generate AI suggestions based on scan results."""
        suggestions = []
        if data.get("open_ports", 0) > 0:
            suggestions.append("Consider running service-specific enumeration")
        if "445" in data.get("raw_output", ""):
            suggestions.append("SMB detected - consider running crackmapexec")
        return suggestions
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "IP or CIDR to scan"},
                "scan_type": {
                    "type": "string",
                    "enum": ["quick", "full", "stealth", "vuln"],
                    "default": "quick"
                },
                "ports": {"type": "string", "description": "Ports to scan"}
            },
            "required": ["target"]
        }
```

**🎯 Golden Path Test:**
```python
from src.tools.base_tool import BaseTool
from src.tools.nmap_wrapper import NmapWrapper
from src.ai.base_capability import BaseCapability

# Nmap inherits correctly
assert issubclass(NmapWrapper, BaseTool)
assert issubclass(NmapWrapper, BaseCapability)

# Instantiable
nmap = NmapWrapper()
assert nmap.name == "nmap_scan"
assert callable(nmap.execute)

# Schema available
schema = nmap.get_parameters_schema()
assert "target" in schema["required"]
```

---

## Phase 7: Traffic & Agent Layers

### 7.1 Traffic Modules

**Deliverables:**
- `src/traffic/__init__.py`
- `src/traffic/jitter.py`
- `src/traffic/dga.py`
- `src/traffic/synthetic.py`
- `src/traffic/domain_fronting.py`
- `src/traffic/malleable_profiles.py`
- `src/traffic/tor_controller.py`

### 7.2 Agent Factory

**Deliverables:**
- `src/agent/__init__.py`
- `src/agent/factory.py`
- `src/agent/donut_converter.py`
- `src/agent/signer.py`
- `src/agent/obfuscator.py`
- `src/agent/loader_generator.py`

**🎯 Golden Path Test:**
```python
from src.traffic.jitter import calculate_jittered_interval
from src.traffic.dga import generate_dga_domain
from src.agent.factory import AgentFactory

# Jitter
interval = calculate_jittered_interval(base=60, jitter_percent=20)
assert 48 <= interval <= 72

# DGA
domain = generate_dga_domain(seed="test", day_offset=0)
assert isinstance(domain, str)
assert '.' in domain

# Factory
factory = AgentFactory(config={'output_dir': '/tmp'})
assert hasattr(factory, 'build')
```

---

## Phase 8: Intel & Orchestration Layers

### 8.1 Intel Management

**Deliverables:**
- `src/intel/__init__.py`
- `src/intel/target_profile.py`
- `src/intel/credential_store.py`
- `src/intel/network_map.py`
- `src/intel/attack_graph.py`

### 8.2 Orchestration

**Deliverables:**
- `src/orchestration/__init__.py`
- `src/orchestration/redis_backend.py`
- `src/orchestration/postgres_backend.py`
- `src/orchestration/mass_beacon.py`
- `src/orchestration/event_handler.py`
- `src/orchestration/scheduler.py`
- `src/orchestration/campaign_manager.py`

**🎯 Golden Path Test:**
```python
from src.orchestration.redis_backend import RedisBackend
from src.orchestration.campaign_manager import CampaignManager
from src.intel.target_profile import TargetProfile

# Redis backend
redis = RedisBackend(host='localhost', port=6379)
assert hasattr(redis, 'store_session')

# Campaign manager
manager = CampaignManager(config={})
assert hasattr(manager, 'run_campaign')

# Target profile
target = TargetProfile(ip='10.0.0.1', hostname='DC01')
assert target.ip == '10.0.0.1'
```

---

## Phase 9: Infrastructure & Docker

### 9.1 Docker Compose Stack

**Deliverables:**
- `infra/docker-compose.yml`
- `infra/docker/parrot-base/Dockerfile` (from Phase 1)
- `infra/docker/sliver/Dockerfile`
- `infra/docker/nginx-redirector/Dockerfile`
- `infra/docker/tor/Dockerfile`
- `infra/docker/tor/torrc`

### 9.2 Nginx & Cloudflare Configs

**Deliverables:**
- `infra/nginx/nginx.conf`
- `infra/nginx/stream.conf`
- `infra/cloudflare/worker.js`

**🎯 Golden Path Test:**
```bash
# Docker compose validates
docker-compose -f infra/docker-compose.yml config

# Dockerfile syntax valid
docker build -f infra/docker/parrot-base/Dockerfile --check .
```

---

## Phase 10: Scripts & Final Integration

### 10.1 Utility Scripts

**Deliverables:**
- `scripts/build_all.sh`
- `scripts/start_stack.sh`
- `scripts/health_check.sh`
- `scripts/burn.py` (infrastructure rotation)
- `scripts/nuke.py` (self-destruct)

### 10.2 Tests

**Deliverables:**
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/mocks/__init__.py`
- `tests/mocks/mock_c2_server.py`
- `tests/mocks/mock_tool_output.py`
- `tests/test_safety.py`
- `tests/test_c2_clients.py`
- `tests/test_ai_capabilities.py`

**🎯 Golden Path Test:**
```bash
# All scripts valid
bash -n scripts/build_all.sh
bash -n scripts/start_stack.sh

# Python tests discoverable
python -m pytest tests/ --collect-only
```

---

## 📋 Final Success Criteria

### Syntax & Imports
- [ ] All Python files pass `python -m py_compile`
- [ ] All imports resolve (no ModuleNotFoundError)
- [ ] No circular imports
- [ ] All Dockerfiles valid syntax

### Instantiation
- [ ] All classes instantiable with mock configs
- [ ] AI capabilities register properly
- [ ] C2 clients inherit from BaseC2Client
- [ ] Tools inherit from BaseTool

### Core Functionality
- [ ] Safety Governor blocks unauthorized targets
- [ ] AI Decision Engine plans tasks
- [ ] Unified C2 aggregates sessions
- [ ] Tool wrappers return CapabilityResult

### Integration
- [ ] MCP server starts without error
- [ ] docker-compose.yml validates
- [ ] All shell scripts valid syntax
- [ ] Mock servers enable testing

---

## 🎯 Token Budget Priority

**High Priority (Cycles 1-3):**
1. ✅ Shared foundation (required by everything)
2. ✅ AI orchestration layer (core differentiator)
3. ✅ Safety controls (MUST be present)
4. ✅ C2 base + unified interface

**Medium Priority (Cycles 4-5):**
5. ⚠️ C2 client implementations
6. ⚠️ Tool wrappers (2-3 key tools)
7. ⚠️ Traffic modules

**Lower Priority (Cycles 6-7):**
8. 📦 Agent factory
9. 📦 Intel management
10. 📦 Docker infrastructure
11. 📦 Scripts & tests

---

*AutoWonqNet v3.0 - For authorized penetration testing only.*
*Parrot Security + AI Orchestration = Ultimate Red Team Platform*
