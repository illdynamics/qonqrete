#!/usr/bin/env python3
# worqer/qompressor.py
"""
The 'Skeletonizer' for QonQrete.
v1.2.2-stable: Contract-preserving skeletonization with deterministic summaries.

PRESERVES:
- Import statements
- Module-level constant assignments (PORT, next_id, etc.)
- Pydantic model class bodies (all field annotations)
- Route decorators and function signatures
- First N meaningful statements inside endpoint functions
- Lines matching key patterns (id assignment, dict insertions)

STRIPPED BODIES get deterministic summary comments (no AI):
- Mentions called functions, DB/storage mutations, returned type, main side effects
- Max 2 lines per function

FAST. ZERO TOKEN COST. Output is valid Python.
"""
import sys
import os
import ast
import re
import shutil
from pathlib import Path

# --- Configuration ---
COMPRESS_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp', '.php'}
COPY_EXTENSIONS = {'.yaml', '.yml', '.json', '.md', '.txt', '.toml'}
COPY_FILENAMES  = {'Dockerfile', 'Makefile', 'Jenkinsfile', 'docker-compose.yml'}

# Patterns that indicate key lines to preserve inside function bodies
KEY_PATTERNS = [
    re.compile(r'next_id', re.IGNORECASE),
    re.compile(r'\bid\s*=', re.IGNORECASE),
    re.compile(r'\[.*\]\s*='),          # dict/list assignment
    re.compile(r'\.append\('),
    re.compile(r'\.update\('),
    re.compile(r'\.insert\('),
    re.compile(r'return\s+'),
]


def _is_pydantic_or_dataclass(node: ast.ClassDef) -> bool:
    """Check if a class inherits from BaseModel, dataclass, etc."""
    for base in node.bases:
        try:
            name = ast.unparse(base)
        except:
            name = ""
        if any(kw in name for kw in ('BaseModel', 'Base', 'Schema', 'Model')):
            return True
    for decorator in node.decorator_list:
        try:
            name = ast.unparse(decorator)
        except:
            name = ""
        if 'dataclass' in name:
            return True
    return False


def _is_route_decorator(decorator) -> bool:
    """Check if a decorator is a route/endpoint decorator."""
    try:
        name = ast.unparse(decorator)
    except:
        return False
    route_patterns = ['get(', 'post(', 'put(', 'delete(', 'patch(', 'route(', 'api_route(']
    return any(p in name.lower() for p in route_patterns)


def _has_route_decorator(node) -> bool:
    """Check if a function has route decorators."""
    if not hasattr(node, 'decorator_list'):
        return False
    return any(_is_route_decorator(d) for d in node.decorator_list)


def _generate_body_summary(node, lines: list[str], indent_level: int = None) -> str:
    """Generate a deterministic summary comment for a stripped function body.
    
    indent_level: number of spaces for indentation. If None, computed from the
    function body's first statement.
    """
    # Compute indentation from the function body
    if indent_level is None:
        indent_level = 4  # default fallback
        if hasattr(node, 'body') and node.body:
            first_body = node.body[0]
            if hasattr(first_body, 'col_offset'):
                indent_level = first_body.col_offset
            elif first_body.lineno - 1 < len(lines):
                body_line = lines[first_body.lineno - 1]
                indent_level = len(body_line) - len(body_line.lstrip())

    indent = ' ' * indent_level
    parts = []

    body_text = ""
    if hasattr(node, 'body') and node.body:
        try:
            start = node.body[0].lineno - 1
            end = node.end_lineno
            body_text = "\n".join(lines[start:end])
        except:
            pass

    # Detect called functions
    calls = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            try:
                call_name = ast.unparse(child.func)
                # Keep short call names
                if len(call_name) < 40:
                    calls.add(call_name)
            except:
                pass
    if calls:
        call_list = ", ".join(sorted(calls)[:5])
        parts.append(f"calls: {call_list}")

    # Detect return type
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value:
            try:
                ret = ast.unparse(child.value)
                if len(ret) < 50:
                    parts.append(f"returns: {ret[:40]}")
                    break
            except:
                pass

    # Detect storage mutations
    mutations = []
    for child in ast.walk(node):
        if isinstance(child, ast.Subscript) and isinstance(child.ctx, ast.Store):
            mutations.append("dict/list store")
            break
    for kw in ['append', 'insert', 'update', 'pop', 'remove', 'delete']:
        if kw + '(' in body_text:
            mutations.append(kw)
            break
    if mutations:
        parts.append(f"mutates: {', '.join(list(set(mutations))[:3])}")

    if not parts:
        parts.append("implementation stripped")

    summary = "; ".join(parts)
    return f"{indent}# summary: {summary}"


