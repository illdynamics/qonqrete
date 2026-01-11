#!/usr/bin/env python3
"""
sQavanger: Web Search Harvester Agent (Tier 1)
Part of mindstaQ - REAL web search for code harvesting

This is the REAL sQavanger that:
1. Takes a task/intent from Qomputator
2. Builds optimized search queries
3. Searches via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
4. Harvests REAL code snippets from search results
5. Ranks and filters snippets by relevance
6. Returns the best matching code for the task
7. Falls back to OFFLINE_PATTERNS when web search fails (v1.9.2)

v2.0.0-stable - OFFLINE PATTERNS FALLBACK
- Added _match_offline_pattern() method
- Expanded OFFLINE_PATTERNS from 4 to 11 patterns
- Now actually uses offline patterns when web search returns nothing!
"""

import asyncio
import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import sys

# Import Qrawler
try:
    from worqer.mindstaq.qrawler import Qrawler, QrawlerResult, CodeSnippet, CodeExtractor
    HAS_QRAWLER = True
except ImportError:
    try:
        from qrawler import Qrawler, QrawlerResult, CodeSnippet, CodeExtractor
        HAS_QRAWLER = True
    except ImportError:
        HAS_QRAWLER = False

# Import intent crystallizer for context
try:
    from worqer.mindstaq import CrystallizedIntent, ActionType, TargetType
    HAS_INTENT = True
except ImportError:
    HAS_INTENT = False

# v1.9.8: Safe non-blocking logger
try:
    from worqer.mindstaq.mindstaq_logger import mlog
except ImportError:
    mlog = None

def _log(msg):
    if mlog:
        mlog.tier("SQAVENGER", msg)


