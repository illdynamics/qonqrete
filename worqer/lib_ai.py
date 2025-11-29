#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import sys
import os
import threading
import time

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    if context_files is None: context_files = []

    # Build the prompt
    full_prompt = _build_prompt(prompt, context_files)

    if provider.lower() == 'openai':
        # Pass input via stdin to avoid Argument list too long
        cmd = ['sgpt', '--no-cache', '--no-interaction', '--model', model]
        return _run_streaming_process(cmd, input_text=full_prompt)
    elif provider.lower() == 'gemini':
        cmd = ['gemini', 'prompt', '--model', model, '--approval-mode', 'yolo']
        return _run_streaming_process(cmd, input_text=full_prompt)
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

def _run_streaming_process(cmd, input_text=None) -> str:
    """
    Robust execution: Streams stdout to stderr (visual), collects it for return.
    Avoids communicate() to prevent 'I/O operation on closed file' race conditions.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if input_text else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # 1. Handle Stdin in a thread to prevent deadlocks
        def writer():
            try:
                if input_text:
                    proc.stdin.write(input_text)
                    proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                # Process closed pipe early. This is expected behavior for some errors.
                pass
            finally:
                try: proc.stdin.close()
                except: pass

        if input_text:
            t = threading.Thread(target=writer)
            t.start()

        captured_stdout = []

        # 2. Manual Streaming Loop (Reads Stdout)
        while True:
            char = proc.stdout.read(1)
            if not char and proc.poll() is not None:
                break
            if char:
                captured_stdout.append(char)
                # Mirror to stderr so Qrane logs show progress
                sys.stderr.write(char)
                sys.stderr.flush()

        # 3. Cleanup - Do NOT use communicate()
        # Read any remaining stderr (usually errors)
        stderr_output = proc.stderr.read()

        proc.wait() # Wait for exit code

        if input_text:
            t.join(timeout=2) # Ensure writer thread finishes

        if proc.returncode != 0:
            if stderr_output:
                sys.stderr.write(f"\n[AI ERROR]: {stderr_output}\n")
            raise RuntimeError(f"AI Provider failed with code {proc.returncode}")

        return "".join(captured_stdout).strip()

    except FileNotFoundError:
        raise RuntimeError(f"Missing binary for command: {cmd[0]}")
    except Exception as e:
        raise RuntimeError(f"Subprocess execution failed: {e}")
