#!/usr/bin/env python3
"""
Language Adapters: Multi-Language Code Generation for mindstaQ
v2.0.0-stable - CONTEXT-AWARE generation based on FILENAME FIRST

Supports: Shell, YAML, JSON, Dockerfile, Vagrantfile, Makefile, Go, Rust
"""

from typing import Optional
import hashlib

__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_language(filename: str) -> str:
    """Detect language from filename extension."""
    ext_map = {
        '.py': 'python',
        '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
        '.yaml': 'yaml', '.yml': 'yaml',
        '.json': 'json',
        '.go': 'go',
        '.rs': 'rust',
    }
    basename = filename.split('/')[-1].lower()
    if basename == 'dockerfile':
        return 'dockerfile'
    if basename == 'vagrantfile':
        return 'vagrantfile'
    if basename == 'makefile' or basename == 'gnumakefile':
        return 'makefile'
    for ext, lang in ext_map.items():
        if filename.lower().endswith(ext):
            return lang
    return 'python'


def needs_language_adapter(filename: str) -> bool:
    return detect_language(filename) != 'python'


# ═══════════════════════════════════════════════════════════════════════════════
# SHELL SCRIPT GENERATORS - v2.0.0: FILENAME-FIRST DETECTION!
# ═══════════════════════════════════════════════════════════════════════════════

def generate_shell_script(prompt: str, filename: str) -> str:
    """v2.0.0: Generate UNIQUE shell scripts based on FILENAME primarily."""
    basename = filename.split('/')[-1].lower()
    filename_lower = filename.lower()
    
    # v2.0.0: FILENAME-FIRST detection (more specific)
    # Order matters! Most specific first
    
    # Docker/container scripts
    if 'docker' in basename or 'container' in basename:
        return _gen_docker_script(basename)
    
    # Provisioning/setup scripts
    if 'provision' in filename_lower or 'setup' in basename or basename.startswith('00-'):
        return _gen_provision_script(basename, prompt)
    
    # Nim installation
    if 'nim' in filename_lower or 'choosenim' in filename_lower:
        return _gen_nim_script(basename)
    
    # Go environment
    if basename == 'go.sh' or ('go' in basename and 'profile' in filename_lower):
        return _gen_go_profile()
    
    # C2/Mythic scripts
    if 'mythic' in filename_lower or 'c2' in filename_lower or 'start-' in basename:
        return _gen_c2_script(basename, filename)
    
    # AI/Chat scripts
    if 'ai' in basename and 'chat' in basename:
        return _gen_ai_chat_script(basename)
    
    # Security tools (but NOT provision scripts)
    if 'security' in basename and 'tool' in basename:
        return _gen_security_script(basename)
    
    # Install scripts
    if 'install' in basename:
        return _gen_install_script(basename, prompt)
    
    # Profile scripts
    if 'profile' in filename_lower or basename.endswith('.sh') and 'etc' in filename_lower:
        return _gen_profile_script(basename, prompt)
    
    # Generic fallback - use hash for variety!
    return _gen_varied_script(basename, prompt)


def _gen_docker_script(name: str) -> str:
    return f"""#!/bin/bash
# {name} - Docker Installation
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run as root"; exit 1; fi
apt-get update -qq
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker && systemctl start docker
echo "Docker installed!" && docker --version
"""


def _gen_provision_script(name: str, prompt: str) -> str:
    return f"""#!/bin/bash
# {name} - Base System Provisioning
# Task: {prompt[:60]}...
set -euo pipefail
echo "[*] Starting base provisioning..."
apt-get update -qq && apt-get upgrade -y
apt-get install -y \\
    build-essential git curl wget vim tmux htop jq unzip \\
    python3 python3-pip python3-venv \\
    software-properties-common ca-certificates gnupg
timedatectl set-timezone UTC
# Configure limits
cat >> /etc/security/limits.conf << 'LIMITS'
* soft nofile 65535
* hard nofile 65535
LIMITS
echo "[+] Base provisioning complete!"
"""


