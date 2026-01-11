#!/usr/bin/env python3
"""
Wisdom Pits: Domain Expert Knowledge Banks
Part of mindstaQ v2.1.7 - ZERO LLM Code Generation

Pre-built knowledge banks for specific domains (security, networking, etc.)
that provide TOOL-SPECIFIC code patterns and implementations.

This directly addresses the "copypasta problem" by providing REAL implementations
for specific tools like nmap, bloodhound, feroxbuster, etc.

Key Features:
- Domain-specific code templates (not generic boilerplate!)
- Tool wrapper patterns with actual API knowledge
- Security best practices built-in
- Extensible pit system for new domains

WoNQ Impact: +25-35 points for domain-specific code

v2.1.7
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Callable
from enum import Enum
import json
from pathlib import Path


__version__ = '2.1.7'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class WisdomDomain(Enum):
    """Knowledge domains supported by Wisdom Pits."""
    SECURITY_TOOLS = "security_tools"
    NETWORK_SCANNING = "network_scanning"
    WEB_PENTESTING = "web_pentesting"
    CREDENTIAL_ATTACKS = "credential_attacks"
    POST_EXPLOITATION = "post_exploitation"
    C2_FRAMEWORKS = "c2_frameworks"
    FORENSICS = "forensics"
    CRYPTO = "crypto"
    DATABASE = "database"
    WEB_FRAMEWORKS = "web_frameworks"
    API_CLIENTS = "api_clients"
    AUTOMATION = "automation"


@dataclass
class WisdomEntry:
    """A knowledge entry in a wisdom pit."""
    name: str                           # Entry name (e.g., 'nmap_tcp_scan')
    domain: WisdomDomain                # Knowledge domain
    tool_name: str                      # Tool this applies to (e.g., 'nmap')
    code_template: str                  # Actual code implementation
    description: str                    # What this does
    keywords: List[str]                 # Search keywords
    imports: List[str]                  # Required imports
    dependencies: List[str]             # Python packages needed
    usage_example: str                  # How to use this
    api_docs_url: Optional[str] = None  # Link to official docs
    security_notes: List[str] = field(default_factory=list)
    related_entries: List[str] = field(default_factory=list)
    
    def matches_query(self, query: str) -> float:
        """Return match score for a query (0-1)."""
        query_lower = query.lower()
        score = 0.0
        
        # Exact tool name match
        if self.tool_name.lower() in query_lower:
            score += 0.5
        
        # Keyword matches
        for keyword in self.keywords:
            if keyword.lower() in query_lower:
                score += 0.1
        
        # Name match
        if self.name.lower() in query_lower:
            score += 0.3
        
        return min(score, 1.0)


@dataclass
class WisdomPit:
    """A collection of wisdom entries for a domain."""
    domain: WisdomDomain
    name: str
    description: str
    entries: Dict[str, WisdomEntry] = field(default_factory=dict)
    
    def add_entry(self, entry: WisdomEntry):
        """Add an entry to the pit."""
        self.entries[entry.name] = entry
    
    def search(self, query: str, limit: int = 5) -> List[WisdomEntry]:
        """Search entries by query."""
        scored = [(entry, entry.matches_query(query)) for entry in self.entries.values()]
        scored = [(e, s) for e, s in scored if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, s in scored[:limit]]


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY TOOLS WISDOM PIT
# ═══════════════════════════════════════════════════════════════════════════════

def create_security_tools_pit() -> WisdomPit:
    """Create the security tools wisdom pit with REAL implementations."""
    
    pit = WisdomPit(
        domain=WisdomDomain.SECURITY_TOOLS,
        name="Security Tools",
        description="Penetration testing and security tool wrappers"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NMAP ENTRIES
    # ═══════════════════════════════════════════════════════════════════════════
    
    pit.add_entry(WisdomEntry(
        name="nmap_wrapper",
        domain=WisdomDomain.NETWORK_SCANNING,
        tool_name="nmap",
        keywords=["port scan", "network scan", "tcp", "udp", "service detection"],
        description="Full-featured nmap wrapper with async support",
        imports=["subprocess", "asyncio", "xml.etree.ElementTree", "dataclasses", "typing"],
        dependencies=["nmap"],
        usage_example="scanner = NmapScanner(); results = await scanner.scan('192.168.1.0/24')",
        api_docs_url="https://nmap.org/book/man.html",
        security_notes=["Requires root/admin for SYN scans", "Rate limit to avoid detection"],
        code_template='''
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import subprocess
import asyncio
import xml.etree.ElementTree as ET
import shlex
import tempfile
import os


@dataclass
class PortInfo:
    """Information about a discovered port."""
    port: int
    protocol: str
    state: str
    service: str = ""
    version: str = ""
    product: str = ""
    extra_info: str = ""
    
    @property
    def is_open(self) -> bool:
        return self.state == "open"


@dataclass
class HostInfo:
    """Information about a scanned host."""
    ip: str
    hostname: str = ""
    state: str = "unknown"
    os_guess: str = ""
    ports: List[PortInfo] = field(default_factory=list)
    mac_address: str = ""
    vendor: str = ""
    
    @property
    def open_ports(self) -> List[PortInfo]:
        return [p for p in self.ports if p.is_open]


@dataclass
class ScanResult:
    """Result of an nmap scan."""
    hosts: List[HostInfo] = field(default_factory=list)
    scan_time: float = 0.0
    command: str = ""
    raw_output: str = ""
    success: bool = False
    error: str = ""
    
    @property
    def total_open_ports(self) -> int:
        return sum(len(h.open_ports) for h in self.hosts)


class NmapScanner:
    """
    Wrapper for nmap with async support.
    
    Provides:
    - TCP SYN scan (requires root)
    - TCP connect scan
    - UDP scan
    - Service version detection
    - OS detection
    - Script scanning (NSE)
    """
    
    def __init__(self, nmap_path: str = "nmap"):
        self.nmap_path = nmap_path
        self._verify_nmap()
    
    def _verify_nmap(self):
        """Verify nmap is installed."""
        try:
            result = subprocess.run(
                [self.nmap_path, "--version"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError("nmap not found")
        except FileNotFoundError:
            raise RuntimeError("nmap not found in PATH")
    
    async def scan(
        self,
        target: str,
        ports: str = "1-1000",
        scan_type: str = "tcp_syn",
        service_detection: bool = True,
        os_detection: bool = False,
        scripts: List[str] = None,
        timing: int = 3,
        extra_args: List[str] = None,
    ) -> ScanResult:
        """
        Run an nmap scan.
        
        Args:
            target: IP, hostname, or CIDR range
            ports: Port specification (e.g., "22,80,443" or "1-1000")
            scan_type: tcp_syn, tcp_connect, udp, or ack
            service_detection: Enable version detection (-sV)
            os_detection: Enable OS detection (-O)
            scripts: NSE scripts to run
            timing: Timing template 0-5 (0=paranoid, 5=insane)
            extra_args: Additional nmap arguments
        
        Returns:
            ScanResult with discovered hosts and ports
        """
        cmd = [self.nmap_path]
        
        # Scan type
        scan_flags = {
            "tcp_syn": "-sS",
            "tcp_connect": "-sT",
            "udp": "-sU",
            "ack": "-sA",
        }
        cmd.append(scan_flags.get(scan_type, "-sT"))
        
        # Ports
        cmd.extend(["-p", ports])
        
        # Timing
        cmd.append(f"-T{timing}")
        
        # Service detection
        if service_detection:
            cmd.append("-sV")
        
        # OS detection
        if os_detection:
            cmd.append("-O")
        
        # Scripts
        if scripts:
            cmd.extend(["--script", ",".join(scripts)])
        
        # Extra args
        if extra_args:
            cmd.extend(extra_args)
        
        # XML output for parsing
        cmd.extend(["-oX", "-"])
        
        # Target
        cmd.append(target)
        
        # Run scan
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0 and not stdout:
                return ScanResult(
                    success=False,
                    error=stderr.decode(),
                    command=" ".join(cmd)
                )
            
            # Parse XML output
            return self._parse_xml(stdout.decode(), " ".join(cmd))
            
        except Exception as e:
            return ScanResult(success=False, error=str(e), command=" ".join(cmd))
    
    def _parse_xml(self, xml_output: str, command: str) -> ScanResult:
        """Parse nmap XML output."""
        result = ScanResult(command=command, raw_output=xml_output)
        
        try:
            root = ET.fromstring(xml_output)
            
            # Get scan time
            if 'elapsed' in root.attrib:
                result.scan_time = float(root.attrib['elapsed'])
            
            # Parse hosts
            for host_elem in root.findall('.//host'):
                host = self._parse_host(host_elem)
                if host:
                    result.hosts.append(host)
            
            result.success = True
            
        except ET.ParseError as e:
            result.error = f"XML parse error: {e}"
        
        return result
    
    def _parse_host(self, host_elem) -> Optional[HostInfo]:
        """Parse a host element from XML."""
        # Get IP address
        addr_elem = host_elem.find("address[@addrtype='ipv4']")
        if addr_elem is None:
            addr_elem = host_elem.find("address[@addrtype='ipv6']")
        if addr_elem is None:
            return None
        
        host = HostInfo(ip=addr_elem.attrib.get('addr', ''))
        
        # Get hostname
        hostname_elem = host_elem.find(".//hostname")
        if hostname_elem is not None:
            host.hostname = hostname_elem.attrib.get('name', '')
        
        # Get state
        status_elem = host_elem.find("status")
        if status_elem is not None:
            host.state = status_elem.attrib.get('state', 'unknown')
        
        # Get MAC address
        mac_elem = host_elem.find("address[@addrtype='mac']")
        if mac_elem is not None:
            host.mac_address = mac_elem.attrib.get('addr', '')
            host.vendor = mac_elem.attrib.get('vendor', '')
        
        # Get OS guess
        os_elem = host_elem.find(".//osmatch")
        if os_elem is not None:
            host.os_guess = os_elem.attrib.get('name', '')
        
        # Parse ports
        for port_elem in host_elem.findall(".//port"):
            port = self._parse_port(port_elem)
            if port:
                host.ports.append(port)
        
        return host
    
    def _parse_port(self, port_elem) -> Optional[PortInfo]:
        """Parse a port element from XML."""
        port_num = port_elem.attrib.get('portid')
        if not port_num:
            return None
        
        port = PortInfo(
            port=int(port_num),
            protocol=port_elem.attrib.get('protocol', 'tcp')
        )
        
        # State
        state_elem = port_elem.find("state")
        if state_elem is not None:
            port.state = state_elem.attrib.get('state', 'unknown')
        
        # Service info
        service_elem = port_elem.find("service")
        if service_elem is not None:
            port.service = service_elem.attrib.get('name', '')
            port.product = service_elem.attrib.get('product', '')
            port.version = service_elem.attrib.get('version', '')
            port.extra_info = service_elem.attrib.get('extrainfo', '')
        
        return port
    
    async def quick_scan(self, target: str) -> ScanResult:
        """Quick scan of common ports."""
        return await self.scan(
            target,
            ports="21,22,23,25,53,80,110,111,135,139,143,443,445,993,995,1723,3306,3389,5900,8080",
            timing=4
        )
    
    async def full_scan(self, target: str) -> ScanResult:
        """Full port scan with service detection."""
        return await self.scan(
            target,
            ports="1-65535",
            service_detection=True,
            timing=3
        )
'''
    ))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # BLOODHOUND ENTRIES
    # ═══════════════════════════════════════════════════════════════════════════
    
    pit.add_entry(WisdomEntry(
        name="bloodhound_wrapper",
        domain=WisdomDomain.POST_EXPLOITATION,
        tool_name="bloodhound",
        keywords=["active directory", "ad", "graph", "domain", "kerberos", "ldap"],
        description="BloodHound data collector and analyzer wrapper",
        imports=["subprocess", "json", "pathlib", "dataclasses", "typing", "asyncio"],
        dependencies=["bloodhound", "neo4j"],
        usage_example="bh = BloodHoundWrapper(); await bh.collect(domain='corp.local')",
        api_docs_url="https://bloodhound.readthedocs.io/",
        security_notes=["Requires domain credentials", "May trigger security alerts"],
        code_template='''
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import subprocess
import asyncio
import json
import os


@dataclass
class ADUser:
    """Active Directory user."""
    name: str
    sid: str
    domain: str
    enabled: bool = True
    admin_count: bool = False
    service_account: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ADComputer:
    """Active Directory computer."""
    name: str
    sid: str
    domain: str
    os: str = ""
    enabled: bool = True
    dc: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ADGroup:
    """Active Directory group."""
    name: str
    sid: str
    domain: str
    members: List[str] = field(default_factory=list)
    admin_count: bool = False


@dataclass
class AttackPath:
    """An attack path in the domain."""
    source: str
    target: str
    path_length: int
    relationships: List[str] = field(default_factory=list)
    risk_score: float = 0.0


@dataclass
class CollectionResult:
    """Result of BloodHound collection."""
    success: bool
    output_path: Path
    users: List[ADUser] = field(default_factory=list)
    computers: List[ADComputer] = field(default_factory=list)
    groups: List[ADGroup] = field(default_factory=list)
    sessions: int = 0
    error: str = ""


class BloodHoundWrapper:
    """
    Wrapper for BloodHound data collection and analysis.
    
    Provides:
    - SharpHound collection execution
    - JSON data parsing
    - Attack path analysis
    - High-value target identification
    """
    
    def __init__(
        self,
        sharphound_path: str = None,
        output_dir: str = "./bloodhound_data",
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_pass: str = "bloodhound",
    ):
        self.sharphound_path = sharphound_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_pass = neo4j_pass
    
    async def collect(
        self,
        domain: str,
        collection_method: str = "All",
        credentials: Dict[str, str] = None,
        stealth: bool = False,
    ) -> CollectionResult:
        """
        Run BloodHound collection.
        
        Args:
            domain: Target domain
            collection_method: Collection method (All, DCOnly, Session, etc.)
            credentials: Optional dict with 'username' and 'password'
            stealth: Use stealth collection options
        """
        # Use bloodhound-python for collection
        cmd = [
            "bloodhound-python",
            "-d", domain,
            "-c", collection_method,
        ]
        
        if credentials:
            cmd.extend(["-u", credentials.get("username", "")])
            cmd.extend(["-p", credentials.get("password", "")])
        
        if stealth:
            cmd.extend(["--stealth"])
        
        # Output directory
        cmd.extend(["--zip", "-o", str(self.output_dir)])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                return CollectionResult(
                    success=False,
                    output_path=self.output_dir,
                    error=stderr.decode()
                )
            
            # Parse collected data
            return await self._parse_collection()
            
        except FileNotFoundError:
            return CollectionResult(
                success=False,
                output_path=self.output_dir,
                error="bloodhound-python not found"
            )
        except Exception as e:
            return CollectionResult(
                success=False,
                output_path=self.output_dir,
                error=str(e)
            )
    
    async def _parse_collection(self) -> CollectionResult:
        """Parse collected JSON files."""
        result = CollectionResult(success=True, output_path=self.output_dir)
        
        # Find JSON files
        json_files = list(self.output_dir.glob("*.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                if 'users' in json_file.name.lower():
                    result.users.extend(self._parse_users(data))
                elif 'computers' in json_file.name.lower():
                    result.computers.extend(self._parse_computers(data))
                elif 'groups' in json_file.name.lower():
                    result.groups.extend(self._parse_groups(data))
                    
            except Exception:
                continue
        
        return result
    
    def _parse_users(self, data: Dict) -> List[ADUser]:
        """Parse users from JSON."""
        users = []
        for user_data in data.get('data', []):
            props = user_data.get('Properties', {})
            users.append(ADUser(
                name=props.get('name', ''),
                sid=props.get('objectid', ''),
                domain=props.get('domain', ''),
                enabled=props.get('enabled', True),
                admin_count=props.get('admincount', False),
                properties=props
            ))
        return users
    
    def _parse_computers(self, data: Dict) -> List[ADComputer]:
        """Parse computers from JSON."""
        computers = []
        for comp_data in data.get('data', []):
            props = comp_data.get('Properties', {})
            computers.append(ADComputer(
                name=props.get('name', ''),
                sid=props.get('objectid', ''),
                domain=props.get('domain', ''),
                os=props.get('operatingsystem', ''),
                enabled=props.get('enabled', True),
                dc=props.get('isdc', False),
                properties=props
            ))
        return computers
    
    def _parse_groups(self, data: Dict) -> List[ADGroup]:
        """Parse groups from JSON."""
        groups = []
        for group_data in data.get('data', []):
            props = group_data.get('Properties', {})
            groups.append(ADGroup(
                name=props.get('name', ''),
                sid=props.get('objectid', ''),
                domain=props.get('domain', ''),
                admin_count=props.get('admincount', False),
            ))
        return groups
    
    def find_high_value_targets(self, result: CollectionResult) -> List[str]:
        """Identify high-value targets."""
        targets = []
        
        # Domain admins
        for user in result.users:
            if user.admin_count:
                targets.append(f"User: {user.name} (Admin)")
        
        # Domain controllers
        for computer in result.computers:
            if computer.dc:
                targets.append(f"DC: {computer.name}")
        
        return targets
'''
    ))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FEROXBUSTER ENTRIES
    # ═══════════════════════════════════════════════════════════════════════════
    
    pit.add_entry(WisdomEntry(
        name="feroxbuster_wrapper",
        domain=WisdomDomain.WEB_PENTESTING,
        tool_name="feroxbuster",
        keywords=["directory", "bruteforce", "web", "fuzzing", "content discovery"],
        description="Feroxbuster wrapper for web content discovery",
        imports=["subprocess", "asyncio", "json", "dataclasses", "typing"],
        dependencies=["feroxbuster"],
        usage_example="scanner = FeroxbusterScanner(); results = await scanner.scan('http://target.com')",
        api_docs_url="https://github.com/epi052/feroxbuster",
        security_notes=["Rate limit to avoid detection", "Check scope before scanning"],
        code_template='''
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import subprocess
import asyncio
import json


@dataclass
class DiscoveredPath:
    """A discovered path/endpoint."""
    url: str
    status_code: int
    content_length: int
    content_type: str = ""
    redirect_url: str = ""
    is_directory: bool = False


@dataclass
class ScanResult:
    """Result of feroxbuster scan."""
    target: str
    paths: List[DiscoveredPath] = field(default_factory=list)
    total_requests: int = 0
    scan_time: float = 0.0
    success: bool = False
    error: str = ""
    
    @property
    def directories(self) -> List[DiscoveredPath]:
        return [p for p in self.paths if p.is_directory]
    
    @property
    def files(self) -> List[DiscoveredPath]:
        return [p for p in self.paths if not p.is_directory]


class FeroxbusterScanner:
    """
    Wrapper for feroxbuster web content discovery.
    
    Features:
    - Recursive directory scanning
    - Multiple wordlist support
    - Extension fuzzing
    - Status code filtering
    - Rate limiting
    """
    
    def __init__(self, ferox_path: str = "feroxbuster"):
        self.ferox_path = ferox_path
        self.default_wordlist = "/usr/share/wordlists/dirb/common.txt"
    
    async def scan(
        self,
        target: str,
        wordlist: str = None,
        extensions: List[str] = None,
        threads: int = 50,
        depth: int = 2,
        timeout: int = 7,
        status_codes: List[int] = None,
        filter_codes: List[int] = None,
        headers: Dict[str, str] = None,
        cookies: str = None,
        proxy: str = None,
    ) -> ScanResult:
        """
        Run feroxbuster scan.
        
        Args:
            target: Target URL
            wordlist: Path to wordlist
            extensions: File extensions to try
            threads: Number of threads
            depth: Recursion depth
            timeout: Request timeout
            status_codes: Only show these codes
            filter_codes: Filter out these codes
            headers: Custom headers
            cookies: Cookie string
            proxy: Proxy URL
        """
        cmd = [self.ferox_path]
        
        # Target
        cmd.extend(["-u", target])
        
        # Wordlist
        cmd.extend(["-w", wordlist or self.default_wordlist])
        
        # Extensions
        if extensions:
            cmd.extend(["-x", ",".join(extensions)])
        
        # Threads
        cmd.extend(["-t", str(threads)])
        
        # Depth
        cmd.extend(["-d", str(depth)])
        
        # Timeout
        cmd.extend(["--timeout", str(timeout)])
        
        # Status codes
        if status_codes:
            cmd.extend(["-s", ",".join(map(str, status_codes))])
        
        if filter_codes:
            for code in filter_codes:
                cmd.extend(["-C", str(code)])
        
        # Headers
        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])
        
        # Cookies
        if cookies:
            cmd.extend(["-b", cookies])
        
        # Proxy
        if proxy:
            cmd.extend(["-p", proxy])
        
        # JSON output
        cmd.extend(["--json", "-q"])
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            return self._parse_output(target, stdout.decode())
            
        except FileNotFoundError:
            return ScanResult(
                target=target,
                success=False,
                error="feroxbuster not found"
            )
        except Exception as e:
            return ScanResult(
                target=target,
                success=False,
                error=str(e)
            )
    
    def _parse_output(self, target: str, output: str) -> ScanResult:
        """Parse JSON output from feroxbuster."""
        result = ScanResult(target=target, success=True)
        
        for line in output.strip().split("\\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                
                if data.get('type') == 'response':
                    path = DiscoveredPath(
                        url=data.get('url', ''),
                        status_code=data.get('status', 0),
                        content_length=data.get('content_length', 0),
                        content_type=data.get('content_type', ''),
                        redirect_url=data.get('redirect_url', ''),
                        is_directory=data.get('is_directory', False),
                    )
                    result.paths.append(path)
                    result.total_requests += 1
                    
            except json.JSONDecodeError:
                continue
        
        return result
    
    async def quick_scan(self, target: str) -> ScanResult:
        """Quick scan with common settings."""
        return await self.scan(
            target,
            extensions=["php", "html", "js", "txt"],
            threads=100,
            depth=1,
            filter_codes=[404, 403]
        )
'''
    ))
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MASSCAN ENTRIES
    # ═══════════════════════════════════════════════════════════════════════════
    
    pit.add_entry(WisdomEntry(
        name="masscan_wrapper",
        domain=WisdomDomain.NETWORK_SCANNING,
        tool_name="masscan",
        keywords=["port scan", "fast", "network", "mass scan", "tcp"],
        description="Masscan wrapper for high-speed port scanning",
        imports=["subprocess", "asyncio", "json", "dataclasses", "typing"],
        dependencies=["masscan"],
        usage_example="scanner = MasscanScanner(); results = await scanner.scan('10.0.0.0/8')",
        api_docs_url="https://github.com/robertdavidgraham/masscan",
        security_notes=["Can overwhelm networks", "Requires root", "Rate limit appropriately"],
        code_template='''
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import subprocess
import asyncio
import json


@dataclass
class OpenPort:
    """An open port discovered by masscan."""
    ip: str
    port: int
    protocol: str = "tcp"
    ttl: int = 0


@dataclass
class ScanResult:
    """Result of masscan scan."""
    ports: List[OpenPort] = field(default_factory=list)
    scan_rate: int = 0
    total_hosts: int = 0
    success: bool = False
    error: str = ""


class MasscanScanner:
    """
    High-speed port scanner wrapper.
    
    Can scan millions of hosts quickly.
    Use responsibly!
    """
    
    def __init__(self, masscan_path: str = "masscan"):
        self.masscan_path = masscan_path
    
    async def scan(
        self,
        target: str,
        ports: str = "1-1000",
        rate: int = 1000,
        wait: int = 5,
    ) -> ScanResult:
        """
        Run masscan.
        
        Args:
            target: IP range (CIDR notation)
            ports: Port range
            rate: Packets per second
            wait: Seconds to wait for responses
        """
        cmd = [
            self.masscan_path,
            target,
            "-p", ports,
            "--rate", str(rate),
            "--wait", str(wait),
            "-oJ", "-",  # JSON output
        ]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            return self._parse_output(stdout.decode())
            
        except Exception as e:
            return ScanResult(success=False, error=str(e))
    
    def _parse_output(self, output: str) -> ScanResult:
        """Parse JSON output."""
        result = ScanResult(success=True)
        
        try:
            # Masscan outputs array of results
            for line in output.strip().split("\\n"):
                if not line or line.startswith('[') or line.startswith(']'):
                    continue
                line = line.rstrip(',')
                try:
                    data = json.loads(line)
                    port = OpenPort(
                        ip=data.get('ip', ''),
                        port=data.get('ports', [{}])[0].get('port', 0),
                        protocol=data.get('ports', [{}])[0].get('proto', 'tcp'),
                    )
                    result.ports.append(port)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
        
        result.total_hosts = len(set(p.ip for p in result.ports))
        return result
'''
    ))
    
    return pit


# ═══════════════════════════════════════════════════════════════════════════════
# WISDOM PITS MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class WisdomPitsManager:
    """
    Central manager for all wisdom pits.
    
    Usage:
        manager = WisdomPitsManager()
        manager.load_default_pits()
        
        # Search for tool code
        results = manager.search("nmap port scanner")
        for entry in results:
            print(entry.code_template)
    """
    
    def __init__(self):
        self.pits: Dict[WisdomDomain, WisdomPit] = {}
    
    def load_default_pits(self):
        """Load all default wisdom pits."""
        # Security tools pit
        security_pit = create_security_tools_pit()
        self.pits[WisdomDomain.SECURITY_TOOLS] = security_pit
        self.pits[WisdomDomain.NETWORK_SCANNING] = security_pit
        self.pits[WisdomDomain.WEB_PENTESTING] = security_pit
        self.pits[WisdomDomain.POST_EXPLOITATION] = security_pit
    
    def add_pit(self, pit: WisdomPit):
        """Add a wisdom pit."""
        self.pits[pit.domain] = pit
    
    def search(
        self,
        query: str,
        domain: WisdomDomain = None,
        limit: int = 5
    ) -> List[WisdomEntry]:
        """
        Search all pits for matching entries.
        
        Args:
            query: Search query
            domain: Optional domain filter
            limit: Max results
        
        Returns:
            List of matching WisdomEntry objects
        """
        results = []
        
        pits_to_search = [self.pits[domain]] if domain and domain in self.pits else self.pits.values()
        
        for pit in pits_to_search:
            results.extend(pit.search(query, limit))
        
        # Sort by match score and deduplicate
        seen = set()
        unique = []
        for entry in results:
            if entry.name not in seen:
                seen.add(entry.name)
                unique.append(entry)
        
        return unique[:limit]
    
    def get_code_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Get implementation code for a specific tool.
        
        Args:
            tool_name: Name of tool (e.g., 'nmap', 'bloodhound')
        
        Returns:
            Code template or None
        """
        results = self.search(tool_name, limit=1)
        if results:
            return results[0].code_template
        return None
    
    def list_available_tools(self) -> List[str]:
        """List all tools with wisdom entries."""
        tools = set()
        for pit in self.pits.values():
            for entry in pit.entries.values():
                tools.add(entry.tool_name)
        return sorted(tools)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

