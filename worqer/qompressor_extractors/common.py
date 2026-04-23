from __future__ import annotations

import re
from pathlib import Path

CODE_EXTENSIONS = {
    '.py', '.pyi',
    '.sh', '.bash', '.zsh', '.ksh',
    '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.go', '.rs', '.java', '.c', '.h', '.hpp', '.cpp', '.cc', '.php', '.rb', '.lua', '.swift', '.kt', '.kts', '.scala', '.pl'
}

COPY_EXTENSIONS = {'.yaml', '.yml', '.json', '.md', '.txt', '.toml', '.ini', '.cfg', '.conf', '.env'}
COPY_FILENAMES = {'Dockerfile', 'Makefile', 'Jenkinsfile', 'docker-compose.yml'}

KEYWORDISH_TYPES = {
    'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'case',
}


def comment_marker_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in {'.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.java', '.c', '.h', '.hpp', '.cpp', '.cc', '.css', '.scss', '.sass', '.less', '.go', '.rs', '.php', '.swift', '.kt', '.kts', '.scala'}:
        return '// ... (body stripped by Qompressor) ...'
    if suffix in {'.html', '.htm'}:
        return '<!-- ... (body stripped by Qompressor) ... -->'
    return '# ... (body stripped by Qompressor) ...'


def relative_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def first_nonempty(lines: list[str]) -> str | None:
    for line in lines:
        if line.strip():
            return line
    return None


def is_simple_constant_assignment(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r'^[A-Z][A-Z0-9_]*\s*=\s*[^\n]+$', stripped))


def safe_trim(text: str, limit: int = 120) -> str:
    text = re.sub(r'\s+', ' ', text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + '...'


def signature_until_block(header: str) -> str:
    header = re.sub(r'\s+', ' ', header.strip())
    idx = header.find('{')
    if idx != -1:
        return header[:idx].rstrip() + ' {'
    return header


def normalize_blank_lines(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text + ('\n' if text else '')


def should_copy(path: Path) -> bool:
    return path.name in COPY_FILENAMES or path.suffix.lower() in COPY_EXTENSIONS


def should_compress(path: Path) -> bool:
    return path.suffix.lower() in CODE_EXTENSIONS