def _gen_nim_script(name: str) -> str:
    return f"""#!/bin/bash
# {name} - Nim Language Installation
set -euo pipefail
echo "[*] Installing Nim via choosenim..."
curl https://nim-lang.org/choosenim/init.sh -sSf | sh -s -- -y
export PATH=$HOME/.nimble/bin:$PATH
echo 'export PATH=$HOME/.nimble/bin:$PATH' >> ~/.bashrc
nim --version
echo "[+] Nim installed!"
"""


def _gen_go_profile() -> str:
    return """#!/bin/bash
# Go Environment Profile
export GOROOT=/usr/local/go
export GOPATH=$HOME/go
export PATH=$GOPATH/bin:$GOROOT/bin:$PATH
"""


def _gen_c2_script(name: str, filepath: str) -> str:
    # Determine which C2 based on path
    if 'mythic' in filepath.lower():
        return f"""#!/bin/bash
# {name} - Mythic C2 Framework
set -euo pipefail
cd /opt/Mythic 2>/dev/null || {{ echo "Mythic not found"; exit 1; }}
echo "[*] Starting Mythic..."
./mythic-cli start
echo "[+] Mythic started on https://localhost:7443"
"""
    elif 'sliver' in filepath.lower():
        return f"""#!/bin/bash
# {name} - Sliver C2 Framework
set -euo pipefail
echo "[*] Starting Sliver..."
sliver-server daemon &
sleep 3
sliver-client
"""
    elif 'havoc' in filepath.lower():
        return f"""#!/bin/bash
# {name} - Havoc C2 Framework
set -euo pipefail
cd /opt/Havoc 2>/dev/null || {{ echo "Havoc not found"; exit 1; }}
./havoc server --profile profiles/havoc.yaotl &
echo "[+] Havoc started"
"""
    else:
        return f"""#!/bin/bash
# {name} - C2 Framework Launcher
set -euo pipefail
echo "[*] Starting C2 framework..."
# Add C2-specific startup commands here
echo "[+] C2 ready"
"""


def _gen_ai_chat_script(name: str) -> str:
    return f"""#!/bin/bash
# {name} - AI Chat Interface
API="${{API_ENDPOINT:-http://localhost:11434/api/generate}}"
MODEL="${{MODEL:-llama2}}"
echo "AI Chat ($MODEL) - Type 'exit' to quit"
while true; do
    read -p "You: " input; [ "$input" = "exit" ] && break
    curl -s "$API" -d '{{"model": "'$MODEL'", "prompt": "'$input'", "stream": false}}' | jq -r '.response'
done
"""


def _gen_security_script(name: str) -> str:
    return f"""#!/bin/bash
# {name} - Security Tools Installation
set -euo pipefail
echo "[*] Installing security tools..."
apt-get update -qq
apt-get install -y nmap masscan nikto gobuster sqlmap hydra john netcat-openbsd tcpdump
pip3 install --break-system-packages impacket pwntools requests paramiko
mkdir -p /opt/tools && cd /opt/tools
[ ! -d "SecLists" ] && git clone --depth 1 https://github.com/danielmiessler/SecLists.git
[ ! -d "PEASS-ng" ] && git clone --depth 1 https://github.com/carlospolop/PEASS-ng.git
echo "[+] Security tools installed!"
"""


def _gen_install_script(name: str, prompt: str) -> str:
    """Generate install script based on what's being installed."""
    prompt_lower = prompt.lower()
    
    if 'docker' in prompt_lower:
        return _gen_docker_script(name)
    elif 'nim' in prompt_lower:
        return _gen_nim_script(name)
    elif 'go' in prompt_lower or 'golang' in prompt_lower:
        return f"""#!/bin/bash
# {name} - Go Installation
set -euo pipefail
GO_VERSION="${{GO_VERSION:-1.21.5}}"
wget -q "https://go.dev/dl/go${{GO_VERSION}}.linux-amd64.tar.gz"
rm -rf /usr/local/go && tar -C /usr/local -xzf "go${{GO_VERSION}}.linux-amd64.tar.gz"
rm "go${{GO_VERSION}}.linux-amd64.tar.gz"
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
/usr/local/go/bin/go version
"""
    elif 'rust' in prompt_lower:
        return f"""#!/bin/bash
# {name} - Rust Installation
set -euo pipefail
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env
rustc --version
"""
    else:
        return f"""#!/bin/bash
# {name} - Installation Script
# Task: {prompt[:60]}...
set -euo pipefail
echo "[*] Running installation..."
# TODO: Add installation commands
echo "[+] Installation complete!"
"""


