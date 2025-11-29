#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import sys
import os

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    if context_files is None: context_files = []

    full_prompt = _build_prompt(prompt, context_files)

    if provider.lower() == 'openai':
        # --no-cache helps prevent looping on repetitive tasks
        return _run_process(['sgpt', '--no-cache', '--no-interaction', '--model', model, full_prompt])
    elif provider.lower() == 'gemini':
        # Gemini often takes the prompt via stdin better for large contexts
        cmd = ['gemini', 'prompt', '--model', model, '--approval-mode', 'yolo']
        return _run_process(cmd, input_text=full_prompt)
    else:
        raise ValueError(f"Unknown AI Provider: {provider}")

def _build_prompt(base_prompt, context_files):
    full = base_prompt
    if context_files:
        full += "\n\n--- EXISTING CODEBASE CONTEXT ---\n"
        for fpath in context_files:
            if os.path.exists(fpath) and not os.path.isdir(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        full += f"\nFile: {fpath}\n```\n{f.read()}\n```\n"
                except: pass
    return full

def _run_process(cmd, input_text=None) -> str:
    # ROBUSTNESS FIX: Use communicate() to handle large I/O buffers safely
    stdin_mode = subprocess.PIPE if input_text else None

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=stdin_mode,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        stdout, stderr = proc.communicate(input=input_text)

        if proc.returncode != 0:
            # Print stderr to help debug API limits or token errors
            sys.stderr.write(f"[AI ERROR] {stderr}\n")
            raise RuntimeError(f"AI Provider failed with code {proc.returncode}")

        return stdout.strip()

    except FileNotFoundError:
        raise RuntimeError(f"Missing binary for command: {cmd[0]}")
    except Exception as e:
        raise RuntimeError(f"Subprocess execution failed: {e}")
