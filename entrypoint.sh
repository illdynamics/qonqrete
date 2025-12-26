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
    # Ensure all required subdirectories exist
    mkdir -p /qonq/{tasq.d,exeq.d,reqap.d,qodeyard,struqture,qontext.d,bloq.d,briq.d}
    
    # Fix ownership - qrane:qrew for everything
    chown -R qrane:qrew /qonq
    
    # Set permissions: rwxrwxr-x with setgid for group inheritance
    # Using 2775 instead of 2770 so host user can read files after container exits
    chmod -R 2775 /qonq
fi

# Set umask so new files are world-readable (for host access after container exit)
umask 0002

# Drop privileges and execute the command as qrane user
exec gosu qrane "$@"
