# AutoWonqNet v2.0 - Supercharged Build Plan

> Containerized Adversary Emulation Infrastructure
> Mode: Program | Sensitivity: 3 | Cycles: 7

---

## Project Overview

Build a scalable, containerized C2 infrastructure for authorized red team operations. The system uses Docker microservices, tiered redirectors, and multi-framework agent orchestration.

**Core Principles:**
- Ephemerality: Infrastructure is disposable ("cattle not pets")
- Segregation: Components isolated in containers
- Obfuscation: Multi-layer traffic masking
- Testability: All modules must be testable in isolation with mocks

---

## 🎯 Global Success Criteria

Before ANY cycle is marked SUCCESS, these must be true:
1. All Python files pass `python -m py_compile <file>`
2. All imports resolve within the project structure
3. No circular import dependencies
4. All classes are instantiable with mock/test configs
5. All Dockerfiles pass `docker build` syntax validation

---

## 📦 Dependency Graph (MUST FOLLOW)

```
src/
├── __init__.py
├── shared/                    # NO external deps (base layer)
│   ├── __init__.py
│   ├── constants.py          # Pure Python, no imports from src/
│   ├── exceptions.py         # Pure Python, no imports from src/
│   ├── logger.py             # Only: logging, os
│   └── config_loader.py      # Only: yaml, os, pathlib + shared.exceptions
│
├── safety/                    # Depends on: shared
│   ├── __init__.py
│   ├── crypto_auth.py        # gnupg + shared
│   ├── geofencing.py         # ipaddress + shared
│   ├── timebomb.py           # datetime + shared
│   └── killswitch.py         # shared + safety modules
│
├── traffic/                   # Depends on: shared
│   ├── __init__.py
│   ├── jitter.py             # random, time + shared
│   ├── dga.py                # hashlib + shared
│   ├── synthetic.py          # requests, random + shared
│   ├── domain_fronting.py    # requests + shared
│   └── malleable_profiles.py # json, random + shared
│
├── c2/                        # Depends on: shared, traffic
│   ├── __init__.py
│   ├── base_client.py        # ABC for all C2 clients
│   ├── sliver_client.py      # sliver-py + base_client
│   ├── havoc_client.py       # requests + base_client
│   └── covenant_client.py    # requests + base_client
│
├── agent/                     # Depends on: shared, c2
│   ├── __init__.py
│   ├── factory.py            # subprocess + shared
│   ├── donut_converter.py    # donut + shared
│   ├── signer.py             # subprocess (osslsigncode) + shared
│   └── obfuscator.py         # subprocess + shared
│
└── orchestration/             # Depends on: shared, c2, safety
    ├── __init__.py
    ├── redis_backend.py      # redis + shared
    ├── mass_beacon.py        # redis_backend + c2 clients
    ├── event_handler.py      # redis_backend + c2 clients
    └── scheduler.py          # datetime, threading + shared
```

**CRITICAL:** When implementing any module, ONLY import from layers above it in this graph!

---

## 🧪 Mock Infrastructure (MUST IMPLEMENT)

### Mock C2 Server Base
Create mock servers for testing C2 integrations WITHOUT real C2 servers.

**Deliverables:**
- `tests/__init__.py`
- `tests/mocks/__init__.py`
- `tests/mocks/mock_c2_server.py`

