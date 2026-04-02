#!/usr/bin/env python3
# worqer/lib_ai.py
# ═══════════════════════════════════════════════════════════════════════════════
# AI Provider Abstraction Layer with Budget Enforcement
# v0.9.5 - Security hardened with timeouts and proper exception handling
# ═══════════════════════════════════════════════════════════════════════════════
import sys
import os
import subprocess
import threading
import anthropic
import openai
import google.generativeai as genai
from worqer.lib_security import (
    get_security_logger, sanitize_traceback,
    MAX_TIMEOUT_SECONDS, MAX_RETRIES_HARD_LIMIT
)

# ═══════════════════════════════════════════════════════════════════════════════
# TIMEOUT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_API_TIMEOUT = 300  # 5 minutes default timeout for AI API calls

# ═══════════════════════════════════════════════════════════════════════════════
# DEEPSEEK PROVIDER (built-in, uses OpenAI-compatible API)
# ═══════════════════════════════════════════════════════════════════════════════

class DeepSeekProvider:
    """
    DeepSeek API client using OpenAI-compatible interface.
    Supports models: deepseek-chat, deepseek-coder, deepseek-reasoner
    """
    def __init__(self, api_key=None, model="deepseek-chat", timeout=DEFAULT_API_TIMEOUT):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.base_url = "https://api.deepseek.com"
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment or arguments.")

        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def query(self, prompt, stream=False):
        """
        Sends a prompt to the DeepSeek API and returns the response.
        """
        if not prompt:
            return "Prompt cannot be empty."

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=stream,
            )
            return resp.choices[0].message.content
        except openai.APITimeoutError as e:
            raise TimeoutError(f"DeepSeek API timeout after {self.timeout}s") from e
        except openai.APIError as e:
            raise RuntimeError(f"DeepSeek API error: {e}") from e

    def query_streaming(self, prompt):
        """
        Sends a prompt to DeepSeek with streaming response.
        Yields chunks as they arrive.
        """
        if not prompt:
            yield "Prompt cannot be empty."
            return

        try:
            response_stream = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in response_stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except openai.APITimeoutError as e:
            raise TimeoutError(f"DeepSeek API timeout") from e
        except openai.APIError as e:
            raise RuntimeError(f"DeepSeek API error: {e}") from e


