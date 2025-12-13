#!/usr/bin/env python3
# worqer/qontextor.py
import sys
import os
import yaml
import re
from pathlib import Path

# Add lib_ai to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lib_ai
    import qompressor
except ImportError:
    print("CRITICAL: lib_ai.py or qompressor.py not found.", flush=True)
    sys.exit(1)

# List of file extensions to process
# TODO: Make this configurable
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

def get_ai_config():
    """Loads agent configuration from config.yaml."""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    
    agent_cfg = config.get('agents', {}).get('qontextor', {})
    provider = agent_cfg.get('provider', 'gemini')
    model = agent_cfg.get('model', 'gemini-2.5-flash')
    return provider, model

def generate_qontext_for_file(file_path: Path, provider: str, model: str) -> str:
    """Generates the YAML qontext for a single file using an AI call."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Compress the content before sending it to the AI
    compressed_content = qompressor.compress_file_content(str(file_path), content)

    # Simple heuristic to avoid sending massive files to the AI
    if len(compressed_content) > 100000:
        return f"""
file_path: {str(file_path.as_posix())}
error: "File is too large to analyze even after compression."
"""

    prompt = f"""
Analyze the following 'qompressed' source code file and generate a YAML structure representing its context. The file has had its implementation bodies stripped, but retains all signatures, docstrings, comments, and imports.

**File Path:** {file_path.as_posix()}
**Qompressed File Content:**
```
{compressed_content}
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

**Example Output:**
```yaml
file_path: src/api/user.py
symbols:
  - name: flask
    type: import
    signature: "from flask import Flask"
    purpose: "Imports the main Flask framework class."
    dependencies: []
  - name: get_user
    type: function
    signature: "(user_id: int) -> dict"
    purpose: "Retrieves a user from the database by their ID."
    dependencies:
      - "db.get_connection"
      - "User.serialize"
  - name: User
    type: class
    signature: "class User(db.Model):"
    purpose: "Represents the User data model."
    dependencies:
      - "db.Model"
```

**Generate the YAML for the file provided above:**
"""
    try:
        raw_result = lib_ai.run_ai_completion(provider, model, prompt)
        # Clean the AI output to get only the YAML block
        yaml_match = re.search(r'```yaml\n(.*?)\n```', raw_result, re.DOTALL)
        if yaml_match:
            return yaml_match.group(1)
        # Fallback for when AI doesn't use markdown
        return raw_result

    except Exception as e:
        return f"""
file_path: {str(file_path.as_posix())}
error: "Failed to generate context due to an AI error: {e}"
"""

def should_process_file(file_path: Path) -> bool:
    """Determines if a file should be processed based on its extension or name."""
    return (
        file_path.suffix in CODE_EXTENSIONS or
        file_path.suffix in CONFIG_EXTENSIONS or
        file_path.suffix in DOCS_EXTENSIONS or
        file_path.name in SPECIAL_FILENAMES
    )

def process_file(qodeyard_path: Path, file_path: Path, qontext_path: Path, provider: str, model: str):
    """Processes a single file: generates qontext and saves it."""
    relative_path = file_path.relative_to(qodeyard_path)
    qontext_file = qontext_path / f"{relative_path}.q.yaml"
    
    # Create parent directories for the qontext file
    qontext_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  - Generating qontext for: {relative_path}", flush=True)
    yaml_content = generate_qontext_for_file(file_path, provider, model)
    
    with open(qontext_file, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

def run_initial_scan(qodeyard_path: Path, qontext_path: Path, provider: str, model: str):
    """Scans the entire qodeyard and generates qontext for all files."""
    print(f"--- Qontextor: Starting initial scan of {qodeyard_path} ---", flush=True)
    
    for root, _, files in os.walk(qodeyard_path):
        for file in files:
            file_path = Path(root) / file
            if should_process_file(file_path):
                # Check if qontext already exists
                relative_path = file_path.relative_to(qodeyard_path)
                qontext_file = qontext_path / f"{relative_path}.q.yaml"
                if not qontext_file.exists():
                    process_file(qodeyard_path, file_path, qontext_path, provider, model)
    
    print("--- Qontextor: Initial scan complete ---", flush=True)

def run_update_scan(summary_path: Path, qodeyard_path: Path, qontext_path: Path, provider: str, model: str):
    """Scans a summary file and updates qontext for changed files."""
    print(f"--- Qontextor: Starting update scan based on {summary_path.name} ---", flush=True)
    
    if not summary_path.exists():
        print("  - Summary file not found. Nothing to update.", flush=True)
        return
        
    with open(summary_path, 'r', encoding='utf-8') as f:
        summary_content = f.read()
    
    # This regex finds file paths enclosed in backticks, typical for markdown.
    changed_files = re.findall(r'`([^`]+)`', summary_content)
    
    if not changed_files:
        print("  - No changed files found in summary. Nothing to update.", flush=True)
        return

    processed_files = set()
    for file_str in changed_files:
        # The summary from construqtor may have absolute paths, make them relative
        file_path = Path(file_str)
        if file_path.is_absolute():
            try:
                relative_path = file_path.relative_to(qodeyard_path)
                file_path = qodeyard_path / relative_path
            except ValueError:
                print(f"  - [WARN] Changed file '{file_str}' is outside the qodeyard. Skipping.", flush=True)
                continue
        else:
             file_path = qodeyard_path / file_str

        # Ensure we don't re-process the same file if mentioned multiple times
        if file_path in processed_files:
            continue
        processed_files.add(file_path)

        if file_path.exists() and should_process_file(file_path):
            process_file(qodeyard_path, file_path, qontext_path, provider, model)
        else:
            print(f"  - [INFO] Changed file '{file_str}' does not exist or is not a processable type. Skipping.", flush=True)

    print("--- Qontextor: Update scan complete ---", flush=True)

def main():
    if len(sys.argv) != 3:
        print("Usage: qontextor.py <input_path> <output_path>", flush=True)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) # This will be qontext.d
    
    # The worqspace root is the current working directory set by qrane
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    
    provider, model = get_ai_config()
    
    if not input_path.exists():
        print(f"CRITICAL: Input path does not exist: {input_path}", flush=True)
        sys.exit(1)

    # Mode determination:
    # If input is a directory, it's an initial scan of qodeyard.
    # If input is a file, it's an update scan from a summary.
    if input_path.is_dir():
        # The input path for an initial scan *is* the qodeyard
        run_initial_scan(qodeyard_path=input_path, qontext_path=output_path, provider=provider, model=model)
    elif input_path.is_file():
        run_update_scan(summary_path=input_path, qodeyard_path=qodeyard_path, qontext_path=output_path, provider=provider, model=model)
    else:
        print(f"CRITICAL: Input path is not a file or directory: {input_path}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
