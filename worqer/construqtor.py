#!/usr/bin/env python3
# worqer/construqtor.py
import sys
import os
import yaml
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: import lib_ai
except ImportError: print("CRITICAL: lib_ai.py not found."); sys.exit(1)

def get_mode_persona(mode: str) -> str:
    m = mode.lower()
    if m == 'enterprise': return "Code Style: Enterprise. Add logging, error handling, docstrings, and modular structure."
    if m == 'security': return "Code Style: Security. Validate all inputs, use secure defaults."
    return "Code Style: Functional."

def validate_code(file_path: Path):
    """
    Validates the generated code for common errors, such as syntax errors.
    """
    if file_path.suffix == '.py':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), str(file_path), 'exec')
        except SyntaxError as e:
            print(f"     [WARN] Syntax error in {file_path}: {e}", flush=True)

def _write_ai_output_to_qodeyard(result: str, qodeyard: Path) -> list[str]:
    """
    Parses the AI's markdown output, extracts all code blocks, and writes them
    to the specified qodeyard directory. It enforces that all paths are safely
    within the qodeyard.
    """
    qodeyard.mkdir(parents=True, exist_ok=True)
    written_files = []
    
    language_keywords = {
        'python', 'javascript', 'typescript', 'html', 'css', 'json', 'yaml', 'yml',
        'sh', 'bash', 'go', 'rust', 'java', 'c', 'cpp', 'csharp', 'sql', 'ruby'
    }

    # Pattern to find markdown code blocks with filenames, e.g., ```python:main.py
    pattern = re.compile(r"```(?:\w+:)([\w\./-]+)?\s*\n(.*?)\n```", re.DOTALL)
    matches = pattern.findall(result)

    if not matches:
        return written_files

    for filename, code_content in matches:
        # If the AI provided a language keyword as a filename, treat it as no-filename
        if not filename or (filename and filename.lower() in language_keywords):
            print(f"     [WARN] Skipping code block with invalid filename: {filename}", flush=True)
            continue

        # [FIX] Sanitize filename to prevent nested qodeyard directories
        if filename.strip().startswith('qodeyard/'):
            filename = filename.strip()[len('qodeyard/'):]

        qodeyard_abs = qodeyard.resolve()
        proposed_path = qodeyard_abs.joinpath(filename.strip())
        proposed_abs = proposed_path.resolve()

        if not str(proposed_abs).startswith(str(qodeyard_abs)):
            print(f"     [WARN] Skipping unsafe file path that resolves outside qodeyard: {filename}", flush=True)
            continue
        
        full_path = proposed_abs
        safe_filename = full_path.relative_to(qodeyard_abs)
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code_content.strip(), encoding='utf-8')
        
        written_files.append(str(safe_filename))
        print(f"     - Wrote [Code] {safe_filename}", flush=True)
        validate_code(full_path)

    return written_files

def main():
    if len(sys.argv) != 4:
        print("Usage: construqtor.py <input_dir> <summary_output> <changed_files_output>", flush=True)
        sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    changed_files_summary_file = Path(sys.argv[3])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')
    use_qompressor = config.get('options', {}).get('use_qompressor', True)

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    mode_prompt = get_mode_persona(mode)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found.", flush=True)
        sys.exit(1)

    all_briqs_summary = []
    all_written_files = []
    failure_count = 0

    print(f"--- Construqtor Found {len(briq_files)} Briqs ---", flush=True)

    # Determine context source based on config
    bloq_path = worqspace_root / "bloq.d"
    context_source_path = bloq_path if use_qompressor and bloq_path.is_dir() else qodeyard_path
    context_type = "code skeletons from `bloq.d/`" if use_qompressor else "full source code from `qodeyard/`"

    all_context_files = []
    if context_source_path.is_dir():
        for root, _, files in os.walk(context_source_path):
            for file in files:
                all_context_files.append(str(Path(root) / file))

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan defined in the 'briq'.
**CONTEXT:** You have been provided with the {context_type} of the existing codebase. Use this structural context to ensure your generated code integrates correctly with the existing project.
**ABSOLUTE DIRECTIVE:** ALL code output MUST be written to the `qodeyard/` directory.
**OUTPUT FORMAT:** You MUST format your response using markdown code blocks. Each file must have its path specified after the language in the format `language:path/to/file.ext`.

**EXAMPLE:**
```python:qodeyard/main.py
print("Hello, World!")
```

**RESTRICTION:** GENERATE ONLY THE FILE BLOCKS AS SHOWN IN THE EXAMPLE. Do not add any other text, conversation, or explanations outside the markdown blocks.

**MODE:** {mode.upper()}
{mode_prompt}

**Plan (from Briq):**
{briq_content}
"""
        success = False
        result = ""
        try:
            print(f"     - Sending {briq_file.name} to AI for execution...", flush=True)
            # Note: lib_ai needs to be updated to handle .py files in context correctly if it doesn't already
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=all_context_files)
            success = True
        except Exception as e:
            print(f"     [WARN] AI Pipe Signal: {e}", flush=True)
            if "```" in str(e) or (result and "```" in result):
                success = True
            else:
                success = False

        if result and "```" in result:
             success = True
        
        written_files = []
        if success:
            written_files = _write_ai_output_to_qodeyard(result, qodeyard_path)
            if not written_files:
                success = False
        
        all_written_files.extend(written_files)
        status = "success" if success else "failure"
        if not success: failure_count += 1
        all_briqs_summary.append({
            'briq_file': briq_file.name, 
            'status': status
        })
        print(f"-- Executed Briq: {briq_file.name} (Status: {status}) --", flush=True)

    final_status = "Success" if failure_count == 0 else ("Partial" if failure_count < len(briq_files) else "Failure")

    # --- Write Main Summary File ---
    summary_content = f"# Execution Summary\n\n**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(briq_files)} | **Failures:** {failure_count}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **{item['briq_file']}**: {item['status']}\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)

    # --- Write Changed Files Summary ---
    changed_files_content = "# Changed Files\n\n"
    # Use set for uniqueness and sort for consistent order
    for f in sorted(list(set(all_written_files))):
        changed_files_content += f"- `{f}`\n"
        
    os.makedirs(changed_files_summary_file.parent, exist_ok=True)
    with open(changed_files_summary_file, 'w', encoding='utf-8') as f: f.write(changed_files_content)

if __name__ == "__main__": main()