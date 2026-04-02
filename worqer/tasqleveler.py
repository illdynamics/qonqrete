#!/usr/bin/env python3
# worqer/tasqleveler.py
# ═══════════════════════════════════════════════════════════════════════════════
# TasqLeveler Agent - DEPRECATED
# This file is retained for backward compatibility. It acts as a wrapper 
# around the new Qrystallizer agent.
# ═══════════════════════════════════════════════════════════════════════════════

import sys

try:
    import qrystallizer
except ImportError as e:
    sys.stderr.write(f"CRITICAL: Could not import qrystallizer.py: {e}\n")
    sys.exit(1)

def main() -> None:
    print("[TasqLeveler] ⚠️ DEPRECATION WARNING: tasqleveler is deprecated and replaced by Qrystallizer.", flush=True)
    print("[TasqLeveler] 🔄 Redirecting to Qrystallizer...", flush=True)
    
    # Hand off to qrystallizer, which will read sys.argv exactly the same way.
    qrystallizer.main()

if __name__ == '__main__':
    main()