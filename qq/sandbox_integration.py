"""
Sandbox integration module — bridge between sandbox.py and adapters.

Provides the integration point where adapters can wrap agent subprocess
commands with bubblewrap sandboxing without knowing bubblewrap internals.

This is the "adapter API design" from bubble.md section 12:
  - create sandbox wrapper utility that receives AgentCallSpec and original command
  - adapter asks: maybe_wrap_command_for_sandbox(spec, command, env)
  - returns wrapped command/env/cwd
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .sandbox import (
    BubblewrapSandbox,
    SandboxMode,
    SandboxSpec,
    SandboxUnavailable,
    SandboxPolicyViolation,
    get_sandbox_mode,
    get_sandbox_network,
    get_extra_ro_binds,
    resolve_bwrap_binary,
    bwrap_available,
    validate_sandbox_paths,
    scan_for_symlink_escapes,
)

logger = logging.getLogger(__name__)


def maybe_wrap_command_for_sandbox(
    spec,
    original_cmd: list[str],
    original_env: dict[str, str],
    event_log=None,
) -> tuple[list[str], dict[str, str], Optional[str]]:
    """Wrap a command with bwrap sandbox if sandbox mode requires it.

    Args:
        spec: AgentCallSpec with:
            - role: "qlarifier" | "instruqtor" | "construqtor" | "inspeqtor"
            - workspace_root: project directory
            - run_root: metadata directory
            - cwd / cd / workdir: working directory
        original_cmd: The original command list to run
        original_env: The original environment dict
        event_log: Optional EventLog for emitting sandbox events

    Returns:
        (wrapped_cmd, wrapped_env, new_cwd) tuple.
        - wrapped_cmd: the command to execute (possibly bwrap-wrapped)
        - wrapped_env: the environment to use
        - new_cwd: the cwd to use for the host subprocess (may change if sandboxed)

        If sandbox is off or unavailable in auto mode, returns original values
        with new_cwd=None (meaning "don't change cwd").

    Raises:
        SandboxUnavailable: if sandbox is required but bwrap is unavailable
        SandboxPolicyViolation: if path validation fails
    """
    role = getattr(spec, "role", "")

    # Bubblewrap sandbox wrapping has been REMOVED for all roles.
    # QonQrete must NOT wrap CodeSeeq/Codex with an additional sandbox layer.
    # CodeSeeq/Codex provides its own sandboxing; double-isolation breaks bridge
    # state, host runtime deps, and writable paths, causing construQtor to fail.
    # The bubblewrap binary and sandbox.py infrastructure are kept installed
    # but the actual wrapping of subprocess commands is disabled.
    # See: ultimate-fix.md
    if True:  # All sandbox wrapping disabled — see comment above
        return original_cmd, original_env, None

    mode = get_sandbox_mode()
    network = get_sandbox_network()

    if mode == SandboxMode.OFF:
        if event_log:
            event_log.emit(
                "sandbox_disabled",
                role=role,
                reason="sandbox_mode_off",
            )
        return original_cmd, original_env, None

    # Build sandbox spec — gather paths first
    ws_root = (
        getattr(spec, "workspace_root", "")
        or getattr(spec, "repo_root", "")
        or ""
    )
    run_root = getattr(spec, "run_root", "") or ""
    cwd = (
        getattr(spec, "cd", "")
        or getattr(spec, "workdir", "")
        or ws_root
    )

    if not ws_root or not run_root:
        # Not enough context to sandbox (e.g., ad-hoc adapter calls in tests).
        # Skip sandboxing silently — the path guards and post-scan will still catch violations.
        return original_cmd, original_env, None

    bwrap_bin = resolve_bwrap_binary()

    if bwrap_bin is None:
        if mode == SandboxMode.REQUIRED:
            if event_log:
                event_log.emit(
                    "sandbox_unavailable",
                    role=role,
                    mode="required",
                    error="bwrap not found",
                )
            raise SandboxUnavailable("bwrap not found")
        else:
            # auto mode — warn and fall back
            if event_log:
                event_log.emit(
                    "sandbox_unavailable",
                    role=role,
                    mode="auto",
                    error="bwrap not found; falling back to path guards",
                )
            logger.warning(
                "construQtor sandbox is in 'auto' mode but bwrap is unavailable. "
                "Falling back to path guards only."
            )
            return original_cmd, original_env, None

    sandbox = BubblewrapSandbox(bwrap_bin=bwrap_bin)

    sandbox_spec = SandboxSpec(
        role=role,
        workspace_root=ws_root,
        run_root=run_root,
        command=list(original_cmd),
        cwd=cwd,
        env=dict(original_env),
        network=network,
        writable_tmp=True,
        extra_ro_binds=get_extra_ro_binds(),
    )

    try:
        # Rewrite command paths for sandbox environment:
        # - prompt file path: replace host run_root/sandbox/input/<id>/prompt.md
        #   with /qonqrete/input/prompt.md
        # - cd paths: replace host workspace path with /workspace
        rewritten_cmd = list(sandbox_spec.command)
        ws_root_resolved = os.path.abspath(ws_root)
        sandbox_input_base = os.path.abspath(os.path.join(run_root, "sandbox", "input"))
        
        for i, arg in enumerate(rewritten_cmd):
            # Rewrite prompt file paths (after -f flag)
            if arg == "-f" and i + 1 < len(rewritten_cmd):
                host_prompt = rewritten_cmd[i + 1]
                try:
                    host_prompt_abs = os.path.abspath(host_prompt)
                    if host_prompt_abs.startswith(sandbox_input_base + os.sep) or host_prompt_abs == sandbox_input_base:
                        # Extract the relative part after sandbox/input/
                        rel = os.path.relpath(host_prompt_abs, sandbox_input_base)
                        rewritten_cmd[i + 1] = "/qonqrete/input/" + rel
                except (ValueError, OSError):
                    pass
            # Rewrite --cd paths
            if arg == "--cd" and i + 1 < len(rewritten_cmd):
                host_cd = rewritten_cmd[i + 1]
                try:
                    host_cd_abs = os.path.abspath(host_cd)
                    ws_abs = os.path.abspath(ws_root)
                    if host_cd_abs == ws_abs or host_cd_abs.startswith(ws_abs + os.sep):
                        rewritten_cmd[i + 1] = "/workspace"
                except (ValueError, OSError):
                    pass

        sandbox_spec.command = rewritten_cmd
        wrapped_cmd = sandbox.build_command(sandbox_spec)

        if event_log:
            event_log.emit(
                "sandbox_enabled",
                role=role,
                engine="bubblewrap",
                workspace_root=ws_root,
                run_root=run_root,
                network=network,
            )

        # When running inside bwrap, the host cwd doesn't matter much since
        # bwrap does --chdir /workspace. But we set it to ws_root for
        # consistency and so any pre-bwrap validation works correctly.
        wrapped_env = dict(original_env)
        # Bridge fix: inside bwrap, the process bridge can't start because
        # Python site-packages (fastapi, uvicorn, httpx) are not ro-bound
        # into the sandbox. Switch to external mode pointing at the host's
        # already-running bridge. With --share-net, localhost is reachable.
        #
        # The host bridge URL is discovered via the codeseeq config TOML,
        # the standard env vars, or the well-known default port 8081.
        host_bridge_url = _discover_host_bridge_url(wrapped_env)
        if host_bridge_url and wrapped_env.get("CODESEEQ_BRIDGE_MODE", "") == "process":
            wrapped_env["CODESEEQ_BRIDGE_MODE"] = "external"
            wrapped_env["CODESEEQ_BRIDGE_BASE_URL"] = host_bridge_url
            if event_log:
                event_log.emit(
                    "sandbox_bridge_reroute",
                    role=role,
                    reason="bridge_mode_switched_to_external_for_sandbox",
                    bridge_url=host_bridge_url,
                )

        # The new cwd for the host subprocess — bwrap uses --chdir /workspace
        # internally for the actual agent process.
        new_cwd = ws_root

        return wrapped_cmd, wrapped_env, new_cwd

    except SandboxPolicyViolation:
        if event_log:
            event_log.emit(
                "sandbox_failed",
                role=role,
                exit_code=-1,
                reason="policy_violation",
            )
        raise


def emit_sandbox_disabled_event(event_log, role: str, reason: str) -> None:
    """Emit a sandbox_disabled event when sandbox is explicitly off."""
    if event_log:
        event_log.emit(
            "sandbox_disabled",
            role=role,
            reason=reason,
        )


def _discover_host_bridge_url(env: dict) -> str:
    """Discover the host-side codeseeq bridge URL for sandbox use.

    Checks (in order):
      1. CODESEEQ_BRIDGE_BASE_URL env var (already set explicitly)
      2. codeseeq config TOML base_url (host config, not sandbox config)
      3. CODESEEQ_OPENRESPONSES_URL env var (set by codeseeq wrapper)
      4. Well-known default: http://127.0.0.1:8081/v1

    Returns the bridge URL or empty string if undiscoverable.
    """
    import configparser

    # 1. Already explicitly set in our env
    explicit = env.get("CODESEEQ_BRIDGE_BASE_URL", "")
    if explicit:
        return explicit

    # 2. Check host codeseeq config TOML  
    host_codeseeq_home = os.environ.get(
        "CODEX_HOME",
        os.path.join(os.path.expanduser("~"), ".codeseeq"),
    )
    config_toml = os.path.join(host_codeseeq_home, "config.toml")

    try:
        if os.path.isfile(config_toml):
            parser = configparser.ConfigParser()
            parser.read(config_toml)
            # Look for base_url under [model_providers.codeseeq]
            if parser.has_option("model_providers.codeseeq", "base_url"):
                return parser.get("model_providers.codeseeq", "base_url")
    except Exception:
        pass

    # 3. Check the well-known env var set by codeseeq wrapper
    well_known = os.environ.get("CODESEEQ_OPENRESPONSES_URL", "")
    if well_known:
        return well_known

    # 4. Fallback to well-known default port
    return "http://127.0.0.1:8081/v1"
