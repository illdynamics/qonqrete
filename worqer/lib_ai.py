#!/usr/bin/env python3
# worqer/lib_ai.py
import sys
import os
import subprocess
import threading
import anthropic
import openai
import google.generativeai as genai
from sqeleton.deepseek_provider import DeepSeekProvider

def run_ai_completion(provider: str, model: str, prompt: str, context_files: list[str] = None) -> str:
    if context_files is None: context_files = []
    full_prompt = _build_prompt(prompt, context_files)

    try:
        if provider.lower() == 'openai':
            return _run_openai(model, full_prompt)
        elif provider.lower() == 'gemini':
            return _run_gemini(model, full_prompt)
        elif provider.lower() == 'anthropic':
            return _run_anthropic(model, full_prompt)
        elif provider.lower() == 'deepseek':
            return _run_deepseek(model, full_prompt)
        elif provider.lower() == 'qwen':
            return _run_qwen(model, full_prompt)
        else:
            raise ValueError(f"Unknown AI Provider: {provider}")
    except Exception as e:
        sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {e}\n")
        raise


def _build_prompt(base_prompt, context_files):
    # --- Log Fallback Context ---
    log_context = ""
    prev_log_path = os.environ.get("QONQ_PREVIOUS_LOG")
    if prev_log_path and os.path.exists(prev_log_path):
        try:
            with open(prev_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()
            if log_content:
                log_context = f"\n\n--- PREVIOUS AGENT LOG (FALLBACK CONTEXT) ---\n{log_content}\n"
        except:
            pass # Ignore if reading the log fails

    # --- Architectural Context ---
    arch_context = ""
    if context_files:
        arch_context += "\n\n--- ARCHITECTURAL CONTEXT ---\n"
        for fpath in context_files:
            if os.path.exists(fpath) and not os.path.isdir(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        # Use basename to keep the context clean, and determine language from extension
                        fname = os.path.basename(fpath)
                        f_ext = os.path.splitext(fname)[1].lower()
                        lang = "yaml" if f_ext in ['.yaml', '.q.yaml'] else (f_ext[1:] if f_ext else "")
                        
                        arch_context += f"\nFile: {fname}\n```{lang}\n{f.read()}\n```\n"
                except: pass
    
    full_prompt = log_context + base_prompt + arch_context
    return full_prompt

def _run_streaming_cli_process(cmd, input_text) -> str:
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        def writer():
            try:
                proc.stdin.write(input_text)
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try: proc.stdin.close()
                except: pass

        t = threading.Thread(target=writer)
        t.start()

        captured_stdout = []
        while True:
            char = proc.stdout.read(1)
            if not char and proc.poll() is not None:
                break
            if char:
                captured_stdout.append(char)
                sys.stderr.write(char)
                sys.stderr.flush()
        
        stderr_output = proc.stderr.read()
        proc.wait()
        t.join(timeout=2)

        if proc.returncode != 0:
            if stderr_output:
                sys.stderr.write(f"\n[AI CLI ERROR]: {stderr_output}\n")
            raise RuntimeError(f"AI Provider CLI failed with code {proc.returncode}")

        return "".join(captured_stdout).strip()

    except FileNotFoundError:
        raise RuntimeError(f"Missing binary for command: {cmd[0]}")
    except Exception as e:
        raise RuntimeError(f"Subprocess execution failed: {e}")

def _run_openai(model, prompt):
    client = openai.OpenAI()
    response_stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )
    captured_chunks = []
    for chunk in response_stream:
        content = chunk.choices[0].delta.content
        if content:
            captured_chunks.append(content)
            sys.stderr.write(content)
            sys.stderr.flush()
    return "".join(captured_chunks).strip()

def _run_gemini(model, prompt):
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    client = genai.GenerativeModel(model)
    response_stream = client.generate_content(prompt, stream=True)
    
    captured_chunks = []
    for chunk in response_stream:
        text = getattr(chunk, 'text', None)
        if text:
            captured_chunks.append(text)
            sys.stderr.write(text)
            sys.stderr.flush()
    return "".join(captured_chunks).strip()

def _run_anthropic(model, prompt):
    client = anthropic.Anthropic()
    response_stream = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        stream=True
    )
    captured_chunks = []
    for chunk in response_stream:
        if chunk.type == 'content_block_delta' and hasattr(chunk, 'delta') and hasattr(chunk.delta, 'text'):
            content = chunk.delta.text
            captured_chunks.append(content)
            sys.stderr.write(content)
            sys.stderr.flush()
    return "".join(captured_chunks).strip()

def _run_deepseek(model, prompt):
    provider = DeepSeekProvider(model=model)
    # The DeepSeek provider currently doesn't support streaming to stderr,
    # so we print a marker and then the final result.
    sys.stderr.write("[Querying DeepSeek...]")
    sys.stderr.flush()
    response = provider.query(prompt)
    sys.stderr.write(response)
    sys.stderr.flush()
    return response

def _run_qwen(model, prompt):
    # Assuming Qwen CLI is installed and configured
    # The 'qwen' command with -p flag expects the prompt from stdin
    cmd = ["qwen", "-p", "-y", "--model", model, "--auth-type", "openai", "--openai-base-url", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"]
    api_key = os.environ.get("QWEN_API_KEY")
    if api_key:
        cmd.extend(["--openai-api-key", api_key])
    else:
        raise ValueError("QWEN_API_KEY environment variable not set.")

    sys.stderr.write(f"[Querying Qwen (model: {model})...]")
    sys.stderr.flush()
    # Pass the prompt via stdin
    return _run_streaming_cli_process(cmd, prompt)
