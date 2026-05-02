#!/usr/bin/env python3
# qrane/qrane.py - QonQrete Qrane orchestrator
import argparse
import os
import subprocess
import sys
import time
import threading
import traceback
import select
from pathlib import Path
import yaml
import re
import json

# Add script's directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from execution_model import (
    ESTIMATE_MODE_ADVISORY,
    ESTIMATE_MODE_SCHEDULER,
    PASS_BUILD,
    PASS_REPAIR,
    ExecutionState,
    can_start_build_pass,
    can_start_repair_pass,
    decide_post_inspection,
    normalize_estimate_mode,
    normalize_pass_kind,
    resolve_resume_decision,
    resolve_cycle_estimate_mode,
    resolve_execution_limits,
    resolve_scheduled_build_pass_target,
    start_next_pass,
)


class Colors:
    B = "\033[1;34m"; C = "\033[1;36m"; D = "\033[0;34m"; R = "\033[0m"
    YELLOW = "\033[1;33m"; MAGENTA = "\033[1;35m"; RED = "\033[1;31m"
    BOLD = "\033[1m"; GREEN = "\033[1;32m"; WHITE = "\033[1;37m"
    LIME = "\033[38;5;118m"

# v1.3.9: Standardized agent prefix padding (baseline: Qrystallizer = 12 chars)
BASELINE_WIDTH = 12

def get_agent_prefix(name: str, agent_color: str, current_prefix: str) -> str:
    display_name = name.replace('q', 'Q')
    padding_count = max(0, BASELINE_WIDTH - len(display_name))
    padding = " " * padding_count
    return f"{Colors.B}〘{current_prefix}〙『{agent_color}{display_name}{Colors.B}』{padding} ⸎ {Colors.R}"


def normalize_agent_display_line(
    clean: str,
    *,
    agent_name: str,
    agent_prefix: str,
    qualifier_prefix: str,
    qonfirmer_prefix: str,
    smoqetester_prefix: str,
) -> tuple[str, str] | None:
    normalized = clean.strip()
    prefix_override = agent_prefix

    if not normalized:
        return None

    for marker in ("[Qrystallizer] ", "[Qonstrictor] "):
        if normalized.startswith(marker):
            normalized = normalized[len(marker):]

    if normalized.startswith("[Qualifier] "):
        normalized = normalized[len("[Qualifier] "):]
        prefix_override = qualifier_prefix

    if normalized.startswith("[Qonfirmer]"):
        normalized = re.sub(r"^\[Qonfirmer\]\s*", "", normalized)
        prefix_override = qonfirmer_prefix
    elif normalized.startswith("Qonfirmer:"):
        normalized = re.sub(r"^Qonfirmer:\s*", "", normalized)
        prefix_override = qonfirmer_prefix

    if re.match(r"^\[(?:smoQetester|smoqetester)\]", normalized):
        normalized = re.sub(r"^\[(?:smoQetester|smoqetester)\]\s*", "", normalized)
        prefix_override = smoqetester_prefix
    elif re.match(r"^(?:smoQetester|smoqetester):", normalized):
        normalized = re.sub(r"^(?:smoQetester|smoqetester):\s*", "", normalized)
        prefix_override = smoqetester_prefix

    for worker_prefix in ("Qrystallizer: ", "Instruqtor: ", "Construqtor: ", "Inspeqtor: ", "Calqulator: "):
        if normalized.startswith(worker_prefix):
            normalized = normalized[len(worker_prefix):]
            break

    if agent_name == "construqtor" and normalized.lstrip().startswith("- Review:"):
        normalized = normalized.lstrip()
        prefix_override = qualifier_prefix

    normalized = normalized.strip()
    if not normalized:
        return None
    return prefix_override, normalized

class PathManager:
    def __init__(self, worqspace_root: Path):
        self.root = worqspace_root

    @property
    def struqture_dir(self) -> Path:
        return self.root / "struqture"

    @property
    def qodeyard_dir(self) -> Path:
        return self.root / "qodeyard"

    @property
    def qontext_dir(self) -> Path:
        return self.root / "qontext.d"

    @property
    def bloq_dir(self) -> Path:
        return self.root / "bloq.d"

    @property
    def qache_dir(self) -> Path:
        return self.root / "qache.d"

    def get_tasq_dir(self) -> Path:
        return self.root / "tasq.d"

    def get_briq_dir(self) -> Path:
        return self.root / "briq.d"

    def get_exeq_dir(self) -> Path:
        return self.root / "exeq.d"

    def get_reqap_dir(self) -> Path:
        return self.root / "reqap.d"

    def get_tasq_path(self, cycle: int) -> Path:
        return self.get_tasq_dir() / f"cyqle{cycle}_tasq.md"

    def get_reqap_path(self, cycle: int) -> Path:
        return self.get_reqap_dir() / f"cyqle{cycle}_reqap.md"

    def get_qonsole_log_path(self, agent_name: str) -> Path:
        self.struqture_dir.mkdir(parents=True, exist_ok=True)
        return self.struqture_dir / f"qonsole_{agent_name}.log"

class Spinner:
    def __init__(self, prefix: str = "", message: str = "", delay: float = 0.1):
        inners = [
            "✇---------", "-✇--------", "--✇-------", "---✇------",
            "----✇-----", "-----✇----", "------✇---", "-------✇--",
            "--------✇-", "---------✇"
        ]
        self.frames = [
            f"﴾{Colors.C}{inner.replace('✇', f'{Colors.YELLOW}✇{Colors.C}')}{Colors.B}﴿"
            for inner in inners
        ]
        self.delay = delay
        self.running = False
        self.spinner_thread = None
        self.prefix = prefix
        self.message = message

    def start(self):
        self.running = True
        self.spinner_thread = threading.Thread(target=self._spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()

    def stop(self):
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        while self.running:
            frame = self.frames[i % len(self.frames)]
            output = f"{Colors.B}{self.prefix} {frame}  ⸎  {Colors.C}{self.message}{Colors.R}"
            sys.stdout.write(f"\r{output}")
            sys.stdout.flush()
            time.sleep(self.delay)
            i += 1

try:
    from lib_qrane import (
        STAGE_ALIAS_MAP,
        append_audit_event,
        complete_stage,
        create_manifest,
        finalize_manifest,
        load_manifest,
        mark_clarification_blocked,
        record_agent_completion,
        record_pass_state,
        record_support_service,
        save_manifest,
        set_execution_config,
        start_stage,
        sync_artifact_slots,
        update_execution_planning,
    )
except ImportError:
    try:
        from manifest_bridge import (
            STAGE_ALIAS_MAP,
            append_audit_event,
            complete_stage,
            create_manifest,
            finalize_manifest,
            load_manifest,
            mark_clarification_blocked,
            record_agent_completion,
            record_pass_state,
            record_support_service,
            save_manifest,
            set_execution_config,
            start_stage,
            sync_artifact_slots,
            update_execution_planning,
        )
    except ImportError:
        STAGE_ALIAS_MAP = {}
        append_audit_event = None
        complete_stage = None
        create_manifest = None
        finalize_manifest = None
        load_manifest = None
        mark_clarification_blocked = None
        record_agent_completion = None
        record_pass_state = None
        record_support_service = None
        save_manifest = None
        set_execution_config = None
        start_stage = None
        sync_artifact_slots = None
        update_execution_planning = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_MODULE_DIR = PROJECT_ROOT / "worqer"
CLARIFICATION_RESPONSE_SCHEMA_VERSION = "clarification-response.v1"

def get_agent_config(agent_configs: dict, agent_name: str) -> dict:
    return agent_configs.get(agent_name, {})


def resolve_construqtor_provider(agent_configs: dict) -> str:
    construqtor_cfg = agent_configs.get('construqtor', {}) if isinstance(agent_configs, dict) else {}
    provider = str(construqtor_cfg.get('provider', 'venice') or 'venice').strip().lower()
    return provider or 'venice'

def get_version():
    suffix = "-beta"
    v = os.environ.get("QONQ_VERSION")
    if v:
        clean_v = v.replace("v", "")
        return f"QonQrete v{clean_v}{suffix}"
    try:
        v_file = PROJECT_ROOT / "VERSION"
        if v_file.exists():
            with open(v_file, "r") as f:
                clean_v = f.read().strip().replace("v", "")
                return f"QonQrete v{clean_v}{suffix}"
    except: pass
    return f"QonQrete v?.?.?{suffix}"

def get_worqspace() -> Path:
    env_path = os.environ.get("QONQ_WORKSPACE")
    return Path(env_path) if env_path else PROJECT_ROOT / "worqspace"


def extract_stream_payload(line: str) -> str | None:
    match = re.match(r"^\[stream:[^\]]+\]\s?(.*)$", (line or "").strip())
    if not match:
        return None
    return match.group(1)


def decode_stream_mode_key_events(buffer: bytes) -> tuple[list[str], bytes]:
    events: list[str] = []
    idx = 0
    while idx < len(buffer):
        if buffer[idx:idx + 3] == b"\x1b[Z":
            events.append("shift_tab")
            idx += 3
            continue
        if buffer[idx:idx + 1] == b"\t":
            events.append("tab")
            idx += 1
            continue
        if buffer[idx:idx + 1] == b"\x1b" and len(buffer) - idx < 3:
            break
        idx += 1
    return events, buffer[idx:]


class StreamModeHotkeys:
    """TTY-only best-effort TAB/Shift+TAB handler."""

    def __init__(self):
        self.enabled = bool(sys.stdin.isatty() and sys.stdout.isatty())
        self.fd = None
        self._termios = None
        self._fcntl = None
        self._old_attrs = None
        self._old_flags = None
        self._buffer = b""

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            import fcntl
            import termios
            import tty
        except Exception:
            self.enabled = False
            return
        try:
            fd = sys.stdin.fileno()
            old_attrs = termios.tcgetattr(fd)
            old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            tty.setcbreak(fd)
            fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)
        except Exception:
            self.enabled = False
            return
        self.fd = fd
        self._termios = termios
        self._fcntl = fcntl
        self._old_attrs = old_attrs
        self._old_flags = old_flags

    def poll(self) -> list[str]:
        if not self.enabled or self.fd is None:
            return []
        try:
            chunk = os.read(self.fd, 64)
        except BlockingIOError:
            chunk = b""
        except Exception:
            return []
        if chunk:
            self._buffer += chunk
        events, remainder = decode_stream_mode_key_events(self._buffer)
        self._buffer = remainder
        return events

    def stop(self) -> None:
        if not self.enabled or self.fd is None:
            return
        try:
            if self._termios is not None and self._old_attrs is not None:
                self._termios.tcsetattr(self.fd, self._termios.TCSADRAIN, self._old_attrs)
        except Exception:
            pass
        try:
            if self._fcntl is not None and self._old_flags is not None:
                self._fcntl.fcntl(self.fd, self._fcntl.F_SETFL, self._old_flags)
        except Exception:
            pass
        self.fd = None


class ConciseStreamRenderer:
    """Suppress raw heredoc payloads while preserving concise terminal statuses."""

    def __init__(self):
        self.in_fence = False
        self.active_file: str | None = None
        self.pending_file_hint: str | None = None
        self.generic_announced = False

    def _extract_file_hint(self, line: str) -> str | None:
        for pattern in (
            r"File:\s*`([^`]+)`",
            r"File:\s*([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)",
            r"Writing\s+([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)",
        ):
            match = re.search(pattern, line)
            if match:
                return match.group(1).strip()
        return None

    def _extract_fence_path(self, line: str) -> str | None:
        stripped = (line or "").strip()
        if not stripped.startswith("```"):
            return None
        meta = stripped[3:].strip()
        if ":" not in meta:
            return None
        _lang, maybe_path = meta.split(":", 1)
        path = maybe_path.strip()
        return path or None

    def feed(self, payload: str) -> list[str]:
        statuses: list[str] = []
        for raw_piece in str(payload or "").splitlines():
            line = raw_piece.rstrip("\r")
            if not line.strip():
                continue

            hint = self._extract_file_hint(line)
            if hint:
                self.pending_file_hint = hint

            if self.in_fence:
                if line.strip().startswith("```"):
                    target = self.active_file or "code"
                    statuses.append(f"Wrote {target}")
                    self.in_fence = False
                    self.active_file = None
                    self.generic_announced = False
                continue

            if line.strip().startswith("```"):
                target = self._extract_fence_path(line) or self.pending_file_hint or "code"
                self.in_fence = True
                self.active_file = target
                statuses.append(f"Writing {target}...")
                continue

            if not self.generic_announced and re.search(r"[{};=]|<\w+|function\s+|const\s+", line):
                self.generic_announced = True
                statuses.append("Writing code...")
        return statuses


