#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import shutil
import sys
import os

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    """
    Unified entry point for AI completion.

    Args:
        provider: 'openai' or 'gemini'
        model: Model name (e.g., 'gpt-4o', 'gemini-1.5-pro')
        prompt: The main instruction
        context_files: List of file/dir paths to include (for context)

    Returns:
        The text response from the AI.
    """
    if context_files is None:
        context_files = []

    if provider.lower() == 'openai':
        return _run_sgpt(model, prompt, context_files)
    elif provider.lower() == 'gemini':
        return _run_gemini(model, prompt, context_files)
    else:
        raise ValueError(f"Unknown AI Provider: {provider}")

def _run_sgpt(model: str, prompt: str, context_files: list[str]) -> str:
    sgpt = shutil.which('sgpt')
    if not sgpt:
        raise FileNotFoundError("sgpt binary not found. Install with: pip install shell-gpt")

    full_prompt = prompt
    if context_files:
        full_prompt += "\n\n--- Context Files ---\n"
        for fpath in context_files:
            if os.path.exists(fpath):
                if os.path.isdir(fpath):
                    continue
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        full_prompt += f"\nFile: {fpath}\n```\n{f.read()}\n```\n"
                except Exception:
                    pass

    cmd = [sgpt, '--no-interaction', '--model', model, full_prompt]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Standard error is often useful in SGPT failure cases
        raise RuntimeError(f"SGPT Failed: {e.stderr.strip()}")

def _run_gemini(model: str, prompt: str, context_files: list[str]) -> str:
    gemini = shutil.which('gemini')
    if not gemini:
        raise FileNotFoundError("gemini binary not found. Install with: npm install -g @google/gemini-cli")

    cmd = [gemini, 'prompt', '--model', model, '--approval-mode', 'yolo']

    for c_path in context_files:
        cmd.extend(['--include-directories', c_path])

    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=True)
        return proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Gemini Failed: {e.stderr.strip()}")
