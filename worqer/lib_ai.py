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
import json
import urllib.request
import urllib.error
import anthropic
import openai
import google.generativeai as genai
from worqer.lib_security import (
    get_security_logger, sanitize_traceback,
    MAX_TIMEOUT_SECONDS, MAX_RETRIES_HARD_LIMIT
)
try:
    from worqer.lib_provider_config import is_zero_cost_provider, normalize_llamacpp_endpoint
except ImportError:
    from lib_provider_config import is_zero_cost_provider, normalize_llamacpp_endpoint

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


def run_ai_completion(
    provider: str,
    model: str,
    prompt: str,
    context_files: list[str] = None,
    max_prompt_chars: int = None,
    max_context_files: int = None,
    max_chars_per_file: int = None,
    timeout: int = None,
    request_options: dict | None = None,
) -> str:
    """
    Execute AI completion with budget enforcement.

    Args:
        provider: AI provider name (openai, gemini, anthropic, deepseek, qwen, openrouter, llamacpp)
        model: Model identifier
        prompt: Base prompt content
        context_files: Optional list of file paths to include as architectural context
        max_prompt_chars: Override default max prompt size
        max_context_files: Override default max number of context files
        max_chars_per_file: Override default max chars per individual file
        timeout: Optional provider request timeout override
        request_options: Optional provider-specific runtime options

    Returns:
        AI response content

    Raises:
        ValueError: If provider is unknown
        RuntimeError: If AI call fails
    """
    if context_files is None:
        context_files = []

    if request_options is None:
        request_options = {}

    # Apply budget limits
    budget_config = {
        'max_prompt_chars': max_prompt_chars or DEFAULT_MAX_PROMPT_CHARS,
        'max_context_files': max_context_files or DEFAULT_MAX_CONTEXT_FILES,
        'max_chars_per_file': max_chars_per_file or DEFAULT_MAX_CHARS_PER_FILE,
    }

    full_prompt = _build_prompt(prompt, context_files, budget_config)
    effective_timeout = timeout or request_options.get('timeout') or DEFAULT_API_TIMEOUT

    try:
        provider_lc = provider.lower()
        if provider_lc == 'openai':
            return _run_openai(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'gemini':
            return _run_gemini(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'anthropic':
            return _run_anthropic(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'deepseek':
            return _run_deepseek(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'qwen':
            return _run_qwen(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'openrouter':
            return _run_openrouter(model, full_prompt, timeout=effective_timeout)
        elif provider_lc == 'llamacpp':
            return _run_llamacpp(model, full_prompt, timeout=effective_timeout, request_options=request_options)
        else:
            raise ValueError(f"Unknown AI Provider: {provider}")
    except Exception as e:
        sys.stderr.write(f"\n[AI ERROR - {provider.upper()}]: {e}\n")
        raise


def ai_query(prompt: str, provider: str, model: str, timeout: int = None, request_options: dict | None = None) -> str:
    """Backward-compatible lightweight wrapper used by older call sites."""
    return run_ai_completion(
        provider=provider,
        model=model,
        prompt=prompt,
        timeout=timeout,
        request_options=request_options,
    )

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


def _extract_stream_content(chunk) -> str | None:
    try:
        if not getattr(chunk, 'choices', None):
            return None
        delta = chunk.choices[0].delta
        if delta is None:
            return None
        content = getattr(delta, 'content', None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif hasattr(item, 'text') and item.text:
                    parts.append(item.text)
                elif isinstance(item, dict) and item.get('text'):
                    parts.append(item['text'])
            return ''.join(parts) if parts else None
        return None
    except Exception:
        return None


def _stream_openai_chat_completion(client, request_kwargs, provider_label: str, timeout: int) -> str:
    try:
        response_stream = client.chat.completions.create(stream=True, timeout=timeout, **request_kwargs)
        captured_chunks = []
        for chunk in response_stream:
            content = _extract_stream_content(chunk)
            if content:
                captured_chunks.append(content)
                sys.stderr.write(content)
                sys.stderr.flush()
        return ''.join(captured_chunks).strip()
    except openai.APITimeoutError as e:
        raise TimeoutError(f"{provider_label} API timeout after {timeout}s") from e
    except openai.APIError as e:
        raise RuntimeError(f"{provider_label} API error: {e}") from e


def _run_openai(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """OpenAI provider with streaming and timeout."""
    client = openai.OpenAI(timeout=timeout)
    return _stream_openai_chat_completion(
        client,
        {
            'model': model,
            'messages': [{"role": "user", "content": prompt}],
        },
        'OpenAI',
        timeout,
    )


def _run_gemini(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """Gemini provider with streaming and timeout."""
    try:
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        client = genai.GenerativeModel(model)
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
        return ''.join(captured_chunks).strip()
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
        return ''.join(captured_chunks).strip()
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
    return ''.join(captured_chunks).strip()


def _run_qwen(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """Qwen provider via DashScope OpenAI-compatible endpoint with streaming."""
    api_key = os.environ.get("QWEN_API_KEY")
    if not api_key:
        raise ValueError("QWEN_API_KEY not found in environment.")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout=timeout,
    )
    return _stream_openai_chat_completion(
        client,
        {
            'model': model,
            'messages': [{"role": "user", "content": prompt}],
        },
        'Qwen',
        timeout,
    )


def _run_openrouter(model, prompt, timeout=DEFAULT_API_TIMEOUT):
    """OpenRouter provider via OpenAI-compatible endpoint with streaming."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment.")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=timeout,
    )
    return _stream_openai_chat_completion(
        client,
        {
            'model': model,
            'messages': [{"role": "user", "content": prompt}],
        },
        'OpenRouter',
        timeout,
    )


def _normalize_model_env_hint(model: str) -> str:
    return os.path.expandvars((model or '').strip())


def _model_basename_candidates(*values: str) -> list[str]:
    basenames = []
    seen = set()
    for value in values:
        if not value:
            continue
        basename = os.path.basename(value.strip())
        if basename and basename not in seen:
            seen.add(basename)
            basenames.append(basename)
    return basenames


def _build_llamacpp_model_match_profile(configured_model: str) -> dict[str, str | list[str]]:
    raw = (configured_model or '').strip()
    env_expanded = _normalize_model_env_hint(raw)
    tilde_expanded = ''
    if raw.startswith('~'):
        tilde_expanded = os.path.expanduser(env_expanded or raw)

    return {
        'raw': raw,
        'env_expanded': env_expanded,
        'tilde_expanded': tilde_expanded,
        'basenames': _model_basename_candidates(raw, env_expanded, tilde_expanded),
    }


def _fetch_llamacpp_models(endpoint: str, timeout: int, api_key: str) -> list[dict]:
    models_url = endpoint.rstrip('/') + '/models'
    request = urllib.request.Request(models_url)
    request.add_header('Accept', 'application/json')
    if api_key and api_key != 'sk-no-key-required':
        request.add_header('Authorization', f'Bearer {api_key}')

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))

    data = payload.get('data', []) if isinstance(payload, dict) else []
    return data if isinstance(data, list) else []


def _llamacpp_endpoint_help(candidate: str | None = None) -> str:
    parts = [
        'Make sure llama-server is already running on the host machine.',
        'Docker Desktop users usually want http://host.docker.internal:8080/v1.',
        'Podman users usually want http://host.containers.internal:8080/v1.',
        'Direct non-container testing can use http://localhost:8080/v1.',
    ]
    if candidate:
        parts.insert(0, f'Endpoint tried: {candidate}')
    return ' '.join(parts)


def _iter_llamacpp_entry_candidates(entry: dict) -> list[str]:
    values = []
    for key in ('id', 'root', 'parent', 'alias'):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    aliases = entry.get('aliases')
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                values.append(alias.strip())

    deduped = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _select_llamacpp_model_id(configured_model: str, endpoint: str, timeout: int, api_key: str) -> str:
    profile = _build_llamacpp_model_match_profile(configured_model)
    raw_configured = str(profile['raw'])
    env_expanded = str(profile['env_expanded'])
    tilde_expanded = str(profile['tilde_expanded'])
    basename_candidates = list(profile['basenames'])

    exact_match_candidates = [value for value in (raw_configured, env_expanded) if value]
    comparison_candidates = [value for value in (raw_configured, env_expanded, tilde_expanded) if value]

    try:
        server_models = _fetch_llamacpp_models(endpoint, timeout, api_key)
    except Exception as exc:
        sys.stderr.write(
            f"\n[LLAMACPP] Warning: could not preflight {endpoint}/models ({exc}). "
            f"{_llamacpp_endpoint_help(endpoint)}\n"
        )
        return raw_configured or env_expanded or configured_model

    if not server_models:
        sys.stderr.write(
            f"\n[LLAMACPP] Warning: server returned no /models entries at {endpoint}. "
            "The server may still answer requests, but model reconciliation is unavailable. "
            "Trying the configured model string as-is.\n"
        )
        return raw_configured or env_expanded or configured_model

    ids = []
    alias_matches = []
    basename_matches = []
    for entry in server_models:
        model_id = str(entry.get('id', '')).strip()
        if model_id:
            ids.append(model_id)

        candidates = _iter_llamacpp_entry_candidates(entry)
        if any(candidate in candidates for candidate in exact_match_candidates) and model_id:
            return model_id
        if any(candidate == model_id for candidate in exact_match_candidates):
            return model_id
        if any(candidate in candidates for candidate in comparison_candidates) and model_id:
            alias_matches.append(model_id)
        if basename_candidates and any(os.path.basename(candidate) in basename_candidates for candidate in candidates) and model_id:
            basename_matches.append(model_id)

    alias_matches = list(dict.fromkeys(alias_matches))
    basename_matches = list(dict.fromkeys(basename_matches))
    ids = list(dict.fromkeys(ids))

    if len(alias_matches) == 1:
        matched = alias_matches[0]
        sys.stderr.write(
            f"\n[LLAMACPP] Configured model matched a server alias/root entry: using '{matched}' instead of '{raw_configured or configured_model}'\n"
        )
        return matched

    if len(basename_matches) == 1:
        matched = basename_matches[0]
        sys.stderr.write(
            f"\n[LLAMACPP] Model basename matched server id: using '{matched}' instead of '{raw_configured or configured_model}'\n"
        )
        return matched

    if len(ids) == 1:
        only_id = ids[0]
        server_basename = os.path.basename(only_id)
        if basename_candidates and server_basename in basename_candidates:
            sys.stderr.write(
                f"\n[LLAMACPP] Server exposes a single model id '{only_id}'; using it for configured path '{raw_configured or configured_model}'\n"
            )
            return only_id

        if raw_configured == only_id or env_expanded == only_id:
            return only_id

        sys.stderr.write(
            f"\n[LLAMACPP] Warning: configured model '{raw_configured or configured_model}' does not match server model '{only_id}'. "
            f"Trying configured value as-is instead of any container-expanded path. Available server id: {only_id}\n"
        )
        return raw_configured or env_expanded or configured_model

    preview = ', '.join(ids[:5])
    if len(ids) > 5:
        preview += ', ...'

    sys.stderr.write(
        f"\n[LLAMACPP] Warning: configured model '{raw_configured or configured_model}' was not found in server /models list at {endpoint}. "
        f"Available ids: {preview}. Trying configured value as-is.\n"
    )
    return raw_configured or env_expanded or configured_model
def _build_llamacpp_request_kwargs(model: str, prompt: str, request_options: dict) -> dict:
    kwargs = {
        'model': model,
        'messages': [{"role": "user", "content": prompt}],
    }

    if request_options.get('max_tokens') is not None:
        kwargs['max_tokens'] = request_options.get('max_tokens')
    if request_options.get('temperature') is not None:
        kwargs['temperature'] = request_options.get('temperature')
    if request_options.get('top_p') is not None:
        kwargs['top_p'] = request_options.get('top_p')
    if request_options.get('presence_penalty') is not None:
        kwargs['presence_penalty'] = request_options.get('presence_penalty')
    if request_options.get('frequency_penalty') is not None:
        kwargs['frequency_penalty'] = request_options.get('frequency_penalty')
    if request_options.get('stop') is not None:
        kwargs['stop'] = request_options.get('stop')

    extra_body = {}
    for key in ('top_k', 'min_p', 'seed', 'repeat_penalty', 'mirostat', 'mirostat_tau', 'mirostat_eta'):
        value = request_options.get(key)
        if value is not None:
            extra_body[key] = value

    if extra_body:
        kwargs['extra_body'] = extra_body

    return kwargs


def _run_llamacpp(model, prompt, timeout=DEFAULT_API_TIMEOUT, request_options=None):
    """llama.cpp provider via an OpenAI-compatible HTTP endpoint with streaming."""
    request_options = request_options or {}
    api_key = os.getenv('LLAMACPP_API_KEY', 'sk-no-key-required')
    endpoint_candidates = request_options.get('endpoint_candidates') or []

    endpoint = normalize_llamacpp_endpoint(request_options.get('endpoint'))
    if endpoint and endpoint not in endpoint_candidates:
        endpoint_candidates = [endpoint] + endpoint_candidates

    if not endpoint_candidates:
        raise ValueError(
            'No llama.cpp endpoint configured. Set agents.<agent>.endpoint, providers.llamacpp.endpoint, '
            'LLAMACPP_ENDPOINT, or QONQ_LLAMACPP_ENDPOINT.'
        )

    last_error = None
    configured_model = (model or '').strip() or model

    for candidate in endpoint_candidates:
        try:
            client = openai.OpenAI(
                api_key=api_key,
                base_url=candidate,
                timeout=timeout,
            )
            resolved_model = _select_llamacpp_model_id(configured_model, candidate, timeout, api_key)
            request_kwargs = _build_llamacpp_request_kwargs(resolved_model, prompt, request_options)
            return _stream_openai_chat_completion(client, request_kwargs, 'llama.cpp', timeout)
        except Exception as exc:
            last_error = exc
            sys.stderr.write(
                f"\n[LLAMACPP] Endpoint failed ({candidate}): {exc}. {_llamacpp_endpoint_help(candidate)}\n"
            )

    raise RuntimeError(
        'llama.cpp request failed for all configured endpoints. '
        f'Last error: {last_error}. {_llamacpp_endpoint_help(endpoint_candidates[0] if endpoint_candidates else None)}'
    )