```python
# tests/mocks/mock_c2_server.py
"""
Mock C2 server for testing client integrations.
This allows testing C2 clients without running actual C2 infrastructure.
"""
from dataclasses import dataclass
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
    last_checkin: float

@dataclass
class MockBeacon:
    id: str
    remote_address: str
    interval: int
    jitter: int
    last_checkin: float

class MockC2Server:
    """Base mock C2 server that all mock implementations inherit from."""
    
    def __init__(self):
        self.sessions: Dict[str, MockSession] = {}
        self.beacons: Dict[str, MockBeacon] = {}
        self.command_queue: Dict[str, List[str]] = {}
        self.command_results: Dict[str, str] = {}
        self._connected = False
    
    def add_mock_session(self, **kwargs) -> MockSession:
        """Add a mock session for testing."""
        session = MockSession(
            id=kwargs.get('id', str(uuid.uuid4())),
            remote_address=kwargs.get('remote_address', '10.0.0.1'),
            hostname=kwargs.get('hostname', 'WORKSTATION-01'),
            username=kwargs.get('username', 'testuser'),
            os=kwargs.get('os', 'windows'),
            arch=kwargs.get('arch', 'amd64'),
            last_checkin=time.time()
        )
        self.sessions[session.id] = session
        return session
    
    def add_mock_beacon(self, **kwargs) -> MockBeacon:
        """Add a mock beacon for testing."""
        beacon = MockBeacon(
            id=kwargs.get('id', str(uuid.uuid4())),
            remote_address=kwargs.get('remote_address', '10.0.0.2'),
            interval=kwargs.get('interval', 60),
            jitter=kwargs.get('jitter', 10),
            last_checkin=time.time()
        )
        self.beacons[beacon.id] = beacon
        return beacon
    
    def connect(self) -> bool:
        """Simulate connection."""
        self._connected = True
        return True
    
    def disconnect(self):
        """Simulate disconnection."""
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected


class MockSliverServer(MockC2Server):
    """Mock Sliver C2 server for testing SliverClient."""
    
    def get_sessions(self) -> List[MockSession]:
        return list(self.sessions.values())
    
    def get_beacons(self) -> List[MockBeacon]:
        return list(self.beacons.values())
    
    def execute_command(self, session_id: str, command: str) -> str:
        """Mock command execution."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        # Return mock output based on command
        mock_outputs = {
            'whoami': 'DOMAIN\\testuser',
            'hostname': 'WORKSTATION-01',
            'pwd': 'C:\\Users\\testuser',
            'id': 'uid=1000(testuser) gid=1000(testuser)',
        }
        return mock_outputs.get(command.split()[0], f"Mock output for: {command}")
    
    def generate_implant(self, config: dict) -> bytes:
        """Mock implant generation - returns fake binary data."""
        return b"MOCK_SLIVER_IMPLANT_" + str(config).encode()[:100]


class MockHavocServer(MockC2Server):
    """Mock Havoc C2 server for testing HavocClient."""
    
    def get_demons(self) -> List[MockSession]:
        """Havoc calls agents 'Demons'."""
        return list(self.sessions.values())
    
    def execute_task(self, demon_id: str, task: str) -> str:
        if demon_id not in self.sessions:
            raise ValueError(f"Demon {demon_id} not found")
        return f"Task '{task}' queued for demon {demon_id}"
    
    def configure_sleep(self, demon_id: str, interval: int, jitter: int) -> bool:
        if demon_id not in self.sessions:
            return False
        return True


class MockCovenantServer(MockC2Server):
    """Mock Covenant C2 server for testing CovenantClient."""
    
    def __init__(self):
        super().__init__()
        self.listeners: Dict[str, dict] = {}
    
    def get_grunts(self) -> List[MockSession]:
        """Covenant calls agents 'Grunts'."""
        return list(self.sessions.values())
    
    def get_listeners(self) -> List[dict]:
        return list(self.listeners.values())
    
    def add_mock_listener(self, name: str, bind_port: int) -> dict:
        listener = {
            'id': str(uuid.uuid4()),
            'name': name,
            'bindPort': bind_port,
            'status': 'Active'
        }
        self.listeners[listener['id']] = listener
        return listener
    
    def execute_task(self, grunt_id: str, task_name: str, parameters: dict) -> str:
        if grunt_id not in self.sessions:
            raise ValueError(f"Grunt {grunt_id} not found")
        return f"Task '{task_name}' executed on grunt {grunt_id}"
    
    def create_launcher(self, listener_id: str, launcher_type: str) -> bytes:
        return b"MOCK_COVENANT_LAUNCHER_" + launcher_type.encode()
```

---

## Phase 1: Project Foundation

### 1.1 Project Structure Setup
Create the base directory structure and configuration files.

**Deliverables:**
- `README.md` - Project documentation
- `requirements.txt` - Python dependencies
- `config.yaml.example` - Configuration template
- `.gitignore` - Ignore patterns
- `main.py` - Entry point with CLI argument parsing

