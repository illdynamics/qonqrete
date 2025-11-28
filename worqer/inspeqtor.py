#!/usr/bin/env python3
# worqer/inspeqtor.py
import os
import sys
import yaml
import subprocess
import shutil

def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: inspeqtor.py <input_summary_file> <output_reqap_file>")
        sys.exit(1)

    summary_path = sys.argv[1]
    reqap_path = sys.argv[2]

    # [SHERLONQ FIX] Read Cycle for logging
    cycle_num = os.environ.get('CYCLE_NUM', '1')

    summary_dir = os.path.dirname(summary_path)
    worqspace_dir = os.path.dirname(summary_dir)
    qodeyard_path = os.path.join(worqspace_dir, 'qodeyard')

    # [SHERLONQ FIX] Pre-Execution Logs
    # We calculate the relative path to match user request: "Checking exeq.d/..."
    rel_summary_path = os.path.relpath(summary_path, worqspace_dir)
    print(f"Checking {rel_summary_path} (current cyqle summary)")
    print(f"Checking cyQle {cycle_num} codebase")

    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_content = f.read()
    except FileNotFoundError:
        print(f"CRITICAL: Summary file not found at {summary_path}")
        sys.exit(1)

    context = f"## ConstruQtor's Report\n{summary_content}"

    if os.path.isdir(qodeyard_path):
        context += "\n\n## Generated Artifacts\n"
        for root, _, files in os.walk(qodeyard_path):
            for name in files:
                fpath = os.path.join(root, name)
                relative_path = os.path.relpath(fpath, qodeyard_path)
                context += f"\n### File: `{relative_path}`\n```\n"
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        context += f.read()
                except Exception as e:
                    context += f"[Error reading file: {e}]"
                context += "\n```\n"

    direqtor_prompt = os.environ.get('DIREQTOR_PROMPT', '')
    reviewer_prompt = f"""
{direqtor_prompt}

You are the 'inspeQtor', a senior code reviewer. Your purpose is to analyze the construQtor's work and provide a clear, actionable review for the next cycle.

**Output Format (Strict Markdown):**
1.  **Assessment:** The first line must be one of: `Assessment: Success`, `Assessment: Partial`, or `Assessment: Failure`.
2.  **Summary:** Briefly describe your findings.
3.  **Suggestions:** Provide a bulleted list of concrete suggestions for the next cycle. Your suggestions are critical for the evolution of the project.
    * **Go Beyond Improvement:** Do not just suggest minor fixes. Propose new features, new functionalities, and creative ideas that will expand the project's scope and capabilities.
    * **Be Visionary:** Think about what this project *could* become. What's the next logical step? What would a user love to see?
    * **Actionable Steps:** Ensure your suggestions are clear and can be translated into actionable development tasks.

**Context from Current Cycle:**
{context}

**Begin Review:**
"""
    sgpt = shutil.which('sgpt')
    if not sgpt:
        print("CRITICAL: sgpt not found.")
        sys.exit(1)

    try:
        with open(os.path.join(worqspace_dir, 'config.yaml')) as f:
            cfg = yaml.safe_load(f) or {}
    except:
        cfg = {}
    model = cfg.get('agents', {}).get('inspeqtor', {}).get('model', 'gpt-4o')

    try:
        proc = subprocess.run(
            [sgpt, '--no-interaction', '--model', model, reviewer_prompt],
            capture_output=True, text=True, check=True
        )

        if proc.stderr:
            print(f"[SGPT STDERR] {proc.stderr.strip()}")

        content = proc.stdout.strip()
        content = content.replace("```markdown", "").replace("```", "").strip()

    except subprocess.CalledProcessError as e:
        print(f"Inspeqtor Failure (Subprocess): {e}")
        print(f"--- STDERR START ---\n{e.stderr}\n--- STDERR END ---")
        sys.exit(1)
    except Exception as e:
        print(f"Inspeqtor Failure: {e}")
        sys.exit(1)

    os.makedirs(os.path.dirname(reqap_path), exist_ok=True)
    with open(reqap_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"reQap written to {reqap_path}")

if __name__ == '__main__':
    main()
