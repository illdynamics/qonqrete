#!/usr/bin/env python3
"""
mindstaQ Logger v2.0.0 - Agent-level logging with event files

Provides:
- Console output with spinners (like instruqtor/construqtor/inspeqtor)
- Event log files (event_qombinator.log, event_sqavenger.log, etc.)
- Full audit log (qonsole_mindstaq.log)

DESIGN: Zero deadlocks - no threading locks, no file handles during import
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

__version__ = '2.1.0-stable'

# ANSI colors
CYAN = '\033[36m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
MAGENTA = '\033[35m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Agent color scheme (matches instruqtor/construqtor/inspeqtor)
AGENT_COLORS = {
    'mindstaQ': CYAN,
    'qomputator': YELLOW,
    'qrystallizer': GREEN,
    'sqavenger': MAGENTA,
    'qombinator': CYAN,
    'qoncentrator': GREEN,
    'qonscience': YELLOW,
    'franqenstein': RED,
    'qrawler': MAGENTA,
    'triple_threat': BOLD + CYAN,
}

# Spinner frames (matches qrane spinner)
SPINNER_FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷']


class MindstaQLogger:
    """Safe, non-blocking logger for mindstaQ agents."""
    
    def __init__(self):
        self._struqture_path: Optional[Path] = None
        self._spinner_idx = 0
        self._current_agent = 'mindstaQ'
        self._audit_log = []
        self._enabled = True
    
    def set_struqture_path(self, path: str):
        """Set the struqture directory for event/qonsole logs."""
        self._struqture_path = Path(path)
        self._struqture_path.mkdir(parents=True, exist_ok=True)
    
    def set_agent(self, agent: str):
        """Set current agent for logging context."""
        self._current_agent = agent
    
    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")
    
    def _spinner(self) -> str:
        frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
        self._spinner_idx += 1
        return frame
    
    def _color(self, agent: str = None) -> str:
        return AGENT_COLORS.get(agent or self._current_agent, CYAN)
    
    def _write_stderr(self, msg: str):
        """Write to stderr with flush (captured by qrane)."""
        if self._enabled:
            sys.stderr.write(msg + '\n')
            sys.stderr.flush()
    
    def _write_event(self, agent: str, level: str, message: str):
        """Write to agent-specific event log."""
        if not self._struqture_path:
            return
        try:
            event_file = self._struqture_path / f"event_{agent.lower()}.log"
            ts = datetime.now().isoformat()
            with open(event_file, 'a') as f:
                f.write(f"{ts} [{level}] {message}\n")
        except Exception:
            pass  # Never fail on logging
    
    def _write_audit(self, message: str):
        """Write to full audit log."""
        if not self._struqture_path:
            return
        try:
            audit_file = self._struqture_path / "qonsole_mindstaq.log"
            ts = datetime.now().isoformat()
            with open(audit_file, 'a') as f:
                f.write(f"{ts} {message}\n")
        except Exception:
            pass
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PUBLIC API - Console Output
    # ═══════════════════════════════════════════════════════════════════════════
    
    def agent_start(self, agent: str, message: str = "Starting..."):
        """Log agent startup with spinner."""
        self._current_agent = agent
        color = self._color(agent)
        spinner = self._spinner()
        prefix = f"[aQQ] {color}⟦{agent}⟧{RESET}"
        self._write_stderr(f"{prefix} {spinner} {message}")
        self._write_event(agent, "START", message)
        self._write_audit(f"[{agent}] START: {message}")
    
    def agent_complete(self, agent: str, message: str = "Complete", success: bool = True):
        """Log agent completion."""
        color = self._color(agent)
        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        prefix = f"[aQQ] {color}⟦{agent}⟧{RESET}"
        self._write_stderr(f"{prefix} {status} {message}")
        level = "SUCCESS" if success else "FAILED"
        self._write_event(agent, level, message)
        self._write_audit(f"[{agent}] {level}: {message}")
    
    def info(self, message: str, agent: str = None):
        """Log info message."""
        agent = agent or self._current_agent
        ts = self._timestamp()
        self._write_stderr(f"[{ts}] [mindstaQ] [INFO] {message}")
        self._write_event(agent, "INFO", message)
        self._write_audit(f"[{agent}] INFO: {message}")
    
    def debug(self, message: str, agent: str = None):
        """Log debug message (only to files, not console)."""
        agent = agent or self._current_agent
        self._write_event(agent, "DEBUG", message)
        self._write_audit(f"[{agent}] DEBUG: {message}")
    
    def warn(self, message: str, agent: str = None):
        """Log warning message."""
        agent = agent or self._current_agent
        ts = self._timestamp()
        self._write_stderr(f"[{ts}] [mindstaQ] {YELLOW}[WARN]{RESET} {message}")
        self._write_event(agent, "WARN", message)
        self._write_audit(f"[{agent}] WARN: {message}")
    
    def error(self, message: str, agent: str = None):
        """Log error message."""
        agent = agent or self._current_agent
        ts = self._timestamp()
        self._write_stderr(f"[{ts}] [mindstaQ] {RED}[ERROR]{RESET} {message}")
        self._write_event(agent, "ERROR", message)
        self._write_audit(f"[{agent}] ERROR: {message}")
    
    def step(self, step_num: int, message: str, agent: str = None):
        """Log a processing step."""
        agent = agent or self._current_agent
        ts = self._timestamp()
        self._write_stderr(f"[{ts}] [mindstaQ] [INFO] STEP {step_num}: {message}")
        self._write_event(agent, "STEP", f"{step_num}: {message}")
        self._write_audit(f"[{agent}] STEP {step_num}: {message}")
    
    def tier(self, tier_name: str, message: str):
        """Log tier agent activity."""
        color = self._color(tier_name.lower())
        spinner = self._spinner()
        prefix = f"[aQQ] {color}⟦{tier_name}⟧{RESET}"
        self._write_stderr(f"{prefix} {spinner} {message}")
        self._write_event(tier_name.lower(), "TIER", message)
        self._write_audit(f"[{tier_name}] {message}")
    
    def result(self, success: bool, message: str, agent: str = None):
        """Log a result."""
        agent = agent or self._current_agent
        ts = self._timestamp()
        status = f"{GREEN}OK{RESET}" if success else f"{RED}FAIL{RESET}"
        self._write_stderr(f"[{ts}] [mindstaQ] [INFO] {status} {message}")
        level = "SUCCESS" if success else "FAILED"
        self._write_event(agent, level, message)
        self._write_audit(f"[{agent}] {level}: {message}")
    
    def separator(self):
        """Log a separator line."""
        sep = "=" * 60
        self._write_stderr(f"[mindstaQ] {sep}")
        self._write_audit(sep)
    
    def progress(self, current: int, total: int, message: str = ""):
        """Log progress (for multi-step operations)."""
        pct = int((current / total) * 100) if total > 0 else 0
        bar_len = 20
        filled = int(bar_len * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        self._write_stderr(f"[mindstaQ] [{bar}] {pct}% {message}")


# Global instance
mlog = MindstaQLogger()


# Convenience functions
def agent_start(agent: str, message: str = "Starting..."):
    mlog.agent_start(agent, message)

def agent_complete(agent: str, message: str = "Complete", success: bool = True):
    mlog.agent_complete(agent, message, success)

def info(message: str):
    mlog.info(message)

def debug(message: str):
    mlog.debug(message)

def warn(message: str):
    mlog.warn(message)

def error(message: str):
    mlog.error(message)

def step(step_num: int, message: str):
    mlog.step(step_num, message)

def tier(tier_name: str, message: str):
    mlog.tier(tier_name, message)

def result(success: bool, message: str):
    mlog.result(success, message)