**requirements.txt contents:**
```
# Core
pyyaml>=6.0
redis>=4.5.0
requests>=2.28.0

# C2 Integration
sliver-py>=0.0.18

# Security
python-gnupg>=0.5.0
cryptography>=40.0.0

# Traffic
scapy>=2.5.0

# Testing
pytest>=7.0.0
```

**🎯 Golden Path Test:**
```python
# This MUST work after phase completion
import yaml
from pathlib import Path

# Config loads without error
with open('config.yaml.example', 'r') as f:
    config = yaml.safe_load(f)
assert 'c2' in config or 'sliver' in config or isinstance(config, dict)

# Main is importable
from main import main
assert callable(main)
```

### 1.2 Shared Utilities Module
Create the shared module with common utilities.

**Deliverables:**
- `src/__init__.py`
- `src/shared/__init__.py`
- `src/shared/config_loader.py`
- `src/shared/logger.py`
- `src/shared/constants.py`
- `src/shared/exceptions.py`

**🎯 Golden Path Test:**
```python
# This MUST work after phase completion
from src.shared.config_loader import ConfigLoader
from src.shared.logger import get_logger
from src.shared.exceptions import ConfigurationError

# Logger works
logger = get_logger("test")
logger.info("Test message")

# Config loader instantiable
loader = ConfigLoader()
assert hasattr(loader, 'load') or hasattr(loader, 'load_config')

# Exception is raisable
try:
    raise ConfigurationError("test")
except ConfigurationError:
    pass  # Expected
```

---

## Phase 2: Container Infrastructure

### 2.1 Sliver C2 Server Dockerfile
Create multi-stage Dockerfile for Sliver team server.

**Deliverables:**
- `infra/docker/sliver/Dockerfile`

**Requirements:**
- Stage 1: golang:1.21-bullseye builder
- Stage 2: debian:bullseye-slim runtime
- Non-root user (sliveruser:slivergroup)
- Expose: 8888 (mTLS), 31337 (gRPC), 443 (HTTPS)

**🎯 Success Criteria:**
```bash
# Dockerfile syntax must be valid
docker build -f infra/docker/sliver/Dockerfile --check .
# OR for older docker: docker build -f infra/docker/sliver/Dockerfile . 2>&1 | head -20
```

### 2.2 Nginx Redirector Dockerfile
Create Dockerfile for traffic filtering redirector.

**Deliverables:**
- `infra/docker/redirector/Dockerfile`

**🎯 Success Criteria:**
```bash
# Must build without syntax errors
docker build -f infra/docker/redirector/Dockerfile --check .
```

### 2.3 Tor Proxy Dockerfile
Create Dockerfile for anonymity layer.

**Deliverables:**
- `infra/docker/tor/Dockerfile`
- `infra/docker/tor/torrc`

### 2.4 Hashcat GPU Dockerfile
Create Dockerfile for credential cracking with GPU support.

**Deliverables:**
- `infra/docker/hashcat/Dockerfile`

### 2.5 Docker Compose Orchestration
Create docker-compose.yml to orchestrate all services.

**Deliverables:**
- `infra/docker-compose.yml`

**Services:** sliver, redirector, tor, redis, hashcat

**🎯 Golden Path Test:**
```bash
# docker-compose config must validate
docker-compose -f infra/docker-compose.yml config
```

---

## Phase 3: Traffic Redirection Layer

### 3.1 Nginx Traffic Filtration Config

**Deliverables:**
- `infra/nginx/nginx.conf`

**Logic:**
- Valid C2 paths → proxy to sliver
- Invalid traffic → proxy to decoy (microsoft.com)

### 3.2 Nginx mTLS Stream Passthrough

**Deliverables:**
- `infra/nginx/stream.conf`

### 3.3 Cloudflare Worker Script

**Deliverables:**
- `infra/cloudflare/worker.js`

**🎯 Success Criteria:**
- JavaScript syntax valid
- Handles request/response

---

## Phase 4: Domain Fronting Module

### 4.1 Domain Fronting Implementation

**Deliverables:**
- `src/traffic/__init__.py`
- `src/traffic/domain_fronting.py`

