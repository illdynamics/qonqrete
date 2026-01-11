#!/usr/bin/env python3
"""
mindstaQ Logger: Unified Logging Infrastructure for All Agents
Part of QonQrete - Consistent logging across all mindstaQ components

Provides:
- Event logs: High-level agent events (start/stop/status)
- Audit logs: Detailed operation traces (qonsole_*.log style)
- Structured output for observability
- File-based persistence to struqture directory

v1.9.6-stable - Initial release with full agent coverage

Usage:
    from worqer.mindstaq.logger import MindstaQLogger
    
    logger = MindstaQLogger('sqavenger', struqture_dir='/path/to/struqture')
    logger.event('Starting web search...')
    logger.audit('Query: python async worker pool example')
    logger.audit('Found 5 results from stackoverflow.com')
    logger.event('Web search complete.')
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import json
import threading


__version__ = '1.9.6-stable'


class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: datetime
    level: LogLevel
    agent: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level.value,
            'agent': self.agent,
            'message': self.message,
            'details': self.details
        }
    
    def format_event(self) -> str:
        """Format for event log (concise)."""
        ts = self.timestamp.strftime('%H:%M:%S')
        return f"[{ts}] {self.message}"
    
    def format_audit(self) -> str:
        """Format for audit log (detailed)."""
        ts = self.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        prefix = f"[{self.agent.upper()}]"
        return f"{prefix} {self.message}"


class MindstaQLogger:
    """
    Unified logger for all mindstaQ agents.
    
    Creates two log files per agent:
    - events_{agent}.log: High-level events (start, stop, status)
    - qonsole_{agent}.log: Detailed audit trail
    """
    
    # Global registry of loggers
    _instances: Dict[str, 'MindstaQLogger'] = {}
    _lock = threading.Lock()
    
    def __init__(
        self,
        agent_name: str,
        struqture_dir: str = None,
        console_output: bool = True,
        prefix: str = '[mindstaQ]'
    ):
        self.agent_name = agent_name.lower()
        self.struqture_dir = Path(struqture_dir) if struqture_dir else None
        self.console_output = console_output
        self.prefix = prefix
        
        self._event_log: List[LogEntry] = []
        self._audit_log: List[LogEntry] = []
        self._file_handles: Dict[str, Any] = {}
        
        # Register instance
        with MindstaQLogger._lock:
            MindstaQLogger._instances[agent_name] = self
    
    @classmethod
    def get_logger(cls, agent_name: str) -> 'MindstaQLogger':
        """Get or create logger for an agent."""
        with cls._lock:
            if agent_name not in cls._instances:
                cls._instances[agent_name] = cls(agent_name)
            return cls._instances[agent_name]
    
    def set_struqture_dir(self, path: str):
        """Set the struqture directory for file output."""
        self.struqture_dir = Path(path)
        self.struqture_dir.mkdir(parents=True, exist_ok=True)
    
    def _write_to_file(self, filename: str, content: str):
        """Write content to log file."""
        if not self.struqture_dir:
            return
        
        filepath = self.struqture_dir / filename
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        except Exception:
            pass  # Silent fail for logging
    
    def event(self, message: str, level: LogLevel = LogLevel.INFO, **details):
        """
        Log a high-level event.
        
        Events are for major state changes:
        - Agent started/stopped
        - Processing started/completed
        - Major milestones
        """
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            agent=self.agent_name,
            message=message,
            details=details
        )
        self._event_log.append(entry)
        
        # Write to file
        self._write_to_file(f'events_{self.agent_name}.log', entry.format_event())
    
    def audit(self, message: str, level: LogLevel = LogLevel.INFO, **details):
        """
        Log a detailed audit entry.
        
        Audit entries are for detailed operation traces:
        - Function calls with parameters
        - Intermediate results
        - Performance metrics
        - Debug information
        """
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            agent=self.agent_name,
            message=message,
            details=details
        )
        self._audit_log.append(entry)
        
        # Write to file
        self._write_to_file(f'qonsole_{self.agent_name}.log', entry.format_audit())
        
        # Console output if enabled
        if self.console_output:
            print(f"{self.prefix} {message}")
    
    def debug(self, message: str, **details):
        """Log debug message to audit log."""
        self.audit(message, LogLevel.DEBUG, **details)
    
    def info(self, message: str, **details):
        """Log info message to audit log."""
        self.audit(message, LogLevel.INFO, **details)
    
    def warning(self, message: str, **details):
        """Log warning message to audit log."""
        self.audit(message, LogLevel.WARNING, **details)
    
    def error(self, message: str, **details):
        """Log error message to audit log."""
        self.audit(message, LogLevel.ERROR, **details)
    
    def separator(self, char: str = '=', length: int = 60):
        """Log a separator line for visual grouping."""
        self.audit(char * length)
    
    def step(self, step_num: int, description: str):
        """Log a pipeline step."""
        self.audit(f"STEP {step_num}: {description}")
    
    def result(self, key: str, value: Any):
        """Log a result key-value pair."""
        self.audit(f"  {key}: {value}")
    
    def start_operation(self, operation: str):
        """Log operation start."""
        self.event(f"Starting {operation}...")
        self.audit(f">>> Starting {operation}")
    
    def end_operation(self, operation: str, success: bool = True, **stats):
        """Log operation end."""
        status = "completed successfully" if success else "failed"
        self.event(f"{operation} {status}.")
        self.audit(f"<<< {operation} {status}")
        for key, value in stats.items():
            self.result(key, value)
    
    def get_event_log(self) -> List[Dict]:
        """Get all event log entries as dicts."""
        return [e.to_dict() for e in self._event_log]
    
    def get_audit_log(self) -> List[Dict]:
        """Get all audit log entries as dicts."""
        return [e.to_dict() for e in self._audit_log]
    
    def clear(self):
        """Clear in-memory logs."""
        self._event_log.clear()
        self._audit_log.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_logger(agent_name: str) -> MindstaQLogger:
    """Get a logger instance for an agent."""
    return MindstaQLogger.get_logger(agent_name)


def configure_logging(struqture_dir: str, agents: List[str] = None):
    """
    Configure logging for multiple agents.
    
    Args:
        struqture_dir: Directory for log files
        agents: List of agent names (default: all mindstaQ agents)
    """
    default_agents = [
        'qomputator', 'qombinator', 'sqavenger', 'qrawler',
        'qrystallizer', 'qoncentrator', 'qonscience',
        'qalibrator', 'qualifier', 'mindstaq'
    ]
    
    agents = agents or default_agents
    
    for agent in agents:
        logger = get_logger(agent)
        logger.set_struqture_dir(struqture_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import tempfile
    
    # Create temp directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Testing logging in {tmpdir}")
        
        # Configure logging
        configure_logging(tmpdir)
        
        # Get logger
        log = get_logger('sqavenger')
        
        # Test various log methods
        log.event("Agent initialized")
        log.separator()
        log.audit("mindstaQ SQavenger v1.9.6-stable")
        log.separator()
        log.start_operation("web search")
        log.step(1, "Building search queries")
        log.result("queries", ["python async example", "asyncio worker pool"])
        log.step(2, "Executing search")
        log.result("engine", "duckduckgo")
        log.result("results_found", 15)
        log.step(3, "Extracting code snippets")
        log.result("snippets_extracted", 5)
        log.end_operation("web search", success=True, 
                        total_results=15, 
                        snippets=5, 
                        latency_ms=1234)
        log.event("Agent completed")
        
        # Show generated files
        print("\nGenerated log files:")
        for f in Path(tmpdir).iterdir():
            print(f"  {f.name}: {f.stat().st_size} bytes")
            with open(f) as fp:
                print(fp.read())
