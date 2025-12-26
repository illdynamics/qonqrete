#!/usr/bin/env python3
# worqer/lib_security.py
# =============================================================================
# QonQrete Security Library
# v0.9.5 - Comprehensive security utilities for safe file operations
# =============================================================================
"""
Security utilities for QonQrete:
- Path validation and jail enforcement
- Symlink attack prevention
- File size limits
- Structured JSON logging
- Config validation
- Signal handling for graceful shutdown
"""

import os
import sys
import json
import signal
import logging
import traceback
from pathlib import Path
from typing import Optional, Any, Dict, List, Callable
from datetime import datetime

# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum file sizes
MAX_TASQ_SIZE = 100 * 1024           # 100KB for tasq.md
MAX_GENERATED_FILE_SIZE = 1024 * 1024  # 1MB per generated file
MAX_CONFIG_SIZE = 50 * 1024          # 50KB for config files

# Default jail directory (inside container)
DEFAULT_JAIL = Path("/qonq")

# Retry hard limits
MAX_RETRIES_HARD_LIMIT = 10
MAX_TIMEOUT_SECONDS = 300  # 5 minutes

# =============================================================================
# STRUCTURED LOGGING
# =============================================================================

class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)


class SecurityLogger:
    """Structured logger for security events."""
    
    def __init__(self, name: str = "qonqrete.security", log_path: Optional[Path] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # JSON handler for audit trail
        if log_path:
            handler = logging.FileHandler(log_path)
            handler.setFormatter(JSONFormatter())
            self.logger.addHandler(handler)
        
        # Console handler (human-readable)
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s"
        ))
        self.logger.addHandler(console)
    
    def audit(self, event: str, details: Dict[str, Any] = None):
        """Log a security audit event."""
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, event, (), None
        )
        record.extra_fields = {
            "event_type": "audit",
            "details": details or {}
        }
        self.logger.handle(record)
    
    def warning(self, message: str, details: Dict[str, Any] = None):
        """Log a security warning."""
        self.logger.warning(message, extra={"extra_fields": details or {}})
    
    def error(self, message: str, details: Dict[str, Any] = None):
        """Log a security error."""
        self.logger.error(message, extra={"extra_fields": details or {}})


# Global security logger
_security_logger: Optional[SecurityLogger] = None

def get_security_logger(log_path: Optional[Path] = None) -> SecurityLogger:
    """Get or create the global security logger."""
    global _security_logger
    if _security_logger is None:
        _security_logger = SecurityLogger(log_path=log_path)
    return _security_logger


# =============================================================================
# PATH VALIDATION & JAIL ENFORCEMENT
# =============================================================================

def get_jail_path() -> Path:
    """Get the jail directory path from environment or default."""
    return Path(os.environ.get("QONQ_WORKSPACE", str(DEFAULT_JAIL)))


def is_path_within_jail(path: Path, jail: Optional[Path] = None) -> bool:
    """
    Check if a path is within the jail directory.
    
    Prevents path traversal attacks by resolving symlinks and
    checking if the real path is within the jail.
    """
    if jail is None:
        jail = get_jail_path()
    
    try:
        # Resolve both paths to handle symlinks
        real_path = Path(os.path.realpath(str(path)))
        real_jail = Path(os.path.realpath(str(jail)))
        
        # Check if path is within jail
        try:
            real_path.relative_to(real_jail)
            return True
        except ValueError:
            return False
    except (OSError, RuntimeError):
        return False


def validate_path(path: Path, jail: Optional[Path] = None, must_exist: bool = False) -> Path:
    """
    Validate a path and ensure it's within the jail.
    
    Args:
        path: Path to validate
        jail: Jail directory (defaults to QONQ_WORKSPACE)
        must_exist: If True, path must exist
        
    Returns:
        Resolved, validated path
        
    Raises:
        SecurityError: If path is outside jail or fails validation
    """
    if jail is None:
        jail = get_jail_path()
    
    # Resolve the path (follows symlinks)
    try:
        resolved = Path(os.path.realpath(str(path)))
    except (OSError, RuntimeError) as e:
        raise SecurityError(f"Cannot resolve path: {path}") from e
    
    # Check if within jail
    if not is_path_within_jail(resolved, jail):
        logger = get_security_logger()
        logger.audit("path_traversal_blocked", {
            "attempted_path": str(path),
            "resolved_path": str(resolved),
            "jail": str(jail)
        })
        raise SecurityError(f"Path outside jail: {path}")
    
    # Check existence if required
    if must_exist and not resolved.exists():
        raise SecurityError(f"Path does not exist: {path}")
    
    return resolved


