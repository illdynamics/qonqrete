"""
Environment helpers — shared env-building for CodeSeeq and skill subprocesses.

Ensures CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES and CODESEEQ_RUNTIME_MODE
are consistently propagated to every CodeSeeq invocation, skill subprocess,
and image-generation call.
"""
from __future__ import annotations

import os
from typing import Mapping


def build_codeseeq_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a clean environment dict for CodeSeeq/skill subprocesses.

    Always includes:
      CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES (default: "true")
      CODESEEQ_RUNTIME_MODE (default: "host")

    User-set values are preserved; only missing keys get defaults.

    Args:
        base_env: Optional base environment dict. If None, uses os.environ.

    Returns:
        A new dict with the required CodeSeeq env vars.
    """
    env = dict(os.environ if base_env is None else base_env)
    env.setdefault("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES", "true")
    env.setdefault("CODESEEQ_RUNTIME_MODE", "host")
    return env


def check_upstream_services_enabled(env: Mapping[str, str] | None = None) -> tuple[bool, str]:
    """Check whether upstream Codex services are properly configured.

    Returns:
        (True, "") if everything is configured correctly.
        (False, reason) if something is missing or misconfigured.
    """
    e = env if env is not None else os.environ
    allow_raw = e.get("CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES")
    runtime_raw = e.get("CODESEEQ_RUNTIME_MODE")
    allow = allow_raw.strip().lower() if allow_raw else ""
    runtime = runtime_raw.strip().lower() if runtime_raw else ""

    reasons = []
    if allow != "true":
        if allow_raw is None:
            reasons.append(
                "CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES is missing "
                "(must be 'true')"
            )
        else:
            reasons.append(
                f"CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES is "
                f"{allow_raw!r} (must be 'true')"
            )
    if runtime != "host":
        if runtime_raw is None:
            reasons.append(
                "CODESEEQ_RUNTIME_MODE is missing (must be 'host')"
            )
        else:
            reasons.append(
                f"CODESEEQ_RUNTIME_MODE is {runtime_raw!r} (must be 'host')"
            )

    if reasons:
        return False, "; ".join(reasons)
    return True, ""


def upstream_codex_services_available() -> bool:
    """Return True if upstream Codex services are configured and enabled."""
    ok, _ = check_upstream_services_enabled()
    return ok

def get_venice_api_key() -> str | None:
    """Return the VENICE_API_KEY environment variable, or None."""
    key = os.environ.get("VENICE_API_KEY", "").strip()
    return key if key else None


def venice_available() -> bool:
    """Return True if VENICE_API_KEY is set and non-empty."""
    return get_venice_api_key() is not None


def check_venice_configured() -> tuple[bool, str]:
    """Check if Venice API is properly configured for image generation.

    Returns:
        (True, "") if everything is configured correctly.
        (False, reason) if something is missing or misconfigured.
    """
    key = get_venice_api_key()
    if not key:
        return False, (
            "VENICE_API_KEY is not set. Set it in your environment or .env file. "
            "Get a key at https://venice.ai/settings/api"
        )
    return True, ""
