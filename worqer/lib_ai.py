#!/usr/bin/env python3
# worqer/lib_ai.py
import subprocess
import sys
import os
import threading
import time
import select


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
    Robust, infinitely retrying execution: Streams stdout for visuals, 
    collects it for return, and retries on common transient API errors.
    """
    original_input_text = input_text
    retry_count = 0

    while True: # Infinite retry loop
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

            def writer():
                try:
                    if input_text:
                        proc.stdin.write(input_text)
                        proc.stdin.flush()
                except (BrokenPipeError, OSError, ValueError):
                    pass # Expected behavior if process closes pipe early
                finally:
                    try: proc.stdin.close()
                    except: pass

            if input_text:
                t = threading.Thread(target=writer)
                t.start()

            captured_stdout = []
            captured_stderr = []

            # Non-blocking read from both stdout and stderr
            while True:
                reads = [proc.stdout, proc.stderr]
                ret = select.select(reads, [], [], 0.1)

                for r in ret[0]:
                    if r is proc.stdout:
                        char = proc.stdout.read(1)
                        if char:
                            captured_stdout.append(char)
                            sys.stderr.write(char)
                            sys.stderr.flush()
                    elif r is proc.stderr:
                        line = proc.stderr.readline()
                        if line:
                            captured_stderr.append(line)
                            # Also print to main stderr for visibility
                            sys.stderr.write(f"[AI STDERR]: {line}")
                            sys.stderr.flush()

                if proc.poll() is not None and not ret[0]:
                    break

            proc.wait()
            if input_text:
                t.join(timeout=2)

            stderr_output = "".join(captured_stderr)

            # --- QonQrete Error Handling & Retry Logic ---
            error_signatures = ["503", "400", "service unavailable", "model overloaded", "rate limit"]
            if proc.returncode != 0 and any(sig in stderr_output.lower() for sig in error_signatures):
                retry_count += 1
                error_message = f"[AI WARN] Transient error detected (e.g., 503/400/Overload). Retrying in 10s... (Attempt {retry_count})"
                sys.stderr.write(f"\n{error_message}\n")
                time.sleep(10)
                
                # Modify prompt for continuation
                input_text = f"Continue where you left off please?\n\n{original_input_text}"
                continue # Retry the loop

            if proc.returncode != 0:
                sys.stderr.write(f"\n[AI ERROR]: Non-recoverable error. Full stderr below:\n{stderr_output}\n")
                raise RuntimeError(f"AI Provider failed with a non-recoverable error (Code {proc.returncode})")

            # If successful, break the loop and return
            return "".join(captured_stdout).strip()

        except FileNotFoundError:
            raise RuntimeError(f"Missing binary for command: {cmd[0]}")
        except Exception as e:
            # Catch other potential exceptions during process handling
            raise RuntimeError(f"Subprocess execution failed: {e}")