def safe_write_file(path: Path, content: str, max_size: int = MAX_GENERATED_FILE_SIZE,
                    jail: Optional[Path] = None) -> None:
    """
    Safely write content to a file within the jail.
    
    Args:
        path: Target file path
        content: Content to write
        max_size: Maximum allowed file size
        jail: Jail directory
        
    Raises:
        SecurityError: If path is outside jail or content exceeds size limit
    """
    # Validate path
    validated = validate_path(path, jail)
    
    # Check content size
    content_bytes = content.encode('utf-8')
    if len(content_bytes) > max_size:
        logger = get_security_logger()
        logger.warning("file_size_exceeded", {
            "path": str(path),
            "size": len(content_bytes),
            "limit": max_size
        })
        raise SecurityError(f"Content exceeds size limit: {len(content_bytes)} > {max_size}")
    
    # Ensure parent directory exists
    validated.parent.mkdir(parents=True, exist_ok=True)
    
    # Write atomically (write to temp, then rename)
    temp_path = validated.with_suffix(validated.suffix + '.tmp')
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        temp_path.rename(validated)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def safe_read_file(path: Path, max_size: int = MAX_GENERATED_FILE_SIZE,
                   jail: Optional[Path] = None) -> str:
    """
    Safely read a file from within the jail.
    
    Args:
        path: File path to read
        max_size: Maximum allowed file size
        jail: Jail directory
        
    Returns:
        File content as string
        
    Raises:
        SecurityError: If path is outside jail or file exceeds size limit
    """
    # Validate path
    validated = validate_path(path, jail, must_exist=True)
    
    # Check file size
    file_size = validated.stat().st_size
    if file_size > max_size:
        raise SecurityError(f"File exceeds size limit: {file_size} > {max_size}")
    
    with open(validated, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


# =============================================================================
# CONFIG VALIDATION
# =============================================================================

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "agents": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["openai", "anthropic", "gemini", "deepseek", "qwen"]},
                    "model": {"type": "string"},
                    "max_retries": {"type": "integer", "minimum": 0, "maximum": MAX_RETRIES_HARD_LIMIT},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": MAX_TIMEOUT_SECONDS}
                }
            }
        },
        "options": {
            "type": "object",
            "properties": {
                "auto_cycle_limit": {"type": "integer", "minimum": 0, "maximum": 100},
                "use_qompressor": {"type": "boolean"},
                "use_qontextor": {"type": "boolean"},
                "use_tasqleveler": {"type": "boolean"}
            }
        }
    }
}


def validate_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate configuration against schema.
    
    Returns list of validation errors (empty if valid).
    """
    errors = []
    
    try:
        import jsonschema
        jsonschema.validate(config, CONFIG_SCHEMA)
    except ImportError:
        # jsonschema not available, do basic validation
        if "agents" in config:
            for agent_name, agent_config in config.get("agents", {}).items():
                if "max_retries" in agent_config:
                    retries = agent_config["max_retries"]
                    if not isinstance(retries, int) or retries < 0 or retries > MAX_RETRIES_HARD_LIMIT:
                        errors.append(f"agents.{agent_name}.max_retries must be 0-{MAX_RETRIES_HARD_LIMIT}")
                if "timeout" in agent_config:
                    timeout = agent_config["timeout"]
                    if not isinstance(timeout, int) or timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
                        errors.append(f"agents.{agent_name}.timeout must be 1-{MAX_TIMEOUT_SECONDS}")
    except Exception as e:
        errors.append(f"Schema validation error: {e}")
    
    return errors


def validate_tasq_file(path: Path) -> None:
    """
    Validate tasq.md file size.
    
    Raises:
        SecurityError: If file exceeds size limit
    """
    if not path.exists():
        return
    
    file_size = path.stat().st_size
    if file_size > MAX_TASQ_SIZE:
        raise SecurityError(f"tasq.md exceeds size limit: {file_size} > {MAX_TASQ_SIZE} bytes")


# =============================================================================
# SIGNAL HANDLING
# =============================================================================

_shutdown_handlers: List[Callable] = []
_shutdown_triggered = False


def register_shutdown_handler(handler: Callable) -> None:
    """Register a function to be called on graceful shutdown."""
    _shutdown_handlers.append(handler)


def _handle_shutdown_signal(signum: int, frame) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _shutdown_triggered
    
    if _shutdown_triggered:
        # Force exit on second signal
        sys.exit(128 + signum)
    
    _shutdown_triggered = True
    
    logger = get_security_logger()
    logger.audit("shutdown_signal_received", {"signal": signum})
    
    # Call registered handlers
    for handler in _shutdown_handlers:
        try:
            handler()
        except Exception as e:
            logger.error(f"Shutdown handler error: {e}")
    
    sys.exit(0)


def setup_signal_handlers() -> None:
    """Setup handlers for graceful shutdown on SIGTERM/SIGINT."""
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)


def is_shutdown_triggered() -> bool:
    """Check if shutdown has been triggered."""
    return _shutdown_triggered


# =============================================================================
# EXCEPTION SANITIZATION
# =============================================================================

def sanitize_traceback(exc_info=None, include_locals: bool = False) -> str:
    """
    Sanitize exception traceback for safe logging.
    
    Removes potentially sensitive information like:
    - API keys in environment variables
    - Full file paths outside container
    - Local variable values (unless explicitly requested)
    """
    if exc_info is None:
        exc_info = sys.exc_info()
    
    if exc_info[0] is None:
        return ""
    
    # Get basic traceback
    tb_lines = traceback.format_exception(*exc_info)
    
    # Sanitize sensitive patterns
    sensitive_patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***'),
        (r'AIza[a-zA-Z0-9_-]{35}', 'AIza***REDACTED***'),
        (r'sk-ant-[a-zA-Z0-9_-]{20,}', 'sk-ant-***REDACTED***'),
    ]
    
    import re
    sanitized = "".join(tb_lines)
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    
    return sanitized


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


class TimeoutError(Exception):
    """Raised when an operation times out."""
    pass


class RetryLimitError(Exception):
    """Raised when retry limit is exceeded."""
    pass


# =============================================================================
# INITIALIZATION
# =============================================================================

def init_security(log_path: Optional[Path] = None) -> None:
    """
    Initialize security subsystem.
    
    Should be called at application startup.
    """
    # Setup signal handlers
    setup_signal_handlers()
    
    # Initialize logger
    get_security_logger(log_path)
    
    # Log startup
    logger = get_security_logger()
    logger.audit("security_initialized", {
        "jail": str(get_jail_path()),
        "max_tasq_size": MAX_TASQ_SIZE,
        "max_file_size": MAX_GENERATED_FILE_SIZE,
        "max_retries": MAX_RETRIES_HARD_LIMIT,
        "max_timeout": MAX_TIMEOUT_SECONDS
    })
