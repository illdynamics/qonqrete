#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import sys
import os
import threading

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    if context_files is None: context_files = []

    full_prompt = _build_prompt(prompt, context_files)

    if provider.lower() == 'openai':
        return _run_streaming_process(['sgpt', '--no-cache', '--no-interaction', '--model', model, full_prompt])
    elif provider.lower() == 'gemini':
        # Using 1.5-pro or 2.0-flash-exp is critical here.
        # Ensure your config uses a valid model ID.
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
    Advanced execution: Uses a thread to write to stdin to prevent deadlocks,
    while the main thread reads stdout to stream tokens to the user.
    """
    try:
        # Open process with pipes
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if input_text else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1, # Line buffered
            universal_newlines=True
        )

        # Helper function to write stdin in background
        def writer():
            try:
                if input_text:
                    proc.stdin.write(input_text)
                    proc.stdin.flush()
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                # Process exited early/crashed
                pass

        # Start writer thread
        if input_text:
            t = threading.Thread(target=writer)
            t.start()

        captured_stdout = []

        # STREAMING LOOP
        while True:
            # Read char-by-char for smooth effect
            char = proc.stdout.read(1)
            if not char and proc.poll() is not None:
                break
            if char:
                captured_stdout.append(char)
                # Write to stderr so it shows up in logs/console immediately
                sys.stderr.write(char)
                sys.stderr.flush()

        # Clean up
        if input_text:
            t.join(timeout=5)

        # Check for errors in stderr *after* stdout is done
        _, stderr_output = proc.communicate()
        if proc.returncode != 0:
            # If it failed, print the error
            if stderr_output:
                sys.stderr.write(f"\n[AI ERROR]: {stderr_output}\n")
            raise RuntimeError(f"AI Provider failed with code {proc.returncode}")

        return "".join(captured_stdout).strip()

    except FileNotFoundError:
        raise RuntimeError(f"Missing binary for command: {cmd[0]}")
    except Exception as e:
        raise RuntimeError(f"Subprocess execution failed: {e}")
