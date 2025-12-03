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

def _write_ai_output_to_qodeyard(result: str, qodeyard: Path) -> list[str]:
    """
    Parses the AI's markdown output, extracts all code blocks, and writes them
    to the specified qodeyard directory. It enforces that all paths are safely
    within the qodeyard.
    """
    # Pattern to find markdown code blocks with optional filenames
    # e.g., ```python:main.py or ```json
    pattern = re.compile(r"```(?:\w+:)?([\w\./-]+)?\s*\n(.*?)\n```", re.DOTALL)
    matches = pattern.findall(result)
    
    written_files = []
    
    # List of common language identifiers that might be mistaken for filenames
    language_keywords = {
        'python', 'javascript', 'typescript', 'html', 'css', 'json', 'yaml', 'yml',
        'sh', 'bash', 'go', 'rust', 'java', 'c', 'cpp', 'csharp', 'sql', 'ruby'
    }

    if not matches:
        # If no filenames are specified, write the whole blob to a default file
        if "```" in result:
             # Fallback for code blocks without language specifier
            fallback_pattern = re.compile(r"```\s*\n(.*?)\n```", re.DOTALL)
            fallback_matches = fallback_pattern.findall(result)
            if fallback_matches:
                code_content = "\n".join(fallback_matches).strip()
                if code_content:
                    fallback_file = qodeyard / "construqted_code.txt"
                    fallback_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(fallback_file, 'w', encoding='utf-8') as f:
                        f.write(code_content)
                    written_files.append(str(fallback_file))
        return written_files

    for filename, code_content in matches:
        # If the AI provided a language keyword as a filename, treat it as no-filename
        if filename and filename.lower() in language_keywords:
            filename = None

        if not filename:
            # Use a default filename for code blocks without a specified name
            fallback_file = qodeyard / "construqted_code.txt"
            fallback_file.parent.mkdir(parents=True, exist_ok=True)
            # Append if it exists, as there might be multiple unnamed blocks
            with open(fallback_file, 'a', encoding='utf-8') as f:
                f.write(code_content.strip() + "\n\n")
            if str(fallback_file) not in written_files:
                written_files.append(str(fallback_file))
            continue

        # --- SECURITY CRITICAL ---
        # 1. Forcibly remove any parent directory traversal attempts.
        # 2. Normalize the path to resolve any '.' or residual '..' components.
        # 3. Ensure the resolved path is inside the qodeyard.
        safe_filename = filename.strip().replace("../", "").replace("..\\", "")
        safe_filename = os.path.normpath(safe_filename)

        if os.path.isabs(safe_filename):
            # If path is absolute after sanitization, strip leading chars to make it relative
            safe_filename = re.sub(r'^[./\\]+', '', safe_filename)

        full_path = qodeyard.joinpath(safe_filename).resolve()

        # Final check: is the resolved path a child of the qodeyard?
        if qodeyard.resolve() != full_path and qodeyard.resolve() not in full_path.parents:
            print(f"     [WARN] Skipping unsafe file path after sanitization: {filename}", flush=True)
            continue
        
        # Create subdirectories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(code_content.strip())
        
        written_files.append(str(full_path))
        print(f"     - Wrote [Code] {safe_filename}", flush=True)

    return written_files

def main():
    if len(sys.argv) < 3: print("Usage: construqtor.py <input> <output>"); sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    worqspace_root = Path(os.getcwd())
    qodeyard_path = worqspace_root / "qodeyard"
    qodeyard_path.mkdir(parents=True, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
    except: config = {}

    agent_cfg = config.get('agents', {}).get('construqtor', {})
    ai_provider = agent_cfg.get('provider', 'gemini')
    ai_model = agent_cfg.get('model', 'gemini-1.5-pro')

    mode = os.environ.get('QONQ_MODE', 'enterprise')
    mode_prompt = get_mode_persona(mode)

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briqs found.", flush=True); sys.exit(1)

    all_briqs_summary = []
    failure_count = 0

    print(f"--- Construqtor Found {len(briq_files)} Briqs ---", flush=True)

    context_dirs = [str(qodeyard_path.resolve())]

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan.
**CRITICAL RULE:** You MUST write all code files to the `qodeyard/` directory. You can create subdirectories inside `qodeyard/`, but you are forbidden from writing to any other location. All file paths in your output must start with `qodeyard/`.
**RESTRICTION:** GENERATE CODE ONLY.
**OUTPUT:** Return the code files inside markdown blocks.

**MODE:** {mode.upper()}
{mode_prompt}

**Plan:**
{briq_content}
"""
        success = False
        result = ""
        try:
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=context_dirs)
            success = True
        except Exception as e:
            # [FIX] If we got a partial result or pipe error, check if code was generated anyway
            print(f"     [WARN] AI Pipe Signal: {e}", flush=True)
            if "```" in str(e) or (result and "```" in result):
                success = True
            else:
                success = False

        # [FIX] Double check: Did we actually get code?
        if result and "```" in result:
             success = True

        written_files = []
        if success:
            written_files = _write_ai_output_to_qodeyard(result, qodeyard_path)
            # If the parser found no files, it could be a raw code block.
            # Re-evaluate success based on whether files were actually written.
            if not written_files:
                success = False

        status = "success" if success else "failure"
        if not success: failure_count += 1

        all_briqs_summary.append({ 
            'briq_file': briq_file.name, 
            'status': status,
            'files_written': written_files 
        })
        print(f"-- Executed Briq: {briq_file.name} (Status: {status}) --", flush=True)

    final_status = "Success" if failure_count == 0 else ("Partial" if failure_count < len(briq_files) else "Failure")

    summary_content = f"# Execution Summary\n\n**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(briq_files)} | **Failures:** {failure_count}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **{item['briq_file']}**: {item['status']}\n"
        if item['files_written']:
            for f in item['files_written']:
                summary_content += f"  - `{f}`\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)

if __name__ == "__main__": main()