**🎯 Golden Path Test:**
```python
from src.traffic.domain_fronting import create_fronted_request, validate_fronting_config

# Function exists and is callable
assert callable(create_fronted_request)
assert callable(validate_fronting_config)

# Basic call works (may return None for invalid config, but shouldn't crash)
result = create_fronted_request(
    front_domain="cdn.example.com",
    real_host="c2.internal",
    path="/api/update",
    payload=b"test"
)
# Result should be dict or None, not crash
assert result is None or isinstance(result, (dict, bytes, str))
```

### 4.2 Malleable C2 Profile Generator

**Deliverables:**
- `src/traffic/malleable_profiles.py`

**🎯 Golden Path Test:**
```python
from src.traffic.malleable_profiles import generate_profile, randomize_uris

# Generate a profile
profile = generate_profile("default")
assert profile is not None
assert isinstance(profile, (dict, str))

# Randomize URIs
if isinstance(profile, dict):
    modified = randomize_uris(profile)
    assert modified is not None
```

---

## Phase 5: Agent Factory

### 5.1 Builder Toolchain Dockerfile

**Deliverables:**
- `infra/docker/builder/Dockerfile`

### 5.2 Agent Factory Core

**Deliverables:**
- `src/agent/__init__.py`
- `src/agent/factory.py`

**🎯 Golden Path Test:**
```python
from src.agent.factory import AgentFactory

# Instantiable with mock config
factory = AgentFactory(config={'output_dir': '/tmp'})
assert factory is not None
assert hasattr(factory, 'build_sliver_implant') or hasattr(factory, 'build')
```

### 5.3 Donut Shellcode Integration

**Deliverables:**
- `src/agent/donut_converter.py`

**🎯 Golden Path Test:**
```python
from src.agent.donut_converter import convert_to_shellcode

# Function exists (actual conversion needs donut installed)
assert callable(convert_to_shellcode)
```

### 5.4 Binary Signing Module

**Deliverables:**
- `src/agent/signer.py`

### 5.5 Obfuscation Pipeline

**Deliverables:**
- `src/agent/obfuscator.py`

**🎯 Golden Path Test:**
```python
from src.agent.obfuscator import run_pipeline, strip_symbols

assert callable(run_pipeline)
assert callable(strip_symbols)
```

---

## Phase 6: C2 Framework Integrations

### 6.0 Base C2 Client (IMPLEMENT FIRST)

**Deliverables:**
- `src/c2/__init__.py`
- `src/c2/base_client.py`

```python
# src/c2/base_client.py
"""
Abstract base class for all C2 client implementations.
This ensures consistent interface across Sliver, Havoc, Covenant.
"""
from abc import ABC, abstractmethod
from typing import List, Any, Optional
from dataclasses import dataclass

@dataclass
class Session:
    """Unified session representation across C2 frameworks."""
    id: str
    remote_address: str
    hostname: str
    username: str
    os: str
    arch: str
    
@dataclass  
class CommandResult:
    """Unified command result."""
    success: bool
    output: str
    error: Optional[str] = None

class BaseC2Client(ABC):
    """Abstract base class for C2 client implementations."""
    
    def __init__(self, config: dict):
        self.config = config
        self._connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to C2 server."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to C2 server."""
        pass
    
    @abstractmethod
    def get_sessions(self) -> List[Session]:
        """Get list of active sessions/agents."""
        pass
    
    @abstractmethod
    def execute_command(self, session_id: str, command: str) -> CommandResult:
        """Execute command on target session."""
        pass
    
    def is_connected(self) -> bool:
        return self._connected
```

### 6.1 Sliver Integration

**Deliverables:**
- `src/c2/sliver_client.py`

**MUST inherit from BaseC2Client!**

**🎯 Golden Path Test:**
```python
from src.c2.sliver_client import SliverClient
from src.c2.base_client import BaseC2Client

# Must inherit from base
assert issubclass(SliverClient, BaseC2Client)

# Instantiable with config dict (not actual connection)
client = SliverClient(config={'config_path': 'test.cfg'})
assert client is not None
assert hasattr(client, 'connect')
assert hasattr(client, 'get_sessions')
assert hasattr(client, 'execute_command')

# Test with mock (if mock infrastructure exists)
try:
    from tests.mocks.mock_c2_server import MockSliverServer
    mock = MockSliverServer()
    mock.add_mock_session(hostname="TEST-PC")
    # Client should be testable against mock
except ImportError:
    pass  # Mocks not yet implemented
```

