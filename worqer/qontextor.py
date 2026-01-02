#!/usr/bin/env python3
# worqer/qontextor.py
"""
QonQrete Qontextor - Dual-Mode Context Generator

Supports two modes based on the agent's configuration in config.yaml:
- provider: 'local' -> Pure deterministic analysis using AST and heuristics.
- provider: [ai_provider] -> Uses an LLM for semantic analysis.

v1.0.1 Fix: Proper HuggingFace cache handling for Docker hardened environments.
"""
import sys
import os
import ast
import re
import json
import yaml
import subprocess
import argparse
from pathlib import Path

# =============================================================================
# v1.0.1 FIX: Set HuggingFace environment variables before imports
# =============================================================================
# These must be set BEFORE importing sentence_transformers or transformers
# to ensure the pre-downloaded model in /opt/hf_cache is used
if os.path.isdir('/opt/hf_cache'):
    os.environ.setdefault('HF_HOME', '/opt/hf_cache')
    os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', '/opt/hf_cache')
    os.environ.setdefault('TRANSFORMERS_CACHE', '/opt/hf_cache')

# --- Local Mode Imports (Optional) ---
try:
    import jedi
    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    np = None

# --- AI Mode Imports (Optional) ---
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lib_ai
    import qompressor
    AI_MODE_AVAILABLE = True
except ImportError:
    AI_MODE_AVAILABLE = False
    lib_ai = None
    qompressor = None

# --- Globals for Complex Mode ---
embedding_model = None
call_graph = None
semantic_index = None  # Stores (file_path, symbol_name, purpose, embedding) tuples

def get_embedding_model():
    """
    Lazy loader for the sentence transformer model.
    
    v1.0.1 Fix: Improved error handling and cache directory detection.
    Falls back gracefully if model loading fails (e.g., permission issues).
    """
    global embedding_model
    if embedding_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            # Check if pre-downloaded model exists in /opt/hf_cache
            cache_dir = os.environ.get('SENTENCE_TRANSFORMERS_HOME', '/opt/hf_cache')
            if os.path.isdir(cache_dir):
                print(f"  - Loading semantic model from cache ({cache_dir})...", flush=True)
            else:
                print("  - Loading semantic analysis model (first run may download)...", flush=True)
            
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("  - Semantic model loaded successfully.", flush=True)
        except PermissionError as e:
            # v1.0.1 Fix: Catch permission errors explicitly
            print(f"  - [WARN] Model loading failed (PermissionError): {e}", flush=True)
            print("  - [WARN] Falling back to AST-only analysis (no semantic embeddings).", flush=True)
            embedding_model = False  # Mark as "tried and failed"
        except Exception as e:
            # Catch any other errors (network, disk space, etc.)
            print(f"  - [WARN] Model loading failed: {e}", flush=True)
            print("  - [WARN] Falling back to AST-only analysis (no semantic embeddings).", flush=True)
            embedding_model = False  # Mark as "tried and failed"
    
    # Return None if model loading failed (embedding_model == False)
    return embedding_model if embedding_model else None