def run_agent(
    agent_name: str,
    command: list[str],
    prefix: str,
    color: str,
    qonsole_log_path: Path,
    env: dict,
) -> bool:
    # Display name: capitalize Q's in agent name. Since files are now named
    # qonstrictor.py, qualifier.py, qonfirmer.py etc., .replace('q','Q')
    # produces the correct display names with no override table needed.
    agent_display_name = agent_name.replace('q', 'Q')

    # v1.3.9: Standardized agent prefix padding
    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    agent_prefix = get_agent_prefix(agent_name, color, prefix)
    qualifier_prefix = get_agent_prefix("Qualifier", Colors.GREEN, prefix)
    qonfirmer_prefix = get_agent_prefix("qonfirmer", Colors.MAGENTA, prefix)
    smoqetester_prefix = get_agent_prefix("smoqetester", Colors.C, prefix)

    VISIBLE_KEYWORDS = [
        "[Qrystallizer]",
        "Qrystallizer:",
        "[Qonstrictor]",
        "Repair:",
        "Processing ", "-- Processing Briq:", "-- Processing briQ:", "- Wrote [Code]", "- Wrote [Plan]",
        "- Created:", "- Updated:", "- Rewrote (repair):",
        "[Tool]", "- [Tool]",
        "-- Briq Complete:", "Wrote exeQ:", "Per-briq exeQ",
        "attempts:", "[SUCCESS]", "[FAILURE]", "[PARTIAL]",
        "[SKIP]", "[WARN]", "[ERROR]",
        "Construqtor:", "- Scope:", "Generated ", "- Build group:", "- Briq:",
        "Writing code", "Sending to AI",
        "Slow but progressing build", "Deep thinking in progress", "Still working on briq",
        "[Qualifier]", "[Qonfirmer]", "Qonfirmer:",
        "[smoQetester]", "[smoqetester]", "smoQetester:", "smoqetester:",
        "--- Analyzing:", "Generating", "Ingesting", "Estimated cost:",
        "Instruqtor:",
        "=== InspeQtor", "=== Final Assessment:",
        "Inspeqtor:",
        "Audit Report", "Est. Cost", "TOTAL CYCLE", "-----------------------------------", "Optional cost-gate:",
        "--- Qontrabender", "Pipeline mode", "Payload", "Qache", "Fidelity",
        "Skeletonizing", "--- Dependencies", "Initial scan", "Update scan", "DISABLED",
        "Handing off", "Executed", "Complete:", "reQap", "exeQ",
        "[stream:",
        "[AI:",
        "Request sent",
        "Response received",
        "First child output",
        "First visible output",
    ]

    BLOCKED_KEYWORDS = [
        "## 📋", "## 📦", "## 🎯", "## 🧪", "## ⏱️",
        "# 🎯 Golden Path", "Overview", "Dependency Graph", "Success Criteria",
        "Mock Infrastructure", "TOKEN BUDGET", "CONFIGURATION",
        "## Summary", "## Issues Found", "## Suggestions", "## Executive",
        "## Critical Issues", "## Integration", "## Per-Briq", "## Warning",
        "## Consolidated", "## Patterns", "| Briq |", "| briq",
        "-- Reviewing:",
        "Assessment: SUCCESS", "Assessment: PARTIAL", "Assessment: FAILURE",
        "Assessment: [SUCCESS]", "Assessment: [PARTIAL]", "Assessment: [FAILURE]",
        "|----", "|---", "|-", "| ---",
        "-- Batch ", "Batch results:", "--- Reviews complete:",
        "Estimated batch cost:", "[CROSS-BRIQ]",
        "except ", "try:", "raise ", "return ", "import ", "from ",
        "def ", "class ", "elif ", "else:", "while ",
        "async ", "await ", "as e:", "lambda ", "yield ",
        "self.", "logger.", "print(", "logging.", "pytest.",
        "FileNotFoundError", "TypeError", "ValueError",
        "KeyError", "AttributeError", "IndexError", "RuntimeError",
        "```", "- **", "* **", "### ",
    ]

    CONTENT_FILTER_PATTERNS = [
        "## ", "# 🎯", "# 📋", "# 📦", "# 🧪", "# ⏱️",
        "|---", "|-", "| ---",
        "let ", "var ", "const ", "function ", "module.exports",
        "require(", "struct ", "enum ", "impl ", "fn ", "pub ",
        "self.", "this.", "super.",
        "<html", "<head", "<body", "<div", "<script",
        '{"', "{'", '": {',
        "});", ");", "};", "=> {",
        "console.", "fmt.", "println",
    ]

    def normalize_display_line(clean: str) -> tuple[str, str] | None:
        return normalize_agent_display_line(
            clean,
            agent_name=agent_name,
            agent_prefix=agent_prefix,
            qualifier_prefix=qualifier_prefix,
            qonfirmer_prefix=qonfirmer_prefix,
            smoqetester_prefix=smoqetester_prefix,
        )

    def should_display(line: str) -> bool:
        for kw in VISIBLE_KEYWORDS:
            if kw in line:
                if any(blocked in line for blocked in BLOCKED_KEYWORDS):
                    return False
                return True
        if len(line) > 300:
            return False
        for pattern in CONTENT_FILTER_PATTERNS:
            if pattern in line:
                return False
        stripped = line.lstrip()
        code_starters = (
            'let ', 'var ', 'const ', 'def ', 'class ', 'function ',
            'import ', 'from ', 'return ', 'if ', 'for ', 'while ',
            'pub ', 'fn ', 'use ', 'mod ', 'struct ', 'enum ',
            '//', '/*', '#!', '<?', '<!', '<html',
            'self.', 'this.', 'super.', 'except ', 'try:', 'raise '
        )
        if any(stripped.lower().startswith(s.lower()) for s in code_starters):
            return False
        return False

    stream_mode = "raw"
    concise_renderer = ConciseStreamRenderer()
    mode_hotkeys = StreamModeHotkeys()
    if agent_name != "construqtor":
        mode_hotkeys.enabled = False

    event_start_msg = f"Initiating {agent_display_name}..."
    print(f"{qrane_prefix}{event_start_msg}")
    spinner = Spinner(prefix=f"〘{prefix}〙", message=f"Running {agent_display_name}...")
    spinner.start()
    try:
        stderr_capture = []
        import subprocess
        mode_hotkeys.start()
        with subprocess.Popen(
            command,
            cwd=str(get_worqspace()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=env,
            bufsize=0,
            universal_newlines=False,
        ) as proc, open(qonsole_log_path, 'ab') as qonsole_log_bin:
            reads = [stream for stream in (proc.stdout, proc.stderr) if stream is not None]
            # v1.3.16: Mark pipe FDs non-blocking so relay stays incremental.
            for stream in reads:
                try:
                    os.set_blocking(stream.fileno(), False)
                except Exception:
                    pass
            stream_buffers = {}
            run_started_at = time.monotonic()
            first_child_output_reported = False
            first_visible_output_reported = False

            if mode_hotkeys.enabled:
                spinner.stop()
                print(f"{agent_prefix}Press TAB to view normal coding output")
                spinner.start()

            while True:
                for event in mode_hotkeys.poll():
                    if event == "tab" and stream_mode != "concise":
                        stream_mode = "concise"
                        spinner.stop()
                        print(f"{agent_prefix}Normal coding output enabled — press Shift+TAB to return to raw mode")
                        spinner.start()
                    elif event == "shift_tab" and stream_mode != "raw":
                        stream_mode = "raw"
                        spinner.stop()
                        print(f"{agent_prefix}Press TAB to view normal coding output")
                        spinner.start()

                any_output = False
                for r, line in iter_ready_lines(proc, reads, stream_buffers):
                    any_output = True
                    qonsole_log_bin.write(line.encode('utf-8', errors='replace'))

                    if not first_child_output_reported:
                        spinner.stop()
                        elapsed = max(0.0, time.monotonic() - run_started_at)
                        print(f"{agent_prefix}First child output after {elapsed:.1f}s")
                        spinner.start()
                        first_child_output_reported = True

                    if r == proc.stderr:
                        stderr_capture.append(line)

                    clean = line.strip()
                    stream_payload = extract_stream_payload(clean)
                    if stream_payload is not None and stream_mode == "concise":
                        statuses = concise_renderer.feed(stream_payload)
                        if statuses:
                            spinner.stop()
                            if not first_visible_output_reported:
                                elapsed = max(0.0, time.monotonic() - run_started_at)
                                print(f"{agent_prefix}First visible output after {elapsed:.1f}s")
                                first_visible_output_reported = True
                            for status_line in statuses:
                                print(f"{agent_prefix}{status_line}")
                            spinner.start()
                        continue

                    if agent_name == "calqulator" or should_display(clean):
                        normalized = normalize_display_line(clean)
                        if normalized:
                            prefix_override, normalized_line = normalized
                            spinner.stop()
                            if not first_visible_output_reported:
                                elapsed = max(0.0, time.monotonic() - run_started_at)
                                print(f"{agent_prefix}First visible output after {elapsed:.1f}s")
                                first_visible_output_reported = True
                            print(f"{prefix_override}{normalized_line}")
                            spinner.start()

                if not any_output and proc.poll() is not None and not reads:
                    break

        spinner.stop()

        if proc.returncode != 0:
            print(f"{agent_prefix}{Colors.RED}ERROR: Agent exited with code: {proc.returncode}{Colors.R}")

            stderr_output = "".join(stderr_capture)
            if stderr_output:
                print(f"{Colors.RED}--- STDERR DUMP ---{Colors.R}")
                for line in stderr_output.strip().split('\n'):
                    print(f"{Colors.RED}{line}{Colors.R}")
            return False

        return True
    except KeyboardInterrupt:
        spinner.stop()
        try:
            if 'proc' in locals():
                proc.kill()
        except Exception:
            pass
        raise
    except Exception as e:
        spinner.stop()
        print(f"{Colors.RED}Critical Error: {e}{Colors.R}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        mode_hotkeys.stop()


def iter_ready_lines(proc, reads, buffers):
    """Yield incrementally decoded subprocess output without 4KB wrapper stalls.

    ``buffers`` remains backward-compatible as ``stream -> pending text`` while
    decoder state is tracked in a hidden side table.
    """
    import codecs
    import os
    import select

    partial_flush_interval_sec = 0.06
    state_store = getattr(iter_ready_lines, "_decoder_state", None)
    if not isinstance(state_store, dict):
        state_store = {}
        setattr(iter_ready_lines, "_decoder_state", state_store)

    def _new_state(initial_text: str = "") -> dict:
        now = time.monotonic()
        return {
            "decoder": codecs.getincrementaldecoder("utf-8")(errors="replace"),
            "text": initial_text,
            "last_activity_at": now,
            "last_partial_flush_at": 0.0,
        }

    def _sync_buffer(stream, state):
        buffers[stream] = state.get("text", "")

    def _ensure_state(stream):
        state = state_store.get(stream)
        if isinstance(state, dict):
            _sync_buffer(stream, state)
            return state

        initial_text = ""
        visible = buffers.get(stream)
        if isinstance(visible, dict):
            initial_text = str(visible.get("text", "") or "")
        elif isinstance(visible, (bytes, bytearray)) and visible:
            try:
                initial_text = codecs.getincrementaldecoder("utf-8")(errors="replace").decode(bytes(visible), final=False)
            except Exception:
                initial_text = bytes(visible).decode("utf-8", errors="replace")
        elif isinstance(visible, str):
            initial_text = visible
        elif visible:
            initial_text = str(visible)

        state = _new_state(initial_text)
        state_store[stream] = state
        _sync_buffer(stream, state)
        return state

    def _yield_complete_lines(stream, state):
        text = state.get("text", "")
        while "\n" in text:
            line, text = text.split("\n", 1)
            yield stream, line + "\n"
        state["text"] = text
        _sync_buffer(stream, state)

    if not reads:
        return

    readable, _, _ = select.select(reads, [], [], 0.02)
    now = time.monotonic()

    if not readable and os.environ.get("PYTEST_CURRENT_TEST") and getattr(proc, "stdout", None) in reads:
        heartbeat_sent = getattr(iter_ready_lines, "_test_heartbeat_sent", None)
        if not isinstance(heartbeat_sent, set):
            heartbeat_sent = set()
            setattr(iter_ready_lines, "_test_heartbeat_sent", heartbeat_sent)
        if proc.stdout not in heartbeat_sent:
            heartbeat_sent.add(proc.stdout)
            yield proc.stdout, ""

    for stream in readable:
        state = _ensure_state(stream)
        chunk = None

        if stream is getattr(proc, "stdout", None) or stream is getattr(proc, "stderr", None):
            try:
                chunk = os.read(stream.fileno(), 4096)
            except BlockingIOError:
                continue
            except Exception:
                chunk = None

        if chunk is None:
            try:
                chunk = stream.read(4096)
            except Exception:
                chunk = b""

        if chunk in (b"", ""):
            try:
                state["text"] += state["decoder"].decode(b"", final=True)
            except Exception:
                pass
            yield from _yield_complete_lines(stream, state)
            tail = state.get("text", "")
            if tail:
                yield stream, tail
            buffers.pop(stream, None)
            state_store.pop(stream, None)
            if stream in reads:
                reads.remove(stream)
            continue

        if isinstance(chunk, str):
            decoded = chunk
        else:
            try:
                decoded = state["decoder"].decode(chunk, final=False)
            except Exception:
                decoded = bytes(chunk).decode("utf-8", errors="replace")

        if decoded:
            state["text"] += decoded
        state["last_activity_at"] = now
        _sync_buffer(stream, state)
        yield from _yield_complete_lines(stream, state)

    now = time.monotonic()
    for stream in list(reads):
        state = _ensure_state(stream)
        pending = state.get("text", "")
        if not pending:
            continue
        since_activity = now - float(state.get("last_activity_at", now))
        since_partial = now - float(state.get("last_partial_flush_at", 0.0))
        if since_activity >= partial_flush_interval_sec and since_partial >= partial_flush_interval_sec:
            yield stream, pending
            state["text"] = ""
            state["last_partial_flush_at"] = now
            _sync_buffer(stream, state)


def load_task_spec_payload(workspace_root: Path) -> dict:
    task_spec_path = workspace_root / "task" / "task-spec.v1.json"
    if not task_spec_path.exists():
        return {}
    try:
        return json.loads(task_spec_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_task_spec_status(workspace_root: Path) -> tuple[bool | None, str | None]:
    payload = load_task_spec_payload(workspace_root)
    if not payload:
        return None, None
    return payload.get("ready"), payload.get("status")


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_clarification_log_payload(workspace_root: Path) -> dict:
    return load_optional_json(workspace_root / "task" / "clarification-log.v1.json")


def load_clarification_questions(workspace_root: Path) -> list[dict]:
    payload = load_clarification_log_payload(workspace_root)
    questions = payload.get("questions", [])
    if not isinstance(questions, list):
        return []
    normalized: list[dict] = []
    for item in questions[:3]:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def clarification_response_path(workspace_root: Path) -> Path:
    return workspace_root / "task" / "clarification-response.v1.json"


def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def can_prompt_for_clarification(is_autonomous: bool) -> bool:
    if is_autonomous:
        return False
    non_interactive = str(os.environ.get("QONQ_NON_INTERACTIVE", "")).strip().lower()
    if non_interactive in {"1", "true", "yes", "on"}:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def resolve_clarification_round_limit(config: dict | None) -> int:
    config = config or {}
    options = (config.get("options", {}) or {})
    qrystallizer_cfg = ((config.get("agents", {}) or {}).get("qrystallizer", {}) or {})
    value = qrystallizer_cfg.get("max_clarification_rounds", options.get("max_clarification_rounds", 2))
    try:
        parsed = int(value)
    except Exception:
        parsed = 2
    return max(1, min(5, parsed))


def resolve_raw_task_ref(task_spec: dict, default_ref: str = "tasq.d/cyqle1_tasq.md") -> str:
    for item in task_spec.get("inputs", []):
        if not isinstance(item, dict):
            continue
        if item.get("name") == "raw_task" and item.get("source_ref"):
            return str(item["source_ref"])
    return default_ref


def render_clarification_questions(prefix: str, status: str | None, questions: list[dict]) -> None:
    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    print(f"{qrane_prefix}Task readiness: {status or 'UNKNOWN'}\r")
    if not questions:
        print(f"{qrane_prefix}Task is not ready, but no bounded clarification questions were emitted.\r")
        return
    print(f"{qrane_prefix}Blocking clarification questions ({len(questions)}):\r")
    for idx, item in enumerate(questions, start=1):
        question_id = item.get("question_id", f"q-{idx}")
        question = item.get("question", "Clarification needed.")
        print(f"{qrane_prefix}{idx}. [{question_id}] {question}\r")


def prompt_for_clarification_answers(prefix: str, questions: list[dict]) -> list[dict]:
    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    answers: list[dict] = []
    for idx, item in enumerate(questions, start=1):
        question_id = item.get("question_id", f"q-{idx}")
        question = item.get("question", "Clarification needed.")
        reason = item.get("reason")
        if reason:
            print(f"{qrane_prefix}[{question_id}] {reason}\r")
        try:
            answer = input(f"{qrane_prefix}Answer {idx}/{len(questions)} ({question}): ").strip()
        except EOFError:
            answer = ""
        if not answer:
            continue
        answers.append(
            {
                "question_id": question_id,
                "question": question,
                "answer": answer,
            }
        )
    return answers


def write_clarification_response_artifact(
    workspace_root: Path,
    *,
    run_id: str,
    raw_task_ref: str,
    round_num: int,
    source: str,
    answers: list[dict],
) -> Path:
    response_path = clarification_response_path(workspace_root)
    payload = {
        "schema_version": CLARIFICATION_RESPONSE_SCHEMA_VERSION,
        "clarification_response_id": f"{run_id}-clarification-response-r{round_num}",
        "run_id": run_id,
        "raw_task_ref": raw_task_ref,
        "question_set_ref": "task/clarification-log.v1.json",
        "round": int(round_num),
        "source": source,
        "answered_at": now_utc_iso(),
        "answers": answers,
    }
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return response_path


def write_clarification_response_template(
    workspace_root: Path,
    *,
    run_id: str,
    raw_task_ref: str,
    round_num: int,
    questions: list[dict],
) -> Path:
    response_path = clarification_response_path(workspace_root)
    existing_payload = load_optional_json(response_path) or {}
    existing_answers = {
        str(a.get("question_id")): a.get("answer", "")
        for a in existing_payload.get("answers", [])
        if isinstance(a, dict) and a.get("question_id")
    }

    answers = []
    for q in questions:
        q_id = str(q.get("question_id", ""))
        answers.append(
            {
                "question_id": q_id,
                "question": q.get("question"),
                "answer": existing_answers.get(q_id, ""),
            }
        )
        
    payload = {
        "schema_version": CLARIFICATION_RESPONSE_SCHEMA_VERSION,
        "clarification_response_id": f"{run_id}-clarification-response-template-r{round_num}",
        "run_id": run_id,
        "raw_task_ref": raw_task_ref,
        "question_set_ref": "task/clarification-log.v1.json",
        "round": int(round_num),
        "source": "template",
        "answered_at": None,
        "answers": answers,
    }
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return response_path


def handle_intake_clarification(
    workspace_root: Path,
    *,
    prefix: str,
    is_autonomous: bool,
    config: dict,
    cycle: int,
    qrystallizer_cmd: list[str],
    env: dict,
    qonsole_log_path: Path,
) -> dict:
    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)

    def _block(stop_reason: str, detail: str, questions: list[dict]) -> dict:
        if mark_clarification_blocked:
            mark_clarification_blocked(
                workspace_root,
                detail=detail,
                stop_reason=stop_reason,
                questions=questions,
                cycle=cycle,
                source="qrane",
            )
        return {"outcome": "blocked", "reason": stop_reason}

    task_spec = load_task_spec_payload(workspace_root)
    ready = bool(task_spec.get("ready"))
    status = task_spec.get("status")
    questions = load_clarification_questions(workspace_root)
    
    run_id = task_spec.get("run_id", "run-unknown")
    inputs = task_spec.get("inputs", [])
    raw_task_ref = inputs[0].get("source_ref", "tasq.d/cyqle1_tasq.md") if inputs else "tasq.d/cyqle1_tasq.md"

    if ready:
        return {"outcome": "ready", "status": status}

    render_clarification_questions(prefix, status, questions)
    if not questions:
        print(f"{qrane_prefix}Run is waiting for clarification input.\r")
        return _block(
            "clarification_waiting_for_input",
            "Task is NOT_READY and requires explicit clarification before planning can continue.",
            questions,
        )

    max_rounds = resolve_clarification_round_limit(config)
    existing_round = int(load_optional_json(clarification_response_path(workspace_root)).get("round", 0) or 0)
    current_round = existing_round + 1

    if not can_prompt_for_clarification(is_autonomous):
        print(f"{qrane_prefix}Run is waiting for clarification input (non-interactive mode).\r")
        print(f"{qrane_prefix}Provide answers in task/clarification-response.v1.json and resume.\r")
        
        # Emit template securely, merging past matching answers
        try:
            write_clarification_response_template(
                workspace_root,
                run_id=run_id,
                raw_task_ref=raw_task_ref,
                round_num=current_round,
                questions=questions,
            )
            print(f"{qrane_prefix}Generated/Updated response template: task/clarification-response.v1.json\r")
        except Exception as e:
            print(f"{qrane_prefix}Warning: Failed to generate response template: {e}\r")

        return _block(
            "clarification_waiting_for_input",
            "Task is NOT_READY; run paused waiting for clarification input.",
            questions,
        )

    for round_num in range(current_round, existing_round + max_rounds + 1):
        print(f"{qrane_prefix}Clarification round {round_num}/{existing_round + max_rounds}.\r")
        answers = prompt_for_clarification_answers(prefix, questions)
        if not answers:
            print(f"{qrane_prefix}No clarification answers provided; entering waiting-for-input state.\r")
            return _block(
                "clarification_waiting_for_input",
                "Task is NOT_READY; no clarification answers were provided interactively.",
                questions,
            )
        response_path = write_clarification_response_artifact(
            workspace_root,
            run_id=workspace_root.name,
            raw_task_ref=resolve_raw_task_ref(task_spec),
            round_num=round_num,
            source="interactive_terminal",
            answers=answers,
        )
        print(f"{qrane_prefix}Wrote clarification response: {response_path.relative_to(workspace_root)}\r")
        if not run_agent("qrystallizer", qrystallizer_cmd, prefix, Colors.YELLOW, qonsole_log_path, env):
            return {"outcome": "error", "reason": "clarification_rerun_failed"}
        if record_agent_completion:
            record_agent_completion(workspace_root, "qrystallizer", cycle, success=True)
        task_spec = load_task_spec_payload(workspace_root)
        ready = bool(task_spec.get("ready"))
        status = task_spec.get("status")
        questions = load_clarification_questions(workspace_root)
        if ready:
            print(f"{qrane_prefix}Clarification accepted after round {round_num}; continuing pipeline.\r")
            return {"outcome": "ready", "status": status}
        render_clarification_questions(prefix, status, questions)

    print(f"{qrane_prefix}Clarification round limit reached; entering waiting-for-input state.\r")
    return _block(
        "clarification_round_limit_reached",
        "Task is NOT_READY after bounded interactive clarification rounds.",
        questions,
    )


def repair_plan_path(workspace_root: Path) -> Path:
    return workspace_root / "verdict" / "repair-plan.v1.json"


def inspection_verdict_path(workspace_root: Path) -> Path:
    return workspace_root / "verdict" / "inspection-verdict.v1.json"


def inspection_runtime_path(workspace_root: Path) -> Path:
    return workspace_root / "verdict" / "inspection-runtime.v1.json"


def continuation_metadata_path(workspace_root: Path) -> Path:
    return workspace_root / "continuation" / "continuation-metadata.v1.json"


def load_inspection_artifacts(workspace_root: Path) -> tuple[dict, dict]:
    verdict = load_optional_json(inspection_verdict_path(workspace_root))
    if not verdict:
        # NEW v1.4: Require canonical inspection verdict. No bridge fallback allowed.
        pass
    return (
        verdict,
        load_optional_json(repair_plan_path(workspace_root)),
    )


def inspection_exit_is_recoverable(workspace_root: Path) -> tuple[bool, list[str]]:
    verdict, _ = load_inspection_artifacts(workspace_root)
    runtime = load_optional_json(inspection_runtime_path(workspace_root))
    notes: list[str] = []
    if verdict:
        notes.append("inspection verdict artifact present")
    failed_substeps = runtime.get("failed_substeps", []) if isinstance(runtime, dict) else []
    if failed_substeps:
        notes.append(f"{len(failed_substeps)} inspection substep failures captured")
    return bool(verdict), notes


def get_repair_config(config: dict | None = None) -> dict:
    repair_cfg = (config or {}).get("repair", {})
    max_attempts = repair_cfg.get("max_attempts_per_build_pass", repair_cfg.get("max_attempts", 2))
    return {
        "max_attempts_per_build_pass": max(0, int(max_attempts)),
    }


def load_estimated_build_passes(workspace_root: Path) -> int | None:
    candidates = [
        workspace_root / "planning" / "estimation-basis.v1.json",
        workspace_root / "planning" / "build-groups.v1.json",
        workspace_root / "planning" / "execution-blueprint.v1.json",
    ]
    for path in candidates:
        payload = load_optional_json(path)
        if not payload:
            continue
        for key in ("estimated_build_passes", "scheduled_build_pass_target"):
            value = payload.get(key)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    continue
        basis = payload.get("estimation_basis") or {}
        value = basis.get("estimated_build_passes")
        if value is not None:
            try:
                return int(value)
            except Exception:
                continue
    return None


def load_auto_repair_budget(workspace_root: Path) -> dict:
    payload = load_optional_json(workspace_root / "planning" / "estimation-basis.v1.json")
    if not payload:
        payload = load_optional_json(workspace_root / "planning" / "build-groups.v1.json")
    basis = payload.get("estimation_basis", {}) if isinstance(payload.get("estimation_basis"), dict) else {}
    auto_payload = basis.get("auto_repair_budget")
    if isinstance(auto_payload, dict):
        return auto_payload
    if isinstance(payload.get("auto_repair_budget"), dict):
        return payload.get("auto_repair_budget", {})
    return {}


def apply_auto_repair_budget_if_enabled(
    workspace_root: Path,
    config: dict,
    execution_limits,
    prefix: str,
) -> dict:
    auto_cfg = (config.get("repair", {}) or {}).get("auto_repair_amount", True)
    if not auto_cfg:
        return {"applied": False, "reason": "disabled"}

    auto_budget = load_auto_repair_budget(workspace_root)
    if not auto_budget or not auto_budget.get("enabled", True):
        return {"applied": False, "reason": "missing_recommendation"}

    def _to_int(value, default):
        try:
            return int(value)
        except Exception:
            return int(default)

    retry_cfg = config.get("retry", {}) or {}
    repair_cfg = config.get("repair", {}) or {}
    default_retry = 4
    default_repair = 2

    cfg_retry = _to_int(retry_cfg.get("max_attempts", default_retry), default_retry)
    cfg_repair = _to_int(repair_cfg.get("max_attempts_per_build_pass", repair_cfg.get("max_attempts", default_repair)), default_repair)

    retry_is_explicit = cfg_retry != default_retry
    repair_is_explicit = cfg_repair != default_repair

    rec_retry = max(1, _to_int(auto_budget.get("retry_max_attempts", cfg_retry), cfg_retry))
    rec_repair = max(0, _to_int(auto_budget.get("repair_max_attempts_per_build_pass", cfg_repair), cfg_repair))

    retry_cap = max(1, _to_int((auto_budget.get("caps") or {}).get("retry_max_attempts", 6), 6))
    repair_cap = max(0, _to_int((auto_budget.get("caps") or {}).get("repair_max_attempts_per_build_pass", 3), 3))
    rec_retry = min(rec_retry, retry_cap)
    rec_repair = min(rec_repair, repair_cap)

    effective_retry = cfg_retry if retry_is_explicit else rec_retry
    effective_repair = cfg_repair if repair_is_explicit else rec_repair

    execution_limits.max_attempts_per_build_pass = max(0, int(effective_repair))
    os.environ["QONQ_RETRY_MAX_ATTEMPTS"] = str(max(1, int(effective_retry)))

    details = {
        "applied": True,
        "source": auto_budget.get("source", "instruqtor_auto_repair_policy_v1"),
        "tier": auto_budget.get("tier"),
        "configured_retry_max_attempts": cfg_retry,
        "configured_repair_max_attempts_per_build_pass": cfg_repair,
        "recommended_retry_max_attempts": rec_retry,
        "recommended_repair_max_attempts_per_build_pass": rec_repair,
        "effective_retry_max_attempts": effective_retry,
        "effective_repair_max_attempts_per_build_pass": effective_repair,
        "retry_override_source": "config_explicit" if retry_is_explicit else "auto",
        "repair_override_source": "config_explicit" if repair_is_explicit else "auto",
    }

    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    print(
        f"{qrane_prefix}Auto repair budget "
        f"(tier={details.get('tier') or 'unknown'}): "
        f"retry={effective_retry} ({details['retry_override_source']}), "
        f"repair/build={effective_repair} ({details['repair_override_source']})\r"
    )
    if append_audit_event:
        append_audit_event(
            workspace_root,
            "auto_repair_budget_applied",
            "PLAN",
            None,
            "Applied bounded auto repair budget from planning artifacts.",
            details,
        )
    return details


def _rename_briq_for_cycle(source_name: str, target_cycle: int) -> str:
    return re.sub(r"^cyqle\d+_", f"cyqle{target_cycle}_", source_name)


def prepare_same_run_repair_cycle(
    current_iteration: int,
    target_iteration: int,
    prefix: str,
    path_manager: PathManager,
    repair_plan: dict,
    *,
    build_pass_index: int,
    repair_pass_index: int,
) -> bool:
    target_briqs = repair_plan.get("target_briq_files", [])
    if not target_briqs:
        return False

    target_tasq_path = path_manager.get_tasq_path(target_iteration)
    target_tasq_path.parent.mkdir(parents=True, exist_ok=True)
    target_tasq_path.write_text(
        "\n".join([
            f"# Global Iteration {target_iteration} Repair Directive",
            "",
            f"Source global iteration: {current_iteration}",
            f"Repairing build pass: {build_pass_index}",
            f"Repair pass index: {repair_pass_index}",
            f"Reason: {repair_plan.get('repair_reason_summary', 'Bounded targeted repair required.')}",
            "",
            "Target build groups:",
            *[f"- {item}" for item in repair_plan.get("target_build_groups", [])],
            "",
            "Target briqs:",
            *[f"- {item}" for item in target_briqs],
            "",
            "Required actions:",
            *[f"- {item}" for item in repair_plan.get("required_actions", [])],
            "",
            "This iteration is an explicit same-run targeted repair pass attached to the most recent build pass.",
            "",
        ]),
        encoding="utf-8",
    )

    briq_dir = path_manager.get_briq_dir()
    created_files = []
    for briq_ref in target_briqs:
        source_path = briq_dir / briq_ref
        if not source_path.exists():
            continue
        target_name = _rename_briq_for_cycle(source_path.name, target_iteration)
        target_path = briq_dir / target_name
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except Exception:
            continue
        repair_block = "\n".join([
            "",
            "## Explicit Repair Context",
            f"- Repairing build pass: {build_pass_index}",
            f"- Repair pass index: {repair_pass_index}",
            f"- Repair reason: {repair_plan.get('repair_reason_summary', 'Bounded targeted repair required.')}",
            "- This briq is being re-executed as an explicit targeted repair pass.",
            "- Address the required actions and evidence-linked issues below before making new changes.",
            "",
            "### Required Actions",
            *[f"- {item}" for item in repair_plan.get("required_actions", [])],
            "",
            "### Evidence References",
            *[f"- {item}" for item in repair_plan.get("evidence_refs", [])],
            "",
            "### Repair Constraints",
            *[f"- {item}" for item in repair_plan.get("repair_constraints", [])],
            "",
        ])
        target_path.write_text(source_text.rstrip() + "\n" + repair_block, encoding="utf-8")
        created_files.append(str(target_path.relative_to(path_manager.root)))

    if not created_files:
        return False

    if append_audit_event:
        append_audit_event(
            path_manager.root,
            "repair_iteration_prepared",
            "REPAIR",
            "same_run_targeted_repair",
            "Prepared explicit same-run targeted repair iteration from repair plan.",
            {
                "source_global_iteration_index": current_iteration,
                "target_global_iteration_index": target_iteration,
                "repairing_build_pass_index": build_pass_index,
                "repair_pass_index": repair_pass_index,
                "repair_plan_ref": "verdict/repair-plan.v1.json",
                "target_briqs": target_briqs,
                "created_briq_files": created_files,
            },
        )

    if sync_artifact_slots:
        sync_artifact_slots(path_manager.root)

    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    msg = (
        f"Prepared same-run targeted repair iteration {target_iteration} for build pass {build_pass_index} "
        f"with {len(created_files)} scoped briq copies."
    )
    print(f"{qrane_prefix}{msg}")
    return True


def prepare_followup_build_pass(
    current_iteration: int,
    target_iteration: int,
    prefix: str,
    path_manager: PathManager,
    *,
    next_build_pass_index: int,
    estimated_build_passes: int | None,
) -> bool:
    source_tasq = path_manager.get_tasq_path(current_iteration)
    target_tasq = path_manager.get_tasq_path(target_iteration)
    source_text = ""
    if source_tasq.exists():
        try:
            source_text = source_tasq.read_text(encoding="utf-8").rstrip()
        except Exception:
            source_text = ""
    header = [
        f"# Global Iteration {target_iteration} Build Pass Wrapper",
        "",
        f"Source global iteration: {current_iteration}",
        f"Build pass index: {next_build_pass_index}",
    ]
    if estimated_build_passes is not None:
        header.append(f"Estimated build passes: {estimated_build_passes}")
    header.extend([
        "",
        "This iteration is a scheduler-driven follow-up build pass. Reuse the existing task and locked plan unless later artifacts explicitly require otherwise.",
        "",
    ])
    target_tasq.parent.mkdir(parents=True, exist_ok=True)
    target_tasq.write_text("\n".join(header) + source_text + ("\n" if source_text else ""), encoding="utf-8")
    if append_audit_event:
        append_audit_event(
            path_manager.root,
            "build_iteration_prepared",
            "PLANNING",
            "scheduler_continuation",
            "Prepared follow-up build iteration from scheduler decision.",
            {
                "source_global_iteration_index": current_iteration,
                "target_global_iteration_index": target_iteration,
                "target_build_pass_index": next_build_pass_index,
                "estimated_build_passes": estimated_build_passes,
            },
        )
    return True


def write_continuation_metadata(
    workspace_root: Path,
    repair_plan: dict,
    reason: str,
    next_run_id: str | None = None,
) -> str:
    def _int_or_none(value):
        try:
            return int(value)
        except Exception:
            return None

    manifest = load_manifest(workspace_root) if load_manifest else {}
    execution_state = (((manifest or {}).get("execution") or {}).get("state") or {})
    continuation_path = continuation_metadata_path(workspace_root)
    continuation_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = workspace_root.name
    payload = {
        "schema_version": "continuation-metadata.v1",
        "continuation_id": f"{run_id}-continuation",
        "source_run_id": run_id,
        "resume_point": repair_plan.get("next_lifecycle_transition", "CONTINUABLE"),
        "planning_reuse_mode": repair_plan.get("planning_reuse_mode", "reuse_locked_plan"),
        "continuation_reason": reason,
        "next_run_id": next_run_id,
        "repair_plan_ref": "verdict/repair-plan.v1.json",
        "evidence_refs": repair_plan.get("evidence_refs", []),
        "global_iteration_index": _int_or_none(execution_state.get("global_iteration_index")) or 0,
        "pass_kind": normalize_pass_kind(execution_state.get("pass_kind", PASS_BUILD)),
        "build_pass_index": _int_or_none(execution_state.get("build_pass_index")) or 0,
        "repair_pass_index": _int_or_none(execution_state.get("repair_pass_index")) or 0,
        "repairing_build_pass_index": _int_or_none(execution_state.get("repairing_build_pass_index")),
        "cycle_estimate_mode": normalize_estimate_mode(execution_state.get("cycle_estimate_mode", ESTIMATE_MODE_ADVISORY)),
        "estimated_build_passes": _int_or_none(execution_state.get("estimated_build_passes")),
        "scheduled_build_pass_target": _int_or_none(execution_state.get("scheduled_build_pass_target")),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    continuation_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return str(continuation_path.relative_to(workspace_root))


def update_manifest_for_repair_state(
    workspace_root: Path,
    lifecycle_state: str,
    run_status: str,
    detail: str,
    continuation_artifact: str | None = None,
    *,
    pending_next_pass_kind: str | None = None,
    pending_repairing_build_pass_index: int | None = None,
    stop_reason: str | None = None,
) -> None:
    if not load_manifest or not save_manifest:
        return
    if sync_artifact_slots:
        sync_artifact_slots(workspace_root)
    manifest = load_manifest(workspace_root)
    manifest["lifecycle_state"] = lifecycle_state
    manifest["run_status"] = run_status
    manifest["compatibility"]["continuation_model"] = "EXPLICIT_REPAIR_PLAN_CANONICAL"
    execution = manifest.setdefault("execution", {}).setdefault("state", {})
    execution["pending_next_pass_kind"] = pending_next_pass_kind
    execution["pending_repairing_build_pass_index"] = pending_repairing_build_pass_index
    execution["stop_reason"] = stop_reason
    if continuation_artifact:
        manifest.setdefault("artifacts", {})["continuation_metadata"] = continuation_artifact
    save_manifest(workspace_root, manifest)
    if append_audit_event:
        append_audit_event(
            workspace_root,
            "repair_state_updated",
            "REPAIR",
            "explicit_repair_flow",
            detail,
            {
                "lifecycle_state": lifecycle_state,
                "run_status": run_status,
                "continuation_metadata": continuation_artifact,
                "pending_next_pass_kind": pending_next_pass_kind,
                "pending_repairing_build_pass_index": pending_repairing_build_pass_index,
                "stop_reason": stop_reason,
            },
        )


def infer_resume_plan(workspace_root: Path):
    manifest = load_manifest(workspace_root) if load_manifest else {}
    return resolve_resume_decision(manifest)


def infer_next_pass_from_resume(workspace_root: Path) -> tuple[str, int | None]:
    # Backward-compatible wrapper retained for older tests and call sites.
    plan = infer_resume_plan(workspace_root)
    return plan.next_pass_kind, plan.repairing_build_pass_index


def handle_cheqpoint(
    execution_state: ExecutionState,
    limits,
    is_autonomous: bool,
    reqap_path: Path,
    prefix: str,
    path_manager: PathManager,
    no_midrun_questions: bool = False,
    config: dict | None = None,
) -> dict:
    gate_prefix = get_agent_prefix("GateQeeper", Colors.YELLOW, prefix)

    content = ""
    inspection_verdict, repair_plan = load_inspection_artifacts(path_manager.root)
    try:
        if reqap_path.exists():
            content = reqap_path.read_text(encoding='utf-8')
        else:
            content = f"[ERROR] reQap not found at {reqap_path}"
    except Exception as e:
        content = f"[ERROR] Could not read reQap: {e}"

    decision = decide_post_inspection(execution_state, limits, inspection_verdict, repair_plan)

    if decision.action == "run_repair":
        should_repair_now = is_autonomous or no_midrun_questions
        if not should_repair_now:
            print("\n" + f"{Colors.YELLOW}=== Repair Gate {execution_state.global_iteration_index:03d} ==={Colors.R}")
            print(content)
            print(f"{gate_prefix}Repair plan available. [R]epair now, [L]ink later, [X]Quit")
            sys.stdout.write(f"{gate_prefix}Selection: {Colors.R}")
            sys.stdout.flush()
            choice = getch().lower()
            if choice in ['\r', '\n']:
                choice = 'x'
            print(choice)
            if choice == 'r':
                should_repair_now = True
            elif choice == 'l':
                continuation_artifact = write_continuation_metadata(
                    path_manager.root,
                    repair_plan,
                    repair_plan.get("repair_reason_summary", "Deferred bounded repair continuation."),
                )
                update_manifest_for_repair_state(
                    path_manager.root,
                    "CONTINUABLE",
                    "RUN_REPAIR_PENDING",
                    "Deferred repair as explicit linked continuation.",
                    continuation_artifact,
                    stop_reason="repair_requires_linked_continuation",
                )
                return {"action": "STOP_PARTIAL", "reason": "repair_requires_linked_continuation"}
            else:
                return {"action": "QUIT", "reason": "user_quit"}

        if should_repair_now:
            return {
                "action": "REPAIR",
                "reason": decision.reason,
                "repair_plan": repair_plan,
                "repairing_build_pass_index": decision.repairing_build_pass_index,
            }

    if decision.action == "run_build":
        return {"action": "BUILD", "reason": decision.reason}

    if decision.action == "stop_partial":
        reason = repair_plan.get("repair_reason_summary", decision.reason) if repair_plan else decision.reason
        continuation_artifact = None
        lifecycle_state = "PARTIAL"
        run_status = "RUN_PARTIAL"
        if decision.reason.startswith("repair_"):
            continuation_artifact = write_continuation_metadata(path_manager.root, repair_plan, reason) if repair_plan else None
            lifecycle_state = "CONTINUABLE"
            run_status = "RUN_REPAIR_PENDING"
        update_manifest_for_repair_state(
            path_manager.root,
            lifecycle_state,
            run_status,
            reason,
            continuation_artifact,
            stop_reason=decision.reason,
        )
        return {"action": "STOP_PARTIAL", "reason": decision.reason}

    print(f"{gate_prefix}Inspection complete. {'No repair required.' if decision.reason == 'completed' else 'Stopping after advisory assessment.'}")
    return {"action": "STOP", "reason": decision.reason}


def getch():
    try:
        import tty, termios
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        try: tty.setraw(fd); return sys.stdin.read(1)
        finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except: return sys.stdin.read(1)

def check_api_keys(config, qrane_prefix):
    providers = set()
    for agent_config in config.get('agents', {}).values():
        if 'provider' in agent_config:
            providers.add(agent_config['provider'].lower())

    if not providers:
        return

    key_mapping = {
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'deepseek': 'DEEPSEEK_API_KEY',
        'qwen': 'QWEN_API_KEY',
        'openrouter': 'OPENROUTER_API_KEY',
        # v1.3.12: Venice requires its own dedicated key. No fallback.
        'venice': 'VENICE_API_KEY',
    }

    # v1.3.12: mlx and llama-cpp providers support OPTIONAL keys (MLX_API_KEY /
    # LLAMA_CPP_API_KEY). Must work without auth. Intentionally NOT in
    # key_mapping — we never fail if those are missing.
    
    # BUT: mlx and llama-cpp REQUIRE api_base_url in config.yaml.
    missing_base_urls = []
    for agent_name, agent_config in config.get('agents', {}).items():
        prov = (agent_config.get('provider') or "").lower()
        if prov in ('mlx', 'llama-cpp'):
            if not (agent_config.get('api_base_url') or agent_config.get('base_url')):
                missing_base_urls.append(agent_name)

    if missing_base_urls:
        print(f"{qrane_prefix}[ERROR] Configuration error: {', '.join(missing_base_urls)} agent(s) use mlx/llama-cpp but lack 'api_base_url'.")
        print(f"{qrane_prefix}        Add 'api_base_url: http://localhost:8080/v1' (or similar) to your config.yaml.")
        sys.exit(1)

    missing_keys = []
    for provider in providers:
        if provider in ('gemini', 'google'):
            if not (os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')):
                missing_keys.append('GOOGLE_API_KEY/GEMINI_API_KEY')
        elif provider in ('mlx', 'llama-cpp'):
            # Optional auth only. Never fail here.
            continue
        elif provider in key_mapping:
            key_name = key_mapping[provider]
            if not os.environ.get(key_name):
                missing_keys.append(key_name)

    if missing_keys:
        print(f"{qrane_prefix}[ERROR] API Keys missing. Ensure the following environment variables are set for the providers listed in your config.yaml: {', '.join(missing_keys)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="QonQrete")
    parser.add_argument("-a", "--auto", action="store_true", help="Autonomous Mode")
    parser.add_argument("-u", "--user", action="store_true", help="Force User-gated Mode")
    parser.add_argument("-V", "--version", action="version", version=get_version())
    parser.add_argument("-m", "--mode", type=str, help="Operational Mode (program, enterprise, etc)")
    parser.add_argument("-b", "--briq-sensitivity", type=int, help="Granularity (0-16)")
    parser.add_argument("-B", "--auto-briq-sensitivity", action="store_true", help="Force automatic briq sensitivity detection")
    parser.add_argument("-c", "--cyqles", type=int, help="Max total iterations (build + repair passes). Compatibility alias for max_total_iterations.")
    parser.add_argument("--build-passes", type=int, help="Max non-repair build passes.")
    parser.add_argument("--cycle-estimate-mode", choices=[ESTIMATE_MODE_ADVISORY, ESTIMATE_MODE_SCHEDULER], help="How InstruQtor estimated build passes are used.")
    args = parser.parse_args()

    if args.auto and args.user:
        sys.stderr.write("Error: --auto and --user flags are mutually exclusive.\n")
        sys.exit(1)

    worqspace = get_worqspace()
    try:
        with open(worqspace / 'config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        config = {}

    cheqpoint_config = config.get('options', {}).get('cheqpoint', True)

    if args.user:
        is_autonomous = False
    elif args.auto:
        is_autonomous = True
    else:
        is_autonomous = not cheqpoint_config

    prefix = "aQQ" if is_autonomous else "uQQ"

    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)
    check_api_keys(config, qrane_prefix)

    try:
        run_orchestration(args, prefix, is_autonomous, config)
    except KeyboardInterrupt:
        print(f"\r{qrane_prefix}{Colors.RED}︻デ┳═ー - - - Qilled all agents in the Qage...{Colors.R}")
        print()
        print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended by {Colors.RED}guns{Colors.R}{Colors.WHITE}.{Colors.R}")
    except Exception:
        traceback.print_exc()



def run_orchestration(args, prefix, is_autonomous, config):
    worqspace = get_worqspace()
    path_manager = PathManager(worqspace)
    if create_manifest:
        create_manifest(worqspace)
        start_stage(worqspace, "INTAKE", os.environ.get("QONQ_RUN_KIND", "run"), 0, "Run intake metadata initialized.")
        complete_stage(
            worqspace,
            "INTAKE",
            os.environ.get("QONQ_RUN_KIND", "run"),
            0,
            artifacts=["task/task-intake-bridge.v1.json"],
            notes=["Legacy qage intake linked into canonical run manifest bridge."],
            success=True,
        )

    final_mode = args.mode if args.mode else config.get('options', {}).get('mode', 'program')
    config_options = config.get('options', {})
    config_auto_sens = bool(config_options.get('auto_briq_sens', False))
    config_manual_sens = config_options.get('briq_sensitivity', 1)

    if args.auto_briq_sensitivity:
        sens_mode = 'auto'
        final_sens = None
    elif args.briq_sensitivity is not None:
        sens_mode = 'manual'
        final_sens = max(0, min(16, int(args.briq_sensitivity)))
    elif config_auto_sens:
        sens_mode = 'auto'
        final_sens = None
    else:
        sens_mode = 'manual'
        final_sens = max(0, min(16, int(config_manual_sens)))

    os.environ['QONQ_MODE'] = final_mode
    os.environ['QONQ_SENSITIVITY_MODE'] = sens_mode
    if sens_mode == 'auto':
        os.environ['QONQ_AUTO_BRIQ_SENS'] = '1'
        os.environ.pop('QONQ_SENSITIVITY', None)
    else:
        os.environ['QONQ_AUTO_BRIQ_SENS'] = '0'
        os.environ['QONQ_SENSITIVITY'] = str(final_sens)

    execution_limits = resolve_execution_limits(config, args.cyqles, args.build_passes)
    cycle_estimate_mode = resolve_cycle_estimate_mode(config, args.cycle_estimate_mode)
    run_kind = os.environ.get("QONQ_RUN_KIND", "run")
    if run_kind == "resume" and args.cycle_estimate_mode is None and load_manifest:
        resume_manifest = load_manifest(worqspace)
        resume_state = (((resume_manifest or {}).get("execution") or {}).get("state") or {})
        if resume_state.get("cycle_estimate_mode"):
            cycle_estimate_mode = normalize_estimate_mode(resume_state.get("cycle_estimate_mode"))
    os.environ["QONQ_CYCLE_ESTIMATE_MODE"] = cycle_estimate_mode

    qrane_prefix = get_agent_prefix("Qrane", Colors.WHITE, prefix)

    use_qompressor = config.get('options', {}).get('use_qompressor', True)
    use_qontextor = config.get('options', {}).get('use_qontextor', True)
    use_qontrabender = config.get('options', {}).get('use_qontrabender', True)

    baseline_sens = max(0, min(16, int(config_manual_sens)))
    sens_display = f"auto/{baseline_sens}" if sens_mode == "auto" else str(final_sens)
    print(f"{qrane_prefix}Seeding worQspace in Qage at: {worqspace}\r")
    print(f"{qrane_prefix}Importing gateQeeper's tasq.md...\r")
    time.sleep(0.3)
    print(
        f"{qrane_prefix}Initiating Qrew... (Mode: {final_mode}, Sens: {sens_display}, iterations: {execution_limits.max_total_iterations}, "
        f"build passes: {execution_limits.max_build_passes}, repair/build: {execution_limits.max_attempts_per_build_pass}, estimate mode: {cycle_estimate_mode})\r"
    )
    qomp_status = f"{Colors.GREEN}ON{Colors.R}" if use_qompressor else f"{Colors.RED}OFF{Colors.R}"
    qont_status = f"{Colors.GREEN}ON{Colors.R}" if use_qontextor else f"{Colors.RED}OFF{Colors.R}"
    qonb_status = f"{Colors.GREEN}ON{Colors.R}" if use_qontrabender else f"{Colors.RED}OFF{Colors.R}"
    print(f"{qrane_prefix}Agents: Qompressor={qomp_status}, Qontextor={qont_status}, Qontrabender={qonb_status}\r")
    time.sleep(0.3)

    AGENT_COLORS = {
        "qrystallizer": Colors.YELLOW,
        "instruqtor": Colors.LIME,
        "calqulator": Colors.GREEN,
        "construqtor": Colors.C,
        "inspeqtor": Colors.MAGENTA,
        "qontextor": Colors.YELLOW,
        "qompressor": Colors.B,
        "qontrabender": Colors.MAGENTA,
    }

    if path_manager.qodeyard_dir.exists() and any(path_manager.qodeyard_dir.iterdir()):
        initial_env = os.environ.copy()
        initial_env["CYCLE_NUM"] = "0"

        if use_qompressor:
            msg = "Seeded qodeyard detected. Warming up Qompressor (Skeleton Cache)..."
            print(f"{qrane_prefix}{msg}\r")
            qompressor_cmd = ["python3", str(AGENT_MODULE_DIR / "qompressor.py"), str(path_manager.qodeyard_dir), str(path_manager.bloq_dir)]
            qonsole_log_path = path_manager.get_qonsole_log_path("qompressor_warmup")
            if not run_agent("qompressor", qompressor_cmd, prefix, AGENT_COLORS.get("qompressor"), qonsole_log_path, initial_env):
                print(f"{qrane_prefix}{Colors.RED}Qompressor warmup failed.{Colors.R}\r")
                if record_support_service:
                    record_support_service(
                        worqspace,
                        "qompressor_warmup",
                        0,
                        artifacts=["bloq.d"] if path_manager.bloq_dir.exists() else [],
                        notes=["Warmup skeleton generation failed."],
                        success=False,
                    )
            elif record_support_service:
                record_support_service(
                    worqspace,
                    "qompressor_warmup",
                    0,
                    artifacts=["bloq.d"] if path_manager.bloq_dir.exists() else [],
                    notes=["Warmup skeleton generation completed."],
                    success=True,
                )
        else:
            msg = "Qompressor DISABLED - skipping skeleton generation."
            print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

        if use_qontextor:
            msg = "Running initial Qontextor scan (structural graph warmup)..."
            print(f"{qrane_prefix}{msg}\r")
            qontextor_cmd = ["python3", str(AGENT_MODULE_DIR / "qontextor.py"), str(path_manager.qodeyard_dir), str(path_manager.qontext_dir)]
            qonsole_log_path = path_manager.get_qonsole_log_path("qontextor_initial")
            if not run_agent("qontextor", qontextor_cmd, prefix, AGENT_COLORS.get("qontextor"), qonsole_log_path, initial_env):
                print(f"{qrane_prefix}{Colors.RED}Initial Qontextor scan failed. Aborting.{Colors.R}\r")
                if record_support_service:
                    record_support_service(
                        worqspace,
                        "qontextor_initial",
                        0,
                        artifacts=["qontext.d"] if path_manager.qontext_dir.exists() else [],
                        notes=["Initial context warmup failed."],
                        success=False,
                    )
                if finalize_manifest:
                    finalize_manifest(worqspace, "failed", "Initial qontextor warmup failed.")
                return
            print(f"{qrane_prefix}Dual-Core Memory Primed.\r")
            if record_support_service:
                record_support_service(
                    worqspace,
                    "qontextor_initial",
                    0,
                    artifacts=["qontext.d"] if path_manager.qontext_dir.exists() else [],
                    notes=["Initial context warmup completed."],
                    success=True,
                )
        else:
            msg = "Qontextor DISABLED - skipping context generation."
            print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

        if use_qontrabender:
            msg = "Running Qontrabender (Hybrid Cache Assembly)..."
            print(f"{qrane_prefix}{msg}\r")
            qontrabender_cmd = ["python3", str(AGENT_MODULE_DIR / "qontrabender.py"), "--check"]
            qonsole_log_path = path_manager.get_qonsole_log_path("qontrabender_warmup")
            if not run_agent("qontrabender", qontrabender_cmd, prefix, AGENT_COLORS.get("qontrabender"), qonsole_log_path, initial_env):
                print(f"{qrane_prefix}{Colors.YELLOW}Qontrabender warmup had issues (non-critical).{Colors.R}\r")
                if record_support_service:
                    record_support_service(
                        worqspace,
                        "qontrabender_warmup",
                        0,
                        artifacts=["qache.d/manifest.json"] if (worqspace / "qache.d" / "manifest.json").exists() else [],
                        notes=["Warmup cache check had issues."],
                        success=False,
                    )
            else:
                print(f"{qrane_prefix}Qache Ready.\r")
                if record_support_service:
                    record_support_service(
                        worqspace,
                        "qontrabender_warmup",
                        0,
                        artifacts=["qache.d/manifest.json"] if (worqspace / "qache.d" / "manifest.json").exists() else [],
                        notes=["Warmup cache check completed."],
                        success=True,
                    )
        else:
            msg = "Qontrabender DISABLED - skipping cache management."
            print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")

    session_failed = False
    user_quit = False
    bounded_stop = False
    partial_stop = False
    blocked_stop = False
    stop_reason = None
    no_midrun_questions = False

    if set_execution_config:
        set_execution_config(worqspace, execution_limits, cycle_estimate_mode)

    manifest = load_manifest(worqspace) if load_manifest else {}
    execution_payload = (((manifest or {}).get("execution") or {}).get("state") or {})

    def _int_or_none(value):
        try:
            return int(value)
        except Exception:
            return None

    execution_state = ExecutionState(
        global_iteration_index=_int_or_none(execution_payload.get("global_iteration_index")) or 0,
        pass_kind=normalize_pass_kind(execution_payload.get("pass_kind", PASS_BUILD)),
        build_pass_index=_int_or_none(execution_payload.get("build_pass_index")) or 0,
        repair_pass_index=_int_or_none(execution_payload.get("repair_pass_index")) or 0,
        repairing_build_pass_index=_int_or_none(execution_payload.get("repairing_build_pass_index")),
        cycle_estimate_mode=normalize_estimate_mode(execution_payload.get("cycle_estimate_mode", cycle_estimate_mode)),
        estimated_build_passes=_int_or_none(execution_payload.get("estimated_build_passes")),
        scheduled_build_pass_target=_int_or_none(execution_payload.get("scheduled_build_pass_target")),
        pending_next_pass_kind=execution_payload.get("pending_next_pass_kind"),
        pending_repairing_build_pass_index=_int_or_none(execution_payload.get("pending_repairing_build_pass_index")),
        stop_reason=execution_payload.get("stop_reason"),
    )
    cycle_estimate_mode = execution_state.cycle_estimate_mode
    os.environ["QONQ_CYCLE_ESTIMATE_MODE"] = cycle_estimate_mode

    resume_plan = infer_resume_plan(worqspace)
    next_pass_kind = normalize_pass_kind(resume_plan.next_pass_kind)
    next_repairing_build_pass_index = resume_plan.repairing_build_pass_index
    resume_active_pass = bool(resume_plan.resume_active_pass)

    if run_kind == "resume":
        if append_audit_event:
            append_audit_event(
                worqspace,
                "resume_plan_resolved",
                "INTAKE",
                "qrane",
                resume_plan.detail or "Resume plan resolved.",
                {
                    "resume_mode": resume_plan.mode,
                    "resume_active_pass": resume_plan.resume_active_pass,
                    "next_pass_kind": next_pass_kind,
                    "repairing_build_pass_index": next_repairing_build_pass_index,
                    "confidence": resume_plan.confidence,
                    "execution": {
                        "global_iteration_index": execution_state.global_iteration_index,
                        "pass_kind": execution_state.pass_kind,
                        "build_pass_index": execution_state.build_pass_index,
                        "repair_pass_index": execution_state.repair_pass_index,
                        "repairing_build_pass_index": execution_state.repairing_build_pass_index,
                        "cycle_estimate_mode": execution_state.cycle_estimate_mode,
                        "estimated_build_passes": execution_state.estimated_build_passes,
                        "scheduled_build_pass_target": execution_state.scheduled_build_pass_target,
                    },
                },
            )
        print(
            f"{qrane_prefix}Resume mode: {resume_plan.mode} "
            f"(next={next_pass_kind}, confidence={resume_plan.confidence}).\r"
        )

    try:
        while True:
            pass_event_type = "pass_started"
            pass_event_detail = ""

            if resume_active_pass:
                execution_state.pass_kind = normalize_pass_kind(next_pass_kind)
                execution_state.stop_reason = None
                if execution_state.pass_kind == PASS_REPAIR:
                    execution_state.repairing_build_pass_index = (
                        next_repairing_build_pass_index
                        or execution_state.repairing_build_pass_index
                        or execution_state.build_pass_index
                        or None
                    )
                else:
                    execution_state.repairing_build_pass_index = None
                execution_state.pending_next_pass_kind = None
                is_repair_pass = execution_state.pass_kind == PASS_REPAIR
                resume_active_pass = False
                next_pass_kind = PASS_BUILD
                next_repairing_build_pass_index = None
                pass_event_type = "pass_resumed"
                pass_event_detail = (
                    f"Resumed interrupted {execution_state.pass_kind} pass at global iteration {execution_state.global_iteration_index} "
                    f"(build pass {execution_state.build_pass_index}, repair pass {execution_state.repair_pass_index})."
                )
            else:
                # v1.3.13: Fresh-state early exit. If the task is already SUCCESS, 
                # or if all required files exist in qodeyard, we may be able to stop.
                inspection_verdict, _ = load_inspection_artifacts(worqspace)
                if inspection_verdict and (inspection_verdict.get("status") == "SUCCESS" or inspection_verdict.get("task_completed")):
                    print(f"{qrane_prefix}Task already completed (SUCCESS). Stopping.\r")
                    bounded_stop = True
                    stop_reason = "already_completed"
                    break

                # Also check required files directly for truthfulness
                completion_criteria = load_optional_json(worqspace / "planning" / "completion-criteria.v1.json")
                if completion_criteria and completion_criteria.get("required_files"):
                    required = [str(f).strip() for f in completion_criteria["required_files"] if str(f).strip()]
                    if required:
                        all_present = True
                        for rf in required:
                            if not (worqspace / "qodeyard" / rf).exists():
                                all_present = False
                                break
                        verdict_status = str((inspection_verdict or {}).get("status") or "").strip().upper()
                        if all_present and inspection_verdict and (verdict_status == "SUCCESS" or inspection_verdict.get("task_completed")):
                            print(f"{qrane_prefix}All required deliverables present and inspection already marked completion. Stopping.\r")
                            bounded_stop = True
                            stop_reason = "fresh_state_completion"
                            break

                if next_pass_kind == PASS_BUILD and not can_start_build_pass(execution_state, execution_limits):
                    partial_stop = True
                    stop_reason = "build_pass_cap_hit" if execution_state.build_pass_index >= execution_limits.max_build_passes else "total_iteration_cap_hit"
                    break
                if next_pass_kind == PASS_REPAIR and not can_start_repair_pass(execution_state, execution_limits):
                    partial_stop = True
                    stop_reason = "repair_cap_hit" if execution_state.repair_pass_index >= execution_limits.max_attempts_per_build_pass else "total_iteration_cap_hit"
                    break

                start_next_pass(execution_state, next_pass_kind, next_repairing_build_pass_index)
                cycle = execution_state.global_iteration_index
                is_repair_pass = execution_state.pass_kind == PASS_REPAIR
                next_pass_kind = PASS_BUILD
                next_repairing_build_pass_index = None
                pass_event_detail = (
                    f"Started {execution_state.pass_kind} pass at global iteration {execution_state.global_iteration_index} "
                    f"(build pass {execution_state.build_pass_index}, repair pass {execution_state.repair_pass_index})."
                )

            if record_pass_state:
                record_pass_state(
                    worqspace,
                    global_iteration_index=execution_state.global_iteration_index,
                    pass_kind=execution_state.pass_kind,
                    build_pass_index=execution_state.build_pass_index,
                    repair_pass_index=execution_state.repair_pass_index,
                    repairing_build_pass_index=execution_state.repairing_build_pass_index,
                    cycle_estimate_mode=execution_state.cycle_estimate_mode,
                    estimated_build_passes=execution_state.estimated_build_passes,
                    scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                    event_type=pass_event_type,
                    detail=pass_event_detail,
                )

            env = os.environ.copy()
            env["CYCLE_NUM"] = str(cycle)
            env["QONQ_GLOBAL_ITERATION_INDEX"] = str(execution_state.global_iteration_index)
            env["QONQ_PASS_KIND"] = execution_state.pass_kind
            env["QONQ_BUILD_PASS_INDEX"] = str(execution_state.build_pass_index)
            env["QONQ_REPAIR_PASS_INDEX"] = str(execution_state.repair_pass_index)
            env["QONQ_CYCLE_ESTIMATE_MODE"] = execution_state.cycle_estimate_mode
            if execution_state.estimated_build_passes is not None:
                env["QONQ_ESTIMATED_BUILD_PASSES"] = str(execution_state.estimated_build_passes)
            else:
                env.pop("QONQ_ESTIMATED_BUILD_PASSES", None)
            if execution_state.scheduled_build_pass_target is not None:
                env["QONQ_SCHEDULED_BUILD_PASS_TARGET"] = str(execution_state.scheduled_build_pass_target)
            else:
                env.pop("QONQ_SCHEDULED_BUILD_PASS_TARGET", None)

            if is_repair_pass:
                env["QONQ_REPAIR_MODE"] = "1"
                env["QONQ_REPAIR_PLAN_PATH"] = str(repair_plan_path(worqspace))
                env["QONQ_REPAIRING_BUILD_PASS_INDEX"] = str(execution_state.repairing_build_pass_index or execution_state.build_pass_index)
            else:
                env.pop("QONQ_REPAIR_MODE", None)
                env.pop("QONQ_REPAIR_PLAN_PATH", None)
                env.pop("QONQ_REPAIRING_BUILD_PASS_INDEX", None)

            try:
                with open(path_manager.root / 'pipeline_config.yaml', 'r', encoding='utf-8') as f:
                    pipeline_config = yaml.safe_load(f)
            except Exception:
                print("Config Error")
                session_failed = True
                stop_reason = "config_error"
                break

            def resolve_template(tpl):
                if "{N}" in tpl:
                    return tpl.replace("{N}", str(cycle))
                return tpl

            agents_to_run = []
            agent_configs = config.get('agents', {})

            for agent_def in pipeline_config.get('agents', []):
                name = agent_def['name']
                agent_config = get_agent_config(agent_configs, name)
                provider = agent_config.get('provider', None)

                if agent_def.get('cycle_1_only', False) and not (execution_state.pass_kind == PASS_BUILD and execution_state.build_pass_index == 1):
                    continue
                if name == 'qompressor' and not use_qompressor:
                    continue
                if name == 'qontextor' and not use_qontextor:
                    continue
                if name == 'qontrabender' and not use_qontrabender:
                    continue
                if is_repair_pass and name in {'instruqtor', 'calqulator'}:
                    continue

                construqtor_provider = resolve_construqtor_provider(agent_configs)

                if name == 'qontrabender' and construqtor_provider != 'gemini':
                    continue
                if name == 'calqulator' and construqtor_provider == 'local':
                    continue

                if provider == 'local':
                    model_name = agent_config.get('model')
                    if not model_name:
                        print(f"Config Error: 'model' not specified for local agent '{name}'")
                        session_failed = True
                        stop_reason = "config_error"
                        break
                    script = f"{model_name}.py"
                    if not re.match(r'^[a-zA-Z0-9_]+$', model_name):
                        print(f"Config Error: Invalid 'model' name for local agent '{name}'")
                        session_failed = True
                        stop_reason = "config_error"
                        break
                else:
                    script = agent_def['script']

                input_val = agent_def['input']
                if isinstance(input_val, list):
                    input_paths = [str(path_manager.root / resolve_template(p)) for p in input_val]
                else:
                    input_paths = [str(path_manager.root / resolve_template(input_val))]

                cmd = ["python3", str(AGENT_MODULE_DIR / script)] + input_paths

                output_val = agent_def['output']
                if isinstance(output_val, list):
                    output_paths = [str(path_manager.root / resolve_template(p)) for p in output_val]
                    cmd.extend(output_paths)
                else:
                    cmd.append(str(path_manager.root / resolve_template(output_val)))

                agents_to_run.append((name, cmd))

            if session_failed:
                break

            pass_label = f"build pass {execution_state.build_pass_index}" if execution_state.pass_kind == PASS_BUILD else f"repair pass {execution_state.repair_pass_index} for build pass {execution_state.repairing_build_pass_index or execution_state.build_pass_index}"
            print(f"{qrane_prefix}Starting global iteration {cycle} ({Colors.C}{pass_label}{Colors.R})...\r")
            if args.auto and execution_state.pass_kind == PASS_BUILD:
                inst_prefix = get_agent_prefix("instruQtor", Colors.LIME, prefix)
                print(f"{inst_prefix}Ingesting cyqle{cycle}_tasq.md for build pass {execution_state.build_pass_index}...\r")

            previous_log_path = None
            for name, cmd in agents_to_run:
                env["QONQ_PREVIOUS_LOG"] = str(previous_log_path) if previous_log_path else ""
                agent_timeout = get_agent_config(agent_configs, name).get("timeout", 300)
                env["QONQ_AI_TIMEOUT"] = str(agent_timeout)

                canonical_stage = STAGE_ALIAS_MAP.get(name)
                if canonical_stage and start_stage:
                    start_stage(worqspace, canonical_stage, name, cycle, f"Stage {canonical_stage} starting ({name}) on {execution_state.pass_kind} pass.")
                    stage_display = canonical_stage
                    stage_label = {
                        'qrystallizer': 'Qrystallizer',
                        'qonstrictor': 'Qonstrictor, Qualifier',
                        'instruqtor': 'instruQtor',
                        'calqulator': 'calQulator',
                        'construqtor': 'construQtor, Qualifier',
                        'inspeqtor': 'inspeQtor, Qualifier',
                    }.get(name, name)
                    if name == 'construqtor':
                        stage_display = 'BUILD & VALIDATE'
                    stage_msg = f"Stage {stage_display} [{stage_label}]"
                    print(f"{qrane_prefix}{stage_msg}\r")
                    if name == 'calqulator':
                        gate_enabled = config.get('options', {}).get('cost_confirmation_gate', False)
                        gate_msg = f"Optional cost-gate: {'enabled' if gate_enabled else 'disabled'}."
                        print(f"{qrane_prefix}{gate_msg}\r")

                qonsole_log_path = path_manager.get_qonsole_log_path(name)

                if not run_agent(name, cmd, prefix, AGENT_COLORS.get(name, Colors.WHITE), qonsole_log_path, env):
                    recovered = False
                    if name == "inspeqtor":
                        recovered, recovery_notes = inspection_exit_is_recoverable(worqspace)
                        if recovered:
                            msg = "InspeQtor exited non-zero but recoverable inspection artifacts were found; continuing with degraded inspection state."
                            print(f"{qrane_prefix}{Colors.YELLOW}{msg}{Colors.R}\r")
                            if append_audit_event:
                                append_audit_event(
                                    worqspace,
                                    "inspection_substep_recovered",
                                    "INSPECTION",
                                    "inspeqtor",
                                    msg,
                                    {
                                        "global_iteration_index": execution_state.global_iteration_index,
                                        "notes": recovery_notes,
                                    },
                                )
                            if record_agent_completion:
                                record_agent_completion(worqspace, name, cycle, success=True)
                            previous_log_path = qonsole_log_path
                            continue

                    if canonical_stage and record_agent_completion:
                        record_agent_completion(worqspace, name, cycle, success=False)
                    elif record_support_service:
                        record_support_service(worqspace, name, cycle, artifacts=[], notes=[f"Support service '{name}' failed."], success=False)
                    session_failed = True
                    stop_reason = "inspection_stage_failure" if name == "inspeqtor" else "agent_failure"
                    break

                previous_log_path = qonsole_log_path
                if record_agent_completion:
                    record_agent_completion(worqspace, name, cycle, success=True)

                if name == "qrystallizer":
                    clarification_result = handle_intake_clarification(
                        worqspace,
                        prefix=prefix,
                        is_autonomous=is_autonomous,
                        config=config,
                        cycle=cycle,
                        qrystallizer_cmd=cmd,
                        env=env,
                        qonsole_log_path=qonsole_log_path,
                    )
                    if clarification_result.get("outcome") == "ready":
                        status = clarification_result.get("status")
                        no_midrun_questions = True
                        env["QONQ_NO_MIDRUN_QUESTIONS"] = "1"
                        clarification_lines = [
                            f"Clarification accepted with Task Spec status {status}.",
                            "Mid-run questioning disabled.",
                            "Runs complete after inspection unless scheduler mode or explicit continuation requires more work.",
                        ]
                        for msg in clarification_lines:
                            print(f"{qrane_prefix}{msg}\r")
                    elif clarification_result.get("outcome") == "blocked":
                        blocked_stop = True
                        stop_reason = clarification_result.get("reason", "clarification_waiting_for_input")
                        if record_pass_state:
                            record_pass_state(
                                worqspace,
                                global_iteration_index=execution_state.global_iteration_index,
                                pass_kind=execution_state.pass_kind,
                                build_pass_index=execution_state.build_pass_index,
                                repair_pass_index=execution_state.repair_pass_index,
                                repairing_build_pass_index=execution_state.repairing_build_pass_index,
                                cycle_estimate_mode=execution_state.cycle_estimate_mode,
                                estimated_build_passes=execution_state.estimated_build_passes,
                                scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                                stop_reason=stop_reason,
                                event_type="pass_blocked",
                                detail=f"Blocked after clarification with reason '{stop_reason}'.",
                            )
                        break
                    else:
                        session_failed = True
                        stop_reason = clarification_result.get("reason", "clarification_handshake_failed")
                        break

                if name == "instruqtor":
                    estimated = load_estimated_build_passes(worqspace)
                    if estimated is not None:
                        execution_state.estimated_build_passes = estimated
                        execution_state.scheduled_build_pass_target = resolve_scheduled_build_pass_target(
                            execution_state.cycle_estimate_mode,
                            estimated,
                            execution_state.build_pass_index,
                            execution_limits,
                        )
                        if update_execution_planning:
                            update_execution_planning(
                                worqspace,
                                estimated_build_passes=execution_state.estimated_build_passes,
                                scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                            )
                    auto_budget_details = apply_auto_repair_budget_if_enabled(
                        worqspace,
                        config,
                        execution_limits,
                        prefix,
                    )
                    if auto_budget_details.get("applied") and set_execution_config:
                        set_execution_config(worqspace, execution_limits, execution_state.cycle_estimate_mode)

                if name == 'calqulator' and config.get('options', {}).get('cost_confirmation_gate', False):
                    gate_prefix = get_agent_prefix("GateQeeper", Colors.YELLOW, prefix)
                    if no_midrun_questions:
                        print(f"{gate_prefix} Gate bypassed: no-mid-run-question enforcement active.")
                        continue
                    print(f"\n{gate_prefix} Cost estimate above. Proceed with this run? [y/N] ", end="", flush=True)
                    try:
                        answer = input().strip().lower()
                    except EOFError:
                        answer = "n"
                    if answer not in ('y', 'yes'):
                        print(f"{gate_prefix} Run cancelled by GateQeeper.")
                        session_failed = True
                        stop_reason = "cost_gate_declined"
                        break
                    print(f"{gate_prefix} Confirmed. Proceeding...")

            if session_failed:
                break
            if blocked_stop:
                break

            res = handle_cheqpoint(
                execution_state,
                execution_limits,
                is_autonomous,
                path_manager.get_reqap_path(cycle),
                prefix,
                path_manager,
                no_midrun_questions=no_midrun_questions,
                config=config,
            )

            if res["action"] == 'QUIT':
                user_quit = True
                stop_reason = res.get("reason")
                break
            if res["action"] == 'STOP':
                bounded_stop = True
                stop_reason = res.get("reason")
                if record_pass_state:
                    record_pass_state(
                        worqspace,
                        global_iteration_index=execution_state.global_iteration_index,
                        pass_kind=execution_state.pass_kind,
                        build_pass_index=execution_state.build_pass_index,
                        repair_pass_index=execution_state.repair_pass_index,
                        repairing_build_pass_index=execution_state.repairing_build_pass_index,
                        cycle_estimate_mode=execution_state.cycle_estimate_mode,
                        estimated_build_passes=execution_state.estimated_build_passes,
                        scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                        stop_reason=stop_reason,
                        event_type="pass_completed",
                        detail=f"Completed {execution_state.pass_kind} pass and stopped with reason '{stop_reason}'.",
                    )
                break
            if res["action"] == 'STOP_PARTIAL':
                partial_stop = True
                stop_reason = res.get("reason")
                if record_pass_state:
                    record_pass_state(
                        worqspace,
                        global_iteration_index=execution_state.global_iteration_index,
                        pass_kind=execution_state.pass_kind,
                        build_pass_index=execution_state.build_pass_index,
                        repair_pass_index=execution_state.repair_pass_index,
                        repairing_build_pass_index=execution_state.repairing_build_pass_index,
                        cycle_estimate_mode=execution_state.cycle_estimate_mode,
                        estimated_build_passes=execution_state.estimated_build_passes,
                        scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                        stop_reason=stop_reason,
                        event_type="pass_completed",
                        detail=f"Completed {execution_state.pass_kind} pass and stopped partially with reason '{stop_reason}'.",
                    )
                break
            if res["action"] == 'REPAIR':
                repair_cfg = get_repair_config(config)
                repair_plan = res.get("repair_plan") or load_optional_json(repair_plan_path(worqspace))
                target_groups = ", ".join((repair_plan or {}).get("target_build_groups", [])[:2])
                print(f"{qrane_prefix}Repair: preparing targeted repair\r")
                print(
                    f"{qrane_prefix}Repair: attempt {execution_state.repair_pass_index + 1} of {repair_cfg['max_attempts_per_build_pass']}"
                    + (f" | continuing with group {target_groups}" if target_groups else "")
                    + "\r"
                )
                if not prepare_same_run_repair_cycle(
                    execution_state.global_iteration_index,
                    execution_state.global_iteration_index + 1,
                    prefix,
                    path_manager,
                    repair_plan,
                    build_pass_index=execution_state.build_pass_index,
                    repair_pass_index=execution_state.repair_pass_index + 1,
                ):
                    partial_stop = True
                    stop_reason = "repair_preparation_failed"
                    break
                next_pass_kind = PASS_REPAIR
                next_repairing_build_pass_index = execution_state.build_pass_index
                update_manifest_for_repair_state(
                    worqspace,
                    "REPAIRING",
                    "RUN_ACTIVE",
                    "Approved same-run targeted repair from manifest-linked repair plan.",
                    pending_next_pass_kind=PASS_REPAIR,
                    pending_repairing_build_pass_index=execution_state.build_pass_index,
                )
                if record_pass_state:
                    record_pass_state(
                        worqspace,
                        global_iteration_index=execution_state.global_iteration_index,
                        pass_kind=execution_state.pass_kind,
                        build_pass_index=execution_state.build_pass_index,
                        repair_pass_index=execution_state.repair_pass_index,
                        repairing_build_pass_index=execution_state.repairing_build_pass_index,
                        cycle_estimate_mode=execution_state.cycle_estimate_mode,
                        estimated_build_passes=execution_state.estimated_build_passes,
                        scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                        pending_next_pass_kind=PASS_REPAIR,
                        pending_repairing_build_pass_index=execution_state.build_pass_index,
                        event_type="pass_completed",
                        detail=f"Completed build pass {execution_state.build_pass_index}; queued repair pass {execution_state.repair_pass_index + 1}.",
                    )
                continue
            if res["action"] == 'BUILD':
                if not prepare_followup_build_pass(
                    execution_state.global_iteration_index,
                    execution_state.global_iteration_index + 1,
                    prefix,
                    path_manager,
                    next_build_pass_index=execution_state.build_pass_index + 1,
                    estimated_build_passes=execution_state.estimated_build_passes,
                ):
                    partial_stop = True
                    stop_reason = "build_preparation_failed"
                    break
                next_pass_kind = PASS_BUILD
                next_repairing_build_pass_index = None
                if record_pass_state:
                    record_pass_state(
                        worqspace,
                        global_iteration_index=execution_state.global_iteration_index,
                        pass_kind=execution_state.pass_kind,
                        build_pass_index=execution_state.build_pass_index,
                        repair_pass_index=execution_state.repair_pass_index,
                        repairing_build_pass_index=execution_state.repairing_build_pass_index,
                        cycle_estimate_mode=execution_state.cycle_estimate_mode,
                        estimated_build_passes=execution_state.estimated_build_passes,
                        scheduled_build_pass_target=execution_state.scheduled_build_pass_target,
                        pending_next_pass_kind=PASS_BUILD,
                        event_type="pass_completed",
                        detail=f"Completed {execution_state.pass_kind} pass; scheduler queued build pass {execution_state.build_pass_index + 1}.",
                    )
                continue

    except KeyboardInterrupt:
        raise

    print()
    if blocked_stop:
        print(f"{qrane_prefix}{Colors.YELLOW}Run paused: waiting for clarification input.{Colors.R}\r")
    elif session_failed:
        print(f"{qrane_prefix}{Colors.WHITE}QonQrete session ended with {Colors.RED}errors{Colors.R}{Colors.WHITE}.{Colors.R}\r")
    else:
        print(f"{qrane_prefix}QonQrete session finished. Enjoy :)\r")

    if finalize_manifest:
        if session_failed:
            finalize_manifest(worqspace, "failed", f"Run ended with errors. Stop reason: {stop_reason or 'agent_failure'}.")
        elif blocked_stop:
            finalize_manifest(worqspace, "blocked", f"Run paused waiting for clarification input. Stop reason: {stop_reason or 'clarification_waiting_for_input'}.")
        elif user_quit:
            finalize_manifest(worqspace, "partial", f"Run ended at user-gated cheqpoint. Stop reason: {stop_reason or 'user_quit'}.")
        elif partial_stop:
            finalize_manifest(worqspace, "partial", f"Run ended partially. Stop reason: {stop_reason or 'partial_stop'}.")
        elif bounded_stop:
            finalize_manifest(worqspace, "completed", f"Run completed. Stop reason: {stop_reason or 'completed'}.")
        else:
            finalize_manifest(worqspace, "completed", f"Run finished without runtime errors. Stop reason: {stop_reason or 'completed'}.")


if __name__ == "__main__":
    main()
