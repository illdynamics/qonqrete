#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import shutil
import sys
import os

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    if context_files is None: context_files = []

    if provider.lower() == 'openai':
        return _run_streaming_cmd(['sgpt', '--no-interaction', '--model', model, _build_prompt(prompt, context_files)])
    elif provider.lower() == 'gemini':
        cmd = ['gemini', 'prompt', '--model', model, '--approval-mode', 'yolo']
        for c in context_files: cmd.extend(['--include-directories', c])
        return _run_streaming_cmd(cmd, input_text=prompt)
    else:
        raise ValueError(f"Unknown AI Provider: {provider}")

def _build_prompt(base_prompt, context_files):
    full = base_prompt
    if context_files:
        full += "\n\n--- Context ---\n"
        for fpath in context_files:
            if os.path.exists(fpath) and not os.path.isdir(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        full += f"\nFile: {fpath}\n```\n{f.read()}\n```\n"
                except: pass
    return full

def _run_streaming_cmd(cmd, input_text=None) -> str:
    # [FIX] Use PIPE for input only if needed
    stdin_val = subprocess.PIPE if input_text else None

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=stdin_val,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # [FIX] Write to stdin and flush, then allow read loop to start.
        # Closing stdin immediately can sometimes cause issues if the process hasn't consumed it yet.
        if input_text:
            try:
                proc.stdin.write(input_text)
                proc.stdin.flush()
                proc.stdin.close()
            except BrokenPipeError:
                # Process exited early
                pass

        captured_stdout = []

        while True:
            char = proc.stdout.read(1)
            if not char and proc.poll() is not None:
                break
            if char:
                captured_stdout.append(char)
                sys.stderr.write(char)
                sys.stderr.flush()

        _, err = proc.communicate()
        if err:
            sys.stderr.write(err)

        if proc.returncode != 0:
            raise RuntimeError(f"AI Provider failed with code {proc.returncode}")

        return "".join(captured_stdout).strip()

    except FileNotFoundError:
        raise RuntimeError("AI binary (sgpt/gemini) not found.")
