#!/usr/bin/env python3
# worqer/lib_ai.py
import sys
import os
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
        max_tokens=4096,  # Recommended to set a max
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