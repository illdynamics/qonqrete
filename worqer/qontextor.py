#!/usr/bin/env python3
# worqer/qontextor.py
"""
QonQrete Qontextor - Dual-Mode Context Generator

Supports two modes based on the agent's configuration in config.yaml:
- provider: 'local' -> Pure deterministic analysis using AST and heuristics.
- provider: [ai_provider] -> Uses an LLM for semantic analysis.
"""
import sys
import os
import ast
import re
import json
import yaml
import subprocess
from pathlib import Path

# --- Local Mode Imports (Optional) ---
try:
    import jedi
    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

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

def get_embedding_model():
    """Lazy loader for the sentence transformer model."""
    global embedding_model
    if embedding_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        print("  - Loading semantic analysis model (once)...", flush=True)
        # Uses a cached model, downloads on first run
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return embedding_model

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
    signature: str
    purpose: str
    dependencies: List[str] = field(default_factory=list)
    embedding: Optional[Any] = None # Stores numpy array from sentence-transformer

    def to_dict(self) -> dict:
        data = {
            'name': self.name,
            'type': self.type,
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
            self.symbols.append(Symbol(name=name, type='import', signature=f"import {alias.name}", purpose=f"Imports the {alias.name} library."))

    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.symbols.append(Symbol(name=name, type='import', signature=f"from {module} import {alias.name}", purpose=f"Imports {alias.name} from {module}."))

    def visit_ClassDef(self, node):
        doc = ast.get_docstring(node)
        purpose = extract_first_sentence(doc) if doc else infer_purpose_from_name(node.name, 'class')[0]
        self.symbols.append(Symbol(name=node.name, type='class', signature=self._get_sig(node), purpose=purpose, dependencies=[b.id for b in node.bases if isinstance(b, ast.Name)]))
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
        self.symbols.append(Symbol(name=node.name, type=stype, signature=self._get_sig(node), purpose=purpose))

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

def generate_context_local(file_path: Path, local_mode: str) -> FileContext:
    ext = file_path.suffix.lower()
    content = file_path.read_text(errors='ignore')

    if ext != '.py':
        if ext in DOCS_EXTENSIONS: return FileContext(str(file_path), summary=extract_first_sentence(content))
        return FileContext(str(file_path), summary=f"Configuration file: {file_path.name}")

    extractor = SymbolExtractor(content)
    try:
        tree = ast.parse(content)
        extractor.visit(tree)
        
        # --- Semantic Enhancement (Complex Mode) ---
        if local_mode == 'complex':
            model = get_embedding_model()
            if model:
                purposes = [sym.purpose for sym in extractor.symbols if sym.purpose]
                if purposes:
                    embeddings = model.encode(purposes)
                    # Map embeddings back to the symbols that had purposes
                    emb_idx = 0
                    for sym in extractor.symbols:
                        if sym.purpose:
                            sym.embedding = embeddings[emb_idx]
                            emb_idx += 1
        
        return FileContext(file_path=str(file_path), symbols=extractor.symbols)
    except Exception as e:
        return FileContext(str(file_path), error=f"AST Parse Error: {e}")


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

    print(f"  - Generating qontext for: {relative_path} (Mode: {provider}, Detail: {local_mode})", flush=True)

    if provider == 'local':
        context = generate_context_local(file_path, local_mode)
        yaml_content = yaml.dump(context.to_dict(), sort_keys=False, default_flow_style=False, indent=2)
    else:
        file_type = get_file_type(file_path)
        yaml_content = generate_qontext_ai(file_path, provider, model, file_type)

    with open(qontext_file, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

def run_initial_scan(qodeyard_path: Path, qontext_path: Path, config: dict):
    print(f"--- Qontextor: Starting initial scan of {qodeyard_path} ---", flush=True)
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
    if len(sys.argv) != 3:
        print("Usage: qontextor.py <input_path> <output_path>", flush=True)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"

    config = get_qontextor_config()

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
