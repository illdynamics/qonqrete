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


# 2. Install Python packages for agents
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