def compress_python(content: str) -> str:
    """
    v1.2.2: Contract-preserving Python skeletonizer.
    Uses AST to strip function bodies while preserving key evidence.
    Generates deterministic summary comments for stripped bodies.
    Output is valid, parseable Python.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return compress_generic(content)

    lines = content.splitlines()
    output_lines = []
    skip_until = -1  # Line number to skip until (exclusive)

    class SmartSkeletonizer(ast.NodeVisitor):
        def __init__(self):
            self.intervals_to_keep = []  # (start, end) 1-indexed inclusive
            self.summaries = {}           # line_number -> (summary_str, indent_level)
            self.skip_ranges = []         # (start, end) ranges to skip entirely

        def visit_Import(self, node):
            self.intervals_to_keep.append((node.lineno, node.end_lineno))

        def visit_ImportFrom(self, node):
            self.intervals_to_keep.append((node.lineno, node.end_lineno))

        def visit_Assign(self, node):
            """Preserve module-level constant assignments."""
            # Only module-level (not nested)
            if self._is_module_level(node):
                self.intervals_to_keep.append((node.lineno, node.end_lineno))

        def visit_AnnAssign(self, node):
            """Preserve module-level annotated assignments."""
            if self._is_module_level(node):
                self.intervals_to_keep.append((node.lineno, node.end_lineno))

        def _is_module_level(self, node):
            """Heuristic: check if node is at module level (col_offset == 0)."""
            return getattr(node, 'col_offset', -1) == 0

        def visit_ClassDef(self, node):
            if _is_pydantic_or_dataclass(node):
                # Preserve entire class (model fields are critical)
                self.intervals_to_keep.append((node.lineno, node.end_lineno))
            else:
                # Keep class signature + decorators
                self._keep_decorators_and_sig(node)
                # Visit children (methods)
                self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self._process_func(node)

        def visit_AsyncFunctionDef(self, node):
            self._process_func(node)

        def _process_func(self, node):
            # Keep decorators + signature
            self._keep_decorators_and_sig(node)

            # Compute body indent level
            body_indent = 4
            if node.body:
                first_body = node.body[0]
                if hasattr(first_body, 'col_offset'):
                    body_indent = first_body.col_offset
                elif first_body.lineno - 1 < len(lines):
                    body_line = lines[first_body.lineno - 1]
                    body_indent = len(body_line) - len(body_line.lstrip())

            # Determine what to keep from body
            if _has_route_decorator(node):
                # Endpoint function: keep first N meaningful statements + key pattern lines
                self._keep_endpoint_body(node, body_indent)
            else:
                # Regular function: just generate summary
                if node.body:
                    body_start = node.body[0].lineno
                    body_end = node.end_lineno
                    # Mark body for skipping, insert summary
                    summary = _generate_body_summary(node, lines, body_indent)
                    # Find where the signature ends (line with ':')
                    sig_end = node.lineno
                    for i in range(node.lineno - 1, min(node.end_lineno, node.lineno + 20)):
                        if i < len(lines) and lines[i].rstrip().endswith(':'):
                            sig_end = i + 1
                            break
                    self.summaries[sig_end] = (summary, body_indent)

        def _keep_decorators_and_sig(self, node):
            """Keep decorators and the full signature (possibly multi-line)."""
            start = node.lineno
            # Include decorators
            if node.decorator_list:
                start = node.decorator_list[0].lineno

            # Find end of signature (line ending with ':')
            sig_end = node.lineno
            for i in range(node.lineno - 1, min(node.end_lineno, node.lineno + 20)):
                if i < len(lines) and lines[i].rstrip().endswith(':'):
                    sig_end = i + 1
                    break

            self.intervals_to_keep.append((start, sig_end))

        def _keep_endpoint_body(self, node, body_indent=4):
            """Keep first few meaningful statements + key pattern lines from endpoint function body."""
            if not node.body:
                return

            # Skip docstring
            body_start_idx = 0
            if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                self.intervals_to_keep.append((node.body[0].lineno, node.body[0].end_lineno))
                body_start_idx = 1

            # Keep first 3 meaningful statements
            kept_count = 0
            for stmt in node.body[body_start_idx:]:
                if kept_count < 3:
                    self.intervals_to_keep.append((stmt.lineno, stmt.end_lineno))
                    kept_count += 1
                else:
                    # Check if this line matches a key pattern
                    for ln in range(stmt.lineno - 1, min(stmt.end_lineno, len(lines))):
                        if ln < len(lines):
                            for pat in KEY_PATTERNS:
                                if pat.search(lines[ln]):
                                    self.intervals_to_keep.append((stmt.lineno, stmt.end_lineno))
                                    break

            # Add summary for remaining body
            if len(node.body) > body_start_idx + 3:
                summary = _generate_body_summary(node, lines, body_indent)
                last_kept = node.body[min(body_start_idx + 2, len(node.body) - 1)]
                self.summaries[last_kept.end_lineno] = (summary, body_indent)

    visitor = SmartSkeletonizer()
    visitor.visit(tree)

    # Merge and sort intervals
    intervals = sorted(visitor.intervals_to_keep)
    merged = []
    if intervals:
        curr_start, curr_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= curr_end + 2:  # Allow small gaps
                curr_end = max(curr_end, end)
            else:
                merged.append((curr_start, curr_end))
                curr_start, curr_end = start, end
        merged.append((curr_start, curr_end))

    # Build output
    output = []
    for start, end in merged:
        for ln in range(start - 1, min(end, len(lines))):
            output.append(lines[ln])
        # Insert summary if one exists at end
        if end in visitor.summaries:
            summary_str, indent_level = visitor.summaries[end]
            output.append(summary_str)
            output.append(' ' * indent_level + 'pass')
        # Add spacing
        output.append("")

    result = "\n".join(output)

    # Verify output is valid Python
    try:
        ast.parse(result)
    except SyntaxError:
        # If invalid, add pass statements after colons
        fixed_lines = []
        for i, line in enumerate(result.splitlines()):
            fixed_lines.append(line)
            if line.rstrip().endswith(':'):
                # Check if next line is indented (body exists)
                next_lines = result.splitlines()[i+1:i+3]
                if not next_lines or (next_lines and not next_lines[0].startswith(' ')):
                    indent = len(line) - len(line.lstrip()) + 4
                    fixed_lines.append(' ' * indent + 'pass')
        result = "\n".join(fixed_lines)

    return result

def compress_generic(content: str) -> str:
    """Regex-based stripper for other languages."""
    lines = content.splitlines()
    output = []
    for line in lines:
        stripped = line.strip()
        # Keep comments, structure keywords, and openers
        if (stripped.startswith(('/', '*', '#', '-')) or 
            any(k in stripped for k in ['function', 'class', 'func', 'def', 'struct', 'pub ', 'import ']) or
            stripped.endswith('{') or stripped.endswith('}')):
            output.append(line)
    return "\n".join(output)

def compress_file_content(file_path: str, content: str) -> str:
    """
    Selects the appropriate compressor based on file extension and compresses
    the provided content.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.py':
        return compress_python(content)
    else:
        return compress_generic(content)