### 6.2 Havoc Integration

**Deliverables:**
- `src/c2/havoc_client.py`

**MUST inherit from BaseC2Client!**

**🎯 Golden Path Test:**
```python
from src.c2.havoc_client import HavocClient
from src.c2.base_client import BaseC2Client

assert issubclass(HavocClient, BaseC2Client)

client = HavocClient(config={
    'teamserver_url': 'https://localhost:40056',
    'username': 'test',
    'password': 'test'
})
assert hasattr(client, 'get_demons') or hasattr(client, 'get_sessions')
```

### 6.3 Covenant Integration

**Deliverables:**
- `src/c2/covenant_client.py`

**MUST inherit from BaseC2Client!**

**🎯 Golden Path Test:**
```python
from src.c2.covenant_client import CovenantClient
from src.c2.base_client import BaseC2Client

assert issubclass(CovenantClient, BaseC2Client)

client = CovenantClient(config={
    'base_url': 'https://localhost:7443',
    'api_token': 'test-token'
})
assert hasattr(client, 'get_grunts') or hasattr(client, 'get_sessions')
```

---

## Phase 7: Safety Controls

### 7.1 GPG Cryptographic Authorization

**Deliverables:**
- `src/safety/__init__.py`
- `src/safety/crypto_auth.py`

**🎯 Golden Path Test:**
```python
from src.safety.crypto_auth import CryptoAuthorization

# Instantiable (won't have valid key, but shouldn't crash)
auth = CryptoAuthorization(public_key_path='/nonexistent/key.asc')
assert hasattr(auth, 'verify_license') or hasattr(auth, 'is_authorized')
```

### 7.2 Geofencing Restrictions

**Deliverables:**
- `src/safety/geofencing.py`

**🎯 Golden Path Test:**
```python
from src.safety.geofencing import Geofencing

# Create with allowed ranges
geo = Geofencing(allowed_cidrs=['10.0.0.0/8', '192.168.0.0/16'])

# Test authorization
assert geo.is_authorized('10.0.0.1') == True
assert geo.is_authorized('8.8.8.8') == False
```

### 7.3 Time-Bomb Self-Destruction

**Deliverables:**
- `src/safety/timebomb.py`

**🎯 Golden Path Test:**
```python
from src.safety.timebomb import TimeBomb
from datetime import datetime, timedelta

# Future date - not expired
future = datetime.now() + timedelta(days=30)
bomb = TimeBomb(kill_date=future)
assert bomb.is_expired() == False

# Past date - expired
past = datetime.now() - timedelta(days=1)
bomb_expired = TimeBomb(kill_date=past)
assert bomb_expired.is_expired() == True
```

### 7.4 Global Kill Switch

**Deliverables:**
- `src/safety/killswitch.py`

**🎯 Golden Path Test:**
```python
from src.safety.killswitch import kill_all_sessions, broadcast_kill_command

assert callable(kill_all_sessions)
assert callable(broadcast_kill_command)
```

---

## Phase 8: Mass Orchestration

### 8.1 Redis Backend Integration

**Deliverables:**
- `src/orchestration/__init__.py`
- `src/orchestration/redis_backend.py`

**🎯 Golden Path Test:**
```python
from src.orchestration.redis_backend import RedisBackend

# Instantiable (won't connect without Redis, but shouldn't crash)
backend = RedisBackend(host='localhost', port=6379, db=0)
assert hasattr(backend, 'store_session')
assert hasattr(backend, 'queue_command')
```

### 8.2 Mass Beacon Orchestrator

**Deliverables:**
- `src/orchestration/mass_beacon.py`

**🎯 Golden Path Test:**
```python
from src.orchestration.mass_beacon import MassBeaconOrchestrator

# Should be instantiable with mock objects
orchestrator = MassBeaconOrchestrator(
    config={},
    c2_clients=[],
    redis=None  # Or mock
)
assert hasattr(orchestrator, 'broadcast_command')
```

