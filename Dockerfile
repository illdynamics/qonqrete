# Base image with Python and essential tools
FROM ubuntu:22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install base dependencies, modern Node.js, and Chafa (for splash)
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
    && rm -rf /var/lib/apt/lists/*

# Setup NodeSource repository for Node.js 20.x
RUN mkdir -p /etc/apt/keyrings
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
RUN NODE_MAJOR=20 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list

# Install Node.js from the new repository
RUN apt-get update && apt-get install -y nodejs

# Install Qwen CLI (needed for the 'qwen' provider)
RUN npm install -g @qwen-code/qwen-code@latest

# 2. Install Python packages for agents
RUN pip3 install --no-cache-dir --upgrade pip

# Core AI provider packages
RUN pip3 install --no-cache-dir pyyaml openai anthropic google-generativeai

# =============================================================================
# LOCAL QONTEXTOR DEPENDENCIES
# These enable AI-free context generation with 85-95% quality parity
# =============================================================================

# Jedi - IDE-like type inference and cross-file resolution
RUN pip3 install --no-cache-dir jedi

# Docstring Parser - Structured docstring extraction (Google, NumPy, Sphinx styles)
RUN pip3 install --no-cache-dir docstring-parser

# PyCG - Academic-grade call graph generation for Python
# Achieves ~99.2% precision for dependency extraction
RUN pip3 install --no-cache-dir pycg

# Optional: Sentence Transformers for semantic similarity (90MB model)
# Uncomment if you want deep semantic lookup capability
RUN pip3 install --no-cache-dir sentence-transformers

# =============================================================================

# 3. Create a working directory for the project
WORKDIR /qonqrete

# 4. Copy the entire project into the container
COPY . .

# 5. Set PYTHONPATH and make provider executable
ENV PYTHONPATH="/qonqrete"
RUN chmod +x sqeleton/deepseek_provider.py

# 6. Dynamic Versioning (Injected by qonqrete.sh --build-arg)
ARG QONQ_VERSION
ENV QONQ_VERSION=${QONQ_VERSION}
