#!/bin/bash
# =============================================================================
# QonQrete Entrypoint Script
# =============================================================================
# This script runs as root at container startup, fixes permissions on the
# mounted /qonq volume, then drops to the qrane user for actual execution.
# =============================================================================

set -e

# Fix ownership on mounted /qonq volume
# This is needed because Docker bind mounts inherit host permissions
if [ -d "/qonq" ]; then
    chown -R qrane:qrew /qonq 2>/dev/null || true
    chmod -R 2770 /qonq 2>/dev/null || true
fi

# Drop privileges and execute the command as qrane user
exec gosu qrane "$@"
