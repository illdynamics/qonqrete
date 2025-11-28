#!/usr/bin/env python3
# worqer/instruqtor.py
import os
import sys
import subprocess
import yaml
import shutil
import re
from pathlib import Path

def split_markdown_into_briqs(markdown_content: str) -> list[str]:
    # Splitting logic based on the strict header format
    parts = re.split(r"(### Step \d+:.*)", markdown_content)
    intro = parts[0].strip()
    briqs = []
    for i in range(1, len(parts), 2):
        header = parts[i]
        content = parts[i+1].strip() if (i+1) < len(parts) else ""
        briq_content = f"{intro}\n\n{header}\n\n{content}"
        briqs.append(briq_content)
    if not briqs:
        return [markdown_content]
    return briqs

def clean_filename_slug(text: str) -> str:
    """Creates a safe, 3-word max snake_case slug from a step title."""
    # Remove special chars, keep spaces and alphanumerics
    clean = re.sub(r'[^a-zA-Z0-9 ]', '', text)
    # Split by whitespace
    words = clean.split()
    # Take max 3 words, join with underscore, lowercase
    slug = "_".join(words[:3]).lower()
    return slug if slug else "step"

def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python instruqtor.py <input_tasq_directory> <output_briq_directory>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_dir = sys.argv[2]

    cycle_num = os.environ.get('CYCLE_NUM', '1')
    tasq_num = os.environ.get('TASQ_NUM', '1')

    target_filename = f"cyqle{cycle_num}_tasq.md"
    input_file = input_dir / target_filename

    if not input_file.exists():
        print(f"[WARN] Targeted file {target_filename} not found. Attempting fallback search...")
        try:
            input_file = next(input_dir.glob(f"cyqle{cycle_num}*_tasq.md"))
        except StopIteration:
            print(f"CRITICAL: No tasq file found for cycle {cycle_num} in {input_dir}")
            sys.exit(1)

    print(f"--- Instruqtor reading: {input_file.name} ---")

    with open(input_file, 'r', encoding='utf-8') as f:
        task_content = f.read()

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}

    direqtor_prompt = os.environ.get('DIREQTOR_PROMPT', '')

    # Enhanced Prompt for Semantic Naming and Bullet Handling
    planner_prompt = f"""
{direqtor_prompt}

You are the 'instruQtor', a senior engineer. Your role is to create a detailed, step-by-step plan for the 'construQtor'.

Your output must be a single, comprehensive markdown document.

**CRITICAL INSTRUCTIONS:**
1.  **Analyze the Input:** * If the input is a list of bullet points (e.g., from a code review), convert **EACH** bullet point into a separate Step.
    * If the input is a single request, break it down into logical atomic steps.
2.  **Header Format:** * Each step **MUST** start with a header in this exact format: `### Step N: <Action Verb> <Object> <Modifier>`
    * **Crucial:** The title after the colon should be short (2-4 words) and descriptive.
    * *Good Examples:* `### Step 1: Create Web Server`, `### Step 2: Implement Logging`, `### Step 3: Refactor Database Connector`.
    * *Bad Examples:* `### Step 1: Do it`, `### Step 1: Step 1`.
3.  **Content:**
    * For `'code'` steps, provide the **relative file path** (e.g., `qodeyard/server.py`) and clear natural language instructions.
    * For `'shell'` steps, provide the exact command.
4.  **Constraints:**
    * **DO NOT** generate steps to run/start the server (no infinite blocking processes). Build only.

**Input Task:**
{task_content}

**Begin Plan:**
"""
    sgpt_binary = shutil.which('sgpt')
    if not sgpt_binary:
        print("CRITICAL: sgpt not found.")
        sys.exit(1)

    model_name = config.get('agents', {}).get('instruqtor', {}).get('model', 'gpt-4o')

    try:
        proc = subprocess.run(
            [sgpt_binary, '--no-interaction', '--model', model_name, planner_prompt],
            capture_output=True, text=True, check=True
        )
        if proc.stderr:
            print(f"[SGPT STDERR] {proc.stderr.strip()}")
        master_plan = proc.stdout.strip()

    except subprocess.CalledProcessError as e:
        print(f"Instruqtor Failure (Subprocess): {e}")
        print(f"--- STDERR START ---\n{e.stderr}\n--- STDERR END ---")
        sys.exit(1)
    except Exception as e:
        print(f"Instruqtor Failure: {e}")
        sys.exit(1)

    briqs = split_markdown_into_briqs(master_plan)

    print(f"--- Generating {len(briqs)} Briqs for Cycle {cycle_num} ---")
    for i, briq_content in enumerate(briqs):
        # Extracting the semantic name from the header
        match = re.search(r"### Step \d+:\s*([^\n]+)", briq_content)

        if match:
            # Generate the 3-word slug (e.g., "create_web_server")
            step_slug = clean_filename_slug(match.group(1))
        else:
            step_slug = f"step{i}"

        filename = f"cyqle{cycle_num}_tasq{tasq_num}_briq{i:03d}_{step_slug}.md"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(briq_content)
        print(f"  - Wrote Briq: {filename}")

if __name__ == '__main__':
    main()