__version__ = '2.2.8-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# v2.1.9: TOOL-SPECIFIC PATTERNS - REAL IMPLEMENTATIONS!
# These are ACTUAL tool wrappers, not generic copypasta!
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_PATTERNS = {
    'nmap_wrapper': '''#!/usr/bin/env python3
"""Nmap Scanner Wrapper - Network reconnaissance and port scanning."""
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import json


@dataclass
class NmapHost:
    """Discovered host from nmap scan."""
    ip: str
    hostname: str = ""
    state: str = "unknown"
    ports: List[Dict[str, Any]] = field(default_factory=list)
    os_matches: List[str] = field(default_factory=list)


@dataclass 
class NmapResult:
    """Result from nmap scan."""
    hosts: List[NmapHost] = field(default_factory=list)
    scan_info: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    xml_output: str = ""


class NmapScanner:
    """Wrapper for nmap network scanner."""
    
    def __init__(self, nmap_path: str = "nmap"):
        self.nmap_path = nmap_path
        self._verify_nmap()
    
    def _verify_nmap(self):
        """Verify nmap is installed."""
        try:
            result = subprocess.run([self.nmap_path, "--version"], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("nmap not found")
        except FileNotFoundError:
            raise RuntimeError("nmap not installed - apt install nmap")
    
    def scan(self, target: str, ports: str = "1-1000", 
             arguments: str = "-sV -sC", timeout: int = 300) -> NmapResult:
        """
        Run nmap scan on target.
        
        Args:
            target: IP, hostname, or CIDR range
            ports: Port specification (e.g., "22,80,443" or "1-1000")
            arguments: Nmap arguments (e.g., "-sV -sC -O")
            timeout: Scan timeout in seconds
        
        Returns:
            NmapResult with discovered hosts and services
        """
        cmd = [self.nmap_path, "-oX", "-", "-p", ports]
        cmd.extend(arguments.split())
        cmd.append(target)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return self._parse_xml(result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return NmapResult(raw_output=f"Scan timeout after {timeout}s")
        except Exception as e:
            return NmapResult(raw_output=f"Scan error: {e}")
    
    def _parse_xml(self, xml_output: str, stderr: str) -> NmapResult:
        """Parse nmap XML output."""
        result = NmapResult(xml_output=xml_output, raw_output=stderr)
        
        try:
            root = ET.fromstring(xml_output)
            
            # Parse scan info
            scaninfo = root.find("scaninfo")
            if scaninfo is not None:
                result.scan_info = dict(scaninfo.attrib)
            
            # Parse hosts
            for host_elem in root.findall("host"):
                host = NmapHost(ip="")
                
                # Get address
                addr = host_elem.find("address")
                if addr is not None:
                    host.ip = addr.get("addr", "")
                
                # Get hostname
                hostnames = host_elem.find("hostnames")
                if hostnames is not None:
                    hostname_elem = hostnames.find("hostname")
                    if hostname_elem is not None:
                        host.hostname = hostname_elem.get("name", "")
                
                # Get state
                status = host_elem.find("status")
                if status is not None:
                    host.state = status.get("state", "unknown")
                
                # Get ports
                ports_elem = host_elem.find("ports")
                if ports_elem is not None:
                    for port_elem in ports_elem.findall("port"):
                        port_info = {
                            "port": int(port_elem.get("portid", 0)),
                            "protocol": port_elem.get("protocol", "tcp"),
                            "state": "unknown",
                            "service": "",
                            "version": ""
                        }
                        
                        state = port_elem.find("state")
                        if state is not None:
                            port_info["state"] = state.get("state", "unknown")
                        
                        service = port_elem.find("service")
                        if service is not None:
                            port_info["service"] = service.get("name", "")
                            port_info["version"] = service.get("version", "")
                        
                        host.ports.append(port_info)
                
                # Get OS matches
                os_elem = host_elem.find("os")
                if os_elem is not None:
                    for osmatch in os_elem.findall("osmatch"):
                        host.os_matches.append(osmatch.get("name", ""))
                
                result.hosts.append(host)
        
        except ET.ParseError:
            pass
        
        return result
    
    def quick_scan(self, target: str) -> NmapResult:
        """Quick scan of common ports."""
        return self.scan(target, ports="21,22,23,25,53,80,110,139,143,443,445,3306,3389,8080", 
                        arguments="-sV -T4")
    
    def full_scan(self, target: str) -> NmapResult:
        """Full port scan with service detection."""
        return self.scan(target, ports="1-65535", arguments="-sV -sC -O -T4")


if __name__ == "__main__":
    scanner = NmapScanner()
    result = scanner.quick_scan("127.0.0.1")
    for host in result.hosts:
        print(f"Host: {host.ip} ({host.hostname}) - {host.state}")
        for port in host.ports:
            print(f"  {port['port']}/{port['protocol']} {port['state']} {port['service']}")
''',

    'bloodhound_wrapper': '''#!/usr/bin/env python3
"""BloodHound/SharpHound Wrapper - Active Directory attack path analysis."""
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import zipfile


@dataclass
class ADObject:
    """Active Directory object."""
    name: str
    object_type: str  # User, Computer, Group, Domain
    distinguished_name: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttackPath:
    """Attack path between AD objects."""
    source: str
    target: str
    relationship: str  # MemberOf, AdminTo, HasSession, etc.
    is_inherited: bool = False


@dataclass
class BloodHoundResult:
    """Result from BloodHound collection."""
    users: List[ADObject] = field(default_factory=list)
    computers: List[ADObject] = field(default_factory=list)
    groups: List[ADObject] = field(default_factory=list)
    domains: List[ADObject] = field(default_factory=list)
    relationships: List[AttackPath] = field(default_factory=list)
    collection_method: str = ""
    domain: str = ""


class BloodHoundCollector:
    """Wrapper for BloodHound/SharpHound collection."""
    
    def __init__(self, sharphound_path: str = None, output_dir: str = "/tmp/bloodhound"):
        self.sharphound_path = sharphound_path or self._find_sharphound()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _find_sharphound(self) -> Optional[str]:
        """Find SharpHound executable."""
        possible_paths = [
            "/opt/SharpHound/SharpHound.exe",
            "/usr/share/bloodhound/collectors/SharpHound.exe",
            "./SharpHound.exe"
        ]
        for path in possible_paths:
            if Path(path).exists():
                return path
        return None
    
    def collect(self, domain: str = None, collection_method: str = "All",
                username: str = None, password: str = None,
                timeout: int = 600) -> BloodHoundResult:
        """
        Run BloodHound collection.
        
        Args:
            domain: Target domain (auto-detect if None)
            collection_method: Collection method (All, DCOnly, Session, etc.)
            username: Domain username for authentication
            password: Domain password
            timeout: Collection timeout
        
        Returns:
            BloodHoundResult with collected data
        """
        result = BloodHoundResult(collection_method=collection_method, domain=domain or "")
        
        if not self.sharphound_path:
            # Fall back to Python-based collection
            return self._collect_python(domain, username, password)
        
        # Build SharpHound command
        cmd = ["mono", self.sharphound_path] if self.sharphound_path.endswith(".exe") else [self.sharphound_path]
        cmd.extend(["--CollectionMethod", collection_method])
        cmd.extend(["--OutputDirectory", str(self.output_dir)])
        
        if domain:
            cmd.extend(["--Domain", domain])
        if username and password:
            cmd.extend(["--LDAPUser", username, "--LDAPPass", password])
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            
            # Find and parse output zip
            zip_files = list(self.output_dir.glob("*.zip"))
            if zip_files:
                result = self._parse_bloodhound_zip(zip_files[-1])
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            result.collection_method = f"Error: {e}"
        
        return result
    
    def _collect_python(self, domain: str, username: str, password: str) -> BloodHoundResult:
        """Python-based AD collection using ldap3."""
        result = BloodHoundResult(collection_method="Python-LDAP")
        
        try:
            from ldap3 import Server, Connection, ALL, SUBTREE
            
            server = Server(domain, get_info=ALL)
            conn = Connection(server, user=username, password=password, auto_bind=True)
            
            base_dn = ",".join([f"DC={part}" for part in domain.split(".")])
            
            # Collect users
            conn.search(base_dn, "(objectClass=user)", search_scope=SUBTREE,
                       attributes=["sAMAccountName", "distinguishedName", "memberOf"])
            for entry in conn.entries:
                user = ADObject(
                    name=str(entry.sAMAccountName),
                    object_type="User",
                    distinguished_name=str(entry.distinguishedName)
                )
                result.users.append(user)
            
            # Collect groups
            conn.search(base_dn, "(objectClass=group)", search_scope=SUBTREE,
                       attributes=["sAMAccountName", "distinguishedName", "member"])
            for entry in conn.entries:
                group = ADObject(
                    name=str(entry.sAMAccountName),
                    object_type="Group",
                    distinguished_name=str(entry.distinguishedName)
                )
                result.groups.append(group)
            
            conn.unbind()
        except ImportError:
            result.collection_method = "Error: ldap3 not installed"
        except Exception as e:
            result.collection_method = f"Error: {e}"
        
        return result
    
    def _parse_bloodhound_zip(self, zip_path: Path) -> BloodHoundResult:
        """Parse BloodHound zip output."""
        result = BloodHoundResult()
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for filename in zf.namelist():
                if filename.endswith('.json'):
                    data = json.loads(zf.read(filename))
                    
                    if 'users' in filename.lower():
                        for item in data.get('data', []):
                            result.users.append(ADObject(
                                name=item.get('Properties', {}).get('name', ''),
                                object_type='User',
                                properties=item.get('Properties', {})
                            ))
                    elif 'computers' in filename.lower():
                        for item in data.get('data', []):
                            result.computers.append(ADObject(
                                name=item.get('Properties', {}).get('name', ''),
                                object_type='Computer',
                                properties=item.get('Properties', {})
                            ))
                    elif 'groups' in filename.lower():
                        for item in data.get('data', []):
                            result.groups.append(ADObject(
                                name=item.get('Properties', {}).get('name', ''),
                                object_type='Group',
                                properties=item.get('Properties', {})
                            ))
        
        return result


if __name__ == "__main__":
    collector = BloodHoundCollector()
    result = collector.collect(domain="example.local")
    print(f"Users: {len(result.users)}")
    print(f"Computers: {len(result.computers)}")
    print(f"Groups: {len(result.groups)}")
''',

    'feroxbuster_wrapper': '''#!/usr/bin/env python3
"""Feroxbuster Wrapper - Fast web directory brute-forcing."""
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import json


@dataclass
class FeroxResult:
    """Single feroxbuster result."""
    url: str
    status_code: int
    content_length: int
    content_type: str = ""
    redirects_to: str = ""


@dataclass
class FeroxScanResult:
    """Feroxbuster scan results."""
    target: str
    results: List[FeroxResult] = field(default_factory=list)
    statistics: Dict[str, int] = field(default_factory=dict)
    wordlist: str = ""
    raw_output: str = ""


class FeroxbusterScanner:
    """Wrapper for feroxbuster web directory scanner."""
    
    def __init__(self, ferox_path: str = "feroxbuster"):
        self.ferox_path = ferox_path
        self.default_wordlist = "/usr/share/seclists/Discovery/Web-Content/common.txt"
        self._verify_feroxbuster()
    
    def _verify_feroxbuster(self):
        """Verify feroxbuster is installed."""
        try:
            result = subprocess.run([self.ferox_path, "--version"],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("feroxbuster not found")
        except FileNotFoundError:
            raise RuntimeError("feroxbuster not installed - cargo install feroxbuster")
    
    def scan(self, target: str, wordlist: str = None, extensions: str = "",
             threads: int = 50, timeout: int = 300, 
             extra_args: List[str] = None) -> FeroxScanResult:
        """
        Run feroxbuster scan.
        
        Args:
            target: Target URL (e.g., http://example.com)
            wordlist: Path to wordlist file
            extensions: File extensions to scan (e.g., "php,html,txt")
            threads: Number of concurrent threads
            timeout: Scan timeout in seconds
            extra_args: Additional feroxbuster arguments
        
        Returns:
            FeroxScanResult with discovered paths
        """
        wordlist = wordlist or self.default_wordlist
        
        cmd = [
            self.ferox_path,
            "-u", target,
            "-w", wordlist,
            "-t", str(threads),
            "--json",
            "-q"  # Quiet mode for JSON output
        ]
        
        if extensions:
            cmd.extend(["-x", extensions])
        
        if extra_args:
            cmd.extend(extra_args)
        
        result = FeroxScanResult(target=target, wordlist=wordlist)
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result.raw_output = proc.stdout
            
            # Parse JSON lines output
            for line in proc.stdout.strip().split("\\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "response":
                        result.results.append(FeroxResult(
                            url=data.get("url", ""),
                            status_code=data.get("status", 0),
                            content_length=data.get("content_length", 0),
                            content_type=data.get("content_type", "")
                        ))
                except json.JSONDecodeError:
                    continue
            
            result.statistics = {
                "total_found": len(result.results),
                "status_200": len([r for r in result.results if r.status_code == 200]),
                "status_301": len([r for r in result.results if r.status_code == 301]),
                "status_403": len([r for r in result.results if r.status_code == 403])
            }
        
        except subprocess.TimeoutExpired:
            result.raw_output = f"Scan timeout after {timeout}s"
        except Exception as e:
            result.raw_output = f"Scan error: {e}"
        
        return result
    
    def quick_scan(self, target: str) -> FeroxScanResult:
        """Quick scan with common wordlist."""
        return self.scan(target, extensions="php,html,txt,bak,old")
    
    def deep_scan(self, target: str) -> FeroxScanResult:
        """Deep recursive scan."""
        return self.scan(target, extensions="php,html,asp,aspx,jsp,txt,bak,old,conf",
                        extra_args=["--depth", "3", "--extract-links"])


if __name__ == "__main__":
    scanner = FeroxbusterScanner()
    result = scanner.quick_scan("http://localhost")
    print(f"Found {len(result.results)} paths")
    for r in result.results[:10]:
        print(f"  [{r.status_code}] {r.url}")
''',

    'subprocess_tool': '''#!/usr/bin/env python3
"""Generic Subprocess Tool Wrapper - Safe command execution."""
import subprocess
import shlex
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import os


@dataclass
class CommandResult:
    """Result from command execution."""
    returncode: int
    stdout: str
    stderr: str
    command: str
    timeout_expired: bool = False


class ToolWrapper:
    """Generic wrapper for subprocess tool execution."""
    
    def __init__(self, tool_name: str, tool_path: str = None):
        self.tool_name = tool_name
        self.tool_path = tool_path or tool_name
        self._verify_tool()
    
    def _verify_tool(self):
        """Verify tool is available."""
        try:
            result = subprocess.run(
                ["which", self.tool_path],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError(f"{self.tool_name} not found in PATH")
        except FileNotFoundError:
            raise RuntimeError(f"Cannot verify {self.tool_name}")
    
    def run(self, args: List[str], timeout: int = 60,
            env: Dict[str, str] = None, cwd: str = None) -> CommandResult:
        """
        Run tool with arguments.
        
        Args:
            args: Command arguments
            timeout: Execution timeout
            env: Environment variables
            cwd: Working directory
        
        Returns:
            CommandResult with output
        """
        cmd = [self.tool_path] + args
        cmd_str = " ".join(cmd)
        
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
                cwd=cwd
            )
            return CommandResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=cmd_str
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                command=cmd_str,
                timeout_expired=True
            )
        except Exception as e:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                command=cmd_str
            )
    
    def run_string(self, args_string: str, **kwargs) -> CommandResult:
        """Run tool with arguments as string (safely parsed)."""
        args = shlex.split(args_string)
        return self.run(args, **kwargs)


if __name__ == "__main__":
    # Example: wrap ls command
    tool = ToolWrapper("ls")
    result = tool.run(["-la", "/tmp"])
    print(f"Return code: {result.returncode}")
    print(result.stdout)
''',

    'masscan_wrapper': '''#!/usr/bin/env python3
"""Masscan Wrapper - Fast port scanning at scale."""
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class MasscanHost:
    """Host discovered by masscan."""
    ip: str
    ports: List[Dict[str, int]] = field(default_factory=list)


@dataclass
class MasscanResult:
    """Masscan scan results."""
    hosts: List[MasscanHost] = field(default_factory=list)
    scan_rate: int = 0
    total_hosts: int = 0
    raw_output: str = ""


class MasscanScanner:
    """Wrapper for masscan - fast port scanner."""
    
    def __init__(self, masscan_path: str = "masscan"):
        self.masscan_path = masscan_path
        self._verify_masscan()
    
    def _verify_masscan(self):
        """Verify masscan is installed."""
        try:
            result = subprocess.run([self.masscan_path, "--version"],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("masscan not found")
        except FileNotFoundError:
            raise RuntimeError("masscan not installed - apt install masscan")
    
    def scan(self, target: str, ports: str = "1-1000",
             rate: int = 1000, timeout: int = 300) -> MasscanResult:
        """
        Run masscan on target.
        
        Args:
            target: IP or CIDR range
            ports: Port range (e.g., "80,443" or "1-65535")
            rate: Packets per second
            timeout: Scan timeout
        
        Returns:
            MasscanResult with open ports
        """
        cmd = [
            self.masscan_path,
            target,
            "-p", ports,
            "--rate", str(rate),
            "-oJ", "-"  # JSON output to stdout
        ]
        
        result = MasscanResult(scan_rate=rate)
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result.raw_output = proc.stdout
            
            # Parse JSON output
            hosts_map: Dict[str, MasscanHost] = {}
            
            for line in proc.stdout.strip().split("\\n"):
                if not line or line.startswith("{") == False:
                    continue
                try:
                    data = json.loads(line.rstrip(","))
                    ip = data.get("ip", "")
                    port = data.get("ports", [{}])[0]
                    
                    if ip not in hosts_map:
                        hosts_map[ip] = MasscanHost(ip=ip)
                    
                    hosts_map[ip].ports.append({
                        "port": port.get("port", 0),
                        "protocol": port.get("proto", "tcp"),
                        "status": port.get("status", "open")
                    })
                except json.JSONDecodeError:
                    continue
            
            result.hosts = list(hosts_map.values())
            result.total_hosts = len(result.hosts)
        
        except subprocess.TimeoutExpired:
            result.raw_output = f"Scan timeout after {timeout}s"
        except Exception as e:
            result.raw_output = f"Scan error: {e}"
        
        return result


if __name__ == "__main__":
    scanner = MasscanScanner()
    result = scanner.scan("127.0.0.1", ports="1-1000", rate=1000)
    print(f"Found {result.total_hosts} hosts")
    for host in result.hosts:
        print(f"  {host.ip}: {[p['port'] for p in host.ports]}")
''',

    'hashcat_wrapper': '''#!/usr/bin/env python3
"""Hashcat Wrapper - Password cracking and hash analysis."""
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class CrackedHash:
    """A cracked hash result."""
    hash_value: str
    plaintext: str
    hash_type: str = ""


@dataclass
class HashcatResult:
    """Hashcat crack results."""
    cracked: List[CrackedHash] = field(default_factory=list)
    total_hashes: int = 0
    cracked_count: int = 0
    status: str = ""
    raw_output: str = ""


class HashcatCracker:
    """Wrapper for hashcat password cracker."""
    
    # Common hash modes
    HASH_MODES = {
        "md5": 0,
        "sha1": 100,
        "sha256": 1400,
        "sha512": 1700,
        "ntlm": 1000,
        "bcrypt": 3200,
        "mysql": 300,
        "mssql": 1731,
    }
    
    def __init__(self, hashcat_path: str = "hashcat"):
        self.hashcat_path = hashcat_path
        self._verify_hashcat()
    
    def _verify_hashcat(self):
        """Verify hashcat is installed."""
        try:
            result = subprocess.run([self.hashcat_path, "--version"],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("hashcat not found")
        except FileNotFoundError:
            raise RuntimeError("hashcat not installed")
    
    def crack(self, hash_file: str, wordlist: str,
              hash_mode: int = 0, rules: str = None,
              timeout: int = 3600) -> HashcatResult:
        """
        Crack hashes with wordlist attack.
        
        Args:
            hash_file: Path to file containing hashes
            wordlist: Path to wordlist
            hash_mode: Hashcat hash mode (e.g., 0=MD5, 1000=NTLM)
            rules: Optional rules file
            timeout: Crack timeout
        
        Returns:
            HashcatResult with cracked passwords
        """
        potfile = Path("/tmp/hashcat.pot")
        
        cmd = [
            self.hashcat_path,
            "-m", str(hash_mode),
            "-a", "0",  # Dictionary attack
            hash_file,
            wordlist,
            "--potfile-path", str(potfile),
            "--outfile-format", "2",  # hash:plain format
            "-O"  # Optimized kernels
        ]
        
        if rules:
            cmd.extend(["-r", rules])
        
        result = HashcatResult()
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result.raw_output = proc.stdout + proc.stderr
            result.status = "completed"
            
            # Parse potfile for results
            if potfile.exists():
                for line in potfile.read_text().strip().split("\\n"):
                    if ":" in line:
                        parts = line.rsplit(":", 1)
                        if len(parts) == 2:
                            result.cracked.append(CrackedHash(
                                hash_value=parts[0],
                                plaintext=parts[1]
                            ))
            
            result.cracked_count = len(result.cracked)
        
        except subprocess.TimeoutExpired:
            result.status = f"timeout ({timeout}s)"
        except Exception as e:
            result.status = f"error: {e}"
        
        return result
    
    def identify_hash(self, hash_value: str) -> List[str]:
        """Identify possible hash types."""
        possible = []
        hash_len = len(hash_value)
        
        if hash_len == 32:
            possible.extend(["md5", "ntlm"])
        elif hash_len == 40:
            possible.append("sha1")
        elif hash_len == 64:
            possible.append("sha256")
        elif hash_len == 128:
            possible.append("sha512")
        elif hash_value.startswith("$2"):
            possible.append("bcrypt")
        
        return possible


if __name__ == "__main__":
    cracker = HashcatCracker()
    possible = cracker.identify_hash("5f4dcc3b5aa765d61d8327deb882cf99")
    print(f"Possible hash types: {possible}")
''',

    'gobuster_wrapper': '''#!/usr/bin/env python3
"""Gobuster Wrapper - Directory/DNS brute forcing."""
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class GobusterResult:
    """Single gobuster result."""
    path: str
    status_code: int = 0
    size: int = 0


@dataclass
class GobusterScanResult:
    """Gobuster scan results."""
    target: str
    results: List[GobusterResult] = field(default_factory=list)
    mode: str = "dir"
    raw_output: str = ""


class GobusterScanner:
    """Wrapper for gobuster directory/DNS scanner."""
    
    def __init__(self, gobuster_path: str = "gobuster"):
        self.gobuster_path = gobuster_path
        self.default_wordlist = "/usr/share/wordlists/dirb/common.txt"
    
    def dir_scan(self, target: str, wordlist: str = None,
                 extensions: str = "", threads: int = 10,
                 timeout: int = 300) -> GobusterScanResult:
        """
        Directory brute force scan.
        
        Args:
            target: Target URL
            wordlist: Wordlist path
            extensions: File extensions (e.g., "php,html")
            threads: Concurrent threads
            timeout: Scan timeout
        
        Returns:
            GobusterScanResult with discovered paths
        """
        wordlist = wordlist or self.default_wordlist
        
        cmd = [
            self.gobuster_path, "dir",
            "-u", target,
            "-w", wordlist,
            "-t", str(threads),
            "-q"
        ]
        
        if extensions:
            cmd.extend(["-x", extensions])
        
        result = GobusterScanResult(target=target, mode="dir")
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result.raw_output = proc.stdout
            
            for line in proc.stdout.strip().split("\\n"):
                if not line or "Status:" not in line:
                    continue
                
                # Parse: /path (Status: 200) [Size: 1234]
                parts = line.split()
                if len(parts) >= 3:
                    path = parts[0]
                    status = int(parts[2].rstrip(")").lstrip("("))
                    size = 0
                    if "[Size:" in line:
                        size_part = line.split("[Size:")[1].split("]")[0]
                        size = int(size_part.strip())
                    
                    result.results.append(GobusterResult(
                        path=path, status_code=status, size=size
                    ))
        
        except subprocess.TimeoutExpired:
            result.raw_output = f"Timeout after {timeout}s"
        except Exception as e:
            result.raw_output = f"Error: {e}"
        
        return result


if __name__ == "__main__":
    scanner = GobusterScanner()
    result = scanner.dir_scan("http://localhost", extensions="php,html")
    print(f"Found {len(result.results)} paths")
''',

    'nuclei_wrapper': '''#!/usr/bin/env python3
"""Nuclei Wrapper - Vulnerability scanning with templates."""
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class NucleiVuln:
    """Vulnerability found by nuclei."""
    template_id: str
    name: str
    severity: str
    host: str
    matched_at: str = ""
    description: str = ""


@dataclass
class NucleiResult:
    """Nuclei scan results."""
    target: str
    vulnerabilities: List[NucleiVuln] = field(default_factory=list)
    templates_used: int = 0
    raw_output: str = ""


class NucleiScanner:
    """Wrapper for nuclei vulnerability scanner."""
    
    def __init__(self, nuclei_path: str = "nuclei"):
        self.nuclei_path = nuclei_path
    
    def scan(self, target: str, templates: str = None,
             severity: str = None, timeout: int = 600) -> NucleiResult:
        """
        Run nuclei vulnerability scan.
        
        Args:
            target: Target URL or file with URLs
            templates: Template directory or specific templates
            severity: Filter by severity (critical,high,medium,low)
            timeout: Scan timeout
        
        Returns:
            NucleiResult with vulnerabilities
        """
        cmd = [self.nuclei_path, "-target", target, "-json", "-silent"]
        
        if templates:
            cmd.extend(["-t", templates])
        if severity:
            cmd.extend(["-severity", severity])
        
        result = NucleiResult(target=target)
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result.raw_output = proc.stdout
            
            for line in proc.stdout.strip().split("\\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    result.vulnerabilities.append(NucleiVuln(
                        template_id=data.get("template-id", ""),
                        name=data.get("info", {}).get("name", ""),
                        severity=data.get("info", {}).get("severity", ""),
                        host=data.get("host", ""),
                        matched_at=data.get("matched-at", "")
                    ))
                except json.JSONDecodeError:
                    continue
        
        except subprocess.TimeoutExpired:
            result.raw_output = f"Timeout after {timeout}s"
        except Exception as e:
            result.raw_output = f"Error: {e}"
        
        return result
    
    def update_templates(self) -> bool:
        """Update nuclei templates."""
        try:
            proc = subprocess.run([self.nuclei_path, "-update-templates"],
                                 capture_output=True, text=True, timeout=120)
            return proc.returncode == 0
        except:
            return False


if __name__ == "__main__":
    scanner = NucleiScanner()
    result = scanner.scan("http://localhost", severity="critical,high")
    print(f"Found {len(result.vulnerabilities)} vulnerabilities")
''',
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HarvestedCode:
    """A harvested and processed code snippet ready for use."""
    code: str
    language: str
    source_url: str
    source_name: str
    relevance_score: float  # 0-1 how well it matches the task
    quality_score: float    # 0-1 code quality assessment
    upvotes: int = 0
    is_complete: bool = True  # False if snippet needs adaptation
    needs_imports: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SQavengerResult:
    """Result from sQavanger search and harvest."""
    task: str
    success: bool = False  # v1.8.9: Added default to fix instantiation error
    harvested_code: List[HarvestedCode] = field(default_factory=list)
    best_code: Optional[str] = None
    search_queries: List[str] = field(default_factory=list)
    total_snippets_found: int = 0
    search_time_ms: int = 0
    engines_used: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# CODE QUALITY ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class CodeQualityAnalyzer:
    """Analyze and score code quality without running it."""
    
    @classmethod
    def analyze_python(cls, code: str) -> Tuple[float, List[str]]:
        """
        Analyze Python code quality.
        Returns (score 0-1, list of warnings).
        """
        score = 1.0
        warnings = []
        
        # Check syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return 0.0, [f"Syntax error: {e}"]
        
        # Check for common issues
        code_lower = code.lower()
        
        # Hardcoded secrets (bad)
        if re.search(r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']', code, re.IGNORECASE):
            score -= 0.1
            warnings.append("Contains potential hardcoded secrets")
        
        # TODO/FIXME comments (incomplete)
        if re.search(r'#\s*(TODO|FIXME|HACK|XXX)', code, re.IGNORECASE):
            score -= 0.05
            warnings.append("Contains TODO/FIXME comments")
        
        # Pass/NotImplementedError (incomplete)
        if 'raise NotImplementedError' in code or re.search(r'^\s+pass\s*$', code, re.MULTILINE):
            score -= 0.2
            warnings.append("Contains stub implementations")
        
        # Check for docstrings (good)
        has_docstring = '"""' in code or "'''" in code
        if not has_docstring:
            score -= 0.05
            warnings.append("No docstrings found")
        
        # Check for type hints (good)
        has_type_hints = '->' in code or ': str' in code or ': int' in code or ': List' in code
        if not has_type_hints:
            score -= 0.05
        
        # Check for error handling
        has_try_except = 'try:' in code and 'except' in code
        if 'open(' in code or 'requests.' in code or 'http' in code.lower():
            if not has_try_except:
                score -= 0.1
                warnings.append("External operations without error handling")
        
        # Bonus for comprehensive code
        num_functions = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
        if num_functions >= 2:
            score = min(1.0, score + 0.05)
        
        return max(0.0, score), warnings
    
    @classmethod
    def analyze(cls, code: str, language: str) -> Tuple[float, List[str]]:
        """Analyze code quality for any supported language."""
        if language == 'python':
            return cls.analyze_python(code)
        elif language in ('yaml', 'json'):
            # Basic validation for config files
            try:
                if language == 'yaml':
                    import yaml
                    yaml.safe_load(code)
                else:
                    import json
                    json.loads(code)
                return 1.0, []
            except Exception as e:
                return 0.0, [f"Parse error: {e}"]
        elif language in ('bash', 'shell'):
            # Basic shell script checks
            warnings = []
            score = 1.0
            if 'rm -rf' in code:
                score -= 0.2
                warnings.append("Contains dangerous rm -rf")
            if 'eval' in code:
                score -= 0.1
                warnings.append("Contains eval (security risk)")
            return score, warnings
        else:
            return 0.8, []  # Unknown language, assume okay


# ═══════════════════════════════════════════════════════════════════════════════
# RELEVANCE SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class RelevanceScorer:
    """Score how relevant a code snippet is to a task."""
    
    @classmethod
    def score(cls, code: str, task: str, context: dict = None) -> float:
        """
        Score relevance of code to task (0-1).
        
        Args:
            code: The code snippet
            task: The task description
            context: Optional context (entities, action, etc.)
        """
        context = context or {}
        score = 0.5  # Base score
        
        task_lower = task.lower()
        code_lower = code.lower()
        
        # Extract keywords from task
        keywords = set(re.findall(r'\b\w{3,}\b', task_lower))
        stopwords = {'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'are', 'was', 'were'}
        keywords = keywords - stopwords
        
        # Check keyword presence in code
        matches = 0
        for keyword in keywords:
            if keyword in code_lower:
                matches += 1
        
        if keywords:
            keyword_score = matches / len(keywords)
            score += keyword_score * 0.3
        
        # Check for entities from context
        entities = context.get('entities', [])
        entity_matches = 0
        for entity in entities:
            if entity.lower() in code_lower:
                entity_matches += 1
        if entities:
            entity_score = entity_matches / len(entities)
            score += entity_score * 0.2
        
        # Check for action type patterns
        action = context.get('action', '').lower()
        if action:
            if action in ('create', 'add', 'implement') and 'def ' in code:
                score += 0.1
            elif action in ('validate', 'check') and ('return' in code and ('True' in code or 'False' in code)):
                score += 0.1
            elif action == 'fix' and ('try:' in code or 'except' in code):
                score += 0.1
        
        # Bonus for complete-looking code
        if 'def ' in code and 'return' in code:
            score += 0.1
        if 'import ' in code:
            score += 0.05
        
        # Penalty for very short snippets
        if len(code) < 100:
            score -= 0.1
        
        # Penalty for very long snippets (might be too much)
        if len(code) > 2000:
            score -= 0.05
        
        return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════════════════════
# SQAVENGER MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class SQavenger:
    """
    sQavanger: Web Search Harvester Agent (Tier 1)
    
    Searches the web for REAL code snippets and harvests them.
    This is the brain that finds how to build things we don't have templates for!
    
    Process:
    1. Build search queries from task
    2. Search via Qrawler (SearXNG, DuckDuckGo, StackOverflow, GitHub)
    3. Extract and rank code snippets
    4. Return best matching code
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        sqavenger_cfg = self.config.get('sqavenger', self.config.get('mindstaq', {}))
        
        # v1.9.9: Check for offline_mode - skip web search entirely
        sqav_cfg = self.config.get('sqavenger', {})
        self.offline_mode = sqav_cfg.get('offline_mode', False)  # v2.0.0: Online by default
        self.search_timeout = sqav_cfg.get('timeout', 10)  # v2.0.0: 10s timeout per query  # v1.9.9: Reduced from 30s to 5s
        
        # Initialize Qrawler (unless offline_mode)
        if HAS_QRAWLER and not self.offline_mode:
            self.qrawler = Qrawler(self.config)
        else:
            self.qrawler = None
        
        # Configuration
        self.max_results = sqavenger_cfg.get('max_results', 10)
        self.min_relevance = sqavenger_cfg.get('min_relevance', 0.3)
        self.min_quality = sqavenger_cfg.get('min_quality', 0.5)
        self.target_languages = sqavenger_cfg.get('languages', ['python', 'yaml', 'json', 'bash', 'shell'])
        
        # Query templates for different task types
        self.query_templates = {
            'validate': '{lang} {entity} validation example',
            'create': '{lang} how to create {entity}',
            'add': '{lang} {entity} implementation example',
            'fix': '{lang} {entity} fix solution',
            'parse': '{lang} parse {entity} example',
            'convert': '{lang} convert {entity} example',
            'connect': '{lang} {entity} connection example',
            'default': '{lang} {entity} example code',
        }
    
    def _clean_keywords(self, keywords: List[str], task: str = "") -> List[str]:
        """
        v2.2.7: Clean garbage keywords from briq filenames.
        
        PROBLEM: BRIQ filenames like 'cyqle1_tasq1_briq000_10_and_172_and_192.md'
        produce garbage keywords: ['10', 'and', '172', 'and', '192']
        
        SOLUTION: Filter out meaningless tokens, extract real tool names
        """
        # Garbage tokens to filter out (from briq filenames)
        GARBAGE_TOKENS = {
            'and', 'or', 'the', 'a', 'an', 'to', 'for', 'in', 'on', 'at', 'by',
            'of', 'with', 'as', 'is', 'was', 'be', 'are', 'were', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'cyqle', 'cycle', 'tasq', 'task', 'briq', 'brick', 'create', 'gap',
            'priority', 'description', 'dependencies', 'style', 'line', 'fix',
            'src', 'init', 'py', 'md', 'yaml', 'json', 'txt',
            '000', '001', '002', '003', '004', '005', '006', '007', '008', '009',
        }
        
        # Known security tools/concepts to KEEP
        TOOL_KEYWORDS = {
            'nmap', 'bloodhound', 'feroxbuster', 'masscan', 'hashcat', 'gobuster',
            'nuclei', 'sharphound', 'crackmapexec', 'impacket', 'mimikatz',
            'rubeus', 'kerberos', 'ldap', 'smb', 'ssh', 'ftp', 'http', 'https',
            'scanner', 'wrapper', 'client', 'server', 'orchestrator', 'manager',
            'beacon', 'agent', 'implant', 'payload', 'loader', 'injector',
            'credential', 'authentication', 'authorization', 'encryption',
            'crypto', 'certificate', 'keystore', 'vault', 'secret',
            'network', 'socket', 'connection', 'session', 'protocol',
            'config', 'configuration', 'settings', 'options', 'parameters',
            'logger', 'logging', 'audit', 'monitor', 'event', 'handler',
            'database', 'storage', 'cache', 'queue', 'message', 'bus',
            'api', 'rest', 'graphql', 'grpc', 'websocket', 'rpc',
            'attack', 'exploit', 'vulnerability', 'scan', 'recon', 'enumerate',
            'domain', 'forest', 'trust', 'group', 'user', 'computer', 'service',
            'c2', 'command', 'control', 'callback', 'beacon', 'listener',
            'evasion', 'obfuscation', 'bypass', 'defense', 'detection',
            'subprocess', 'process', 'thread', 'async', 'concurrent',
        }
        
        cleaned = []
        task_lower = task.lower()
        
        for kw in keywords:
            if not kw:
                continue
            kw_clean = kw.lower().strip()
            
            # Skip pure numbers
            if kw_clean.isdigit():
                continue
            
            # Skip if 2 chars or less (usually garbage)
            if len(kw_clean) <= 2:
                continue
            
            # Skip if in garbage list
            if kw_clean in GARBAGE_TOKENS:
                continue
            
            # Skip underscore-prefixed tokens
            if kw_clean.startswith('_'):
                continue
            
            # Keep tool keywords always
            if kw_clean in TOOL_KEYWORDS:
                cleaned.append(kw_clean)
                continue
            
            # Keep if it looks meaningful (has letters, not just numbers)
            if any(c.isalpha() for c in kw_clean) and len(kw_clean) > 3:
                cleaned.append(kw_clean)
        
        # ALSO extract tool names directly from task text
        for tool in TOOL_KEYWORDS:
            if tool in task_lower and tool not in cleaned:
                cleaned.insert(0, tool)  # Priority at front
        
        # Dedupe while preserving order
        seen = set()
        result = []
        for kw in cleaned:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
        
        return result[:5]  # Max 5 keywords
    
    def _build_queries(self, task: str, context: dict = None) -> List[str]:
        """
        v2.2.7: Build INTELLIGENT search queries from a task.
        
        FIXES:
        - Clean garbage keywords from briq filenames
        - Extract actual tool names from task
        - Build tool-specific queries for security tools
        """
        context = context or {}
        queries = []
        
        lang = context.get('language', 'python')
        raw_entities = context.get('entities', [])
        action = context.get('action', '').lower()
        
        # v2.2.7: CLEAN the keywords first!
        entities = self._clean_keywords(raw_entities, task)
        
        _log(f"[SQavenger] Raw keywords: {raw_entities[:5]}")
        _log(f"[SQavenger] Cleaned keywords: {entities}")
        
        # Get query template
        template = self.query_templates.get(action, self.query_templates['default'])
        
        # Build primary query with cleaned entities
        if entities:
            entity_str = ' '.join(entities[:3])
            primary_query = template.format(lang=lang, entity=entity_str)
            queries.append(primary_query)
        
        # v2.2.7: Tool-specific queries for security tools
        security_tools = ['nmap', 'bloodhound', 'feroxbuster', 'masscan', 
                         'crackmapexec', 'impacket', 'nuclei', 'gobuster']
        
        for tool in security_tools:
            if tool in task.lower():
                # Add tool-specific search queries
                queries.append(f"python {tool} wrapper implementation")
                queries.append(f"python {tool} subprocess example github")
                queries.append(f"{tool} python library example")
                break  # Only add for first matching tool
        
        # Build alternative queries based on cleaned entities
        if entities:
            queries.append(f"python {entities[0]} implementation example")
            queries.append(f"python {' '.join(entities[:2])} github")
        
        # Fallback: extract key terms from task directly
        if not entities:
            # Extract potential class/function names from task
            words = task.split()
            meaningful = [w for w in words if len(w) > 4 and w[0].isalpha()]
            if meaningful:
                queries.append(f"python {' '.join(meaningful[:3])} example")
        
        # Add stackoverflow query
        if entities:
            queries.append(f"python {entities[0]} stackoverflow")
        
        # Deduplicate
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = ' '.join(q.split()).lower()
            if q_clean not in seen and len(q_clean) > 10:  # Min query length
                seen.add(q_clean)
                unique_queries.append(q)
        
        _log(f"[SQavenger] Search queries: {unique_queries[:4]}")
        
        return unique_queries[:4]  # Max 4 queries
    
    def _extract_imports(self, code: str) -> List[str]:
        """Extract required imports from code."""
        imports = []
        
        # Match import statements
        import_pattern = r'^(?:import|from)\s+[\w.]+'
        for line in code.split('\n'):
            line = line.strip()
            if re.match(import_pattern, line):
                imports.append(line)
        
        return imports
    
    def _process_snippets(self, snippets: List[CodeSnippet], task: str, context: dict) -> List[HarvestedCode]:
        """Process and rank code snippets."""
        harvested = []
        
        for snippet in snippets:
            # Filter by language
            if snippet.language not in self.target_languages and snippet.language != 'unknown':
                continue
            
            # Score relevance
            relevance = RelevanceScorer.score(snippet.code, task, context)
            if relevance < self.min_relevance:
                continue
            
            # Analyze quality
            quality, warnings = CodeQualityAnalyzer.analyze(snippet.code, snippet.language)
            if quality < self.min_quality:
                continue
            
            # v2.2.2: STRUCTURAL COMPLETENESS CHECK
            # Reject snippets that are just method bodies without proper structure
            is_complete = True
            code_lines = snippet.code.strip().split('\n')
            
            if code_lines:
                first_line = code_lines[0].strip()
                # v2.2.2: Check if code starts with indentation (incomplete snippet)
                if snippet.code.strip().startswith('        ') or snippet.code.strip().startswith('\t\t'):
                    is_complete = False
                    warnings.append("Code starts with deep indentation - likely incomplete snippet")
                    quality *= 0.3  # Heavily penalize incomplete structures
                
                # v2.2.2: Check if code is JUST method body without class/def
                has_class_or_def = any(
                    line.strip().startswith(('class ', 'def ', 'async def ', '@', 'from ', 'import '))
                    for line in code_lines[:10]
                )
                if not has_class_or_def and len(code_lines) > 5:
                    is_complete = False
                    warnings.append("No class/function definition found in first 10 lines")
                    quality *= 0.5
            
            # Check completeness - existing checks
            if 'raise NotImplementedError' in snippet.code:
                is_complete = False
            if re.search(r'^\s+pass\s*$', snippet.code, re.MULTILINE):
                is_complete = False
            
            # v2.2.2: Skip severely incomplete snippets
            if quality < 0.2:
                continue
            
            # Extract imports
            imports = self._extract_imports(snippet.code)
            
            harvested.append(HarvestedCode(
                code=snippet.code,
                language=snippet.language,
                source_url=snippet.source_url,
                source_name=snippet.source_name,
                relevance_score=relevance,
                quality_score=quality,
                upvotes=snippet.score,
                is_complete=is_complete,
                needs_imports=imports,
                warnings=warnings
            ))
        
        # Sort by combined score
        harvested.sort(key=lambda h: (h.relevance_score * 0.5 + h.quality_score * 0.3 + min(h.upvotes / 100, 0.2)), reverse=True)
        
        return harvested
    
    async def harvest_async(self, task: str, context: dict = None) -> SQavengerResult:
        """
        Harvest code from the web for a task (async).
        
        Args:
            task: The task description (e.g., "add email validation")
            context: Optional context (language, entities, action, etc.)
        
        Returns:
            SQavengerResult with harvested code
        """
        context = context or {}
        start_time = datetime.utcnow()
        
        result = SQavengerResult(task=task)
        
        # v1.9.9: If offline mode or no qrawler, immediately use offline patterns
        if not self.qrawler or self.offline_mode:
            # Try offline patterns instead of failing
            offline_code = self._match_offline_pattern(task, context or {})
            if offline_code:
                result.best_code = offline_code
                result.success = True
                result.engines_used = ['offline_patterns']
            else:
                result.error = "No matching pattern found (offline mode)"
                result.success = False
            return result
        
        # Build search queries
        queries = self._build_queries(task, context)
        result.search_queries = queries
        
        # Search all queries
        all_snippets = []
        engines_used = set()
        
        # v2.0.0: Add timeout to Qrawler searches - use what we have if timeout
        for query in queries:
            try:
                # Run search with timeout (default 10s per query, configurable)
                qrawler_result = await asyncio.wait_for(
                    self.qrawler.search(query, max_results=self.max_results),
                    timeout=self.search_timeout
                )
                all_snippets.extend(qrawler_result.code_snippets)
                engines_used.update(qrawler_result.engines_used)
            except asyncio.TimeoutError:
                # v2.0.0: Timeout - use snippets collected so far
                result.engines_used = ['offline_patterns', 'timeout_fallback']
                if all_snippets:
                    result.harvested_code = [HarvestedCode(
                        code=s.code, source_url=s.source_url, language=s.language,
                        relevance_score=0.7, quality_score=0.5
                    ) for s in all_snippets[:5]]
                    result.best_code = all_snippets[0].code
                    result.success = True
                else:
                    # Fall back to offline patterns
                    offline_code = self._match_offline_pattern(task, context or {})
                    if offline_code:
                        result.best_code = offline_code
                        result.success = True
                return result
            except Exception as e:
                result.error = str(e)
        
        result.engines_used = list(engines_used)
        result.total_snippets_found = len(all_snippets)
        
        # Process and rank snippets
        harvested = self._process_snippets(all_snippets, task, context)
        result.harvested_code = harvested
        
        # Set best code
        if harvested:
            result.best_code = harvested[0].code
            result.success = True
        else:
            result.success = False
            if not result.error:
                result.error = "No suitable code found"
        
        result.search_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return result
    
    def harvest(self, task: str, context: dict = None) -> SQavengerResult:
        """Synchronous wrapper for harvest_async."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.harvest_async(task, context))
    
    def generate(self, intent) -> Optional[str]:
        """
        Generate code for a crystallized intent.
        This is the interface called by MindstaQEngine.
        
        Args:
            intent: CrystallizedIntent from intent crystallizer
        
        Returns:
            Generated code string or None if not found
        
        v1.8.8 FIX: Use correct attribute names (keywords, raw_text)
        v1.9.2 FIX: Use OFFLINE_PATTERNS as fallback when web search fails
        v2.2.2 FIX: Check TOOL_PATTERNS FIRST for security tools!
        v2.2.4 FIX: WEB SEARCH FIRST! Templates only as fallback!
        v2.2.7 FIX: Also check target_file and keywords for tool detection!
        """
        # Build context from intent
        if HAS_INTENT and hasattr(intent, 'action'):
            context = {
                'action': intent.action.value if hasattr(intent.action, 'value') else str(intent.action),
                'entities': intent.keywords,  # v1.8.8: Fixed - was intent.entities
                'language': 'python',  # Default to Python
            }
            task = intent.raw_text  # v1.8.8: Fixed - was intent.raw_task
            target_file = getattr(intent, 'target_file', '') or ''
        else:
            # Fallback: treat intent as string
            context = {'language': 'python'}
            task = str(intent)
            target_file = ''
        
        # v2.2.7: Build combined search text including filename
        # This ensures we detect tools even when BRIQ description is generic
        combined_text = f"{task} {target_file} {' '.join(context.get('entities', []))}"
        combined_lower = combined_text.lower()
        
        # v2.2.8: Extract filename from BRIQ task if present
        # BRIQ tasks often have patterns like "# CREATE: bloodhound_wrapper.py"
        filename_from_task = None
        if 'create:' in task.lower():
            import re
            create_match = re.search(r'create:\s*(\w+\.py)', task.lower())
            if create_match:
                filename_from_task = create_match.group(1)
                _log(f"[SQavenger] Extracted filename from task: {filename_from_task}")
                combined_text = f"{combined_text} {filename_from_task}"
                combined_lower = combined_text.lower()
        
        # v2.2.7: Check for tool tasks FIRST - if tool detected, try TOOL_PATTERNS first!
        tool_keywords = [
            'nmap', 'bloodhound', 'feroxbuster', 'masscan', 'hashcat',
            'gobuster', 'nuclei', 'sharphound', 'crackmapexec', 'impacket',
        ]
        
        detected_tool = None
        for kw in tool_keywords:
            if kw in combined_lower:
                detected_tool = kw
                break
        
        # v2.2.7: If tool detected, try TOOL_PATTERNS FIRST before web search!
        # TOOL_PATTERNS have real implementations - web search returns garbage for
        # generic queries like "python base_tool example"
        if detected_tool:
            _log(f"[SQavenger] Tool '{detected_tool}' detected in task/filename!")
            _log(f"[SQavenger] Trying TOOL_PATTERNS first (better than garbage web results)...")
            tool_code = self._match_offline_pattern(combined_text, context)
            if tool_code:
                _log(f"[SQavenger] Using TOOL_PATTERN for '{detected_tool}'!")
                return tool_code
            _log(f"[SQavenger] No TOOL_PATTERN matched, falling back to web search...")
        
        # v2.2.8 CRITICAL FIX: Use combined_text for harvest, not just task!
        # This ensures the filename (bloodhound_wrapper.py) is included in search queries
        search_text = combined_text if detected_tool else task
        
        # v2.2.4 CRITICAL CHANGE: WEB SEARCH FIRST!
        # Web results are task-specific and more likely to be correct
        # Templates are generic fallbacks only
        _log(f"[SQavenger] Harvesting from web for: {search_text[:80]}...")
        result = self.harvest(search_text, context)
        
        if result.success and result.best_code:
            # v2.2.4: Check if web code is high quality
            web_code = result.best_code
            web_quality = self._assess_code_quality(web_code, search_text)
            
            _log(f"[SQavenger] Web result quality: {web_quality:.2f}")
            
            if web_quality >= 0.5:  # Good enough quality from web
                _log(f"[SQavenger] Using WEB result (quality={web_quality:.2f})")
                return web_code
            else:
                _log(f"[SQavenger] Web quality too low, checking patterns...")
        
        # v2.2.4: Only use patterns as FALLBACK if web search failed or returned poor quality
        task_lower = task.lower()
        
        # Check if this is a security tool task (patterns might be better)
        is_tool_task = any(kw in task_lower for kw in tool_keywords)
        
        if is_tool_task:
            _log(f"[SQavenger] Tool task detected, checking TOOL_PATTERNS...")
            tool_code = self._match_offline_pattern(task, context)
            if tool_code:
                _log(f"[SQavenger] Using TOOL_PATTERN (specific implementation)")
                return tool_code
        
        # If web had SOME result but low quality, still use it over nothing
        if result.success and result.best_code:
            _log(f"[SQavenger] Using low-quality web result as fallback")
            return result.best_code
        
        # v1.9.2: Try OFFLINE_PATTERNS as final fallback
        _log(f"[SQavenger] Web search failed, trying OFFLINE_PATTERNS...")
        offline_code = self._match_offline_pattern(task, context)
        if offline_code:
            _log(f"[SQavenger] Using OFFLINE_PATTERN fallback")
            return offline_code
        
        _log(f"[SQavenger] No code generated!")
        return None
    
    def _assess_code_quality(self, code: str, task: str) -> float:
        """
        v2.2.4: Assess quality of harvested web code.
        
        Returns score 0.0-1.0 where:
        - 0.0 = garbage/copypasta
        - 0.5 = acceptable
        - 1.0 = excellent task-specific code
        """
        if not code:
            return 0.0
        
        score = 0.5  # Base score
        
        # Penalties for boilerplate/copypasta
        boilerplate = [
            'class ValidationResult', 'class Validator',
            'class SafetyGovernor', 'class EventBus',
            'EMAIL_RE = re.compile', 'IP_RE = re.compile',
            '# TODO: Implement', 'raise NotImplementedError',
        ]
        boilerplate_count = sum(1 for b in boilerplate if b in code)
        score -= boilerplate_count * 0.15
        
        # Bonus for task-relevant code
        task_words = set(task.lower().split())
        code_lower = code.lower()
        relevant_matches = sum(1 for w in task_words if len(w) > 4 and w in code_lower)
        score += relevant_matches * 0.05
        
        # Bonus for implementation indicators
        impl_indicators = [
            'subprocess.run', 'subprocess.Popen',  # Tool execution
            'requests.', 'aiohttp.',               # HTTP clients
            'socket.', 'asyncio.',                 # Network/async
            'def __init__', 'class ',              # Proper structure
        ]
        impl_count = sum(1 for i in impl_indicators if i in code)
        score += impl_count * 0.08
        
        # Penalty for structural issues
        lines = code.strip().split('\n')
        if lines and lines[0].strip().startswith('        '):
            score -= 0.3  # Starts with deep indent = incomplete
        
        # Ensure score is in valid range
        return max(0.0, min(1.0, score))
    
    def _match_offline_pattern(self, task: str, context: dict) -> Optional[str]:
        """Match task against OFFLINE_PATTERNS when web search unavailable.
        
        v1.9.2: NEW! Actually uses the OFFLINE_PATTERNS that were sitting unused!
        v2.1.9: Added TOOL-SPECIFIC patterns for security tools!
        v2.2.3: EXPANDED tool matching for better security tool generation!
        """
        task_lower = task.lower()
        
        # v2.2.3: COMPREHENSIVE tool matching - security tools get PRIORITY!
        tool_matchers = {
            'nmap_wrapper': [
                'nmap', 'port scan', 'network scan', 'service detection', 'nmap wrapper',
                'scan ports', 'discover hosts', 'host discovery', 'tcp scan', 'udp scan',
                'service version', 'os detection', 'network discovery'
            ],
            'bloodhound_wrapper': [
                'bloodhound', 'active directory', 'ad attack', 'ad enumeration', 'bloodhound wrapper',
                'sharphound', 'ad permissions', 'domain admin', 'kerberos', 'ldap enum',
                'domain controller', 'ad graph', 'privilege path', 'attack path'
            ],
            'feroxbuster_wrapper': [
                'feroxbuster', 'directory brute', 'dir scan', 'web enum', 'feroxbuster wrapper',
                'directory scan', 'web directory', 'path brute', 'endpoint enum',
                'web content', 'recursive scan'
            ],
            'masscan_wrapper': [
                'masscan', 'fast port scan', 'masscan wrapper', 'mass scan',
                'large scale scan', 'internet scan', 'banner grab', 'rate limit scan'
            ],
            'hashcat_wrapper': [
                'hashcat', 'password crack', 'hash crack', 'hashcat wrapper',
                'hash attack', 'dictionary attack', 'brute force', 'ntlm crack',
                'crack hash', 'password recovery', 'wordlist attack'
            ],
            'gobuster_wrapper': [
                'gobuster', 'dir buster', 'gobuster wrapper', 'directory scan',
                'dns brute', 'vhost', 'subdomain enum', 'fuzz endpoint'
            ],
            'nuclei_wrapper': [
                'nuclei', 'vulnerability scan', 'nuclei wrapper', 'template scan',
                'cve scan', 'vuln scanner', 'security scan', 'vulnerability check',
                'exploit check', 'security template'
            ],
            'subprocess_tool': [
                'subprocess', 'run command', 'shell command', 'execute command',
                'tool wrapper', 'cli wrapper', 'command wrapper', 'process exec',
                'system command', 'shell exec'
            ],
        }
        
        # v2.2.3: Score-based matching - prefer patterns with MORE keyword hits
        best_tool = None
        best_tool_score = 0
        
        for pattern_name, keywords in tool_matchers.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_tool_score:
                best_tool_score = score
                best_tool = pattern_name
        
        # Return tool pattern if ANY match (prioritize tools!)
        if best_tool and best_tool_score > 0:
            if best_tool in TOOL_PATTERNS:
                _log(f"TOOL_PATTERN matched: {best_tool} (score: {best_tool_score})")
                return TOOL_PATTERNS[best_tool]
        
        # Pattern matching rules - keywords that trigger each pattern
        pattern_matchers = {
            'http_get': ['get request', 'fetch', 'http get', 'api get', 'download', 'retrieve url', 'get data'],
            'http_post': ['post request', 'send data', 'http post', 'api post', 'submit', 'upload', 'post data'],
            'json_handler': ['json', 'read json', 'write json', 'parse json', 'json file', 'load json', 'save json'],
            'yaml_handler': ['yaml', 'read yaml', 'write yaml', 'parse yaml', 'yaml file', 'yml', 'load yaml', 'config file'],
            'validate_email': ['email', 'validate email', 'email validation', 'email format', 'check email'],
            'validate_url': ['url', 'validate url', 'url validation', 'link validation', 'check url'],
            'database_crud': ['database', 'crud', 'create read update delete', 'db operation', 'record', 'storage'],
            'async_worker': ['async', 'worker', 'pool', 'parallel', 'concurrent', 'task queue', 'background'],
            'config_loader': ['config', 'configuration', 'settings', 'load config', 'config file', 'environment'],
            'logger_setup': ['logger', 'logging', 'log setup', 'log file', 'setup logging', 'debug log'],
            'exception_classes': ['exception', 'error class', 'custom error', 'error handling', 'raise error', 'exception class'],
        }
        
        # Score each pattern
        best_pattern = None
        best_score = 0
        
        for pattern_name, keywords in pattern_matchers.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_score:
                best_score = score
                best_pattern = pattern_name
        
        # Return matching pattern if found
        if best_pattern and best_score > 0:
            return OFFLINE_PATTERNS.get(best_pattern)
        
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FALLBACK PATTERNS (for offline mode)
# ═══════════════════════════════════════════════════════════════════════════════

# These are FALLBACK patterns used when web search is unavailable
# v1.9.2: Expanded with more patterns and actually used now!
OFFLINE_PATTERNS = {
    'http_get': '''import requests
from typing import Optional, Dict, Any


def fetch_data(url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None) -> Optional[Dict]:
    """Fetch data from a URL using GET request."""
    try:
        response = requests.get(url, headers=headers or {}, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
''',
    'http_post': '''import requests
from typing import Optional, Dict, Any


def post_data(url: str, data: Dict[str, Any], headers: Dict[str, str] = None) -> Optional[Dict]:
    """Send data to a URL using POST request."""
    default_headers = {'Content-Type': 'application/json'}
    if headers:
        default_headers.update(headers)
    try:
        response = requests.post(url, json=data, headers=default_headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
''',
    'json_handler': '''import json
from pathlib import Path
from typing import Any, Optional


def read_json(file_path: str) -> Optional[Any]:
    """Read JSON from file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    """Write JSON to file."""
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
    """Read YAML from file."""
    path = Path(file_path)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_yaml(file_path: str, data: Any) -> bool:
    """Write YAML to file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return True
''',
    'validate_email': '''import re
from typing import Tuple


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email address format."""
    if not email:
        return False, "Email is required"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, "Valid"
''',
    'validate_url': '''from urllib.parse import urlparse
from typing import Tuple


def validate_url(url: str) -> Tuple[bool, str]:
    """Validate URL format."""
    if not url:
        return False, "URL is required"
    
    try:
        result = urlparse(url)
        if all([result.scheme, result.netloc]):
            if result.scheme in ('http', 'https'):
                return True, "Valid"
        return False, "Invalid URL format"
    except Exception:
        return False, "URL parsing failed"
''',
    'database_crud': '''from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class Record:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class SimpleDB:
    """Simple in-memory database with CRUD operations."""
    
    def __init__(self):
        self._records: Dict[str, Record] = {}
    
    def create(self, data: Dict[str, Any]) -> Record:
        record = Record(data=data)
        self._records[record.id] = record
        return record
    
    def read(self, record_id: str) -> Optional[Record]:
        return self._records.get(record_id)
    
    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[Record]:
        if record_id in self._records:
            self._records[record_id].data.update(data)
            self._records[record_id].updated_at = datetime.utcnow()
            return self._records[record_id]
        return None
    
    def delete(self, record_id: str) -> bool:
        if record_id in self._records:
            del self._records[record_id]
            return True
        return False
    
    def list_all(self) -> List[Record]:
        return list(self._records.values())
''',
    'async_worker': '''import asyncio
from dataclasses import dataclass, field
from typing import Callable, Any, Optional, List
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


class AsyncWorkerPool:
    """Async worker pool for parallel task execution."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results: dict = {}
        self.running = False
    
    async def start(self) -> List[asyncio.Task]:
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
                    self.results[task.id] = task
                    self.queue.task_done()
            except asyncio.TimeoutError:
                continue
''',
    'config_loader': '''import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
import json


class ConfigLoader:
    """Load configuration from various sources."""
    
    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir) if config_dir else Path.cwd()
        self._cache: Dict[str, Any] = {}
    
    def load(self, name: str, format: str = 'yaml') -> Optional[Dict[str, Any]]:
        """Load config file by name."""
        if name in self._cache:
            return self._cache[name]
        
        extensions = {'yaml': ['.yaml', '.yml'], 'json': ['.json']}
        
        for ext in extensions.get(format, [f'.{format}']):
            path = self.config_dir / f"{name}{ext}"
            if path.exists():
                with open(path, 'r') as f:
                    if format == 'yaml':
                        data = yaml.safe_load(f)
                    else:
                        data = json.load(f)
                self._cache[name] = data
                return data
        return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get env var or default."""
        return os.environ.get(key, default)
''',
    'logger_setup': '''import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
''',
    'exception_classes': '''from typing import Optional, Dict, Any


class BaseError(Exception):
    """Base exception class with structured error info."""
    
    def __init__(self, message: str, code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': self.code,
            'message': self.message,
            'details': self.details
        }


class ValidationError(BaseError):
    """Raised when validation fails."""
    pass


class NotFoundError(BaseError):
    """Raised when resource not found."""
    pass


class AuthenticationError(BaseError):
    """Raised when authentication fails."""
    pass


class ConfigurationError(BaseError):
    """Raised when configuration is invalid."""
    pass
''',
}


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    async def test():
        print("=" * 70)
        print("SQAVENGER WEB HARVESTER TEST")
        print("=" * 70)
        
        sqavenger = SQavenger()
        
        # Test task
        task = "add email validation function"
        context = {
            'action': 'add',
            'entities': ['email', 'validation'],
            'language': 'python'
        }
        
        print(f"\nTask: {task}")
        print(f"Context: {context}")
        
        result = await sqavenger.harvest_async(task, context)
        
        print(f"\nResults:")
        print(f"  Success: {result.success}")
        print(f"  Search queries: {result.search_queries}")
        print(f"  Engines used: {result.engines_used}")
        print(f"  Snippets found: {result.total_snippets_found}")
        print(f"  Harvested: {len(result.harvested_code)}")
        print(f"  Search time: {result.search_time_ms}ms")
        
        if result.error:
            print(f"  Error: {result.error}")
        
        if result.harvested_code:
            print(f"\nBest Match:")
            best = result.harvested_code[0]
            print(f"  Source: {best.source_name}")
            print(f"  Relevance: {best.relevance_score:.2f}")
            print(f"  Quality: {best.quality_score:.2f}")
            print(f"  Upvotes: {best.upvotes}")
            print(f"  Complete: {best.is_complete}")
            print(f"\nCode:\n{best.code[:500]}...")
    
    asyncio.run(test())
