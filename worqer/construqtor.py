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

def extract_and_write_files(response: str, output_base: Path) -> list[str]:
    """
    Parses the AI response for code blocks and writes them to files.
    Expected format:
    ```ext
    # filename: path/to/file.ext
    code
    ```
    """
    written_files = []
    # Regex to capture code blocks. 
    # Group 1: Optional language (ignored)
    # Group 2: Content including the potential filename comment
    code_block_pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    
    matches = code_block_pattern.findall(response)
    
    for _, content in matches:
        lines = content.strip().split('\n')
        if not lines: continue
        
        # Check first line for filename
        first_line = lines[0].strip()
        filename = None
        
        # Support formats: "# filename: path" or "# path" or "// path" etc
        if re.match(r'^(\#|//|<!--)\s*(filename:)?\s*[\w\-\./\\]+', first_line, re.IGNORECASE):
            parts = first_line.split()
            # Try to find the part that looks like a filename
            for part in parts:
                if '.' in part and '/' in part: # rudimentary check for path
                    filename = part
                    break
                if '.' in part and len(parts) <= 3: # simple filename in short comment
                    filename = part
                    break
            
            # If we found a potential filename, strip comment chars
            if filename:
                filename = re.sub(r'^[\#//<!--]+', '', filename).strip()
                # Clean up "filename:" prefix if it got stuck
                filename = re.sub(r'^filename:', '', filename, flags=re.IGNORECASE).strip()
            
            # Remove the filename line from content
            file_content = "\n".join(lines[1:])
        else:
            # Fallback: No filename found in block. 
            # In a real system, we might skip or use a default.
            # For now, let's look for a separate pattern or skip.
            # We will try to match "File: xxx" before the block if we were fancier.
            # But let's stick to the prompt enforcing the pattern.
            continue

        if filename:
            # Security: Prevent escaping qodeyard
            clean_name = os.path.basename(filename) 
            # Allow subdirectories relative to qodeyard
            # But resolving absolute paths or .. is dangerous. 
            # Let's trust the AI but sandboxed to output_base.
            try:
                target_path = (output_base / filename).resolve()
                if not str(target_path).startswith(str(output_base.resolve())):
                    print(f"[WARN] Skipped unsafe path: {filename}", flush=True)
                    continue
                    
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                written_files.append(str(target_path.relative_to(output_base)))
            except Exception as e:
                print(f"[ERROR] Failed to write {filename}: {e}", flush=True)

    return written_files

def main():
    if len(sys.argv) < 3: print("Usage: construqtor.py <input> <output>"); sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    qodeyard_path = Path.cwd() # The CWD is now qodeyard
    qodeyard_path.mkdir(parents=True, exist_ok=True)

    try:
        with open('/qonq_conf/config.yaml', 'r', encoding='utf-8') as f: config = yaml.safe_load(f) or {}
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

    # [FIX] Collect file paths, not just the directory
    context_files = []
    if qodeyard_path.exists():
        for root, _, files in os.walk(qodeyard_path):
            for file in files:
                context_files.append(os.path.join(root, file))

    for briq_file in briq_files:
        print(f"-- Processing Briq: {briq_file.name} --", flush=True)
        with open(briq_file, 'r', encoding='utf-8') as f: briq_content = f.read()

        prompt = f"""You are the 'construQtor'.
**OBJECTIVE:** Write the code to implement the plan.
**RESTRICTION:** GENERATE CODE ONLY.
**OUTPUT FORMAT:**
You MUST wrap code in markdown blocks.
The FIRST LINE of the code block MUST be a comment specifying the filename.
Example:
```python
# filename: src/utils.py
def my_func(): ...
```

**MODE:** {mode.upper()}
{mode_prompt}

**Plan:**
{briq_content}
"""
        success = False
        result = ""
        try:
            # [FIX] Pass context_files
            result = lib_ai.run_ai_completion(ai_provider, ai_model, prompt, context_files=context_files)
            
            # [FIX] Parse and write files
            files_created = extract_and_write_files(result, qodeyard_path)
            
            if files_created:
                success = True
                print(f"   + Created: {', '.join(files_created)}", flush=True)
            else:
                if "```" in result:
                    print("   [WARN] Code generated but no files parsed (check filename comments).", flush=True)
                    # Optional: Dump raw result to debug file?
                success = False

        except Exception as e:
            print(f"     [WARN] AI Pipe Signal: {e}", flush=True)
            # If partial result handling is needed, it goes here.
            success = False

        status = "success" if success else "failure"
        if not success: failure_count += 1

        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })
        print(f"-- Executed Briq: {briq_file.name} (Status: {status}) --", flush=True)

    final_status = "Success" if failure_count == 0 else ("Partial" if failure_count < len(briq_files) else "Failure")

    summary_content = f"# Execution Summary\n\n**Overall Status:** {final_status}\n"
    summary_content += f"**Processed:** {len(briq_files)} | **Failures:** {failure_count}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **{item['briq_file']}**: {item['status']}\n"

    os.makedirs(summary_file.parent, exist_ok=True)
    with open(summary_file, 'w', encoding='utf-8') as f: f.write(summary_content)

if __name__ == "__main__": main()