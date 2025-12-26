# QonQrete Dockerfile - Security Hardened
# v0.9.3-beta - Drops root via gosu entrypoint, implements qrane/worqer/qrew permission model
# DeepSeek provider now built into lib_ai.py (no sqeleton dependency)

FROM ubuntu:22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# =============================================================================
# 1. Install base dependencies, gosu for privilege dropping, and Chafa (splash)
# =============================================================================
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python-is-python3 \
    git \
    ca-certificates \
    curl \
    gnupg \
    chafa \
    vim \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# 2. Install Python packages for agents
# =============================================================================
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir \
    pyyaml \
    openai \
    anthropic \
    google-generativeai \
    jedi \
    docstring-parser \
    pycg \
    numpy \
    sentence-transformers \
    && rm -rf /root/.cache/pip

# =============================================================================
# 3. Security Hardening - Create Users and Groups
# =============================================================================
# Create the qrew group (shared group for container operations)
RUN groupadd -r qrew

# Create qrane user - The Orchestrator (owns /qonq, runs qrane.py)
RUN useradd -r -g qrew -m -d /home/qrane -s /bin/bash qrane

# Create worqer user - The Agent Runner (runs instruqtor/construqtor/inspeqtor)
# Added to qrew group for shared access
RUN useradd -r -g qrew -m -d /home/worqer -s /bin/bash worqer

# =============================================================================
# 4. Create working directories with proper permissions
# =============================================================================
WORKDIR /qonqrete

# Copy the entire project into the container
COPY . .

# Set PYTHONPATH
ENV PYTHONPATH="/qonqrete"

# =============================================================================
# 5. Security Hardening - Set Ownership and Permissions
# =============================================================================
# /qonqrete (code) owned by qrane:qrew - read-only for agents
RUN chown -R qrane:qrew /qonqrete && \
    chmod -R 750 /qonqrete

# Create /qonq directory (the mounted workspace) with proper permissions
# This is where the qage gets mounted at runtime
RUN mkdir -p /qonq && \
    chown qrane:qrew /qonq && \
    chmod 770 /qonq

# Set up workspace subdirectories with setgid for group inheritance
# These get created inside the mounted volume, but we set defaults here
RUN mkdir -p /qonq/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d} && \
    chown -R worqer:qrew /qonq && \
    chmod -R 2770 /qonq

# The setgid bit (2xxx) ensures new files inherit the qrew group
# This allows both qrane and worqer to read/write as needed

# =============================================================================
# 6. Dynamic Versioning (Injected by qonqrete.sh --build-arg)
# =============================================================================
ARG QONQ_VERSION
ENV QONQ_VERSION=${QONQ_VERSION}

# =============================================================================
# 7. Entrypoint for Privilege Dropping
# =============================================================================
# The entrypoint script:
#   1. Runs as root initially (to fix mounted volume permissions)
#   2. chown -R qrane:qrew /qonq (fixes host mount permissions)
#   3. Drops to qrane user via gosu
#   4. Executes the actual command
#
# This ensures the container runs as non-root while handling Docker's
# bind mount permission inheritance from the host.
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default working directory for runtime
WORKDIR /qonqrete