def build_semantic_index(qontext_dir: Path) -> list:
    """
    Builds a semantic index from all .q.yaml files for similarity queries.
    Returns list of (file_path, symbol_name, purpose, embedding) tuples.
    """
    global semantic_index
    if semantic_index is not None:
        return semantic_index
    
    semantic_index = []
    if not qontext_dir.exists():
        return semantic_index
    
    for yaml_file in qontext_dir.rglob("*.q.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not data or 'symbols' not in data:
                continue
            
            file_path = data.get('file_path', str(yaml_file))
            for sym in data.get('symbols', []):
                if 'embedding' in sym and sym['embedding']:
                    import numpy as np
                    embedding = np.array(sym['embedding'])
                    semantic_index.append((
                        file_path,
                        sym.get('name', 'unknown'),
                        sym.get('purpose', ''),
                        embedding
                    ))
        except Exception as e:
            print(f"  - [WARN] Failed to load {yaml_file}: {e}", flush=True)
    
    print(f"  - Built semantic index with {len(semantic_index)} symbols", flush=True)
    return semantic_index

def find_similar_symbols(query: str, qontext_dir: Path, top_k: int = 5) -> list:
    """
    Finds symbols semantically similar to a query string.
    Returns list of (file_path, symbol_name, purpose, similarity_score) tuples.
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        print("  - [WARN] sentence-transformers not available for semantic search", flush=True)
        return []
    
    model = get_embedding_model()
    if not model:
        return []
    
    index = build_semantic_index(qontext_dir)
    if not index:
        return []
    
    import numpy as np
    query_embedding = model.encode(query)
    
    similarities = []
    for file_path, sym_name, purpose, embedding in index:
        # Cosine similarity
        similarity = np.dot(query_embedding, embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(embedding)
        )
        similarities.append((file_path, sym_name, purpose, float(similarity)))
    
    # Sort by similarity descending
    similarities.sort(key=lambda x: x[3], reverse=True)
    return similarities[:top_k]

def find_related_by_verb(verb_pattern: str, qontext_dir: Path) -> list:
    """
    Finds all symbols that match a specific verb pattern.
    Useful for understanding all "get_*", "create_*" etc. functions.
    """
    results = []
    if not qontext_dir.exists():
        return results
    
    for yaml_file in qontext_dir.rglob("*.q.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not data or 'symbols' not in data:
                continue
            
            file_path = data.get('file_path', str(yaml_file))
            for sym in data.get('symbols', []):
                name = sym.get('name', '')
                if re.match(verb_pattern, name, re.IGNORECASE):
                    results.append({
                        'file': file_path,
                        'name': name,
                        'type': sym.get('type', 'unknown'),
                        'purpose': sym.get('purpose', ''),
                        'dependencies': sym.get('dependencies', [])
                    })
        except Exception:
            pass
    
    return results

def analyze_ripple_effect(symbol_name: str, qontext_dir: Path) -> dict:
    """
    Analyzes the "ripple effect" - what other parts of the codebase would be 
    affected if a given symbol is changed. Uses the call graph from PyCG.
    
    Returns:
        {
            'symbol': name,
            'file': file where symbol is defined,
            'called_by': list of symbols that call this one,
            'calls': list of symbols this one calls,
            'depth_1_impact': files that directly use this symbol,
            'depth_2_impact': files indirectly affected
        }
    """
    result = {
        'symbol': symbol_name,
        'file': None,
        'called_by': [],
        'calls': [],
        'depth_1_impact': set(),
        'depth_2_impact': set()
    }
    
    if not qontext_dir.exists():
        return result
    
    # Build a reverse lookup from the call graph data in .q.yaml files
    reverse_graph = {}  # symbol -> list of callers
    forward_graph = {}  # symbol -> list of callees (from dependencies)
    symbol_to_file = {}
    
    for yaml_file in qontext_dir.rglob("*.q.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not data or 'symbols' not in data:
                continue
            
            file_path = data.get('file_path', str(yaml_file))
            for sym in data.get('symbols', []):
                name = sym.get('name', '')
                full_name = f"{Path(file_path).stem}.{name}"
                
                symbol_to_file[name] = file_path
                symbol_to_file[full_name] = file_path
                
                deps = sym.get('dependencies', [])
                forward_graph[name] = deps
                forward_graph[full_name] = deps
                
                # Build reverse graph
                for dep in deps:
                    if dep not in reverse_graph:
                        reverse_graph[dep] = []
                    reverse_graph[dep].append(name)
                    
                    # Also add short name version
                    dep_short = dep.split('.')[-1] if '.' in dep else dep
                    if dep_short not in reverse_graph:
                        reverse_graph[dep_short] = []
                    if name not in reverse_graph[dep_short]:
                        reverse_graph[dep_short].append(name)
        except Exception:
            pass
    
    # Find the symbol
    if symbol_name in symbol_to_file:
        result['file'] = symbol_to_file[symbol_name]
    
    # Find what calls this symbol (reverse lookup)
    if symbol_name in reverse_graph:
        result['called_by'] = reverse_graph[symbol_name]
        for caller in result['called_by']:
            if caller in symbol_to_file:
                result['depth_1_impact'].add(symbol_to_file[caller])
    
    # Find what this symbol calls (forward lookup)
    if symbol_name in forward_graph:
        result['calls'] = forward_graph[symbol_name]
    
    # Depth 2 - what calls the things that call us
    for caller in result['called_by']:
        if caller in reverse_graph:
            for indirect_caller in reverse_graph[caller]:
                if indirect_caller in symbol_to_file:
                    result['depth_2_impact'].add(symbol_to_file[indirect_caller])
    
    # Remove depth_1 from depth_2 to avoid duplicates
    result['depth_2_impact'] -= result['depth_1_impact']
    
    # Convert sets to lists for JSON/YAML serialization
    result['depth_1_impact'] = list(result['depth_1_impact'])
    result['depth_2_impact'] = list(result['depth_2_impact'])
    
    return result

def get_call_graph(directory: Path):
    """Generates and caches the call graph for the entire project.
    
    Note: pycg package is broken on PyPI (module name mismatch).
    This function silently returns empty dict, relying on jedi for dependency analysis.
    """
    global call_graph
    if call_graph is None:
        # pycg is broken on PyPI - module name mismatch prevents import
        # Silently use empty call graph; jedi provides dependency analysis instead
        call_graph = {}
    return call_graph


# --- Configuration & Constants ---

CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.h', '.cpp', '.cs', '.rb', '.php',
    '.html', '.css', '.scss', '.sql'
}
CONFIG_EXTENSIONS = {
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.xml'
}
DOCS_EXTENSIONS = {
    '.md', '.txt', '.rst'
}
SPECIAL_FILENAMES = {
    'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.gitignore', '.dockerignore',
    'Makefile', 'Jenkinsfile', 'Vagrantfile'
}

# --- Data Structures for Local Mode ---
from dataclasses import dataclass, field
from typing import Optional, List, Any

@dataclass
class Symbol:
    name: str
    type: str
    line: int
    signature: str
    purpose: str
    dependencies: List[str] = field(default_factory=list)
    embedding: Optional[Any] = None # Stores numpy array from sentence-transformer

    def to_dict(self) -> dict:
        data = {
            'name': self.name,
            'type': self.type,
            'line': self.line,
            'signature': self.signature,
            'purpose': self.purpose,
            'dependencies': self.dependencies,
        }
        # Serialize embedding to a list for YAML compatibility
        if self.embedding is not None:
            data['embedding'] = self.embedding.tolist()
        return data

@dataclass
class FileContext:
    file_path: str
    symbols: List[Symbol] = field(default_factory=list)
    summary: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        if self.error: return {'file_path': self.file_path, 'error': self.error}
        if self.summary: return {'file_path': self.file_path, 'summary': self.summary}
        return {'file_path': self.file_path, 'symbols': [s.to_dict() for s in self.symbols]}

# --- Local Mode Logic ---

VERB_PATTERNS = {
    r'^(get|fetch|load|read|retrieve|find|lookup|query|select|obtain|pull)': 'Retrieves',
    r'^(set|update|modify|patch|change|alter|edit|adjust|revise)': 'Updates',
    r'^(is|has|can|should|will|does|check|verify|validate|test|assert|ensure)': 'Checks',
    r'^(create|make|build|generate|new|init|initialize|construct|spawn)': 'Creates',
    r'^(delete|remove|destroy|drop|clear|purge|erase|wipe|discard)': 'Removes',
    r'^(parse|convert|transform|translate|map|decode|encode|serialize)': 'Transforms',
    r'^(send|emit|dispatch|publish|broadcast|notify|post|transmit|push)': 'Sends',
    r'^(receive|handle|process|consume|accept|on_|listen|respond|react)': 'Handles',
    r'^(save|store|persist|write|commit|flush|dump|export|backup)': 'Saves',
    r'^(render|display|show|draw|present|format|print|output|visualize)': 'Renders',
    r'^(start|begin|open|launch|run|execute|invoke|trigger|activate)': 'Starts',
    r'^(stop|end|close|terminate|shutdown|halt|abort|kill|finish)': 'Stops',
    r'^(add|append|insert|push|enqueue|register|attach|include)': 'Adds',
    r'^(pop|dequeue|unregister|detach|exclude|omit)': 'Removes from',
    r'^(count|measure|calculate|compute|sum|avg|total|aggregate|tally)': 'Calculates',
}
SPECIAL_METHODS = {
    '__init__': 'Initializes a new instance',
    '__str__': 'Returns string representation',
    '__repr__': 'Returns detailed string representation for debugging',
    '__len__': 'Returns the length or size',
    '__iter__': 'Returns an iterator for the object',
    '__getitem__': 'Gets item by key or index',
}

class SymbolExtractor(ast.NodeVisitor):
    def __init__(self, source_code: str):
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.current_class: Optional[str] = None

    def _get_sig(self, node):
        start = node.lineno - 1
        for i in range(start, min(node.end_lineno, start + 20)):
            if self.lines[i].strip().endswith(':'):
                sig_full = " ".join(self.lines[start:i+1]).strip()
                return sig_full.replace('def ', '').replace('class ', '').rstrip(':')
        return self.lines[start].strip()

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.symbols.append(Symbol(name=name, type='import', line=node.lineno, signature=f"import {alias.name}", purpose=f"Imports the {alias.name} library."))

    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.symbols.append(Symbol(name=name, type='import', line=node.lineno, signature=f"from {module} import {alias.name}", purpose=f"Imports {alias.name} from {module}."))

    def visit_ClassDef(self, node):
        doc = ast.get_docstring(node)
        purpose = extract_first_sentence(doc) if doc else infer_purpose_from_name(node.name, 'class')[0]
        self.symbols.append(Symbol(name=node.name, type='class', line=node.lineno, signature=self._get_sig(node), purpose=purpose, dependencies=[b.id for b in node.bases if isinstance(b, ast.Name)]))
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        self._process_func(node, "method" if self.current_class else "function")

    def visit_AsyncFunctionDef(self, node):
        self._process_func(node, "method" if self.current_class else "function")

    def _process_func(self, node, stype):
        doc = ast.get_docstring(node)
        purpose = extract_first_sentence(doc) if doc else infer_purpose_from_name(node.name, stype)[0]
        self.symbols.append(Symbol(name=node.name, type=stype, line=node.lineno, signature=self._get_sig(node), purpose=purpose))

def infer_purpose_from_name(name: str, stype: str) -> tuple:
    if name in SPECIAL_METHODS: return SPECIAL_METHODS[name], 0.95
    words = [w.lower() for w in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]| )', name)]
    if not words: return f"Defines {name}.", 0.3
    verb = words[0]
    for pattern, action in VERB_PATTERNS.items():
        if re.match(pattern, verb):
            return f"{action} {' '.join(words[1:])}.", 0.7
    return f"Logic for {name}.", 0.4

def extract_first_sentence(text: str) -> str:
    if not text: return ""
    match = re.split(r'(?<=[.!?])\s+', text.strip())
    return match[0] if match else text.strip()

def path_to_module_str(base_path: Path, file_path: Path) -> str:
    """Converts a file path to a python module string."""
    try:
        relative_path = file_path.relative_to(base_path)
        return str(relative_path.with_suffix('')).replace(os.path.sep, '.')
    except ValueError:
        # If the file_path is not inside the base_path, handle it gracefully.
        # This can happen with external libraries.
        return file_path.stem

def generate_context_local(file_path: Path, local_mode: str, project_path: Path) -> FileContext:
    """
    Generate context for a file using local analysis (AST, Jedi, embeddings).
    
    v1.0.1 Fix: Improved error handling to distinguish between:
    - AST parse errors (syntax issues in source file)
    - Model loading errors (handled gracefully, continues without embeddings)
    """
    ext = file_path.suffix.lower()
    content = file_path.read_text(errors='ignore')

    if ext != '.py':
        if ext in DOCS_EXTENSIONS: return FileContext(str(file_path), summary=extract_first_sentence(content))
        return FileContext(str(file_path), summary=f"Configuration file: {file_path.name}")

    extractor = SymbolExtractor(content)
    try:
        tree = ast.parse(content)
        extractor.visit(tree)
        
        # --- Call Graph Analysis (pycg) ---
        cg = get_call_graph(project_path)
        if cg:
            module_str = path_to_module_str(project_path, file_path)
            for sym in extractor.symbols:
                key = f"{module_str}.{sym.name}"
                if key in cg:
                    # Make sure dependencies are unique
                    sym.dependencies = sorted(list(set(sym.dependencies + cg[key])))

        # --- Jedi Enhancement ---
        if JEDI_AVAILABLE:
            script = jedi.Script(code=content, path=str(file_path))
            for sym in extractor.symbols:
                if sym.type in ("function", "method"):
                    try:
                        definitions = script.infer(line=sym.line, column=len(sym.name))
                        for definition in definitions:
                            if definition.module_path and definition.module_path != file_path:
                                dep_str = f"{path_to_module_str(project_path, definition.module_path)}.{definition.name}"
                                if dep_str not in sym.dependencies:
                                    sym.dependencies.append(dep_str)
                    except Exception as e:
                        # Jedi can fail on complex code, so we ignore errors
                        # print(f"  - [WARN] Jedi failed for {sym.name}: {e}", flush=True)
                        pass
        
        # --- Semantic Enhancement (Complex Mode) ---
        # v1.0.1 Fix: Model loading errors are now handled in get_embedding_model()
        # and won't cause the entire file analysis to fail
        if local_mode == 'complex':
            model = get_embedding_model()
            if model:
                purposes = [sym.purpose for sym in extractor.symbols if sym.purpose]
                if purposes:
                    try:
                        embeddings = model.encode(purposes)
                        # Map embeddings back to the symbols that had purposes
                        emb_idx = 0
                        for sym in extractor.symbols:
                            if sym.purpose:
                                sym.embedding = embeddings[emb_idx]
                                emb_idx += 1
                    except Exception as e:
                        # If encoding fails, continue without embeddings
                        print(f"  - [WARN] Embedding generation failed: {e}", flush=True)
        
        return FileContext(file_path=str(file_path), symbols=extractor.symbols)
    
    except SyntaxError as e:
        # Actual AST/syntax error in the source file
        return FileContext(str(file_path), error=f"AST Parse Error (SyntaxError): {e}")
    except Exception as e:
        # Other errors during AST parsing
        error_type = type(e).__name__
        return FileContext(str(file_path), error=f"Analysis Error ({error_type}): {e}")


# --- AI Mode Logic ---

def generate_qontext_ai(file_path: Path, provider: str, model: str, file_type: str) -> str:
    if not AI_MODE_AVAILABLE:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'AI mode dependencies (lib_ai, qompressor) are not installed.'"

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content_to_send = qompressor.compress_file_content(str(file_path), content) if file_type == 'code' else content
    if len(content_to_send) > 100000:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'File is too large to analyze.'"

    if file_type == 'code':
        prompt = f"""
Analyze the following 'qompressed' source code file and generate a YAML structure representing its context. The file has had its implementation bodies stripped, but retains all signatures, docstrings, comments, and imports.

**File Path:** {file_path.as_posix()}
**Qompressed File Content:**
```
{content_to_send}
```

**YAML Structure Rules:**
1.  The root object must have a `file_path` key.
2.  It must have a `symbols` key, which is a list of objects.
3.  Each object in `symbols` represents a class, function, or other significant code construct.
4.  Each symbol object must have:
    - `name`: The name of the function or class.
    - `type`: The type of the symbol (e.g., 'function', 'class', 'method', 'variable', 'import').
    - `signature`: The full signature (e.g., `(self, user_id: int) -> dict`). For imports, this can be the imported module or alias.
    - `purpose`: A concise, one-sentence summary of what the symbol does.
    - `dependencies`: A list of other functions or classes this symbol directly calls or references.
**Generate the YAML for the file provided above:**
"""
    else: # doc, config, other
        prompt = f"""
Analyze the following file and generate a YAML structure that summarizes its purpose.

**File Path:** {file_path.as_posix()}
**File Content:**
```
{content_to_send}
```

**YAML Structure Rules:**
1. The root object must have a `file_path` key.
2. It must have a `summary` key.
3. The `summary` should be a concise, one to three-sentence description of the document's main purpose.
**Generate the YAML for the file provided above:**
"""
    try:
        raw_result = lib_ai.run_ai_completion(provider, model, prompt)
        yaml_match = re.search(r'```yaml\n(.*?)\n```', raw_result, re.DOTALL)
        return yaml_match.group(1) if yaml_match else raw_result
    except Exception as e:
        return f"file_path: {str(file_path.as_posix())}\nerror: 'Failed to generate context due to an AI error: {e}'"

# --- Orchestration Logic ---

def get_qontextor_config():
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    return config.get('agents', {}).get('qontextor', {})

def get_file_type(file_path: Path) -> str:
    if file_path.suffix in CODE_EXTENSIONS or file_path.name in SPECIAL_FILENAMES: return 'code'
    if file_path.suffix in DOCS_EXTENSIONS: return 'doc'
    if file_path.suffix in CONFIG_EXTENSIONS: return 'config'
    return 'unknown'

def should_process_file(file_path: Path) -> bool:
    return get_file_type(file_path) != 'unknown'

def process_file(qodeyard_path: Path, file_path: Path, qontext_path: Path, config: dict):
    relative_path = file_path.relative_to(qodeyard_path)
    qontext_file = qontext_path / f"{relative_path}.q.yaml"
    qontext_file.parent.mkdir(parents=True, exist_ok=True)

    provider = config.get('provider', 'local')
    model = config.get('model', 'qontextor')
    local_mode = config.get('local_mode', 'complex')

    print(f"     - Qontextualizing: {relative_path} (Mode: {provider}, Detail: {local_mode})", flush=True)

    if provider == 'local':
        context = generate_context_local(file_path, local_mode, qodeyard_path)
        yaml_content = yaml.dump(context.to_dict(), sort_keys=False, default_flow_style=False, indent=2)
    else:
        file_type = get_file_type(file_path)
        yaml_content = generate_qontext_ai(file_path, provider, model, file_type)

    with open(qontext_file, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

def run_initial_scan(qodeyard_path: Path, qontext_path: Path, config: dict):
    print(f"--- Qontextor: Starting initial scan of {qodeyard_path} ---", flush=True)
    get_call_graph(qodeyard_path)
    for root, _, files in os.walk(qodeyard_path):
        for file in files:
            file_path = Path(root) / file
            if should_process_file(file_path):
                relative_path = file_path.relative_to(qodeyard_path)
                qontext_file = qontext_path / f"{relative_path}.q.yaml"
                if not qontext_file.exists():
                    process_file(qodeyard_path, file_path, qontext_path, config)
    print("--- Qontextor: Initial scan complete ---", flush=True)

def run_update_scan(summary_path: Path, qodeyard_path: Path, qontext_path: Path, config: dict):
    print(f"--- Qontextor: Starting update scan based on {summary_path.name} ---", flush=True)
    if not summary_path.exists():
        print("  - Summary file not found. Nothing to update.", flush=True)
        return

    get_call_graph(qodeyard_path)

    with open(summary_path, 'r', encoding='utf-8') as f:
        summary_content = f.read()
    changed_files = re.findall(r'`([^`]+)`', summary_content)
    if not changed_files:
        print("  - No changed files found in summary. Nothing to update.", flush=True)
        return

    processed_files = set()
    for file_str in changed_files:
        file_path = Path(file_str)
        if file_path.is_absolute():
            try:
                file_path = qodeyard_path / file_path.relative_to(qodeyard_path)
            except ValueError:
                print(f"  - [WARN] Changed file '{file_str}' is outside the qodeyard. Skipping.", flush=True)
                continue
        else:
             file_path = qodeyard_path / file_str

        if file_path in processed_files: continue
        processed_files.add(file_path)

        if file_path.exists() and should_process_file(file_path):
            process_file(qodeyard_path, file_path, qontext_path, config)
        else:
            print(f"  - [INFO] Changed file '{file_str}' does not exist or is not processable. Skipping.", flush=True)
    print("--- Qontextor: Update scan complete ---", flush=True)

def main():
    parser = argparse.ArgumentParser(description="Qontextor - Code Context Generator and Querier")
    parser.add_argument("input_path", nargs='?', help="The source directory (qodeyard) or summary file for updates.")
    parser.add_argument("output_path", nargs='?', help="The destination for context files (qontext.d).")
    parser.add_argument("--query", help="Perform a semantic search for a given term.")
    parser.add_argument("--verb", help="Find symbols matching a verb pattern (e.g., 'get_.*').")
    parser.add_argument("--ripple", help="Analyze the ripple effect of changing a symbol.")

    args = parser.parse_args()

    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qontext_path = worqspace_root / "qontext.d"
    
    print(f"  - Qontextor running in: {worqspace_root}", flush=True)

    config = get_qontextor_config()
    
    # Ensure qontext_path exists for query operations
    qontext_path.mkdir(exist_ok=True)

    # If qontext is empty, run an initial scan first
    if not any(qontext_path.iterdir()) and (args.query or args.verb or args.ripple):
        print("  - [INFO] Qontext directory is empty. Running initial scan...", flush=True)
        if qodeyard_path.exists():
            run_initial_scan(qodeyard_path, qontext_path, config)
        else:
            print("  - [ERROR] qodeyard not found. Cannot build context.", flush=True)
            sys.exit(1)

    # --- Query Modes ---
    if args.query:
        print(f"--- Semantic Search: '{args.query}' ---", flush=True)
        results = find_similar_symbols(args.query, qontext_path, top_k=10)
        
        if not results:
            print("No results found. Ensure qontext.d was built in 'complex' mode.", flush=True)
        else:
            for file_path, sym_name, purpose, score in results:
                print(f"  [{score:.3f}] {sym_name} ({Path(file_path).name})", flush=True)
                print(f"          → {purpose}", flush=True)
        sys.exit(0)
    
    if args.verb:
        print(f"--- Verb Pattern Search: '{args.verb}' ---", flush=True)
        results = find_related_by_verb(args.verb, qontext_path)
        
        if not results:
            print("No results found.", flush=True)
        else:
            for item in results:
                print(f"  {item['name']} ({item['type']}) - {Path(item['file']).name}", flush=True)
                print(f"      → {item['purpose']}", flush=True)
                if item['dependencies']:
                    print(f"      ⤷ deps: {', '.join(item['dependencies'][:3])}{'...' if len(item['dependencies']) > 3 else ''}", flush=True)
        sys.exit(0)

    if args.ripple:
        print(f"--- Ripple Effect Analysis: '{args.ripple}' ---", flush=True)
        result = analyze_ripple_effect(args.ripple, qontext_path)
        
        print(f"\n  Symbol: {result['symbol']}", flush=True)
        if result['file']:
            print(f"  Defined in: {Path(result['file']).name}", flush=True)
        
        if result['calls']:
            print(f"\n  ↳ CALLS ({len(result['calls'])}):", flush=True)
            for dep in result['calls'][:10]:
                print(f"      → {dep}", flush=True)
            if len(result['calls']) > 10: print(f"      ... and {len(result['calls']) - 10} more", flush=True)
        
        if result['called_by']:
            print(f"\n  ↰ CALLED BY ({len(result['called_by'])}):", flush=True)
            for caller in result['called_by'][:10]:
                print(f"      ← {caller}", flush=True)
            if len(result['called_by']) > 10: print(f"      ... and {len(result['called_by']) - 10} more", flush=True)
        
        if result['depth_1_impact']:
            print(f"\n  ⚡ DIRECT IMPACT ({len(result['depth_1_impact'])} files):", flush=True)
            for f in result['depth_1_impact'][:5]: print(f"      • {Path(f).name}", flush=True)
            if len(result['depth_1_impact']) > 5: print(f"      ... and {len(result['depth_1_impact']) - 5} more files", flush=True)
        
        if result['depth_2_impact']:
            print(f"\n  ⚡⚡ INDIRECT IMPACT ({len(result['depth_2_impact'])} files):", flush=True)
            for f in result['depth_2_impact'][:5]: print(f"      • {Path(f).name}", flush=True)
            if len(result['depth_2_impact']) > 5: print(f"      ... and {len(result['depth_2_impact']) - 5} more files", flush=True)
        
        total_impact = len(result['depth_1_impact']) + len(result['depth_2_impact'])
        print(f"\n  🔥 TOTAL RIPPLE: {total_impact} files potentially affected!" if total_impact > 0 else "\n  ✅ No ripple effect detected.")
        sys.exit(0)

    # --- Standard Generation Mode ---
    if not args.input_path or not args.output_path:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    if not input_path.exists():
        print(f"CRITICAL: Input path does not exist: {input_path}", flush=True)
        sys.exit(1)

    if input_path.is_dir():
        run_initial_scan(qodeyard_path=input_path, qontext_path=output_path, config=config)
    elif input_path.is_file():
        run_update_scan(summary_path=input_path, qodeyard_path=qodeyard_path, qontext_path=output_path, config=config)
    else:
        print(f"CRITICAL: Input path is not a file or directory: {input_path}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