def _gen_profile_script(name: str, prompt: str) -> str:
    """Generate shell profile/environment script."""
    return f"""#!/bin/bash
# {name} - Environment Profile
# Auto-generated environment configuration

# Add custom paths
export PATH="$HOME/.local/bin:$PATH"

# Tool-specific environment
export EDITOR=vim
export PAGER=less

# Aliases
alias ll='ls -la'
alias ..='cd ..'
"""


def _gen_varied_script(name: str, prompt: str) -> str:
    """Generate varied script using hash for deterministic but unique output."""
    # Use hash of filename + prompt to generate variety
    h = hashlib.md5((name + prompt).encode()).hexdigest()
    variant = int(h[:2], 16) % 5
    
    scripts = [
        # Variant 0: Logger script
        f"""#!/bin/bash
# {name} - Logging Utility
log() {{ echo "[$(date +%H:%M:%S)] $*"; }}
log_info() {{ log "[INFO] $*"; }}
log_warn() {{ log "[WARN] $*"; }}
log_error() {{ log "[ERROR] $*" >&2; }}
main() {{
    log_info "Starting {name}..."
    # Add commands here
    log_info "Done!"
}}
main "$@"
""",
        # Variant 1: Service script
        f"""#!/bin/bash
# {name} - Service Management
set -euo pipefail
SERVICE_NAME="{name.replace('.sh', '')}"
start() {{ echo "Starting $SERVICE_NAME..."; }}
stop() {{ echo "Stopping $SERVICE_NAME..."; }}
status() {{ echo "$SERVICE_NAME status: running"; }}
case "${{1:-status}}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    *) status ;;
esac
""",
        # Variant 2: Health check
        f"""#!/bin/bash
# {name} - Health Check
set -euo pipefail
check_service() {{ systemctl is-active --quiet "$1" && echo "✓ $1" || echo "✗ $1"; }}
check_port() {{ nc -z localhost "$1" && echo "✓ Port $1" || echo "✗ Port $1"; }}
echo "=== Health Check ==="
check_port 22
check_port 80
echo "=== Done ==="
""",
        # Variant 3: Cleanup script
        f"""#!/bin/bash
# {name} - Cleanup Utility
set -euo pipefail
echo "[*] Running cleanup..."
rm -rf /tmp/*.log 2>/dev/null
apt-get autoremove -y 2>/dev/null || true
apt-get clean 2>/dev/null || true
docker system prune -f 2>/dev/null || true
echo "[+] Cleanup complete!"
""",
        # Variant 4: Backup script
        f"""#!/bin/bash
# {name} - Backup Utility
set -euo pipefail
BACKUP_DIR="${{BACKUP_DIR:-/var/backups}}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
echo "[*] Creating backup..."
tar -czf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" /etc /home 2>/dev/null || true
echo "[+] Backup saved to $BACKUP_DIR"
""",
    ]
    
    return scripts[variant]


# ═══════════════════════════════════════════════════════════════════════════════
# YAML GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_yaml(prompt: str, filename: str) -> str:
    prompt_lower = prompt.lower()
    basename = filename.split('/')[-1].lower()
    
    if 'docker-compose' in basename or 'compose' in prompt_lower:
        return """version: '3.8'
services:
  app:
    build: .
    ports: ["8080:8080"]
    environment: [NODE_ENV=production]
    depends_on: [db, redis]
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: appdb
    volumes: [db-data:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    volumes: [redis-data:/data]
volumes:
  db-data:
  redis-data:
"""
    elif 'kubernetes' in prompt_lower or 'k8s' in basename:
        return """apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: app
  template:
    metadata:
      labels:
        app: app
    spec:
      containers:
      - name: app
        image: app:latest
        ports:
        - containerPort: 8080
"""
    else:
        # Generic config
        return f"""# {basename}
# Auto-generated configuration

app:
  name: autowonqnet
  version: "1.0.0"
  debug: false

server:
  host: "0.0.0.0"
  port: 8080

logging:
  level: INFO
  format: "json"
"""


