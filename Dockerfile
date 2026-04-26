# syntax=docker/dockerfile:1.7
FROM python:3.11.8-bookworm

# ----------------------------------------------------------------------------
# Build args
# ----------------------------------------------------------------------------
# QONQ_VERSION is populated by qonqrete.sh from the canonical VERSION file.
# Used for OCI labels here; at runtime qonqrete.sh passes it via `-e QONQ_VERSION`.
ARG QONQ_VERSION=""

# HOST_UID matches the container qrane user to the host user on Linux/WSL so
# bind-mounted /qonq files are natively owned by the host user — no helper
# chown/chmod gymnastics at runtime. On macOS/Windows Docker Desktop translates
# ownership through its VM layer, so 1000 is fine and this arg is ignored.
ARG HOST_UID=501

# ----------------------------------------------------------------------------
# OCI labels
# ----------------------------------------------------------------------------
LABEL org.opencontainers.image.title="QonQrete" \
      org.opencontainers.image.version="${QONQ_VERSION}" \
      org.opencontainers.image.source="https://qonqrete.sh"

# ----------------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------------
# QONQ_VERSION is deliberately NOT baked into ENV here. qonqrete.sh passes it
# at runtime via `-e QONQ_VERSION` so the VERSION file remains the single source
# of truth without needing a rebuild to change the display version.
ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONPATH="/qonqrete" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    HOST_UID=501

WORKDIR /qonqrete

# ----------------------------------------------------------------------------
# Python deps
# ----------------------------------------------------------------------------
# requirements.txt now also pins Ruff, used by worqer/qualifier/adapters/python.py
# for lint diagnostics. Qualifier gracefully no-ops if the binary is missing.
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------
# OS packages
# ----------------------------------------------------------------------------
# gosu is NOT installed. We enter the container as qrane via USER directive;
# no root-phase prep is needed because HOST_UID matching makes bind-mount
# ownership natural.
#
# Qualifier/Qontextor/Qompressor additions:
#   - shellcheck: static analysis used by worqer/qualifier/adapters/shell.py
#   - shfmt:      formatting sanity check for shell scripts
#   - curl + gnupg: required to fetch the NodeSource repo for Node.js 20
# All four are standard Debian bookworm packages (shellcheck + shfmt ship
# pre-built binaries, no compilation). Qualifier tolerates their absence
# so adding them here is a hard capability upgrade, not a requirement.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    chafa \
    curl \
    git \
    gnupg \
    shellcheck \
    shfmt \
    vim-tiny \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------
# Node.js 20 + Qualifier node-based tools
# ----------------------------------------------------------------------------
# Node.js is installed so Qontextor/Qompressor can invoke small repo-shipped
# helper scripts for JS/TS and HTML/CSS structural parsing, and so Qualifier
# can invoke its JS/TS and HTML/CSS validators locally and deterministically.
#
# We install the four tools globally (under /usr/local/lib/node_modules
# with shims in /usr/local/bin) so Qualifier's discovery module finds them
# on PATH. A repo-local node_modules is ALSO supported — discovery checks
# node_modules/.bin first — but we avoid shipping the repo's node_modules
# in the image by default to keep it lean.
#
# Pinned versions MUST match the devDependencies block in package.json so
# local dev and container behavior agree.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g --no-audit --no-fund --loglevel=error \
    @biomejs/biome@1.9.4 \
    typescript@5.6.3 \
    postcss@8.5.6 \
    parse5@7.2.1 \
    html-validate@9.2.2 \
    stylelint@16.10.0 \
    stylelint-config-standard@36.0.1 \
 && npm cache clean --force

# ----------------------------------------------------------------------------
# Project code + VERSION sanity
# ----------------------------------------------------------------------------
COPY . .
RUN test -s /qonqrete/VERSION || \
    (echo "FATAL: /qonqrete/VERSION missing or empty in build context" >&2 && exit 1)

# ----------------------------------------------------------------------------
# qrane user — single-user model, UID matches host on Linux/WSL
# ----------------------------------------------------------------------------
# `-U` creates a private group (qrane:qrane) with same GID as UID. Debian UPG
# convention. No shared qrew group — if multi-user /qonq access is ever needed,
# introduce it then, with a concrete design.
RUN set -eux \
 && if getent passwd "${HOST_UID}" >/dev/null 2>&1; then \
        echo "FATAL: UID ${HOST_UID} collides with a base-image system user." >&2; \
        echo "       Rebuild with a different HOST_UID." >&2; \
        exit 1; \
    fi \
 && useradd -u "${HOST_UID}" -U -m -d /home/qrane -s /bin/bash qrane \
 && chown -R qrane:qrane /home/qrane /qonqrete \
 && chmod -R u=rwX,g=,o= /qonqrete \
 && chmod -R u=rwX,g=,o= /home/qrane

# ----------------------------------------------------------------------------
# Runtime identity
# ----------------------------------------------------------------------------
# All subsequent layers and the container process run as qrane. No root phase,
# no gosu, no privilege transition, no caps needed.
USER qrane
WORKDIR /qonqrete

# Inline entrypoint: sets a tight umask (files 0640, dirs 0750) then execs
# whatever command is passed. No external script file needed.
# The "--" becomes $0; everything Docker appends (CMD/args) becomes "$@".
ENTRYPOINT ["/bin/bash", "-c", "umask 0027 && exec \"$@\"", "--"]