_default_manager: Optional[WisdomPitsManager] = None

def get_wisdom_manager() -> WisdomPitsManager:
    """Get the default wisdom pits manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = WisdomPitsManager()
        _default_manager.load_default_pits()
    return _default_manager


def get_tool_code(tool_name: str) -> Optional[str]:
    """Get code for a tool from wisdom pits."""
    return get_wisdom_manager().get_code_for_tool(tool_name)


def search_wisdom(query: str, limit: int = 5) -> List[WisdomEntry]:
    """Search wisdom pits for matching entries."""
    return get_wisdom_manager().search(query, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Wisdom Pits v{__version__}")
    print("=" * 70)
    
    manager = WisdomPitsManager()
    manager.load_default_pits()
    
    print("\n[1] Available tools:")
    print("-" * 40)
    for tool in manager.list_available_tools():
        print(f"  - {tool}")
    
    print("\n[2] Search for 'nmap port scanner':")
    print("-" * 40)
    results = manager.search("nmap port scanner")
    for entry in results:
        print(f"  Found: {entry.name} ({entry.tool_name})")
        print(f"    Keywords: {', '.join(entry.keywords[:5])}")
    
    print("\n[3] Get nmap code:")
    print("-" * 40)
    code = manager.get_code_for_tool("nmap")
    if code:
        print(f"  Code length: {len(code)} chars")
        print(f"  First 200 chars:\n{code[:200]}...")
    
    print("\n" + "=" * 70)
    print("✅ Wisdom Pits working!")
