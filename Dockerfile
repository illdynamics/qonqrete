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
    && rm -rf /var/lib/apt/lists/*

# Setup NodeSource repository for Node.js 20.x
RUN mkdir -p /etc/apt/keyrings
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
RUN NODE_MAJOR=20 && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list

# Install Node.js from the new repository
RUN apt-get update && apt-get install -y nodejs

# 2. Install Python packages for agents
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir shell-gpt pyyaml tiktoken

# 3. Install Gemini CLI using npm
RUN npm install -g @google/gemini-cli

# 4. Create a working directory for the project
WORKDIR /qonqrete

# 5. Copy the entire project into the container
COPY . .

# 6. Dynamic Versioning (Injected by qonqrete.sh --build-arg)
ARG QONQ_VERSION
ENV QONQ_VERSION=${QONQ_VERSION}
