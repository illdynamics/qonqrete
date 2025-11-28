#!/usr/bin/env python3
# worqer/construqtor.py - ConstruQtor Qraft (Supervisor)
import re
import subprocess
from pathlib import Path
import sys
import os
import shutil
import yaml

def execute_briq_with_gemini(briq_file: Path, worqspace: Path, qodeyard: Path, model_name: str) -> bool:
    """
    Uses the Gemini CLI to execute the instructions in a briq file.
    Runs in the Workspace Root, but directed to write to qodeyard.
    """

    with open(briq_file, 'r', encoding='utf-8') as f:
        briq_content = f.read()

    gemini_binary = shutil.which('gemini')
    if not gemini_binary:
        print("     [ERROR] gemini CLI not found.")
        return False

    # Context Directories
    # Since we are running in the root, we can include the directories naturally.
    include_dirs = [
        str(qodeyard.resolve()),
        str((worqspace / "tasq.d").resolve()),
        str((worqspace / "briq.d").resolve()),
        str((worqspace / "exeq.d").resolve()),
    ]

    command = [
        gemini_binary, 'prompt',
        '--model', model_name,
        '--approval-mode', 'yolo'
    ]
    for d in include_dirs:
        command.extend(['--include-directories', d])

    # Soft-Jail Prompting
    # We instruct the agent that its "Source Root" is ./qodeyard/
    full_prompt = f"""You are the 'construQtor' agent. Your task is to execute the following plan from the 'instruQtor'.

**CRITICAL PATH INSTRUCTIONS:**
1.  You are currently located in the **Project Root**.
2.  However, ALL source code and project artifacts MUST be created inside the `qodeyard/` directory.
3.  **CORRECT:** Write to `qodeyard/server.py`, `qodeyard/src/utils.js`.
4.  **WRONG:** Do NOT write to `server.py` or `./server.py`.

**Begin Plan:**

{briq_content}
"""

    try:
        # Un-Jailed Execution
        # We run in 'worqspace' so the agent sees the full context structure.
        # The prompt handles the containment.
        proc = subprocess.run(
            command,
            input=full_prompt,
            capture_output=True,
            text=True,
            check=True,
            cwd=worqspace, # Running in Root
            timeout=300
        )

        return True

    except subprocess.TimeoutExpired:
        print(f"     [FAIL] Gemini execution timed out after 300 seconds.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"     [FAIL] Gemini execution failed with exit code {e.returncode}")
        print(f"     [GEMINI STDOUT] {e.stdout.strip()}")
        print(f"     [GEMINI STDERR] {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"     [ERROR] An unexpected error occurred: {e}")
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: construqtor.py <input_briq_dir> <output_summary_file>")
        sys.exit(1)

    briq_dir = Path(sys.argv[1])
    summary_file = Path(sys.argv[2])
    worqspace_root = briq_dir.parent

    qodeyard_path = worqspace_root / "qodeyard"
    qodeyard_path.mkdir(parents=True, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    model = config.get('agents', {}).get('construqtor', {}).get('model', 'gemini-2.5-pro')

    cycle_num = os.environ.get('CYCLE_NUM', '1')

    pattern = f"cyqle{cycle_num}_*.md"
    briq_files = sorted(briq_dir.glob(pattern))

    if not briq_files:
        print(f"CRITICAL: No briq files (*.md) found matching {pattern} in {briq_dir}")
        sys.exit(1)

    all_briqs_summary = []
    final_status = "success"

    print(f"--- Construqtor filtering for: {pattern} ---")

    for briq_file in briq_files:
        # Requested Logging Format
        print(f"-- Processing Briq: {briq_file.name} --")

        success = execute_briq_with_gemini(briq_file, worqspace_root, qodeyard_path, model)

        status = "success" if success else "failure"
        all_briqs_summary.append({ 'briq_file': briq_file.name, 'status': status })

        print(f"-- Executed Briq: {briq_file.name} --")

        if not success:
            final_status = "failure"
            break

    summary_content = f"# ConstruQtor Execution Summary\n\n**Overall Status:** {final_status}\n\n"
    for item in all_briqs_summary:
        summary_content += f"- **Briq:** `{item['briq_file']}`\n"
        summary_content += f"- **Status:** {item['status']}\n\n"

    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)

if __name__ == "__main__":
    main()
