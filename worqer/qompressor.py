#!/usr/bin/env python3
# worqer/qompressor.py
"""
The 'Skeletonizer' for QonQrete.
Mirrors qodeyard into bloq.d, stripping code bodies but keeping architecture.
FAST. ZERO TOKEN COST.
"""
import sys
import os
import ast
import shutil
from pathlib import Path

# --- Configuration ---
# Files to 'Skeletonize' (Strip bodies, keep signatures)
COMPRESS_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp', '.php'}

# Files to copy 'As-Is' (Context is critical, usually low token count)
COPY_EXTENSIONS = {'.yaml', '.yml', '.json', '.md', '.txt', '.toml'}
COPY_FILENAMES  = {'Dockerfile', 'Makefile', 'Jenkinsfile', 'docker-compose.yml'}

def compress_python(content: str) -> str:
    """Uses AST to strip Python function bodies."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return compress_generic(content)

    lines = content.splitlines()
    kept_intervals = []

    class Skeletonizer(ast.NodeVisitor):
        def visit_Import(self, node):
            kept_intervals.append((node.lineno, node.end_lineno))
        def visit_ImportFrom(self, node):
            kept_intervals.append((node.lineno, node.end_lineno))
        def visit_ClassDef(self, node):
            self._keep_signature(node)
            self._keep_docstring(node)
            self.generic_visit(node)
        def visit_FunctionDef(self, node):
            self._process_func(node)
        def visit_AsyncFunctionDef(self, node):
            self._process_func(node)
        
        def _process_func(self, node):
            self._keep_signature(node)
            self._keep_docstring(node)
        
        def _keep_signature(self, node):
            start = node.lineno
            # Heuristic: Keep lines until we see a colon
            # This handles multi-line decorators and arguments
            for i in range(start - 1, min(node.end_lineno, start + 20)):
                if i < len(lines) and lines[i].strip().endswith(':'):
                    kept_intervals.append((start, i + 1))
                    return
            kept_intervals.append((start, start))

        def _keep_docstring(self, node):
            if (node.body and isinstance(node.body[0], ast.Expr) and 
                isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                doc_node = node.body[0]
                kept_intervals.append((doc_node.lineno, doc_node.end_lineno))

    visitor = Skeletonizer()
    visitor.visit(tree)
    
    # Merge intervals
    kept_intervals.sort()
    merged = []
    if kept_intervals:
        curr_start, curr_end = kept_intervals[0]
        for start, end in kept_intervals[1:]:
            if start <= curr_end + 1:
                curr_end = max(curr_end, end)
            else:
                merged.append((curr_start, curr_end))
                curr_start, curr_end = start, end
        merged.append((curr_start, curr_end))

    output = []
    for start, end in merged:
        output.extend(lines[start-1:end])
        # Add visual indicator for stripped bodies
        if end < len(lines) and lines[end-1].strip().endswith(':'):
            output.append("    # ... (body stripped by Qompressor) ...")
            
    return "\n".join(output)

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

    print(f"--- Qompressor: Skeletonizing {source_dir} -> {dest_dir} ---")
    
    # 1. Clean destination (Fresh start ensures deleted files are removed)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
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
            
    print(f"--- Qompressor: Finished. {file_count} files processed. ---")

if __name__ == "__main__":
    main()
