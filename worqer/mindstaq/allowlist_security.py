#!/usr/bin/env python3
"""
Allowlist Security: Pre-Audited Secure Code Primitives
Part of mindstaQ v1.6.0 - ZERO LLM Code Generation

For security-critical code generation, ONLY compose from pre-audited primitives.
No web scraping (could get vulnerable code), no pattern generation.
Just wire together known-safe components!

Features:
- Pre-audited SQL query builder (parameterized only!)
- Safe file operations (path traversal protected)
- Input sanitization primitives
- JWT/Auth primitives
- Secure defaults

v1.6.0
"""

import re
import ast
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set, Tuple
from enum import Enum


__version__ = '2.1.0-stable'


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class SecurityCategory(Enum):
    """Security primitive categories."""
    SQL = "sql"
    FILE_IO = "file_io"
    INPUT_VALIDATION = "input_validation"
    AUTH = "auth"
    CRYPTO = "crypto"
    HTTP = "http"
    SANITIZATION = "sanitization"


@dataclass
class SecurityPrimitive:
    """A pre-audited security primitive."""
    name: str                        # Primitive name
    category: SecurityCategory       # Security category
    code: str                        # The actual code
    description: str                 # What it does
    imports: List[str]               # Required imports
    parameters: Dict[str, str]       # Parameter name -> type
    usage_example: str               # Example usage
    security_notes: List[str]        # Security considerations
    cve_protected: List[str] = field(default_factory=list)  # CVEs this prevents


@dataclass
class SecurityComposition:
    """Result of composing security primitives."""
    code: str                        # Generated secure code
    imports: List[str]               # All required imports
    primitives_used: List[str]       # Names of primitives used
    security_notes: List[str]        # Combined security notes
    warnings: List[str]              # Any warnings


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-AUDITED SECURITY PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