def process_file(source_path: Path, dest_path: Path):
    """Reads source, compresses if needed, writes to dest."""
    print(f"     - Processing: {source_path.name}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check strict filenames first (Dockerfile, etc)
    if source_path.name in COPY_FILENAMES:
        shutil.copy2(source_path, dest_path)
        return

    # Check extensions
    if source_path.suffix in COPY_EXTENSIONS:
        shutil.copy2(source_path, dest_path)
        return

    # Compress code files
    if source_path.suffix in COMPRESS_EXTENSIONS:
        try:
            with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if source_path.suffix == '.py':
                compressed = compress_python(content)
            else:
                compressed = compress_generic(content)
                
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(compressed)
        except Exception as e:
            print(f"  [Error] Could not compress {source_path.name}: {e}")
            shutil.copy2(source_path, dest_path) # Fallback

def main():
    # Allow running without args (defaults to standard repo layout)
    if len(sys.argv) < 3:
        source_dir = Path("qodeyard")
        dest_dir = Path("bloq.d")
    else:
        source_dir = Path(sys.argv[1])
        dest_dir = Path(sys.argv[2])

    if not source_dir.exists():
        print(f"Error: Source directory '{source_dir}' not found.")
        sys.exit(1)

    cycle_num = os.environ.get('CYCLE_NUM', '?')
    print(f"--- Qompressor v1.2.2: Skeletonizing {source_dir} -> {dest_dir} (Cycle {cycle_num}) ---")
    
    # G6.5: ALWAYS delete bloq.d/* before generating new skeletons
    # This ensures freshness — no stale files from previous cycles
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
        print(f"     [G6.5] Purged stale bloq.d/ (ensuring current-cycle freshness)")
    dest_dir.mkdir()

    # 2. Walk and Process
    file_count = 0
    for root, _, files in os.walk(source_dir):
        for file in files:
            source_file = Path(root) / file
            
            # Skip hidden files and .git
            if '.git' in source_file.parts or file.startswith('.'):
                continue

            rel_path = source_file.relative_to(source_dir)
            dest_file = dest_dir / rel_path
            
            process_file(source_file, dest_file)
            file_count += 1

    # G6.5: Write cycle freshness marker
    marker_path = dest_dir / ".bloq_cycle_marker"
    with open(marker_path, 'w') as f:
        f.write(f"cycle={cycle_num}\n")
            
    print(f"--- Qompressor v1.2.2: Finished. {file_count} files processed (cycle {cycle_num}). ---")

if __name__ == "__main__":
    main()
