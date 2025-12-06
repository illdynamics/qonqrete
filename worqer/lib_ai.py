#!/usr/bin/env python3
# worqer/lib_ai.py
import sys
import os
import subprocess
import threading
import anthropic
import openai
import google.generativeai as genai

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
            return _run_deepseek_cli(model, full_prompt)
        else:
            raise ValueError(f"Unknown AI Provider: {provider}")
    except Exception as e:
        sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {e}\n")
        raise

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
        if chunk.text:
            captured_chunks.append(chunk.text)
            sys.stderr.write(chunk.text)
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

def _run_deepseek_cli(model, prompt):
    cmd = ['deepseek', 'chat', '--model', model]
    return _run_streaming_cli_process(cmd, input_text=prompt)