SECURITY_PRIMITIVES: Dict[str, SecurityPrimitive] = {
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SQL PRIMITIVES - PARAMETERIZED ONLY!
    # ═══════════════════════════════════════════════════════════════════════════
    
    'sql_query_sqlite': SecurityPrimitive(
        name='sql_query_sqlite',
        category=SecurityCategory.SQL,
        code='''def safe_query(conn: sqlite3.Connection, query: str, params: tuple = ()) -> List[Dict]:
    """
    Execute a parameterized SQLite query safely.
    NEVER interpolates values into query string!
    """
    cursor = conn.cursor()
    cursor.execute(query, params)  # Parameterized query
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]''',
        description='Safe parameterized SQLite query execution',
        imports=['import sqlite3', 'from typing import List, Dict'],
        parameters={'conn': 'sqlite3.Connection', 'query': 'str', 'params': 'tuple'},
        usage_example='results = safe_query(conn, "SELECT * FROM users WHERE id = ?", (user_id,))',
        security_notes=[
            'Always use ? placeholders for values',
            'Never use f-strings or .format() with SQL',
            'Query string must be a constant, not user input'
        ],
        cve_protected=['CWE-89 SQL Injection']
    ),
    
    'sql_query_postgres': SecurityPrimitive(
        name='sql_query_postgres',
        category=SecurityCategory.SQL,
        code='''def safe_query_pg(conn, query: str, params: tuple = ()) -> List[Dict]:
    """
    Execute a parameterized PostgreSQL query safely.
    Uses %s placeholders (psycopg2 style).
    """
    cursor = conn.cursor()
    cursor.execute(query, params)  # Parameterized query
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]''',
        description='Safe parameterized PostgreSQL query execution',
        imports=['from typing import List, Dict'],
        parameters={'conn': 'connection', 'query': 'str', 'params': 'tuple'},
        usage_example='results = safe_query_pg(conn, "SELECT * FROM users WHERE id = %s", (user_id,))',
        security_notes=[
            'Always use %s placeholders for values',
            'Never use f-strings or .format() with SQL',
            'Query string must be a constant, not user input'
        ],
        cve_protected=['CWE-89 SQL Injection']
    ),
    
    'sql_insert_safe': SecurityPrimitive(
        name='sql_insert_safe',
        category=SecurityCategory.SQL,
        code='''def safe_insert(conn, table: str, data: Dict[str, Any]) -> int:
    """
    Safely insert a row with parameterized values.
    Table name is validated against allowlist.
    """
    ALLOWED_TABLES = {'users', 'posts', 'comments', 'sessions'}  # Customize!
    
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' not in allowlist")
    
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['?'] * len(data))
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    
    cursor = conn.cursor()
    cursor.execute(query, tuple(data.values()))
    conn.commit()
    return cursor.lastrowid''',
        description='Safe parameterized INSERT with table allowlist',
        imports=['from typing import Dict, Any'],
        parameters={'conn': 'connection', 'table': 'str', 'data': 'Dict[str, Any]'},
        usage_example='row_id = safe_insert(conn, "users", {"name": name, "email": email})',
        security_notes=[
            'Table name validated against allowlist',
            'Values are always parameterized',
            'Customize ALLOWED_TABLES for your schema'
        ],
        cve_protected=['CWE-89 SQL Injection']
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FILE I/O PRIMITIVES - PATH TRAVERSAL PROTECTED
    # ═══════════════════════════════════════════════════════════════════════════
    
    'file_read_safe': SecurityPrimitive(
        name='file_read_safe',
        category=SecurityCategory.FILE_IO,
        code='''def safe_read_file(base_dir: str, filename: str) -> str:
    """
    Safely read a file, preventing path traversal attacks.
    File must be within base_dir.
    """
    from pathlib import Path
    
    base = Path(base_dir).resolve()
    target = (base / filename).resolve()
    
    # Security: Ensure target is within base directory
    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal detected!")
    
    if not target.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    
    if not target.is_file():
        raise ValueError("Path is not a file")
    
    return target.read_text(encoding='utf-8')''',
        description='Safe file reading with path traversal protection',
        imports=['from pathlib import Path'],
        parameters={'base_dir': 'str', 'filename': 'str'},
        usage_example='content = safe_read_file("/app/data", user_requested_file)',
        security_notes=[
            'Resolves symlinks to prevent bypass',
            'Validates file is within base directory',
            'Rejects directory paths'
        ],
        cve_protected=['CWE-22 Path Traversal', 'CWE-23 Relative Path Traversal']
    ),
    
    'file_write_safe': SecurityPrimitive(
        name='file_write_safe',
        category=SecurityCategory.FILE_IO,
        code='''def safe_write_file(base_dir: str, filename: str, content: str) -> Path:
    """
    Safely write a file, preventing path traversal attacks.
    File must be within base_dir.
    """
    from pathlib import Path
    import re
    
    # Sanitize filename
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    base = Path(base_dir).resolve()
    target = (base / safe_name).resolve()
    
    # Security: Ensure target is within base directory
    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal detected!")
    
    # Create parent dirs if needed
    target.parent.mkdir(parents=True, exist_ok=True)
    
    target.write_text(content, encoding='utf-8')
    return target''',
        description='Safe file writing with path traversal protection',
        imports=['from pathlib import Path', 'import re'],
        parameters={'base_dir': 'str', 'filename': 'str', 'content': 'str'},
        usage_example='path = safe_write_file("/app/uploads", user_filename, data)',
        security_notes=[
            'Sanitizes filename to remove dangerous characters',
            'Validates output is within base directory',
            'Uses resolved paths to prevent symlink attacks'
        ],
        cve_protected=['CWE-22 Path Traversal', 'CWE-434 Unrestricted Upload']
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # INPUT VALIDATION PRIMITIVES
    # ═══════════════════════════════════════════════════════════════════════════
    
    'validate_email': SecurityPrimitive(
        name='validate_email',
        category=SecurityCategory.INPUT_VALIDATION,
        code='''def validate_email(email: str) -> bool:
    """
    Validate email format using strict regex.
    Does NOT verify email exists, only format.
    """
    import re
    
    if not email or len(email) > 254:
        return False
    
    # RFC 5322 compliant (simplified)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))''',
        description='Validate email format',
        imports=['import re'],
        parameters={'email': 'str'},
        usage_example='if validate_email(user_email): ...',
        security_notes=[
            'Only validates format, not existence',
            'Max length 254 per RFC 5321',
            'Does not prevent all invalid emails'
        ],
        cve_protected=['CWE-20 Input Validation']
    ),
    
    'validate_url': SecurityPrimitive(
        name='validate_url',
        category=SecurityCategory.INPUT_VALIDATION,
        code='''def validate_url(url: str, allowed_schemes: tuple = ('http', 'https')) -> bool:
    """
    Validate URL format and scheme.
    Prevents SSRF by restricting schemes.
    """
    from urllib.parse import urlparse
    
    if not url or len(url) > 2048:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False
        
        # Restrict to allowed schemes
        if parsed.scheme.lower() not in allowed_schemes:
            return False
        
        # Block localhost/internal IPs (SSRF protection)
        netloc_lower = parsed.netloc.lower()
        blocked = ['localhost', '127.0.0.1', '0.0.0.0', '::1', '169.254.']
        if any(b in netloc_lower for b in blocked):
            return False
        
        return True
    except Exception:
        return False''',
        description='Validate URL with SSRF protection',
        imports=['from urllib.parse import urlparse'],
        parameters={'url': 'str', 'allowed_schemes': 'tuple'},
        usage_example='if validate_url(user_url): ...',
        security_notes=[
            'Blocks localhost/internal IPs to prevent SSRF',
            'Restricts to allowed schemes (default: http/https)',
            'Consider additional IP range blocking for production'
        ],
        cve_protected=['CWE-918 SSRF', 'CWE-20 Input Validation']
    ),
    
    'sanitize_html': SecurityPrimitive(
        name='sanitize_html',
        category=SecurityCategory.SANITIZATION,
        code='''def sanitize_html(html: str, allowed_tags: set = None) -> str:
    """
    Sanitize HTML to prevent XSS attacks.
    Removes all tags except allowed ones.
    """
    import re
    from html import escape
    
    if allowed_tags is None:
        allowed_tags = {'b', 'i', 'u', 'em', 'strong', 'p', 'br'}
    
    # First, escape everything
    safe = escape(html)
    
    # Then selectively restore allowed tags
    for tag in allowed_tags:
        # Restore opening tags
        safe = re.sub(
            f'&lt;({tag})(&gt;|\\s[^&]*&gt;)',
            lambda m: f'<{m.group(1)}>',
            safe,
            flags=re.IGNORECASE
        )
        # Restore closing tags
        safe = re.sub(
            f'&lt;/({tag})&gt;',
            lambda m: f'</{m.group(1)}>',
            safe,
            flags=re.IGNORECASE
        )
    
    return safe''',
        description='Sanitize HTML to prevent XSS',
        imports=['import re', 'from html import escape'],
        parameters={'html': 'str', 'allowed_tags': 'set'},
        usage_example='safe_html = sanitize_html(user_content)',
        security_notes=[
            'Escapes all HTML then restores allowed tags',
            'Does NOT sanitize attributes (use bleach for full sanitization)',
            'Consider using bleach library for production'
        ],
        cve_protected=['CWE-79 XSS']
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH PRIMITIVES
    # ═══════════════════════════════════════════════════════════════════════════
    
    'password_hash': SecurityPrimitive(
        name='password_hash',
        category=SecurityCategory.AUTH,
        code='''def hash_password(password: str) -> str:
    """
    Hash password using bcrypt with secure defaults.
    Returns hash string suitable for storage.
    """
    import bcrypt
    
    # Validate password
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password) > 72:
        raise ValueError("Password too long (bcrypt limit: 72 bytes)")
    
    # Hash with bcrypt (auto-generates salt, cost factor 12)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')''',
        description='Hash password with bcrypt',
        imports=['import bcrypt'],
        parameters={'password': 'str'},
        usage_example='hashed = hash_password(user_password)',
        security_notes=[
            'Uses bcrypt with cost factor 12',
            'Auto-generates secure salt',
            'Enforces minimum password length'
        ],
        cve_protected=['CWE-916 Weak Password Hash']
    ),
    
    'password_verify': SecurityPrimitive(
        name='password_verify',
        category=SecurityCategory.AUTH,
        code='''def verify_password(password: str, hashed: str) -> bool:
    """
    Verify password against bcrypt hash.
    Constant-time comparison to prevent timing attacks.
    """
    import bcrypt
    
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            hashed.encode('utf-8')
        )
    except Exception:
        return False''',
        description='Verify password against bcrypt hash',
        imports=['import bcrypt'],
        parameters={'password': 'str', 'hashed': 'str'},
        usage_example='if verify_password(login_password, stored_hash): ...',
        security_notes=[
            'Uses constant-time comparison',
            'Returns False on any error (prevents oracle attacks)'
        ],
        cve_protected=['CWE-208 Timing Attack']
    ),
    
    'jwt_create': SecurityPrimitive(
        name='jwt_create',
        category=SecurityCategory.AUTH,
        code='''def create_jwt(payload: dict, secret: str, expires_hours: int = 24) -> str:
    """
    Create a signed JWT token with expiration.
    Uses HS256 algorithm.
    """
    import jwt
    from datetime import datetime, timedelta
    
    # Add standard claims
    now = datetime.utcnow()
    payload = {
        **payload,
        'iat': now,
        'exp': now + timedelta(hours=expires_hours),
    }
    
    return jwt.encode(payload, secret, algorithm='HS256')''',
        description='Create signed JWT with expiration',
        imports=['import jwt', 'from datetime import datetime, timedelta'],
        parameters={'payload': 'dict', 'secret': 'str', 'expires_hours': 'int'},
        usage_example='token = create_jwt({"user_id": 123}, SECRET_KEY)',
        security_notes=[
            'Always set expiration (exp claim)',
            'Use strong secret (32+ random bytes)',
            'Consider RS256 for distributed systems'
        ],
        cve_protected=['CWE-347 Improper Verification']
    ),
    
    'jwt_verify': SecurityPrimitive(
        name='jwt_verify',
        category=SecurityCategory.AUTH,
        code='''def verify_jwt(token: str, secret: str) -> dict:
    """
    Verify and decode a JWT token.
    Raises exception on invalid/expired token.
    """
    import jwt
    
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=['HS256'],  # Explicitly allow only HS256
            options={
                'require': ['exp', 'iat'],
                'verify_exp': True,
            }
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")''',
        description='Verify and decode JWT',
        imports=['import jwt'],
        parameters={'token': 'str', 'secret': 'str'},
        usage_example='payload = verify_jwt(token, SECRET_KEY)',
        security_notes=[
            'Explicitly specifies allowed algorithms',
            'Requires exp claim to prevent forever-valid tokens',
            'Raises on any verification failure'
        ],
        cve_protected=['CWE-347 Improper Verification', 'CVE-2015-9235 Algorithm Confusion']
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CRYPTO PRIMITIVES
    # ═══════════════════════════════════════════════════════════════════════════
    
    'generate_secret': SecurityPrimitive(
        name='generate_secret',
        category=SecurityCategory.CRYPTO,
        code='''def generate_secret(length: int = 32) -> str:
    """
    Generate a cryptographically secure random secret.
    Returns hex-encoded string.
    """
    import secrets
    
    if length < 16:
        raise ValueError("Secret must be at least 16 bytes")
    
    return secrets.token_hex(length)''',
        description='Generate secure random secret',
        imports=['import secrets'],
        parameters={'length': 'int'},
        usage_example='api_key = generate_secret(32)',
        security_notes=[
            'Uses secrets module (CSPRNG)',
            'Minimum 16 bytes enforced',
            'Returns hex string (2x length in chars)'
        ],
        cve_protected=['CWE-330 Weak Random']
    ),
    
    'constant_time_compare': SecurityPrimitive(
        name='constant_time_compare',
        category=SecurityCategory.CRYPTO,
        code='''def secure_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time.
    Prevents timing attacks on secret comparison.
    """
    import hmac
    
    return hmac.compare_digest(a.encode(), b.encode())''',
        description='Constant-time string comparison',
        imports=['import hmac'],
        parameters={'a': 'str', 'b': 'str'},
        usage_example='if secure_compare(provided_token, stored_token): ...',
        security_notes=[
            'Uses HMAC compare_digest for constant time',
            'Always use for comparing secrets/tokens'
        ],
        cve_protected=['CWE-208 Timing Attack']
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HTTP PRIMITIVES
    # ═══════════════════════════════════════════════════════════════════════════
    
    'http_request_safe': SecurityPrimitive(
        name='http_request_safe',
        category=SecurityCategory.HTTP,
        code='''def safe_http_get(url: str, timeout: int = 30) -> dict:
    """
    Make a safe HTTP GET request with security defaults.
    Validates URL and sets secure timeouts.
    """
    import requests
    from urllib.parse import urlparse
    
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError("Only HTTP/HTTPS allowed")
    
    # Block internal addresses
    blocked = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
    if any(b in parsed.netloc.lower() for b in blocked):
        raise ValueError("Internal addresses not allowed")
    
    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=False,  # Prevent redirect to internal
        verify=True,  # Verify SSL
    )
    
    return {
        'status': response.status_code,
        'headers': dict(response.headers),
        'body': response.text
    }''',
        description='Safe HTTP GET with SSRF protection',
        imports=['import requests', 'from urllib.parse import urlparse'],
        parameters={'url': 'str', 'timeout': 'int'},
        usage_example='response = safe_http_get(user_provided_url)',
        security_notes=[
            'Blocks internal/localhost addresses',
            'Disables redirects (prevent SSRF via redirect)',
            'Enforces SSL verification'
        ],
        cve_protected=['CWE-918 SSRF']
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# ALLOWLIST SECURITY GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class AllowlistSecurityGenerator:
    """
    Generate secure code using ONLY pre-audited primitives.
    
    When security flag is set:
    - ONLY use SECURITY_PRIMITIVES
    - NO web scraping (could get vulnerable code)
    - NO pattern generation
    - Just wire together known-safe components
    
    Usage:
        gen = AllowlistSecurityGenerator()
        
        # Get a security primitive
        code = gen.get_primitive('sql_query_sqlite')
        print(code.code)
        
        # Compose multiple primitives
        result = gen.compose(['password_hash', 'jwt_create'], function_name='register_user')
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.primitives = SECURITY_PRIMITIVES.copy()
        self._custom_primitives: Dict[str, SecurityPrimitive] = {}
    
    def list_primitives(self, category: SecurityCategory = None) -> List[str]:
        """List available primitives, optionally filtered by category."""
        if category:
            return [name for name, p in self.primitives.items() if p.category == category]
        return list(self.primitives.keys())
    
    def get_primitive(self, name: str) -> Optional[SecurityPrimitive]:
        """Get a security primitive by name."""
        return self.primitives.get(name) or self._custom_primitives.get(name)
    
    def add_custom_primitive(self, primitive: SecurityPrimitive):
        """Add a custom audited primitive."""
        self._custom_primitives[primitive.name] = primitive
    
    def get_primitive_code(self, name: str, include_imports: bool = True) -> str:
        """Get the code for a primitive."""
        prim = self.get_primitive(name)
        if not prim:
            raise ValueError(f"Unknown primitive: {name}")
        
        if include_imports:
            imports = '\n'.join(prim.imports)
            return f"{imports}\n\n{prim.code}"
        return prim.code
    
    def compose(
        self,
        primitive_names: List[str],
        function_name: str = 'secure_operation',
        include_all_imports: bool = True
    ) -> SecurityComposition:
        """
        Compose multiple primitives into a single module.
        
        Args:
            primitive_names: List of primitive names to include
            function_name: Name for wrapper function (if needed)
            include_all_imports: Include all required imports
        
        Returns:
            SecurityComposition with combined code
        """
        primitives = []
        all_imports = set()
        all_notes = []
        warnings = []
        
        for name in primitive_names:
            prim = self.get_primitive(name)
            if not prim:
                warnings.append(f"Unknown primitive: {name}")
                continue
            
            primitives.append(prim)
            all_imports.update(prim.imports)
            all_notes.extend(prim.security_notes)
        
        if not primitives:
            return SecurityComposition(
                code='# No valid primitives found',
                imports=[],
                primitives_used=[],
                security_notes=[],
                warnings=warnings
            )
        
        # Generate code
        code_parts = []
        
        # Imports
        if include_all_imports:
            code_parts.append('\n'.join(sorted(all_imports)))
            code_parts.append('')
        
        # Security header
        code_parts.append('# ═══════════════════════════════════════════════════════════════')
        code_parts.append('# SECURITY MODULE - Generated by mindstaQ AllowlistSecurity')
        code_parts.append('# All primitives are pre-audited and known-safe')
        code_parts.append('# ═══════════════════════════════════════════════════════════════')
        code_parts.append('')
        
        # Each primitive
        for prim in primitives:
            code_parts.append(f'# --- {prim.name} ---')
            code_parts.append(f'# {prim.description}')
            code_parts.append(f'# Protected against: {", ".join(prim.cve_protected)}')
            code_parts.append(prim.code)
            code_parts.append('')
        
        return SecurityComposition(
            code='\n'.join(code_parts),
            imports=list(all_imports),
            primitives_used=[p.name for p in primitives],
            security_notes=list(set(all_notes)),
            warnings=warnings
        )
    
    def analyze_task(self, task: str) -> List[str]:
        """
        Analyze a task and suggest relevant security primitives.
        
        Args:
            task: Task description
        
        Returns:
            List of suggested primitive names
        """
        task_lower = task.lower()
        suggestions = []
        
        # SQL patterns
        if any(w in task_lower for w in ['sql', 'query', 'database', 'select', 'insert']):
            if 'postgres' in task_lower:
                suggestions.append('sql_query_postgres')
            else:
                suggestions.append('sql_query_sqlite')
            if 'insert' in task_lower:
                suggestions.append('sql_insert_safe')
        
        # File patterns
        if any(w in task_lower for w in ['file', 'read', 'write', 'upload', 'download']):
            if 'read' in task_lower:
                suggestions.append('file_read_safe')
            if 'write' in task_lower or 'upload' in task_lower:
                suggestions.append('file_write_safe')
        
        # Auth patterns
        if any(w in task_lower for w in ['password', 'login', 'auth', 'hash']):
            suggestions.append('password_hash')
            suggestions.append('password_verify')
        
        if any(w in task_lower for w in ['jwt', 'token', 'bearer']):
            suggestions.append('jwt_create')
            suggestions.append('jwt_verify')
        
        # Input validation
        if any(w in task_lower for w in ['email', 'validate', 'input']):
            suggestions.append('validate_email')
        
        if any(w in task_lower for w in ['url', 'http', 'request', 'fetch']):
            suggestions.append('validate_url')
            suggestions.append('http_request_safe')
        
        # Sanitization
        if any(w in task_lower for w in ['html', 'xss', 'sanitize']):
            suggestions.append('sanitize_html')
        
        # Crypto
        if any(w in task_lower for w in ['secret', 'key', 'random', 'generate']):
            suggestions.append('generate_secret')
        
        if any(w in task_lower for w in ['compare', 'constant', 'timing']):
            suggestions.append('constant_time_compare')
        
        return list(set(suggestions))
    
    def generate_for_task(self, task: str) -> SecurityComposition:
        """
        Analyze task and generate secure code using appropriate primitives.
        """
        suggested = self.analyze_task(task)
        
        if not suggested:
            return SecurityComposition(
                code='# No security primitives matched for this task',
                imports=[],
                primitives_used=[],
                security_notes=['Consider reviewing task for security requirements'],
                warnings=['No primitives matched - task may not require security primitives']
            )
        
        return self.compose(suggested)
    
    def validate_code_security(self, code: str) -> List[str]:
        """
        Scan code for common security anti-patterns.
        Returns list of warnings.
        """
        warnings = []
        
        # SQL injection patterns
        sql_patterns = [
            (r'f["\'].*SELECT.*{', 'Possible SQL injection: f-string with SELECT'),
            (r'\.format\(.*SELECT', 'Possible SQL injection: .format() with SELECT'),
            (r'%\s*\(.*SELECT', 'Possible SQL injection: % formatting with SELECT'),
            (r'execute\([^,]+\+', 'Possible SQL injection: string concatenation in execute()'),
        ]
        
        for pattern, message in sql_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                warnings.append(f'⚠️ {message}')
        
        # Path traversal patterns
        if 'open(' in code and '../' in code:
            warnings.append('⚠️ Possible path traversal: "../" in file open')
        
        if re.search(r'open\([^)]*\+', code):
            warnings.append('⚠️ Possible path traversal: string concatenation in open()')
        
        # Weak crypto patterns
        if 'md5' in code.lower():
            warnings.append('⚠️ Weak hash: MD5 should not be used for passwords')
        
        if 'sha1' in code.lower() and 'password' in code.lower():
            warnings.append('⚠️ Weak hash: SHA1 should not be used for passwords')
        
        # Hardcoded secrets
        if re.search(r'(password|secret|key)\s*=\s*["\'][^"\']+["\']', code, re.IGNORECASE):
            warnings.append('⚠️ Possible hardcoded secret detected')
        
        # Eval/exec
        if 'eval(' in code or 'exec(' in code:
            warnings.append('⚠️ eval()/exec() detected - potential code injection')
        
        return warnings


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print(f"Allowlist Security Generator v{__version__}")
    print("=" * 70)
    
    gen = AllowlistSecurityGenerator()
    
    # Test 1: List primitives
    print("\n[1] Available Security Primitives:")
    print("-" * 40)
    for cat in SecurityCategory:
        prims = gen.list_primitives(cat)
        if prims:
            print(f"  {cat.value}: {', '.join(prims)}")
    
    # Test 2: Get single primitive
    print("\n[2] SQL Query Primitive:")
    print("-" * 40)
    prim = gen.get_primitive('sql_query_sqlite')
    print(f"  Name: {prim.name}")
    print(f"  Protected against: {prim.cve_protected}")
    print(f"  Usage: {prim.usage_example}")
    
    # Test 3: Compose primitives
    print("\n[3] Compose Auth Primitives:")
    print("-" * 40)
    result = gen.compose(['password_hash', 'password_verify', 'jwt_create'])
    print(f"  Primitives used: {result.primitives_used}")
    print(f"  Imports: {len(result.imports)}")
    
    # Test 4: Task analysis
    print("\n[4] Task Analysis:")
    print("-" * 40)
    task = "Create a login endpoint with password verification and JWT tokens"
    suggestions = gen.analyze_task(task)
    print(f"  Task: '{task}'")
    print(f"  Suggested: {suggestions}")
    
    # Test 5: Code security validation
    print("\n[5] Security Validation:")
    print("-" * 40)
    bad_code = '''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    password = "hardcoded123"
    return eval(query)
'''
    warnings = gen.validate_code_security(bad_code)
    for w in warnings:
        print(f"  {w}")
    
    # Test 6: Generate for task
    print("\n[6] Generate for Task:")
    print("-" * 40)
    result = gen.generate_for_task("read user uploaded file safely")
    print(f"  Generated {len(result.primitives_used)} primitives")
    print(f"  Security notes: {len(result.security_notes)}")
    
    print("\n" + "=" * 70)
    print("✅ Allowlist Security Generator working!")