# ═══════════════════════════════════════════════════════════════════════════════
# JSON GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_json(prompt: str, filename: str) -> str:
    basename = filename.split('/')[-1].lower()
    
    if 'package.json' in basename:
        return """{
  "name": "autowonqnet",
  "version": "1.0.0",
  "description": "AI-Powered Red Team Platform",
  "main": "index.js",
  "scripts": {
    "start": "node index.js",
    "test": "jest"
  },
  "dependencies": {},
  "devDependencies": {}
}
"""
    elif 'tsconfig' in basename:
        return """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true,
    "outDir": "./dist"
  }
}
"""
    else:
        return """{
  "name": "config",
  "version": "1.0.0",
  "settings": {}
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# OTHER LANGUAGE GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_dockerfile(prompt: str, filename: str) -> str:
    prompt_lower = prompt.lower()
    if 'python' in prompt_lower:
        return """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
"""
    elif 'node' in prompt_lower:
        return """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 8080
CMD ["node", "index.js"]
"""
    else:
        return """FROM ubuntu:22.04
WORKDIR /app
RUN apt-get update && apt-get install -y python3 python3-pip
COPY . .
CMD ["/bin/bash"]
"""


def generate_vagrantfile(prompt: str, filename: str) -> str:
    return """# -*- mode: ruby -*-
Vagrant.configure("2") do |config|
  config.vm.box = "parrot-security/rolling"
  config.vm.hostname = "autowonqnet"
  
  config.vm.network "private_network", ip: "192.168.56.10"
  config.vm.network "forwarded_port", guest: 8080, host: 8080
  
  config.vm.provider "virtualbox" do |vb|
    vb.memory = "8192"
    vb.cpus = 4
    vb.name = "AutoWonQNet"
  end
  
  config.vm.provision "shell", path: "provision/00-base-setup.sh"
end
"""


def generate_makefile(prompt: str, filename: str) -> str:
    return """.PHONY: all build test clean install run

all: build

build:
\t@echo "Building..."
\tpython -m pip install -e .

test:
\t@echo "Testing..."
\tpython -m pytest tests/

clean:
\t@echo "Cleaning..."
\trm -rf build/ dist/ *.egg-info __pycache__

install:
\t@echo "Installing..."
\tpip install -r requirements.txt

run:
\t@echo "Running..."
\tpython main.py
"""


def generate_go(prompt: str, filename: str) -> str:
    basename = filename.split('/')[-1]
    if 'main' in basename.lower():
        return """package main

import (
\t"fmt"
\t"net/http"
)

func main() {
\thttp.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
\t\tfmt.Fprintf(w, "Hello, AutoWonQNet!")
\t})
\tfmt.Println("Server starting on :8080")
\thttp.ListenAndServe(":8080", nil)
}
"""
    else:
        return """package lib

// Handler provides request handling
type Handler struct {
\tName string
}

// Process handles incoming requests
func (h *Handler) Process(data []byte) ([]byte, error) {
\treturn data, nil
}
"""


def generate_rust(prompt: str, filename: str) -> str:
    basename = filename.split('/')[-1]
    if 'main' in basename.lower():
        return """fn main() {
    println!("AutoWonQNet Starting...");
    // Entry point
}
"""
    else:
        return """pub struct Handler {
    name: String,
}

impl Handler {
    pub fn new(name: &str) -> Self {
        Handler { name: name.to_string() }
    }
    
    pub fn process(&self, data: &[u8]) -> Vec<u8> {
        data.to_vec()
    }
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def generate_for_language(prompt: str, filename: str) -> Optional[str]:
    """Generate code for non-Python languages."""
    lang = detect_language(filename)
    
    if lang == 'python':
        return None  # Let tier agents handle Python
    elif lang in ('bash', 'zsh'):
        return generate_shell_script(prompt, filename)
    elif lang == 'yaml':
        return generate_yaml(prompt, filename)
    elif lang == 'json':
        return generate_json(prompt, filename)
    elif lang == 'dockerfile':
        return generate_dockerfile(prompt, filename)
    elif lang == 'vagrantfile':
        return generate_vagrantfile(prompt, filename)
    elif lang == 'makefile':
        return generate_makefile(prompt, filename)
    elif lang == 'go':
        return generate_go(prompt, filename)
    elif lang == 'rust':
        return generate_rust(prompt, filename)
    else:
        return None
