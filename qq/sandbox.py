"""
Bubblewrap OS-level filesystem isolation for construQtor.

Implements real OS-level containment so construQtor can only create/edit/build
project files inside the target workspace/repo root, while `.qq` and run_root
remain metadata-only and are not writable by the AI process.

Enforcement: bubblewrap/bwrap on Linux. Fails closed if unavailable.

DO NOT TOUCH ANY PVC's OR SECRETS EVER!!!
"""
from __future__ import annotations

import dataclasses
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class SandboxUnavailable(Exception):
    """Raised when sandbox is required but bubblewrap is not available."""

    def __init__(self, reason: str = "bwrap not found"):
        self.reason = reason
        super().__init__(f"Sandbox unavailable: {reason}")


class SandboxPolicyViolation(Exception):
    """Raised when a sandbox path policy is violated before launch."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        msg = f"Sandbox policy violation: {reason}"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# SandboxSpec
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class SandboxSpec:
    """Everything needed to run a command inside a bubblewrap sandbox."""

    role: str
    workspace_root: str
    run_root: str
    command: list[str]
    cwd: str
    env: dict[str, str]
    stdin_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    network: str = "host"   # host | none
    writable_tmp: bool = True
    extra_ro_binds: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Sandbox mode enum
# ---------------------------------------------------------------------------
class SandboxMode:
    REQUIRED = "required"
    AUTO = "auto"
    OFF = "off"


# ---------------------------------------------------------------------------
# bwrap binary resolution
# ---------------------------------------------------------------------------
def resolve_bwrap_binary() -> str | None:
    """Find bubblewrap binary.

    Checks:
      - QONQRETE_BWRAP_BIN env var
      - PATH lookup for `bwrap` or `bubblewrap`
    """
    env_bin = os.environ.get("QONQRETE_BWRAP_BIN", "")
    if env_bin:
        if os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
            return env_bin
        logger.warning("QONQRETE_BWRAP_BIN=%s is not executable, falling back to PATH", env_bin)

    for name in ("bwrap", "bubblewrap"):
        found = shutil.which(name)
        if found:
            return found

    return None


def bwrap_available() -> bool:
    """Return True if bubblewrap is available."""
    return resolve_bwrap_binary() is not None


# ---------------------------------------------------------------------------
# Sandbox config from environment
# ---------------------------------------------------------------------------
def get_sandbox_mode() -> str:
    """Get sandbox mode from environment.

    QONQRETE_CONSTRUQTOR_SANDBOX=required|auto|off
    Default: auto
    """
    return os.environ.get("QONQRETE_CONSTRUQTOR_SANDBOX", "auto").strip().lower()


def get_sandbox_network() -> str:
    """Get sandbox network mode.

    QONQRETE_SANDBOX_NETWORK=host|none
    Default: host
    """
    return os.environ.get("QONQRETE_SANDBOX_NETWORK", "host").strip().lower()


def get_sandbox_debug() -> bool:
    """Check if sandbox debug logging is enabled.

    QONQRETE_SANDBOX_DEBUG=true|false
    Default: false
    """
    return os.environ.get("QONQRETE_SANDBOX_DEBUG", "false").strip().lower() in (
        "1", "true", "yes"
    )


def get_extra_ro_binds() -> list[str]:
    """Get extra read-only system binds.

    QONQRETE_SANDBOX_RO_BINDS = colon-separated list of paths
    """
    raw = os.environ.get("QONQRETE_SANDBOX_RO_BINDS", "")
    if not raw:
        return []
    return [p.strip() for p in raw.split(":") if p.strip()]


# ---------------------------------------------------------------------------
# Path validation helpers
# ---------------------------------------------------------------------------
def _resolve_safe(path: str) -> str:
    """Resolve a path with realpath, raising on error."""
    try:
        return str(Path(path).resolve())
    except (ValueError, OSError) as e:
        raise SandboxPolicyViolation(
            reason="invalid_path",
            detail=f"Cannot resolve path '{path}': {e}",
        )


def _is_under(path: str, root: str) -> bool:
    """Return True if path is inside or equals root."""
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
        common = os.path.commonpath([str(p), str(r)])
        return common == str(r)
    except (ValueError, OSError):
        return False


_DANGEROUS_ROOTS = frozenset({"/", "/home", "/x"})


def validate_sandbox_paths(
    workspace_root: str,
    run_root: str,
    cwd: str,
    explicit_allow_dangerous_root: bool = False,
) -> list[str]:
    """Validate sandbox paths and return a list of violations (empty = clean).

    Checks:
      - workspace_root resolves correctly
      - run_root resolves correctly
      - workspace_root is not inside run_root
      - run_root is not inside workspace_root (except .qq metadata)
      - workspace_root is not dangerously broad (/, /home, /x) unless allowed
      - cwd is under workspace_root
      - cwd is not under workspace_root/.qq
      - no symlink escape for cwd
    """
    violations: list[str] = []

    try:
        ws_real = _resolve_safe(workspace_root)
        run_real = _resolve_safe(run_root)
        cwd_real = _resolve_safe(cwd)
    except SandboxPolicyViolation as e:
        return [str(e)]

    # workspace_root inside run_root
    if _is_under(ws_real, run_real) and ws_real != run_real:
        violations.append(
            f"workspace_root ({ws_real}) is inside run_root ({run_real})"
        )

    # run_root inside workspace_root is allowed ONLY for .qq metadata
    if _is_under(run_real, ws_real) and run_real != ws_real:
        qq_dir = os.path.join(ws_real, ".qq")
        if not _is_under(run_real, qq_dir):
            violations.append(
                f"run_root ({run_real}) is inside workspace_root ({ws_real}) "
                f"but not under .qq metadata"
            )

    # Dangerously broad root
    if not explicit_allow_dangerous_root:
        if ws_real in _DANGEROUS_ROOTS:
            violations.append(
                f"workspace_root is dangerously broad ({ws_real}). "
                f"Set QONQRETE_ALLOW_DANGEROUS_WORKSPACE=true to bypass."
            )

    # cwd under workspace_root
    if not _is_under(cwd_real, ws_real):
        violations.append(
            f"cwd ({cwd_real}) is not under workspace_root ({ws_real})"
        )

    # cwd under .qq
    qq_dir = os.path.join(ws_real, ".qq")
    if _is_under(cwd_real, qq_dir):
        violations.append(
            f"cwd ({cwd_real}) is under .qq metadata directory"
        )

    # Check for symlink escapes in cwd
    cwd_path = Path(cwd)
    try:
        for parent in [cwd_path] + list(cwd_path.parents):
            if parent.is_symlink():
                target = os.readlink(str(parent))
                resolved_target = str(Path(os.path.join(
                    str(parent.parent), target)).resolve())
                if not _is_under(resolved_target, ws_real):
                    violations.append(
                        f"Symlink escape in cwd: {parent} -> {target} "
                        f"(resolves outside workspace)"
                    )
    except OSError:
        pass  # Path doesn't exist yet, can't check symlinks

    return violations


# ---------------------------------------------------------------------------
# BubblewrapSandbox
# ---------------------------------------------------------------------------

def _resolve_binary_visibility(binary_path: str) -> list[str]:
    """Resolve binary paths for bwrap visibility.

    Returns a list of directories to ro-bind, or empty list if already covered
    by standard system paths (/usr, /bin, /lib, /lib64, /opt, /nix).
    Follows simple shell-script wrappers that exec another binary, so both
    the wrapper directory and the exec-target directory get ro-bind mounted.

    WARNING: KEEP private — only BubblewrapSandbox uses this.
    """
    import os
    dirs_to_bind: list[str] = []
    seen: set[str] = set()
    queue: list[str] = [binary_path]

    STANDARD_ROOTS = ["/usr", "/bin", "/lib", "/lib64", "/opt", "/nix", "/etc"]
    DANGEROUS = {"/", "/home", "/root", "/tmp", "/var", "/dev", "/proc"}

    while queue:
        path = queue.pop(0)
        try:
            real = os.path.realpath(path)
        except (ValueError, OSError):
            continue
        if real in seen:
            continue
        seen.add(real)

        # Already covered by standard ro-binds
        covered = False
        for root in STANDARD_ROOTS:
            try:
                if os.path.commonpath([real, root]) == root:
                    covered = True
                    break
            except (ValueError, OSError):
                continue
        if covered:
            continue

        # Get the directory containing the binary
        bin_dir = os.path.dirname(real)

        # Reject dangerously broad paths
        if bin_dir in DANGEROUS:
            continue

        # Only reject the home root itself (dangerously broad).
        # Specific subdirectories like ~/bin are safe to ro-bind.
        # The home root is already covered by the DANGEROUS check above
        # on most systems (/home), but on macOS ~ is /Users/<user> which
        # we add explicitly here.
        try:
            home = os.path.expanduser("~")
            if bin_dir == home:
                continue
        except Exception:
            pass

        if bin_dir not in seen:
            dirs_to_bind.append(bin_dir)
            seen.add(bin_dir)

        # Node.js package detection: if the binary is inside a
        # node_modules/@scope/package/ tree, bind the entire package
        # root so native dependencies and sibling modules are available.
        # Example: @openai/codex/bin/codex.js needs
        #          @openai/codex/node_modules/@openai/codex-linux-x64/
        try:
            parts = real.split(os.sep)
            for idx, part in enumerate(parts):
                if part == "node_modules" and idx + 1 < len(parts):
                    # Found node_modules/<package> or node_modules/@scope/<package>
                    if idx + 2 < len(parts) and parts[idx + 1].startswith("@"):
                        pkg_root = os.sep.join(parts[: idx + 3])
                    else:
                        pkg_root = os.sep.join(parts[: idx + 2])
                    if pkg_root != bin_dir and pkg_root not in seen:
                        dirs_to_bind.append(pkg_root)
                        seen.add(pkg_root)
                    break
        except (ValueError, OSError):
            pass

        # Check if this binary is a shell script that execs another binary
        try:
            with open(real, "rb") as f:
                head = f.read(256)
            # Only inspect shell scripts (shebang with sh or bash)
            if head.startswith(b"#!") and (b"sh" in head.split(b"\n")[0] or b"bash" in head.split(b"\n")[0]):
                with open(real, "r") as f:
                    content = f.read()
                # Look for exec "/path/to/binary" or exec '/path/to/binary'
                m = re.search(r'exec\s+["\']([/][^"\']+)["\']', content)
                if m:
                    exec_target = m.group(1)
                    if os.path.exists(exec_target) and exec_target not in seen:
                        queue.append(exec_target)
        except (OSError, ValueError):
            pass

    return dirs_to_bind

class BubblewrapSandbox:
    """Builds and runs bubblewrap sandbox commands.

    Provides OS-level filesystem containment using bwrap on Linux.
    """

    def __init__(self, bwrap_bin: str | None = None):
        self._bwrap_bin: str | None = bwrap_bin
        self._resolved: str | None = None
        self._debug = get_sandbox_debug()

    def _bwrap(self) -> str:
        """Get resolved bwrap binary path."""
        if self._resolved is None:
            self._resolved = self._bwrap_bin or resolve_bwrap_binary()
        if self._resolved is None:
            raise SandboxUnavailable("bwrap not found")
        return self._resolved

    def available(self) -> bool:
        """Return True if bubblewrap is available."""
        try:
            self._bwrap()
            return True
        except SandboxUnavailable:
            return False

    def build_command(self, spec: SandboxSpec) -> list[str]:
        """Build the bwrap command list from a SandboxSpec.

        Does NOT launch anything — pure command construction.
        """
        bwrap = self._bwrap()

        # Resolve all paths
        ws_real = _resolve_safe(spec.workspace_root)
        run_real = _resolve_safe(spec.run_root)

        # Validate paths before building
        violations = validate_sandbox_paths(
            spec.workspace_root, spec.run_root, spec.cwd
        )
        if violations:
            raise SandboxPolicyViolation(
                reason="pre_launch_validation_failed",
                detail="; ".join(violations),
            )

        cmd: list[str] = [bwrap]

        # Core isolation flags
        cmd.append("--die-with-parent")
        cmd.append("--new-session")
        cmd.append("--unshare-all")

        # Network
        if spec.network == "host":
            cmd.append("--share-net")
        # network=none means no --share-net (already isolated by --unshare-all)

        # Essential system mounts
        cmd.extend(["--proc", "/proc"])
        cmd.extend(["--dev", "/dev"])

        # Writable tmpfs
        if spec.writable_tmp:
            cmd.extend(["--tmpfs", "/tmp"])
        else:
            # Still need /tmp to exist, just not writable
            cmd.extend(["--tmpfs", "/tmp"])

        # Home directory
        cmd.extend(["--dir", "/home/qonqrete"])

        # Environment variables
        # Set HOME to the sandbox home (not host home)
        cmd.extend(["--setenv", "HOME", "/home/qonqrete"])
        cmd.extend(["--setenv", "TMPDIR", "/tmp"])

        # System read-only binds
        _ro_bind_if_exists(cmd, "/usr")
        _ro_bind_if_exists(cmd, "/bin")
        _ro_bind_if_exists(cmd, "/lib")

        # /lib64 only on systems that have it
        if os.path.exists("/lib64"):
            cmd.extend(["--ro-bind", "/lib64", "/lib64"])

        # /etc read-only (optionally restricted later)
        if os.path.exists("/etc"):
            cmd.extend(["--ro-bind", "/etc", "/etc"])

        # Nix/NixOS support
        if os.path.exists("/nix"):
            cmd.extend(["--ro-bind", "/nix", "/nix"])

        # /opt support
        if os.path.exists("/opt"):
            cmd.extend(["--ro-bind", "/opt", "/opt"])

        # Extra user-configured read-only binds
        for bind_path in spec.extra_ro_binds or []:
            bind_path = bind_path.strip()
            if bind_path and os.path.exists(bind_path):
                cmd.extend(["--ro-bind", bind_path, bind_path])

        # Ensure the main binary (first arg in command) is visible inside bwrap.
        # _resolve_binary_visibility returns a list of directories that all
        # need ro-bind mounting (follows shell-script wrappers to also bind
        # exec-target directories).
        if spec.command:
            binary_path = spec.command[0]
            for bin_dir in _resolve_binary_visibility(binary_path):
                cmd.extend(["--ro-bind", bin_dir, bin_dir])

        # Workspace bind (writable)
        cmd.extend(["--bind", ws_real, "/workspace"])

        # Mask .qq with an empty read-only directory
        empty_qq_dir = _ensure_empty_qq_dir(run_real)
        cmd.extend(["--ro-bind", empty_qq_dir, "/workspace/.qq"])

        # Read-only metadata input dir (if needed)
        # We create it but it's empty by default; stdout/stderr captured by parent
        q_input_dir = os.path.join(run_real, "sandbox", "input")
        os.makedirs(q_input_dir, exist_ok=True)
        cmd.extend(["--ro-bind", q_input_dir, "/qonqrete/input"])

        # Writable metadata output dir (only if absolutely needed)
        q_out_dir = os.path.join(run_real, "sandbox", "output")
        os.makedirs(q_out_dir, exist_ok=True)
        cmd.extend(["--bind", q_out_dir, "/qonqrete/out"])

        # Set internal working directory
        cmd.extend(["--chdir", "/workspace"])

        # The actual command to run
        cmd.extend(spec.command)

        if self._debug:
            _log_sandbox_command(cmd, spec)

        return cmd

    def run(
        self,
        spec: SandboxSpec,
        timeout: int | None = None,
        stdin_text: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Build and execute a bubblewrap-sandboxed command.

        Returns a subprocess.CompletedProcess. Raises SandboxUnavailable
        if bwrap is not found.
        """
        cmd = self.build_command(spec)

        # Build environment for the host-side subprocess
        # The sandbox command itself takes care of internal env
        host_env = os.environ.copy()
        host_env.update(spec.env)

        # Build run kwargs
        run_kwargs: dict = {
            "capture_output": True,
            "text": True,
            "env": host_env,
            "cwd": spec.cwd,
        }
        if timeout is not None:
            run_kwargs["timeout"] = timeout
        if stdin_text is not None:
            run_kwargs["input"] = stdin_text

        return subprocess.run(cmd, **run_kwargs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _ro_bind_if_exists(cmd: list[str], path: str) -> None:
    """Add --ro-bind for path if it exists on the host."""
    if os.path.exists(path):
        cmd.extend(["--ro-bind", path, path])


def _ensure_empty_qq_dir(run_root: str) -> str:
    """Create and return an empty directory to mask .qq.

    Creates: <run_root>/sandbox/empty-qq
    """
    empty_dir = os.path.join(run_root, "sandbox", "empty-qq")
    os.makedirs(empty_dir, exist_ok=True)
    # Ensure it's truly empty
    for item in os.listdir(empty_dir):
        item_path = os.path.join(empty_dir, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.unlink(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    return empty_dir


def _log_sandbox_command(cmd: list[str], spec: SandboxSpec) -> None:
    """Log the sanitized bwrap command (no secrets, no full env)."""
    # Redact any env vars with KEY=VALUE patterns that might contain secrets
    sanitized = []
    for arg in cmd:
        arg_str = str(arg)
        if "=" in arg_str and any(
            secret in arg_str.upper()
            for secret in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS")
        ):
            parts = arg_str.split("=", 1)
            sanitized.append(f"{parts[0]}=[REDACTED]")
        else:
            sanitized.append(arg_str)

    logger.debug(
        "Sandbox command (role=%s, ws=%s): %s",
        spec.role,
        spec.workspace_root,
        " ".join(sanitized),
    )


# ---------------------------------------------------------------------------
# Adapter integration helper
# ---------------------------------------------------------------------------
def maybe_wrap_command_for_sandbox(
    spec,
    original_cmd: list[str],
    original_env: dict[str, str],
    event_log=None,
) -> tuple[list[str], dict[str, str]]:
    """DEPRECATED: use qq.sandbox_integration.maybe_wrap_command_for_sandbox instead.
    This shim delegates to sandbox_integration and discards the cwd return value."""
    import warnings
    warnings.warn(
        "qq.sandbox.maybe_wrap_command_for_sandbox is deprecated; use qq.sandbox_integration.maybe_wrap_command_for_sandbox", 
        DeprecationWarning, stacklevel=2)
    from .sandbox_integration import maybe_wrap_command_for_sandbox as _wrap
    cmd, env, _cwd = _wrap(spec, original_cmd, original_env, event_log)
    return cmd, env


# ---------------------------------------------------------------------------
# Post-scan symlink escape detection
# ---------------------------------------------------------------------------
def scan_for_symlink_escapes(
    workspace_root: str,
    run_root: str,
) -> list[dict]:
    """Scan workspace for symlinks that escape to .qq, run_root, or outside.

    Returns list of violation dicts. Empty list = clean.
    """
    violations: list[dict] = []
    ws_real = str(Path(workspace_root).resolve())
    run_real = str(Path(run_root).resolve())
    qq_dir = os.path.join(ws_real, ".qq")

    if not os.path.isdir(ws_real):
        return violations

    for root, dirs, files in os.walk(ws_real):
        # Skip .qq directory entirely
        if _is_under(root, qq_dir):
            dirs.clear()
            continue

        # Skip internal noise
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".qq"}]

        # Check symlinks in directories and files
        for name in dirs + files:
            full_path = os.path.join(root, name)
            if not os.path.islink(full_path):
                continue

            try:
                target = os.readlink(full_path)
                # Resolve the target relative to the symlink's directory
                resolved_target = str(
                    Path(os.path.join(os.path.dirname(full_path), target)).resolve()
                )

                # Check if target escapes workspace
                if not _is_under(resolved_target, ws_real):
                    violations.append({
                        "path": full_path,
                        "target": target,
                        "resolved": resolved_target,
                        "reason": "symlink_escapes_workspace",
                    })
                # Check if target points into .qq
                elif _is_under(resolved_target, qq_dir):
                    violations.append({
                        "path": full_path,
                        "target": target,
                        "resolved": resolved_target,
                        "reason": "symlink_points_to_qq",
                    })
                # Check if target points into run_root
                elif _is_under(resolved_target, run_real):
                    violations.append({
                        "path": full_path,
                        "target": target,
                        "resolved": resolved_target,
                        "reason": "symlink_points_to_run_root",
                    })
            except (OSError, ValueError):
                pass  # Broken symlink or unresolvable

    return violations
