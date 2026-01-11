# QonQrete Dockerfile - Security Hardened
# v2.1.0-stable - Full mindstaQ with z3 constraint solver
# =============================================================================
# Security Features:
#   - Pinned base image with digest
#   - Pinned Python dependencies  
#   - Non-root execution via gosu
#   - HEALTHCHECK directive
#   - Minimal attack surface
#   - Pre-downloaded ML models
# =============================================================================

# Pinned base image with digest for reproducibility
FROM ubuntu:22.04@sha256:0e5e4a57c2499249aafc3b40fcd541e9a456aab7296681a3994d631587203f97

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# =============================================================================
# 1. Install base dependencies, gosu for privilege dropping
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python-is-python3 \
    git \
    ca-certificates \
    curl \
    chafa \
    vim \
    gosu \
    # Build dependencies for some Python packages
    build-essential \
    libffi-dev \
    libssl-dev \
    # PostgreSQL client libs (for psycopg2)
    libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# =============================================================================
# 2. Install Python packages with pinned versions
# =============================================================================
WORKDIR /qonqrete
COPY requirements.txt .

# Upgrade pip and install all dependencies including z3-solver
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# =============================================================================
# 3. Verify z3 installation (v2.0.3)
# =============================================================================
RUN python3 -c "import z3; print(f'z3 version: {z3.get_version_string()}')" && \
    echo "✓ z3-solver installed successfully"

# =============================================================================
# 4. Security Hardening - Create Users and Groups
# =============================================================================
RUN groupadd -r qrew
RUN useradd -r -g qrew -m -d /home/qrane -s /bin/bash qrane
RUN useradd -r -g qrew -m -d /home/worqer -s /bin/bash worqer

# Ensure pip scripts are in PATH for all users
ENV PATH="/usr/local/bin:${PATH}"

# =============================================================================
# 5. Pre-download ML Models
# =============================================================================
# Create a persistent cache directory OUTSIDE /home/qrane/.cache (which gets
# mounted as tmpfs at runtime). This ensures the pre-downloaded models survive
# the security hardening tmpfs mount.
RUN mkdir -p /opt/hf_cache && chmod 755 /opt/hf_cache

# Set HuggingFace environment variables BEFORE downloading
ENV HF_HOME=/opt/hf_cache
ENV SENTENCE_TRANSFORMERS_HOME=/opt/hf_cache
ENV TRANSFORMERS_CACHE=/opt/hf_cache

# Pre-download the sentence-transformers model during build (runs as root)
# This ensures the model is available at runtime without needing write access
RUN python3 -c "from sentence_transformers import SentenceTransformer; \
    print('Pre-downloading all-MiniLM-L6-v2 model...'); \
    SentenceTransformer('all-MiniLM-L6-v2'); \
    print('Model cached successfully to /opt/hf_cache')"

# Make cache readable by all users (model files are read-only at runtime)
RUN chmod -R 755 /opt/hf_cache

# Create runtime cache directories for sentence-transformers (for any runtime writes)
RUN mkdir -p /home/qrane/.cache/huggingface && \
    chown -R qrane:qrew /home/qrane/.cache

# =============================================================================
# 6. Copy project and set permissions
# =============================================================================
COPY . .

ENV PYTHONPATH="/qonqrete"

RUN chown -R qrane:qrew /qonqrete && chmod -R 750 /qonqrete
RUN mkdir -p /qonq && chown qrane:qrew /qonq && chmod 770 /qonq
RUN mkdir -p /qonq/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d} && \
    chown -R worqer:qrew /qonq && chmod -R 2770 /qonq

# =============================================================================
# 7. Dynamic Versioning
# =============================================================================
ARG QONQ_VERSION=2.1.0-stable
ENV QONQ_VERSION=${QONQ_VERSION}

# =============================================================================
# 8. Entrypoint for Privilege Dropping
# =============================================================================
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# =============================================================================
# 9. HEALTHCHECK - Verify container is responsive (including z3)
# =============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD gosu qrane python3 -c "import yaml, openai, anthropic, z3; print('OK')" || exit 1

WORKDIR /qonqrete