class TimeoutError(Exception):
    """Raised when an API call times out."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# HARD SAFETY LIMITS - These are NON-NEGOTIABLE
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_MAX_PROMPT_CHARS = 800_000       # ~800KB safety cap
DEFAULT_MAX_CONTEXT_FILES = 100          # Max files to include
DEFAULT_MAX_CHARS_PER_FILE = 150_000     # Max chars per context file
STRING_HARD_LIMIT = 9_500_000            # Just under 10MB HTTP limit


def ai_query(prompt: str, provider: str = "openai", model: str = "gpt-4o", timeout: int = None, provider_options: dict = None) -> str:
    """Compatibility wrapper for run_ai_completion."""
    return run_ai_completion(provider=provider, model=model, prompt=prompt, timeout=timeout, provider_options=provider_options)


def run_ai_completion(
    provider: str, 
    model: str, 
    prompt: str, 
    context_files: list[str] = None,
    max_prompt_chars: int = None,
    max_context_files: int = None,
    max_chars_per_file: int = None,
    timeout: int = None,
    provider_options: dict = None
) -> str:
    """
    Execute AI completion with budget enforcement.
    
    Args:
        provider: AI provider name (openai, gemini, anthropic, deepseek, llamacpp)
        model: Model identifier
        prompt: Base prompt content
        context_files: Optional list of file paths to include as architectural context
        max_prompt_chars: Override default max prompt size
        max_context_files: Override default max number of context files
        max_chars_per_file: Override default max chars per individual file
        timeout: Optional timeout in seconds
        provider_options: Optional provider-specific configuration
        
    Returns:
        AI response content
    """
    if context_files is None: 
        context_files = []
    
    # Apply budget limits
    budget_config = {
        'max_prompt_chars': max_prompt_chars or DEFAULT_MAX_PROMPT_CHARS,
        'max_context_files': max_context_files or DEFAULT_MAX_CONTEXT_FILES,
        'max_chars_per_file': max_chars_per_file or DEFAULT_MAX_CHARS_PER_FILE,
    }
    
    full_prompt = _build_prompt(prompt, context_files, budget_config)

    # Use provider-specific timeout or default
    effective_timeout = timeout or DEFAULT_API_TIMEOUT

    try:
        p_low = provider.lower()
        if p_low == 'openai':
            return _run_openai(model, full_prompt, effective_timeout)
        elif p_low == 'gemini':
            return _run_gemini(model, full_prompt, effective_timeout)
        elif p_low == 'anthropic':
            return _run_anthropic(model, full_prompt, effective_timeout)
        elif p_low == 'deepseek':
            return _run_deepseek(model, full_prompt, effective_timeout)
        elif p_low == 'qwen':
            return _run_qwen(model, full_prompt, effective_timeout)
        elif p_low == 'openrouter':
            return _run_openrouter(model, full_prompt, effective_timeout)
        elif p_low == 'llamacpp':
            return _run_llamacpp(model, full_prompt, effective_timeout, provider_options)
        else:
            raise ValueError(f"Unknown AI Provider: {provider}")
    except Exception as e:
        sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {e}\n")
        raise


def _build_prompt(base_prompt: str, context_files: list[str], budget_config: dict) -> str:
    """
    Build the complete prompt with architectural context, respecting budget limits.
    
    Budget enforcement strategy:
    1. Start with log context (if available)
    2. Add base prompt (always included)
    3. Add architectural context files up to budget
    4. If still over limit, truncate context aggressively
    5. NEVER exceed STRING_HARD_LIMIT
    """
    max_chars = budget_config['max_prompt_chars']
    max_files = budget_config['max_context_files']
    max_per_file = budget_config['max_chars_per_file']
    
    # --- Log Fallback Context (low priority, will be dropped first) ---
    log_context = ""
    prev_log_path = os.environ.get("QONQ_PREVIOUS_LOG")
    if prev_log_path and os.path.exists(prev_log_path):
        try:
            with open(prev_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()
            if log_content:
                # Cap log content to 50KB max
                if len(log_content) > 50_000:
                    log_content = log_content[-50_000:]
                    log_content = f"[...truncated...]\n{log_content}"
                log_context = f"\n\n--- PREVIOUS AGENT LOG (FALLBACK CONTEXT) ---\n{log_content}\n"
        except:
            pass

    # --- Architectural Context (budget-enforced) ---
    arch_context = ""
    files_included = 0
    arch_chars_budget = max_chars - len(base_prompt) - len(log_context) - 1000  # 1KB safety margin
    
    if context_files and arch_chars_budget > 0:
        arch_parts = []
        arch_chars_used = 0
        
        # Limit number of files
        files_to_process = context_files[:max_files]
        
        if len(context_files) > max_files:
            sys.stderr.write(f"\n[BUDGET] Limiting context files: {len(context_files)} -> {max_files}\n")
        
        for fpath in files_to_process:
            if os.path.exists(fpath) and not os.path.isdir(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Per-file truncation
                    if len(content) > max_per_file:
                        content = content[:max_per_file]
                        content += f"\n\n[...TRUNCATED at {max_per_file} chars...]"
                        sys.stderr.write(f"\n[BUDGET] Truncated large file: {os.path.basename(fpath)}\n")
                    
                    fname = os.path.basename(fpath)
                    f_ext = os.path.splitext(fname)[1].lower()
                    lang = "yaml" if f_ext in ['.yaml', '.q.yaml'] else (f_ext[1:] if f_ext else "")
                    
                    file_block = f"\nFile: {fname}\n```{lang}\n{content}\n```\n"
                    
                    # Check if adding this file would exceed budget
                    if arch_chars_used + len(file_block) > arch_chars_budget:
                        sys.stderr.write(f"\n[BUDGET] Arch context budget exhausted at {files_included} files\n")
                        break
                    
                    arch_parts.append(file_block)
                    arch_chars_used += len(file_block)
                    files_included += 1
                    
                except Exception as e:
                    sys.stderr.write(f"\n[WARN] Could not read context file {fpath}: {e}\n")
        
        if arch_parts:
            arch_context = "\n\n--- ARCHITECTURAL CONTEXT ---\n" + "".join(arch_parts)
    
    # --- Assemble final prompt ---
    full_prompt = log_context + base_prompt + arch_context
    
    # --- HARD LIMIT ENFORCEMENT ---
    if len(full_prompt) > STRING_HARD_LIMIT:
        sys.stderr.write(f"\n[CRITICAL] Prompt exceeds hard limit ({len(full_prompt)} > {STRING_HARD_LIMIT})\n")
        sys.stderr.write(f"[CRITICAL] Dropping ALL architectural context to prevent 400 error\n")
        
        # Nuclear option: drop everything except base prompt
        full_prompt = log_context + base_prompt
        
        if len(full_prompt) > STRING_HARD_LIMIT:
            # Even log + base is too big, truncate base prompt
            sys.stderr.write(f"[CRITICAL] Truncating base prompt as last resort\n")
            full_prompt = base_prompt[:STRING_HARD_LIMIT - 1000]
    
    # Log final stats
    sys.stderr.write(f"\n[PROMPT] Final size: {len(full_prompt):,} chars | Context files: {files_included}\n")
    
    return full_prompt


def filter_context_by_relevance(
    all_context_files: list[str],
    changed_files: list[str],
    qontext_path: str,
    max_neighbors: int = 2
) -> list[str]:
    """
    Filter context files to only include those relevant to the changed files.
    
    This uses a simple neighbor-based approach:
    1. Include .q.yaml files for directly changed files
    2. Include .q.yaml files for imports/dependencies (1-hop neighbors)
    
    Args:
        all_context_files: List of all available context file paths
        changed_files: List of files that were changed in this briq
        qontext_path: Path to qontext.d directory
        max_neighbors: Maximum neighbor depth (default 2)
        
    Returns:
        Filtered list of relevant context files
    """
    import yaml
    from pathlib import Path
    
    relevant_files = set()
    changed_basenames = {Path(f).stem for f in changed_files}
    changed_stems = {Path(f).stem.replace('.q', '') for f in changed_files}
    
    # Build a quick lookup of qontext files by their corresponding source file
    qontext_lookup = {}
    for ctx_file in all_context_files:
        if ctx_file.endswith('.q.yaml'):
            # e.g., main.py.q.yaml -> main.py
            basename = Path(ctx_file).name
            source_name = basename.replace('.q.yaml', '')
            qontext_lookup[source_name] = ctx_file
    
    # Phase 1: Include context for directly changed files
    for changed in changed_files:
        changed_basename = Path(changed).name
        if changed_basename in qontext_lookup:
            relevant_files.add(qontext_lookup[changed_basename])
    
    # Phase 2: Include context for dependencies (1-hop)
    # Read each relevant .q.yaml and extract its dependencies
    deps_to_check = set()
    
    for ctx_file in list(relevant_files):
        try:
            with open(ctx_file, 'r', encoding='utf-8') as f:
                ctx_data = yaml.safe_load(f) or {}
            
            deps = ctx_data.get('dependencies', [])
            if isinstance(deps, list):
                for dep in deps:
                    if isinstance(dep, str):
                        # Extract just the module/file name
                        dep_name = dep.split('.')[-1]
                        deps_to_check.add(dep_name)
        except:
            pass
    
    # Add context files for dependencies
    for dep in deps_to_check:
        for source_name, ctx_file in qontext_lookup.items():
            if dep in source_name or source_name.startswith(dep):
                relevant_files.add(ctx_file)
    
    return list(relevant_files)


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

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


def _run_llamacpp(model, prompt, timeout=DEFAULT_API_TIMEOUT, options=None):
    """
    Local Llama.cpp (or compatible) provider using OpenAI chat completions.
    Supports dynamic base_url resolution for Docker/Podman environments.
    """
    options = options or {}
    
    # 1. Base URL Resolution (EXACT FALLBACK ORDER per v1.2.2 spec)
    # Priority: 
    # 1. env QONQ_LLAMACPP_BASE_URL
    # 2. config llamacpp.base_url
    # 3. if podman: http://host.containers.internal:8080/v1
    # 4. if docker: http://host.docker.internal:8080/v1
    # 5. FINAL fallback: http://127.0.0.1:8080/v1
    
    base_url = os.environ.get("QONQ_LLAMACPP_BASE_URL")
    
    if not base_url:
        base_url = options.get("base_url")
        
    if not base_url:
        engine = os.environ.get("QONQ_CONTAINER_ENGINE", "").lower()
        if engine == "podman":
            base_url = "http://host.containers.internal:8080/v1"
        elif engine == "docker":
            base_url = "http://host.docker.internal:8080/v1"
            
    if not base_url:
        base_url = "http://127.0.0.1:8080/v1"
            
    api_key = os.environ.get("QONQ_LLAMACPP_API_KEY", "llamacpp-local")
    
    # 2. api_style validation (STRICT: only 'openai' allowed)
    api_style = options.get("api_style", "openai").lower()
    if api_style != "openai":
        raise RuntimeError(f"llamacpp: Invalid api_style '{api_style}'. ONLY 'openai' is supported for v1.2.2.")

    # Extract common LLM params from nested config
    temp = options.get("temperature", 0.3)
    top_p = options.get("top_p", 0.9)
    max_tokens = options.get("max_tokens", 4096)
    extra_body = options.get("extra_body", {})
    extra_headers = options.get("extra_headers", {})

    try:
        # Use OpenAI SDK as the generic HTTP client
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            default_headers=extra_headers
        )
        
        response_stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=temp,
            top_p=top_p,
            max_tokens=max_tokens,
            extra_body=extra_body,
            timeout=timeout # Ensure timeout is passed to the specific call
        )
        
        captured_chunks = []
        for chunk in response_stream:
            if hasattr(chunk, 'choices') and chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    captured_chunks.append(content)
                    sys.stderr.write(content)
                    sys.stderr.flush()
        return "".join(captured_chunks).strip()

    except openai.APITimeoutError as e:
        raise TimeoutError(f"llamacpp: Connection timed out after {timeout}s at {base_url}. "
                           "Ensure the model is loaded and the server is responsive.") from e
    except openai.APIConnectionError as e:
        raise RuntimeError(f"llamacpp: Connection refused or failed at {base_url}. "
                           "Is the Llama.cpp server running with --api? (Connection Error)") from e
    except openai.APIStatusError as e:
        raise RuntimeError(f"llamacpp: Invalid endpoint or server error (HTTP {e.status_code}) at {base_url}. "
                           f"Details: {e.response.text}") from e
    except Exception as e:
        raise RuntimeError(f"llamacpp: Malformed response or unexpected error from {base_url}: {e}") from e


def _run_openai(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """OpenAI provider with streaming and timeout."""
    try:
        client = openai.OpenAI(timeout=timeout)
        response_stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            timeout=timeout
        )
        captured_chunks = []
        for chunk in response_stream:
            content = chunk.choices[0].delta.content
            if content:
                captured_chunks.append(content)
                sys.stderr.write(content)
                sys.stderr.flush()
        return "".join(captured_chunks).strip()
    except openai.APITimeoutError as e:
        raise TimeoutError(f"OpenAI API timeout after {timeout}s") from e
    except openai.APIError as e:
        raise RuntimeError(f"OpenAI API error: {e}") from e


def _run_gemini(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """Gemini provider with streaming and timeout."""
    try:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Gemini API key not found (checked GOOGLE_API_KEY and GEMINI_API_KEY)")
            
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel(model)
        # Note: google-generativeai doesn't support timeout directly in generate_content
        # Timeout is handled at the transport level
        response_stream = client.generate_content(
            prompt, 
            stream=True,
            request_options={"timeout": timeout}
        )
        
        captured_chunks = []
        for chunk in response_stream:
            text = getattr(chunk, 'text', None)
            if text:
                captured_chunks.append(text)
                sys.stderr.write(text)
                sys.stderr.flush()
        return "".join(captured_chunks).strip()
    except Exception as e:
        if "timeout" in str(e).lower() or "deadline" in str(e).lower():
            raise TimeoutError(f"Gemini API timeout after {timeout}s") from e
        raise RuntimeError(f"Gemini API error: {e}") from e


def _run_anthropic(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """Anthropic provider with streaming and timeout."""
    try:
        client = anthropic.Anthropic(timeout=timeout)
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
    except anthropic.APITimeoutError as e:
        raise TimeoutError(f"Anthropic API timeout after {timeout}s") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}") from e


def _run_deepseek(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """DeepSeek provider with streaming output and timeout."""
    provider = DeepSeekProvider(model=model, timeout=timeout)
    captured_chunks = []
    for chunk in provider.query_streaming(prompt):
        captured_chunks.append(chunk)
        sys.stderr.write(chunk)
        sys.stderr.flush()
    return "".join(captured_chunks).strip()


def _run_qwen(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """Qwen provider via DashScope OpenAI-compatible endpoint with streaming."""
    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise ValueError("QWEN_API_KEY not found in environment.")
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=timeout,
        )
        response_stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        captured_chunks = []
        for chunk in response_stream:
            content = chunk.choices[0].delta.content
            if content:
                captured_chunks.append(content)
                sys.stderr.write(content)
                sys.stderr.flush()
        return "".join(captured_chunks).strip()
    except openai.APITimeoutError as e:
        raise TimeoutError(f"Qwen API timeout after {timeout}s") from e
    except openai.APIError as e:
        raise RuntimeError(f"Qwen API error: {e}") from e


def _run_openrouter(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """OpenRouter provider via OpenAI-compatible endpoint with streaming."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment.")
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout,
        )
        response_stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        captured_chunks = []
        for chunk in response_stream:
            content = chunk.choices[0].delta.content
            if content:
                captured_chunks.append(content)
                sys.stderr.write(content)
                sys.stderr.flush()
        return "".join(captured_chunks).strip()
    except openai.APITimeoutError as e:
        raise TimeoutError(f"OpenRouter API timeout after {timeout}s") from e
    except openai.APIError as e:
        raise RuntimeError(f"OpenRouter API error: {e}") from e