### 8.3 Event-Driven Handler

**Deliverables:**
- `src/orchestration/event_handler.py`

### 8.4 Business Hours Scheduler

**Deliverables:**
- `src/orchestration/scheduler.py`

**🎯 Golden Path Test:**
```python
from src.orchestration.scheduler import OperationalScheduler

scheduler = OperationalScheduler(
    timezone='UTC',
    business_start=9,
    business_end=17
)
# is_operational returns bool
result = scheduler.is_operational()
assert isinstance(result, bool)
```

---

## Phase 9: Traffic Simulation

### 9.1 Jitter Implementation

**Deliverables:**
- `src/traffic/jitter.py`

**🎯 Golden Path Test:**
```python
from src.traffic.jitter import calculate_jittered_interval, jittered_sleep

# Calculate jitter
interval = calculate_jittered_interval(base=60, jitter_percent=20)
assert 48 <= interval <= 72  # 60 +/- 20%

# Function exists
assert callable(jittered_sleep)
```

### 9.2 Synthetic Traffic Generator

**Deliverables:**
- `src/traffic/synthetic.py`

**🎯 Golden Path Test:**
```python
from src.traffic.synthetic import generate_decoy_dns, generate_noise_floor

assert callable(generate_decoy_dns)
assert callable(generate_noise_floor)
```

### 9.3 DGA Simulation

**Deliverables:**
- `src/traffic/dga.py`

**🎯 Golden Path Test:**
```python
from src.traffic.dga import generate_dga_domain, generate_dga_batch

# Generate single domain
domain = generate_dga_domain(seed="test", day_offset=0)
assert isinstance(domain, str)
assert '.' in domain  # Should be domain-like

# Generate batch
domains = generate_dga_batch(seed="test", count=5)
assert isinstance(domains, list)
assert len(domains) == 5
```

---

## Phase 10: Infrastructure Scripts

### 10.1 Infrastructure Rotation (burn.py)

**Deliverables:**
- `scripts/burn.py`

### 10.2 Self-Destruct (nuke.py)

**Deliverables:**
- `scripts/nuke.py`

### 10.3 Container Utility Scripts

**Deliverables:**
- `scripts/build_all.sh`
- `scripts/start_stack.sh`
- `scripts/health_check.sh`
- `scripts/logs.sh`

**🎯 Golden Path Test:**
```bash
# All scripts have valid bash syntax
bash -n scripts/build_all.sh
bash -n scripts/start_stack.sh
bash -n scripts/health_check.sh
bash -n scripts/logs.sh
```

---

## 📋 Final Success Criteria Checklist

**Syntax & Imports:**
- [ ] All Python files pass `python -m py_compile`
- [ ] All imports resolve (no ModuleNotFoundError at import time)
- [ ] No circular imports
- [ ] All Dockerfiles have valid syntax

**Instantiation:**
- [ ] All classes instantiable with test/mock configs
- [ ] No crashes on import
- [ ] Base classes properly inherited

**Core Functionality:**
- [ ] Geofencing correctly blocks/allows IPs
- [ ] TimeBomb correctly detects expiration
- [ ] Jitter calculation returns values in expected range
- [ ] DGA generates valid domain-like strings
- [ ] C2 clients inherit from BaseC2Client

**Integration:**
- [ ] Mock C2 servers allow testing without real infrastructure
- [ ] docker-compose.yml validates
- [ ] All shell scripts have valid syntax

---

## Token Budget Guidance

- Phase 1-2: Foundation (cycles 1-2)
- Phase 3-5: Core modules (cycles 3-4)
- Phase 6-8: Integration (cycles 5-6)
- Phase 9-10: Polish (cycle 7)

**Priority if running low on cycles:**
1. ✅ Shared utilities (required by everything)
2. ✅ C2 base client + implementations
3. ✅ Safety controls
4. ⚠️ Orchestration (can be simplified)
5. ⚠️ Traffic simulation (can be stubs)

---

*This specification is for authorized penetration testing only.*
