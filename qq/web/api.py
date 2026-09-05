#!/usr/bin/env python3
"""
briQsQope local API server — lightweight HTTP server for the dashboard.

Serves:
  GET /api/qonqrete/read-model     → Full read model JSON
  GET /api/qonqrete/events/stream  → SSE event stream
  GET /api/qonqrete/events         → All events as JSON array
  GET /api/qonqrete/health         → Health check
  GET /api/qonqrete/config         → Sanitized runtime config
  GET /briQsQope.png, /QonQrete5.png, /briQsQope5.png, etc. → Static assets
  GET /                              → Enhanced dashboard landing page
 POST /api/qonqrete/runs           → authenticated QonQrete run creation (canonical)
 POST /v1/ingest/qq-trans          → legacy compatibility alias (deprecated)

Features:
  - Top menu: Dashboard, Agents, Tasks, Config, Tools
  - Agent Details: Agent, Model, Action (double-width, no Exit)
  - Action status with real event-driven updates
  - Ticket workflow: Build → Review (NOT Done), Review → Done/Repair
  - Clickable build group overlays with briQ drill-down
  - Agents page: 4-pane agent output view
  - Tasks page: build groups + briQs + original/enhanced task
  - Config page: real sanitized config view
  - Progress system: accepted/working/displayed/quality layers
  - FULLY_DONE timer freeze + green
  - Visual theme: construction-yard cybersquid dashboard
  - Logos: QonQrete5.png (Stats left), briQsQope5.png (below)
  - All live via SSE + periodic refresh

Runs on the configured host (default 0.0.0.0). No authentication for GET routes. Read-only.
POST routes are authenticated.
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
from .. import __version__
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# Add parent to path so we can import from qq.web
_sys_path_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _sys_path_root)

from qq.web.read_model import build_read_model, get_read_model_cache
from qq.web.events import EventTailer

# ---------------------------------------------------------------------------
# Import ingest module at module top (absolute import, not relative)
# This fixes the crash when api.py is run as a direct script.
# ---------------------------------------------------------------------------
from qq.web.ingest import (
    RunsAPIConfig,
    load_obelisk_config_from_env,
    check_auth,
    create_external_run_trigger,
    ValidationError,
    _state_artifact,
    _resolve_tmux_session,
    _get_runs_roots,
    command_preview,
)
from qq.web.run_registry import (
    ACTIVE_STATES,
    PENDING_STATES,
    TERMINAL_STATES,
    is_terminal_state,
    is_active_state,
    is_pending_state,
    normalize_state,
    resolve_run_timestamp,
    load_latest_run_records,
    load_latest_tmux_records,
    resolve_run_state,
    merge_run_sources,
    newest_run,
    atomic_write_json,
    atomic_read_json,
    append_jsonl,
    ControlLock,
    build_session_entry,
    sort_sessions_newest_first,
    _run_id_to_sort_key,
    _iso_to_sort_key,
)

# ---------------------------------------------------------------------------
# Route constants
# ---------------------------------------------------------------------------
RUNS_API_PATH = "/api/qonqrete/runs"
RESEND_CALLBACK_PATH = "/api/qonqrete/callbacks/resend"
LEGACY_QQ_TRANS_PATH = "/v1/ingest/qq-trans"

# Resolve path to repo root
_REPO_ROOT = _sys_path_root


def _iso_to_sort_key(iso_str: str) -> float:
    """Convert an ISO 8601 timestamp string to a sortable float.
    
    Returns 0.0 for empty/malformed strings so old runs sort last.
    """
    import time as _time_sort
    if not iso_str or not iso_str.strip():
        return 0.0
    try:
        # Try common ISO formats
        for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return _time_sort.mktime(_time_sort.strptime(iso_str[:19], fmt[:19]))
            except (ValueError, OverflowError):
                continue
        # Fallback: try to parse as epoch float
        return float(iso_str)
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _run_id_to_sort_key(run_id: str) -> float:
    """Parse a run ID to a sortable timestamp (epoch seconds).
    Supports patterns:
      - YYYYMMDD-HHMMSS-xxxx  (20260709-140126-77f11553)
      - YYYY-MM-DD_HH-MM-SS_xxxx
      - YYYYMMDD-HHMMSS
      - Fallback to ISO timestamps or 0.0
    """
    import time as _ts
    if not run_id or not run_id.strip():
        return 0.0
    run_id = run_id.strip()
    patterns = [
        (r'^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-', '%Y%m%d-%H%M%S'),
        (r'^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$', '%Y%m%d-%H%M%S'),
        (r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})', '%Y-%m-%d_%H-%M-%S'),
    ]
    for pat, fmt in patterns:
        m = __import__('re').match(pat, run_id)
        if m:
            try:
                if fmt == '%Y-%m-%d_%H-%M-%S':
                    ts_str = m.group(1) + '-' + m.group(2) + '-' + m.group(3) + '_' + m.group(4) + '-' + m.group(5) + '-' + m.group(6)
                else:
                    ts_str = m.group(1) + m.group(2) + m.group(3) + '-' + m.group(4) + m.group(5) + m.group(6)
                return _ts.mktime(_ts.strptime(ts_str, fmt))
            except (ValueError, OverflowError):
                pass
    return 0.0


_READ_MODEL_CACHE_TTL = 0.1


def _get_cached_read_model(run_root: str, force_refresh: bool = False) -> Dict[str, Any]:
    cache = get_read_model_cache()
    if not force_refresh:
        model = cache.get(run_root, ttl=_READ_MODEL_CACHE_TTL)
        if model is not None:
            return {k: v for k, v in model.items() if not k.startswith("_")}
    model = build_read_model(run_root)
    cache.set(run_root, model)
    return {k: v for k, v in model.items() if not k.startswith("_")}


def _find_logo_path() -> str:
    candidates = [
        os.path.join(_REPO_ROOT, "qq", "web", "briQsQope.png"),
        os.path.join(os.getcwd(), "qq", "web", "briQsQope.png"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0]


def _find_wallpaper_path() -> str:
    candidates = [
        os.path.join(_REPO_ROOT, "qq", "web", "briQsQope-bg.jpg"),
        os.path.join(_REPO_ROOT, "qq", "web", "briQsQope-wallpaper.jpg"),
        os.path.join(os.getcwd(), "qq", "web", "briQsQope-bg.jpg"),
        os.path.join(os.getcwd(), "qq", "web", "briQsQope-wallpaper.jpg"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0]


def _get_asset_path(filename: str) -> Optional[str]:
    candidates = [
        os.path.join(_REPO_ROOT, "qq", "web", filename),
        os.path.join(os.getcwd(), "qq", "web", filename),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Config view helper — sanitize and expose runtime config
# ---------------------------------------------------------------------------
_SENSITIVE_KEYS = [
    "key", "token", "secret", "password", "passwd", "credential",
    "auth", "bearer", "api_key", "access", "refresh", "private",
    "ssh", "cookie", "api-key", "openai_api_key", "deepseek_api_key",
    "codeseeq_api_key",
]


def _redact_dict(d: dict, redacted_keys: list = None) -> tuple:
    """Deep-redact sensitive values. Returns (sanitized_dict, list_of_redacted_keys)."""
    if redacted_keys is None:
        redacted_keys = []
    result = {}
    for k, v in d.items():
        k_lower = k.lower().replace("-", "_")
        if isinstance(v, dict):
            inner, rk = _redact_dict(v, redacted_keys)
            result[k] = inner
            redacted_keys = rk
        elif isinstance(v, list):
            result[k] = v
        elif isinstance(v, (int, float, bool, type(None))):
            result[k] = v
        elif any(s in k_lower for s in _SENSITIVE_KEYS):
            result[k] = "••••••••"
            redacted_keys.append(k)
        else:
            result[k] = str(v)
    return result, redacted_keys


def _read_toml(path: str):
    """Parse a TOML file with tomllib (py3.11+) or the tomli backport."""
    try:
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        try:
            import tomli as tomllib
            with open(path, "rb") as f:
                return tomllib.load(f)
        except ImportError:
            raise


def _read_yaml(path: str):
    """Parse a YAML file with PyYAML, falling back to a minimal JSON/line parser.

    Keeps the config helper from failing when PyYAML is unavailable on the host.
    """
    try:
        import yaml
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except ImportError:
        # Minimal fallback: try JSON first, then simple key: value lines.
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            try:
                return json.loads(txt)
            except Exception:
                values = {}
                for line in txt.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        k, v = line.split(":", 1)
                        values[k.strip().strip("'\"").strip()] = v.strip().strip("'\"").strip()
                return values
        except Exception:
            return None


def _get_sanitized_config() -> Dict[str, Any]:
    """Build a sanitized config view from available runtime sources.

    Read-only and never raises: any source that cannot be parsed is reported
    under that key with an explanatory marker so the Config page still renders.
    """
    config_view = {
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "sources": [],
        "config": {},
        "raw_sanitized": {},
        "redacted_keys": [],
    }
    all_redacted = []

    pyproject = os.path.join(_REPO_ROOT, "pyproject.toml")
    if os.path.isfile(pyproject):
        config_view["sources"].append({"path": pyproject, "type": "toml", "exists": True})
        try:
            raw_toml = _read_toml(pyproject)
            if isinstance(raw_toml, dict):
                sanitized_toml, rk = _redact_dict(raw_toml, all_redacted)
                config_view["config"]["pyproject"] = sanitized_toml
                all_redacted.extend(rk)
        except Exception:
            config_view["config"]["pyproject"] = {"error": "could not parse toml"}
    else:
        config_view["sources"].append({"path": pyproject, "type": "toml", "exists": False})

    config_yaml = os.path.join(_REPO_ROOT, "config", "qq.yaml")
    if os.path.isfile(config_yaml):
        try:
            raw = _read_yaml(config_yaml)
            if isinstance(raw, dict):
                sanitized, rk = _redact_dict(raw, all_redacted)
                config_view["config"]["qq_yaml"] = sanitized
                all_redacted.extend(rk)
            else:
                config_view["config"]["qq_yaml"] = {"error": "could not parse"}
        except Exception:
            config_view["config"]["qq_yaml"] = {"error": "could not parse"}
        config_view["sources"].append({"path": config_yaml, "type": "yaml", "exists": True})
    else:
        config_view["sources"].append({"path": config_yaml, "type": "yaml", "exists": False})

    env_vars = {}
    for k, v in sorted(os.environ.items()):
        if any(s in k.lower().replace("-", "_") for s in _SENSITIVE_KEYS):
            env_vars[k] = "••••••••"
            all_redacted.append(k)
        else:
            env_vars[k] = v
    config_view["config"]["environment"] = env_vars

    config_view["config"]["paths"] = {
        "repo_root": _REPO_ROOT,
        "python_exe": sys.executable,
        "cwd": os.getcwd(),
    }
    config_view["config"]["web"] = {
        "host": os.environ.get("QQ_WEB_HOST", "0.0.0.0"),
        "port": 31337,
        "product": "briQsQope",
        "source_of_truth": "qonqrete",
    }

    config_view["redacted_keys"] = sorted(set(all_redacted))
    return config_view


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class BriQsQopeHandler(http.server.BaseHTTPRequestHandler):
    run_root: str = ""
    repo_root: str = ""
    product_name: str = "briQsQope"
    tailer: EventTailer = None
    timeout: float = 30.0
    control_root: str = ""
    control_root_mode: bool = False
    _config_cache: Optional[Dict] = None
    _config_cache_ts: float = 0

    def log_message(self, format, *args):
        pass

    def _resolve_active_run(self) -> Optional[Dict[str, Any]]:
        """Re-read current-run.json and return the linked run dict, or None.

        If current-run.json is missing/malformed, auto-repair to the newest
        valid run from runs.jsonl or run directories.
        """
        control_root = self.control_root or self.run_root
        if not self.control_root_mode:
            current_run_path = os.path.join(self.run_root, "current-run.json")
        else:
            current_run_path = os.path.join(control_root, "current-run.json")

        if os.path.isfile(current_run_path):
            try:
                with open(current_run_path, "r") as f:
                    cr = json.load(f)
                if cr.get("run_id"):
                    return cr
            except (json.JSONDecodeError, OSError):
                pass

        # current-run.json is missing, malformed, or has no run_id
        # Auto-repair: find newest valid run
        newest = self._find_newest_valid_session()
        if newest and newest.get("run_id"):
            # Write repaired pointer
            atomic_write_json(control_root, "current-run.json", {
                "run_id": newest["run_id"],
                "run_root": newest.get("run_root", ""),
                "events_path": newest.get("events_path", ""),
                "state": newest.get("state", "unknown"),
                "runner": newest.get("runner", ""),
                "selection_reason": "auto-repair",
                "selected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            return newest
        return None

    def _resolve_active_run_executor(self) -> Optional[Dict[str, Any]]:
        """Read active-run.json for the actual executor state, not dashboard linkage."""
        control_root = self.control_root or self.run_root
        return atomic_read_json(control_root, "active-run.json")

    def _resolve_pending_run(self) -> Optional[Dict[str, Any]]:
        """Read pending-run.json for the latest pending run."""
        control_root = self.control_root or self.run_root
        return atomic_read_json(control_root, "pending-run.json")

    def _get_effective_root(self) -> str:
        """Resolve the effective run_root, following current-run.json if in control-root mode."""
        cr = self._resolve_active_run()
        if cr and cr.get("run_root") and os.path.isdir(cr["run_root"]):
            return cr["run_root"]
        return self.run_root

    def _get_effective_events_path(self) -> str:
        """Resolve the effective events_path from current-run.json or fall back."""
        cr = self._resolve_active_run()
        if cr:
            events_path = cr.get("events_path")
            if events_path:
                return events_path
            if cr.get("run_root"):
                return os.path.join(cr["run_root"], "events.jsonl")
        return os.path.join(self.run_root, "events.jsonl")

    def _reconcile_tailer(self) -> EventTailer:
        """Return a tailer bound to the current active events path.
        
        If the tailer is stale (different path than what current-run.json says),
        rebind it. This allows the dashboard to follow session switches.
        """
        effective_events = self._get_effective_events_path()
        current_tailer = BriQsQopeHandler.tailer
        if current_tailer and current_tailer.path != effective_events:
            current_tailer.rebind(effective_events)
        elif current_tailer is None:
            BriQsQopeHandler.tailer = EventTailer(effective_events)
        return BriQsQopeHandler.tailer

    def handle(self):
        """Override handle() to suppress known-disconnect tracebacks."""
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def handle_one_request(self):
        """Override to suppress known-disconnect tracebacks per-request."""
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _send_json(self, data: Any, status: int = 200, extra_headers: Optional[Dict[str, str]] = None):
        body = json.dumps(data, default=str, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _send_file(self, filepath: str):
        if not os.path.isfile(filepath):
            self._send_json({"error": "not found"}, status=404)
            return
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            mime_type = "application/octet-stream"
        with open(filepath, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _get_dashboard_url(self) -> str:
        """Build dashboard URL from actual server config.

        Prefers QONQRETE_PUBLIC_DASHBOARD_URL if set.
        Falls back to inferred http://<host>:<port>.
        Normalizes 0.0.0.0 and :: to 127.0.0.1.
        """
        public_url = os.environ.get("QONQRETE_PUBLIC_DASHBOARD_URL", "")
        if public_url:
            return public_url
        # Try to get from the server attributes or env
        host = getattr(self.server, "server_address", None)
        if host:
            bind_host, bind_port = host
        else:
            bind_host = os.environ.get("QQ_WEB_HOST",  "0.0.0.0")
            bind_port = int(os.environ.get("QQ_WEB_PORT", "31337"))
        # Normalize display host: do NOT use 0.0.0.0 or :: in URLs
        display_host = bind_host
        if display_host in ("0.0.0.0", "::", ""):
            display_host = "127.0.0.1"
        return f"http://{display_host}:{bind_port}"

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # Static assets
        asset_map = {
            "/briQsQope.png": "briQsQope.png",
            "/briQsQope2.png": "briQsQope2.png",
            "/briQsQope3.png": "briQsQope3.png",
            "/briQsQope5.png": "briQsQope5.png",
            "/QonQrete.png": "QonQrete.png",
            "/QonQrete5.png": "QonQrete5.png",
            "/QonQrete-briQsQope.png": "QonQrete-briQsQope.png",
            "/briQsQope-bg.jpg": "briQsQope-bg.jpg",
            "/briQsQope-wallpaper.jpg": "briQsQope-wallpaper.jpg",
            "/qonqrete-bottom-right.jpg": "qonqrete-bottom-right.jpg",
        }

        if path in asset_map:
            filename = asset_map[path]
            if filename in ("briQsQope-bg.jpg", "briQsQope-wallpaper.jpg"):
                wp = _find_wallpaper_path()
                self._send_file(wp)
                return
            p = _get_asset_path(filename)
            if p:
                self._send_file(p)
                return
            self._send_json({"error": f"asset not found: {filename}"}, status=404)
            return

        if path == "/api/qonqrete/health":
            # Read current-run.json fresh every time so dashboard follows session switches
            cr = self._resolve_active_run()
            control_root = self.control_root or self.run_root
            active_run_root = cr.get("run_root") if cr else None
            active_run_id = cr.get("run_id") if cr else None
            active_events_path = cr.get("events_path") if cr else None
            active_run_state = cr.get("state") if cr else None
            active_runner = cr.get("runner") if cr else None
            active_exit_code = cr.get("exit_code") if cr else None
            active_finished_at = cr.get("finished_at") if cr else None
            active_yolo = cr.get("yolo") if cr else None
            active_tmux_session = cr.get("tmux_session") if cr else None
            active_attach_command = cr.get("attach_command") if cr else None
            active_task_path = cr.get("task_path") if cr else None
            active_target_path = cr.get("target_path") if cr else None

            # Build dashboard URL from env var or self
            dashboard_url = os.environ.get("QONQRETE_PUBLIC_DASHBOARD_URL", "")
            if not dashboard_url:
                dashboard_url = self._get_dashboard_url()

            # Resolve active executor and pending from separate files
            active_executor = self._resolve_active_run_executor()
            pending = self._resolve_pending_run()
            health_resp = {
                "status": "ok",
                "product": self.product_name,
                "run_root": self.run_root,
                "control_root": control_root,
                "control_root_mode": self.control_root_mode,
                # Dashboard linkage (current-run.json)
                "linked_run_root": active_run_root,
                "linked_run_id": active_run_id,
                "linked_events_path": active_events_path,
                "linked_run_state": active_run_state,
                "linked_runner": active_runner,
                "linked_yolo": active_yolo,
                "linked_tmux_session": active_tmux_session,
                "linked_attach_command": active_attach_command,
                "linked_task_path": active_task_path,
                "linked_target_path": active_target_path,
                # Executor state (active-run.json)
                "active_run_id": active_executor.get("run_id") if active_executor else None,
                "active_run_root": active_executor.get("run_root") if active_executor else None,
                "active_run_state": active_executor.get("state") if active_executor else None,
                "active_runner": active_executor.get("runner") if active_executor else None,
                # Pending run (pending-run.json)
                "pending_run_id": pending.get("run_id") if pending else None,
                "pending_count": 1 if pending else 0,
                # Backwards compat (deprecated aliases, use linked_* or active_* instead)
                "active_run_id": active_run_id,
                "active_run_root": active_run_root,
                "active_events_path": active_events_path,
                "active_run_state": active_run_state,
                "active_runner": active_runner,
                "active_yolo": active_yolo,
                "active_tmux_session": active_tmux_session,
                "active_attach_command": active_attach_command,
                "active_task_path": active_task_path,
                "active_target_path": active_target_path,
                "dashboard_url": dashboard_url,
                "timestamp": time.time(),
                "source_of_truth": "qonqrete",
            }
            if active_exit_code is not None:
                health_resp["active_exit_code"] = active_exit_code
            if active_finished_at is not None:
                health_resp["active_finished_at"] = active_finished_at
            self._send_json(health_resp)

        elif path == "/api/qonqrete/current-run":
            self._handle_current_run()

        elif path == "/api/qonqrete/read-model":
            try:
                qs = parse_qs(parsed.query)
                force = qs.get("_refresh", [None])[0] is not None

                # Resolve active run_root using the shared helper
                effective_root = self._get_effective_root()

                model = _get_cached_read_model(effective_root, force_refresh=force)
                self._send_json(model)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)

        elif path == "/api/qonqrete/config":
            try:
                now = time.time()
                if self._config_cache and (now - self._config_cache_ts) < 5:
                    self._send_json(self._config_cache)
                    return
                cfg = _get_sanitized_config()
                self._config_cache = cfg
                self._config_cache_ts = now
                self._send_json(cfg)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)

        elif path == "/api/qonqrete/events":
            # Use reconciled tailer that follows current-run.json if in control-root mode
            tailer = self._reconcile_tailer()
            if tailer:
                events = tailer.get_all()
                self._send_json(events)
            else:
                fallback_tailer = EventTailer(os.path.join(self.run_root, "events.jsonl"))
                self._send_json(fallback_tailer.get_all())

        elif path == "/api/qonqrete/events/stream":
            # Use reconciled tailer that follows current-run.json.
            # Re-reads current-run.json on each SSE connect so session switching works.
            tailer = self._reconcile_tailer()

            if tailer:
                # Set a short socket timeout so writes detect client disconnect quickly
                try:
                    self.connection.settimeout(5.0)
                except Exception:
                    pass
                self._send_sse()
                try:
                    for sse_msg in tailer.sse_events():
                        try:
                            self.wfile.write(sse_msg.encode("utf-8"))
                            self.wfile.flush()
                        except (GeneratorExit, StopIteration):
                            break
                        except (BrokenPipeError, ConnectionResetError,
                                ConnectionAbortedError, TimeoutError, OSError):
                            break
                except GeneratorExit:
                    pass
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                        TimeoutError, OSError):
                    pass
            else:
                # Fallback: create EventTailer from run_root/events.jsonl
                try:
                    self.connection.settimeout(5.0)
                except Exception:
                    pass
                fallback_tailer = EventTailer(os.path.join(self.run_root, "events.jsonl"))
                self._send_sse()
                try:
                    for sse_msg in fallback_tailer.sse_events():
                        try:
                            self.wfile.write(sse_msg.encode("utf-8"))
                            self.wfile.flush()
                        except (GeneratorExit, StopIteration):
                            break
                        except (BrokenPipeError, ConnectionResetError,
                                ConnectionAbortedError, TimeoutError, OSError):
                            break
                except GeneratorExit:
                    pass
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError,
                        TimeoutError, OSError):
                    pass

        elif path == RUNS_API_PATH:
            # GET on POST-only route → 405
            self._send_json({
                "ok": False,
                "error": "method_not_allowed",
                "message": "Use POST /api/qonqrete/runs to create a run",
            }, status=405)

        elif path == "/":
            try:
                self._send_html(self._landing_page())
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": f"landing page render failed: {exc}"}, status=500)

        elif path == "/api/qonqrete/sessions":
            self._handle_get_sessions()

        else:
            self._send_json({"error": "not found"}, status=404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # -------------------------------------------------------------------
    # POST routes
    # -------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # Canonical route
        if path == RUNS_API_PATH:
            self._handle_create_run(
                legacy_endpoint=False,
                endpoint_path=RUNS_API_PATH,
            )
        # Session selection
        elif path == "/api/qonqrete/sessions/select":
            self._handle_select_session()

        # Session adoption
        elif path == "/api/qonqrete/sessions/adopt":
            self._handle_adopt_session()
        # Callback resend
        elif path == RESEND_CALLBACK_PATH:
            self._handle_callback_resend()
        # Legacy alias
        elif path == LEGACY_QQ_TRANS_PATH:
            self._handle_create_run(
                legacy_endpoint=True,
                endpoint_path=LEGACY_QQ_TRANS_PATH,
            )
        else:
            self._send_json(
                {"ok": False, "error": "not_found", "message": "POST endpoint not found"},
                status=404,
            )

    # -------------------------------------------------------------------
    # Backwards-compatible wrapper for old callers
    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # GET /api/qonqrete/current-run — current run state
    # -------------------------------------------------------------------
    def _find_newest_valid_session(self):
        """Find the newest valid session using canonical registry.

        Uses folded runs.jsonl (last-record-wins), then falls back to
        run directory scan.
        """
        control_root = self.control_root or self.run_root

        # Use folded history from run_registry (last-record-wins)
        folded = load_latest_run_records(control_root)

        best = None
        best_ts = 0.0

        for rid, entry in folded.items():
            rr = entry.get("run_root", "")
            if rr and os.path.isdir(rr):
                ts = resolve_run_timestamp(entry)
                if ts <= 0:
                    ts = _run_id_to_sort_key(rid)
                if ts > best_ts:
                    best_ts = ts
                    best = {
                        "run_id": rid,
                        "run_root": rr,
                        "events_path": entry.get("events_path", os.path.join(rr, "events.jsonl")),
                        "state": entry.get("state", "indexed"),
                        "runner": entry.get("runner", ""),
                        "yolo": entry.get("yolo"),
                        "created_at": entry.get("created_at", ""),
                        "started_at": entry.get("started_at", ""),
                        "target_path": entry.get("target_path", ""),
                        "task_path": entry.get("task_path", ""),
                        "tmux_session": entry.get("tmux_session", ""),
                        "attach_command": entry.get("attach_command", ""),
                    }

        # Fallback: scan runs_root
        if best is None:
            runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "")
            if not runs_root:
                try:
                    from qq.web.ingest import load_obelisk_config_from_env
                    cfg = load_obelisk_config_from_env()
                    runs_root = cfg.default_run_root
                except Exception:
                    pass
            runs_root = os.path.expanduser(runs_root)
            if runs_root and os.path.isdir(runs_root):
                try:
                    for d in os.listdir(runs_root):
                        run_dir = os.path.join(runs_root, d)
                        if not os.path.isdir(run_dir):
                            continue
                        events_path = os.path.join(run_dir, "events.jsonl")
                        if not os.path.isfile(events_path):
                            continue
                        key = _run_id_to_sort_key(d)
                        if key <= 0:
                            try:
                                key = os.path.getmtime(events_path)
                            except Exception:
                                pass
                        if key > best_ts:
                            best_ts = key
                            best = {
                                "run_id": d,
                                "run_root": run_dir,
                                "events_path": events_path,
                                "state": "indexed",
                                "runner": "",
                                "yolo": None,
                                "created_at": "",
                                "started_at": "",
                                "target_path": "",
                                "task_path": "",
                            }
                except OSError:
                    pass

        return best


    def _handle_current_run(self):
        """Return the current run state from current-run.json.
        ..."""
        cr = self._resolve_active_run()
        if not cr or not cr.get("run_id"):
            cr = self._find_newest_valid_session()
        if not cr or not cr.get("run_id"):
            self._send_json({"exists": False})
            return

        run_root_val = cr.get("run_root", "")
        target_path_val = cr.get("target_path", "")
        events_path_val = cr.get("events_path", "")

        # Resolve display_name / task_title
        display_name = ""
        if run_root_val:
            try:
                from qq.web.status_resolver import resolve_display_name, resolve_final_status
                display_name = resolve_display_name(run_root_val)
                final_status = resolve_final_status(run_root_val)
            except Exception:
                final_status = None

        # ── Resolve runner from all available sources ──
        runner_mode_from_cr = cr.get("runner", "") or cr.get("runner_mode", "")
        runner_mode = ""
        yolo_val = cr.get("yolo")

        if run_root_val:
            try:
                from qq.web.status_resolver import resolve_runner_metadata
                rmeta = resolve_runner_metadata(run_root_val)
                if rmeta.get("mode") and rmeta["mode"] != "unknown":
                    runner_mode = rmeta["mode"]
                    if runner_mode == "local_exec": runner_mode = "local"
                # Try to get yolo from runner metadata too
                if yolo_val is None:
                    yolo_val = rmeta.get("yolo")
            except Exception:
                pass

        if not runner_mode:
            runner_mode = runner_mode_from_cr
            if runner_mode == "local_exec": runner_mode = "local"

        tmux_session_val = cr.get("tmux_session", "")
        if not runner_mode and tmux_session_val:
            runner_mode = "tmux"
        if not runner_mode:
            # Try tmux session inference from session name
            try:
                import subprocess as _sp_cr
                run_id_val = cr.get("run_id", "")
                for prefix in ("qonqrete-", "qq-"):
                    session_name = f"{prefix}{run_id_val}"
                    result = _sp_cr.run(["tmux", "has-session", "-t", session_name],
                                        capture_output=True, timeout=1)
                    if result.returncode == 0:
                        runner_mode = "tmux"
                        tmux_session_val = session_name
                        break
            except Exception:
                pass
        if not runner_mode and run_root_val:
            # Check if runner artifacts exist
            if os.path.isfile(os.path.join(run_root_val, "runner.exit_code")) or                os.path.isfile(os.path.join(run_root_val, "runner.finished")):
                runner_mode = "local"
        if not runner_mode:
            runner_mode = ""

        # Resolve YOLO from tmux user options
        # Resolve YOLO from tmux user options using parse_boolish
        if yolo_val is None and tmux_session_val:
            try:
                import subprocess as _sp_yo
                result = _sp_yo.run(["tmux", "show-option", "-t", tmux_session_val, "-v", "@qonqrete_yolo"],
                                   capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    try:
                        from qq.web.status_resolver import parse_boolish
                        parsed = parse_boolish(result.stdout.strip())
                        if parsed is not None:
                            yolo_val = parsed
                    except Exception:
                        pass
            except Exception:
                pass

        # Also try YOLO from _resolve_tmux_session if still unknown
        if yolo_val is None and (tmux_session_val or run_root_val):
            try:
                run_id_for_tmux = cr.get("run_id", "")
                resolved_tmux = _resolve_tmux_session(tmux_session_val or "", run_id_for_tmux, self.control_root or self.run_root)
                if resolved_tmux.get("yolo") is not None:
                    yolo_val = resolved_tmux["yolo"]
            except Exception:
                pass

        # Resolve active executor and pending from separate files
        active_executor = self._resolve_active_run_executor()
        pending = self._resolve_pending_run()

        resp = {
            "exists": True,
            "run_id": cr.get("run_id", ""),
            "control_root": self.control_root or self.run_root,
            "run_root": run_root_val,
            "target_path": target_path_val,
            "task_path": cr.get("task_path", ""),
            "events_path": events_path_val,
            "state": cr.get("state") or "created",
            "final_status": final_status,
            "display_name": display_name,
            "task_title": display_name,
            "runner": runner_mode,
            "runner_mode": runner_mode,
            "yolo": yolo_val,
            "pid": cr.get("pid"),
            "tmux_session": cr.get("tmux_session", ""),
            "attach_command": cr.get("attach_command", ""),
            "command_preview": cr.get("command_preview", ""),
            "exit_code": cr.get("exit_code"),
            "failure_reason": cr.get("launch_error", ""),
            "stdout_log": cr.get("stdout_log", ""),
            "stderr_log": cr.get("stderr_log", ""),
            "created_at": cr.get("created_at", ""),
            "started_at": cr.get("started_at", ""),
            "finished_at": cr.get("finished_at", ""),
            "events_exists": os.path.isfile(events_path_val) if events_path_val else False,
            "plan_exists": os.path.isfile(_state_artifact(run_root_val, "plan.json")) if run_root_val else False,
            "final_exists": os.path.isfile(_state_artifact(run_root_val, "final.json")) if run_root_val else False,
            "target_exists": os.path.isdir(target_path_val) if target_path_val else False,
            "target_file_count": 0,
            # Dashboard linkage
            "linked_run_id": cr.get("run_id", ""),
            "linked_run_root": run_root_val,
            "linked_run_state": cr.get("state") or "created",
            # Executor state
            "active_run_id": active_executor.get("run_id") if active_executor else None,
            "active_run_root": active_executor.get("run_root") if active_executor else None,
            "active_run_state": active_executor.get("state") if active_executor else None,
            "active_runner_state": active_executor.get("runner") if active_executor else None,
            # Pending state
            "pending_run_id": pending.get("run_id") if pending else None,
            "pending_count": 1 if pending else 0,
        }

        # Count target files
        if target_path_val and os.path.isdir(target_path_val):
            try:
                count = 0
                for root, dirs, files in os.walk(target_path_val):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    count += len(files)
                    if count > 100:
                        break
                resp["target_file_count"] = count
            except OSError:
                pass

        self._send_json(resp)

    # -------------------------------------------------------------------
    # GET /api/qonqrete/sessions — list discoverable QonQrete sessions
    # -------------------------------------------------------------------
    def _handle_get_sessions(self):
        """List discoverable QonQrete sessions using the canonical run registry.

        Returns exactly one entry per run_id, sorted newest-first.
        State is resolved from durable evidence, not tmux liveness alone.
        """
        try:
            cr = self._resolve_active_run()
        except Exception:
            cr = None

        active_executor = self._resolve_active_run_executor()
        pending = self._resolve_pending_run()

        control_root = self.control_root or self.run_root

        # Load folded history from runs.jsonl (last-record-wins)
        folded_history = load_latest_run_records(control_root)

        # Discover run directories
        run_directories: Dict[str, Dict[str, Any]] = {}
        runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "")
        if not runs_root:
            try:
                from qq.web.ingest import load_obelisk_config_from_env
                cfg = load_obelisk_config_from_env()
                runs_root = cfg.default_run_root
            except Exception:
                pass
        runs_root = os.path.expanduser(runs_root)
        if runs_root and os.path.isdir(runs_root):
            try:
                for d in os.listdir(runs_root):
                    run_dir = os.path.join(runs_root, d)
                    if not os.path.isdir(run_dir):
                        continue
                    markers = ["events.jsonl", "state/plan.json", "state/final.json",
                               "task.md", "task.json", "runner.finished",
                               "runner.failed.json", "runner.exit_code"]
                    if not any(os.path.isfile(os.path.join(run_dir, m)) for m in markers):
                        continue
                    run_directories[d] = {
                        "run_id": d,
                        "run_root": run_dir,
                        "events_path": os.path.join(run_dir, "events.jsonl")
                            if os.path.isfile(os.path.join(run_dir, "events.jsonl")) else "",
                    }
            except OSError:
                pass

        # Load tmux records
        tmux_records = load_latest_tmux_records(control_root)

        # Discover live tmux sessions
        live_tmux: Dict[str, Dict[str, Any]] = {}
        try:
            import subprocess
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    name = line.strip()
                    if not name:
                        continue
                    if name.startswith("qonqrete-") or name.startswith("qq-"):
                        run_id = name.replace("qonqrete-", "").replace("qq-", "")
                        # Check managed status
                        managed = False
                        try:
                            mgr = subprocess.run(
                                ["tmux", "show-options", "-v", "-t", name,
                                 "@qonqrete_managed"],
                                capture_output=True, text=True, timeout=2,
                            )
                            managed = mgr.returncode == 0 and mgr.stdout.strip() == "1"
                        except Exception:
                            pass
                        live_tmux[name] = {
                            "run_id": run_id,
                            "tmux_session": name,
                            "attach_command": f"tmux attach -t {name}",
                            "managed": managed,
                            "tmux_alive": True,
                        }
        except (FileNotFoundError, Exception):
            pass

        # Merge all sources into unified entries
        merged = merge_run_sources(
            current_run_pointer=cr,
            active_run_pointer=active_executor,
            pending_run_pointer=pending,
            folded_history=folded_history,
            run_directories=run_directories,
            tmux_records=tmux_records,
            live_tmux_sessions=live_tmux,
            control_root=control_root,
        )

        # Build session entries
                # ── Fallback: if no sessions found from canonical sources, discover from run_root itself ──
        # This ensures the dashboard always shows the currently running session,
        # even without the external ingest/control-root infrastructure.
        if not merged:
            # Try discovering from the dashboard's own run_root
            local_root = self.run_root
            if local_root and os.path.isdir(local_root):
                markers = ["events.jsonl", "state/plan.json", "state/final.json",
                           "final.json", "task.json", "runner.finished"]
                if any(os.path.isfile(os.path.join(local_root, m)) for m in markers):
                    rid = os.path.basename(local_root)
                    merged[rid] = {
                        "run_id": rid,
                        "run_root": local_root,
                        "events_path": os.path.join(local_root, "events.jsonl")
                            if os.path.isfile(os.path.join(local_root, "events.jsonl")) else "",
                        "state": "running",
                        "source": "local-fallback",
                    }
        sessions = []
        seen_run_ids = set()
        for rid, entry in merged.items():
            if rid in seen_run_ids:
                continue
            seen_run_ids.add(rid)
            # Enrich with tmux resolution if we have a tmux session
            tmux_sess = entry.get("tmux_session", "")
            if tmux_sess and not entry.get("run_root"):
                try:
                    resolved = _resolve_tmux_session(tmux_sess, rid, control_root)
                    if resolved.get("run_root"):
                        entry["run_root"] = resolved["run_root"]
                    if resolved.get("events_path"):
                        entry["events_path"] = resolved["events_path"]
                    if resolved.get("target_path"):
                        entry["target_path"] = resolved["target_path"]
                    if resolved.get("task_path"):
                        entry["task_path"] = resolved["task_path"]
                except Exception:
                    pass

            session = build_session_entry(entry)
            sessions.append(session)

        # Sort strictly newest-first
        sessions = sort_sessions_newest_first(sessions)

        # Determine summary IDs
        newest = newest_run(merged)
        linked_run_id = cr.get("run_id") if cr else None
        active_run_id = active_executor.get("run_id") if active_executor else None
        pending_run_id = pending.get("run_id") if pending else None

        resp = {
            "ok": True,
            "control_root": control_root,
            "newest_run_id": newest.get("run_id") if newest else None,
            "linked_run_id": linked_run_id,
            "active_run_id": active_run_id,
            "pending_run_id": pending_run_id,
            "sessions": sessions,
        }
        self._send_json(resp)


    def _build_session_entry(self, run_id, state, runner, run_root, target_path,
                              events_path, task_path, tmux_session, attach_command,
                              yolo, created_at, started_at, exit_code, finished_at, source):
        """Build a consistent session entry dict."""
        # Determine link_status for sessions without run_root/events_path
        link_status = "linked" if (run_root and events_path) else "unresolved"
        if runner == "tmux" and not run_root and not events_path:
            link_status = "tmux_only_unresolved"
        entry = {
            "run_id": run_id,
            "state": state,
            "runner": runner,
            "run_root": run_root,
            "target_path": target_path,
            "events_path": events_path,
            "task_path": task_path,
            "tmux_session": tmux_session,
            "attach_command": attach_command,
            "link_status": link_status,
            "events_exists": os.path.isfile(events_path) if events_path else False,
            "plan_exists": os.path.isfile(_state_artifact(run_root, "plan.json")) if run_root else False,
            "final_exists": os.path.isfile(_state_artifact(run_root, "final.json")) if run_root else False,
            "target_exists": os.path.isdir(target_path) if target_path else False,
            "target_file_count": 0,
            "created_at": created_at,
            "started_at": started_at or created_at,
            "finished_at": finished_at,
            "exit_code": exit_code,
            "source": source,
        }
        if yolo is not None:
            entry["yolo"] = yolo
        # Count target files
        if target_path and os.path.isdir(target_path):
            try:
                count = 0
                for root, dirs, files in os.walk(target_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    count += len(files)
                    if count > 100:
                        break
                entry["target_file_count"] = count
            except OSError:
                pass
        return entry

    # -------------------------------------------------------------------
    # POST /api/qonqrete/sessions/adopt — manually adopt a tmux-only session
    # -------------------------------------------------------------------
    def _handle_adopt_session(self):
        """Adopt a tmux-only unresolved session by providing run metadata."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._send_json({"ok": False, "error": "invalid_json", "message": "Invalid JSON body"}, status=400)
            return

        tmux_session = data.get("tmux_session", "")
        run_root_req = data.get("run_root", "")
        events_path_req = data.get("events_path", "")
        target_path_req = data.get("target_path", "")
        task_path_req = data.get("task_path", "")

        if not tmux_session:
            self._send_json({"ok": False, "error": "missing_tmux_session", "message": "tmux_session is required"}, status=400)
            return
        if not run_root_req:
            self._send_json({"ok": False, "error": "missing_run_root", "message": "run_root is required"}, status=400)
            return

        # Validate tmux session exists
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", tmux_session],
                capture_output=True, timeout=2
            )
            if result.returncode != 0:
                self._send_json({"ok": False, "error": "tmux_session_not_found",
                                 "message": f"tmux session {tmux_session} does not exist"}, status=404)
                return
        except FileNotFoundError:
            self._send_json({"ok": False, "error": "tmux_not_installed", "message": "tmux is not installed"}, status=500)
            return
        except Exception as e:
            self._send_json({"ok": False, "error": "tmux_error", "message": str(e)}, status=500)
            return

        run_root = os.path.abspath(os.path.expanduser(run_root_req))
        if not os.path.isdir(run_root):
            self._send_json({"ok": False, "error": "run_root_not_found",
                             "message": f"run_root does not exist: {run_root}"}, status=404)
            return

        # Default events_path
        if not events_path_req:
            events_path_req = os.path.join(run_root, "events.jsonl")

        # Validate events_path is inside run_root or legacy-allowed
        events_path = os.path.abspath(os.path.expanduser(events_path_req))
        if not events_path.startswith(run_root + os.sep) and not events_path == os.path.join(run_root, "events.jsonl"):
            self._send_json({"ok": False, "error": "invalid_events_path",
                             "message": "events_path must be inside run_root"}, status=400)
            return

        events_exists = os.path.isfile(events_path)

        # Extract run_id from session name
        run_id = tmux_session
        for prefix in ("qonqrete-", "qq-"):
            if tmux_session.startswith(prefix):
                run_id = tmux_session[len(prefix):]
                break

        target_path = ""
        if target_path_req:
            target_path = os.path.abspath(os.path.expanduser(target_path_req))

        task_path = ""
        if task_path_req:
            task_path = os.path.abspath(os.path.expanduser(task_path_req))

        # Write tmux metadata options for future resolution
        control_root = self.control_root or self.run_root
        _tmux_opts = {
            "@qonqrete_run_id": run_id,
            "@qonqrete_control_root": control_root,
            "@qonqrete_run_root": run_root,
            "@qonqrete_events_path": events_path,
            "@qonqrete_runner": "tmux",
        }
        if target_path:
            _tmux_opts["@qonqrete_target_path"] = target_path
        if task_path:
            _tmux_opts["@qonqrete_task_path"] = task_path
        for opt_key, opt_val in _tmux_opts.items():
            try:
                subprocess.run(
                    ["tmux", "set-option", "-t", tmux_session, opt_key, str(opt_val)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                )
            except Exception:
                pass

        # Write tmux-sessions.jsonl
        try:
            _entry = {
                "run_id": run_id,
                "tmux_session": tmux_session,
                "control_root": control_root,
                "run_root": run_root,
                "events_path": events_path,
                "target_path": target_path,
                "task_path": task_path,
                "runner": "tmux",
                "yolo": False,
                "attach_command": f"tmux attach -t {tmux_session}",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "adopted",
            }
            _tmux_jsonl_path = os.path.join(control_root, "tmux-sessions.jsonl")
            os.makedirs(control_root, exist_ok=True)
            with open(_tmux_jsonl_path, "a") as _tf:
                _tf.write(json.dumps(_entry) + "\n")
        except (OSError, IOError):
            pass

        # Write current-run.json
        pointer = {
            "run_id": run_id,
            "run_root": run_root,
            "events_path": events_path,
            "target_path": target_path,
            "task_path": task_path,
            "runner": "tmux",
            "tmux_session": tmux_session,
            "attach_command": f"tmux attach -t {tmux_session}",
            "state": "running",
            "link_status": "adopted",
            "source": "adopted",
            "events_exists": events_exists,
            "yolo": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        current_run_path = os.path.join(control_root, "current-run.json")
        # Backup
        if os.path.isfile(current_run_path):
            try:
                import shutil
                shutil.copy2(current_run_path, os.path.join(control_root, "current-run.previous.json"))
            except OSError:
                pass
        # Atomic write
        try:
            import tempfile
            os.makedirs(control_root, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=control_root, prefix=".current-run.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(pointer, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                os.close(fd)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            os.replace(tmp_path, current_run_path)
        except Exception as e:
            self._send_json({"ok": False, "error": "write_failed", "message": str(e)}, status=500)
            return

        # Append to runs.jsonl
        runs_jsonl_path = os.path.join(control_root, "runs.jsonl")
        try:
            history_entry = dict(pointer)
            history_entry["switched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(runs_jsonl_path, "a") as f:
                f.write(json.dumps(history_entry) + "\n")
        except OSError:
            pass

        # Rebind tailer
        if BriQsQopeHandler.tailer and events_path:
            BriQsQopeHandler.tailer.rebind(events_path)

        self._send_json({
            "ok": True,
            "message": f"Adopted tmux session {tmux_session}",
            "run_id": run_id,
            "run_root": run_root,
            "events_path": events_path,
            "target_path": target_path,
            "task_path": task_path,
            "tmux_session": tmux_session,
            "attach_command": f"tmux attach -t {tmux_session}",
            "state": "running",
            "runner": "tmux",
            "events_exists": events_exists,
            "link_status": "adopted",
            "selectable": True,
        })

    # -------------------------------------------------------------------
    # POST /api/qonqrete/sessions/select — switch dashboard to a session
    # -------------------------------------------------------------------
    def _handle_select_session(self):
        """Switch the dashboard to a different QonQrete run session."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._send_json({"ok": False, "error": "invalid_json", "message": "Invalid JSON body"}, status=400)
            return

        run_id = data.get("run_id")
        run_root_req = data.get("run_root")
        tmux_session_req = data.get("tmux_session")
        control_root = self.control_root or self.run_root

        if not run_id and not run_root_req and not tmux_session_req:
            self._send_json({"ok": False, "error": "missing_identifier", "message": "run_id, run_root, or tmux_session required"}, status=400)
            return

        # If tmux_session provided, run resolver first
        if tmux_session_req and not run_id and not run_root_req:
            resolved = _resolve_tmux_session(tmux_session_req, tmux_session_req.replace("qonqrete-", "").replace("qq-", ""), control_root)
            if resolved.get("run_root") and resolved.get("events_path"):
                run_id = resolved.get("run_id")
                run_root_req = resolved.get("run_root")
            else:
                self._send_json({
                    "ok": False,
                    "error": "unresolved_session",
                    "message": "Cannot link to this session: no run_root or events_path found. The session is tmux-only and unresolved.",
                    "link_status": "tmux_only_unresolved",
                }, status=409)
                return

        # Resolve the run to select
        resolved_run_id = run_id
        resolved_run_root = run_root_req

        if run_root_req and not run_id:
            # Infer run_id from directory name
            resolved_run_id = os.path.basename(run_root_req)

        # Validate the run exists: check current-run.json, runs.jsonl, runs_root, tmux
        found = False
        found_entry = {}

        # Check current-run.json
        current_run_path = os.path.join(control_root, "current-run.json")
        if os.path.isfile(current_run_path):
            try:
                with open(current_run_path) as f:
                    cr = json.load(f)
                if cr.get("run_id") == resolved_run_id:
                    found = True
                    found_entry = cr
            except Exception:
                pass

        # Check runs_root directories
        if not found:
            runs_root = os.environ.get("QONQRETE_RUNS_ROOT", "")
            if not runs_root:
                try:
                    from qq.web.ingest import load_obelisk_config_from_env
                    cfg = load_obelisk_config_from_env()
                    runs_root = cfg.default_run_root
                except Exception:
                    pass
            runs_root = os.path.expanduser(runs_root)
            if runs_root and resolved_run_id:
                candidate = os.path.join(runs_root, resolved_run_id)
                if os.path.isdir(candidate):
                    # Check for at least one marker file
                    markers = ["events.jsonl", "plan.json", "final.json", "task.md", "task.json",
                               "runner.finished", "runner.failed.json"]
                    for m in markers:
                        if os.path.isfile(os.path.join(candidate, m)):
                            found = True
                            resolved_run_root = candidate
                            found_entry = {
                                "run_id": resolved_run_id,
                                "run_root": candidate,
                                "events_path": os.path.join(candidate, "events.jsonl"),
                            }
                            # Try to read state
                            if os.path.isfile(os.path.join(candidate, "runner.finished")):
                                found_entry["state"] = "finished"
                                try:
                                    with open(os.path.join(candidate, "runner.exit_code")) as ef:
                                        found_entry["exit_code"] = int(ef.read().strip())
                                except Exception:
                                    pass
                            else:
                                found_entry["state"] = "unknown"
                            break

        # Check tmux sessions
        if not found and resolved_run_id:
            try:
                import subprocess
                for prefix in ("qonqrete-", "qq-"):
                    session_name = f"{prefix}{resolved_run_id}"
                    result = subprocess.run(
                        ["tmux", "has-session", "-t", session_name],
                        capture_output=True, timeout=2
                    )
                    if result.returncode == 0:
                        found = True
                        found_entry = {
                            "run_id": resolved_run_id,
                            "state": "running",
                            "runner": "tmux",
                            "tmux_session": session_name,
                            "attach_command": f"tmux attach -t {session_name}",
                        }
                        break
            except Exception:
                pass

        if not found:
            self._send_json({"ok": False, "error": "run_not_found", "message": f"Run {resolved_run_id} not found"}, status=404)
            return

        # Reject tmux-only unresolved sessions: if run_root/events_path cannot be resolved,
        # return 409. Do not write an empty current-run.json pointer.
        if found and not found_entry.get("run_root") and not found_entry.get("events_path"):
            self._send_json({
                "ok": False,
                "error": "unresolved_session",
                "message": "Cannot link to this session: no run_root or events_path found. The session is tmux-only and unresolved.",
                "link_status": "tmux_only_unresolved",
            }, status=409)
            return

        # Backup previous current-run.json
        if os.path.isfile(current_run_path):
            try:
                import shutil
                backup_path = os.path.join(control_root, "current-run.previous.json")
                shutil.copy2(current_run_path, backup_path)
            except OSError:
                pass

        # Write updated current-run.json (dashboard linkage ONLY — never modify active-run.json)
        pointer = {
            "run_id": resolved_run_id,
            "run_root": found_entry.get("run_root", resolved_run_root or ""),
            "events_path": found_entry.get("events_path", ""),
            "task_path": found_entry.get("task_path", ""),
            "target_path": found_entry.get("target_path", ""),
            "mode": found_entry.get("mode", ""),
            "source": found_entry.get("source", "manual-switch"),
            "runner": found_entry.get("runner", ""),
            "tmux_session": found_entry.get("tmux_session", ""),
            "attach_command": found_entry.get("attach_command", ""),
            "state": found_entry.get("state", "unknown"),
            "created_at": found_entry.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "command_preview": found_entry.get("command_preview", ""),
            "selection_reason": "manual",
            "selected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if found_entry.get("yolo") is not None:
            pointer["yolo"] = found_entry["yolo"]
        if found_entry.get("exit_code") is not None:
            pointer["exit_code"] = found_entry["exit_code"]
        if found_entry.get("finished_at"):
            pointer["finished_at"] = found_entry["finished_at"]

        # Filter None values
        pointer = {k: v for k, v in pointer.items() if v is not None}

        # Atomic write
        try:
            import tempfile
            os.makedirs(control_root, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=control_root, prefix=".current-run.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(pointer, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                os.close(fd)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            os.replace(tmp_path, current_run_path)
        except Exception as e:
            self._send_json({"ok": False, "error": "write_failed", "message": str(e)}, status=500)
            return

        # Append to runs.jsonl
        runs_jsonl_path = os.path.join(control_root, "runs.jsonl")
        try:
            history_entry = dict(pointer)
            history_entry["switched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(runs_jsonl_path, "a") as f:
                f.write(json.dumps(history_entry) + "\n")
        except OSError:
            pass

        # Rebind the tailer to the new events path
        new_events = found_entry.get("events_path") or pointer.get("events_path", "")
        if new_events and BriQsQopeHandler.tailer:
            BriQsQopeHandler.tailer.rebind(new_events)

        # Return selected session
        resp = {
            "ok": True,
            "message": f"Switched to run {resolved_run_id}",
            "run_id": resolved_run_id,
            "run_root": pointer.get("run_root", ""),
            "events_path": pointer.get("events_path", ""),
            "target_path": pointer.get("target_path", ""),
            "task_path": pointer.get("task_path", ""),
            "state": pointer.get("state", ""),
            "runner": pointer.get("runner", ""),
            "tmux_session": pointer.get("tmux_session", ""),
            "attach_command": pointer.get("attach_command", ""),
            "yolo": pointer.get("yolo"),
        }
        self._send_json(resp)

    def _handle_ingest(self):
        """Legacy wrapper — delegates to _handle_create_run."""
        return self._handle_create_run(
            legacy_endpoint=True,
            endpoint_path=LEGACY_QQ_TRANS_PATH,
        )

    # -------------------------------------------------------------------
    # POST /api/qonqrete/runs — authenticated QonQrete run creation
    # (also serves legacy POST /v1/ingest/qq-trans with deprecation hints)
    # -------------------------------------------------------------------
    def _handle_callback_resend(self):
        """Handle POST /api/qonqrete/callbacks/resend — force resend a callback."""
        try:
            from qq.completion_callback import (
                maybe_send_terminal_callback,
                load_callback_state,
                get_run_terminal_status,
                load_origin_metadata,
                load_completion_callback_config,
                _resolve_per_run_callback_url,
            )
            import configparser as _cp

            # Auth
            from qq.obelisk_config import load_obelisk_config_from_env, check_auth
            config = load_obelisk_config_from_env()
            if not config.enabled:
                self._send_json({"ok": False, "error": "ingest_disabled"}, status=503)
                return

            auth_header = self.headers.get("Authorization")
            if not check_auth(auth_header, config):
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return

            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json({"ok": False, "error": "empty_body"}, status=400)
                return

            try:
                body = self.rfile.read(content_length)
                data = json.loads(body)
            except (json.JSONDecodeError, Exception) as e:
                self._send_json({"ok": False, "error": "invalid_json", "message": str(e)}, status=400)
                return

            if not isinstance(data, dict):
                self._send_json({"ok": False, "error": "invalid_payload"}, status=400)
                return

            force = data.get("force", False)

            # Resolve run_root
            run_root = data.get("run_root", "")
            run_id = data.get("run_id", "")

            if not run_root:
                if run_id:
                    # Look up run_root from runs directory
                    from qq.config import load_config as _qq_load_config
                    qq_cfg = _qq_load_config()
                    runs_root = qq_cfg.get("paths", {}).get("runs_root", "/x/qq/runs")
                    candidate = os.path.join(runs_root, run_id)
                    if os.path.isdir(candidate):
                        run_root = candidate
                    else:
                        # Try to find via control metadata
                        control_dir = qq_cfg.get("paths", {}).get("control_dir", "/x/qq/control")
                        metacand = os.path.join(control_dir, run_id)
                        if os.path.isdir(metacand):
                            run_root = metacand

                if not run_root:
                    self._send_json({
                        "ok": False,
                        "error": "missing_run_root",
                        "message": "Provide run_root or a resolvable run_id",
                    }, status=400)
                    return

            # Safety: validate run_root is under a valid runs/control root
            qq_cfg = _qq_load_config()
            valid_roots = []
            paths = qq_cfg.get("paths", {})
            if paths.get("runs_root"):
                valid_roots.append(os.path.realpath(paths["runs_root"]))
            if paths.get("control_dir"):
                valid_roots.append(os.path.realpath(paths["control_dir"]))
            valid_roots.append(os.path.realpath("/x/qq/runs"))
            valid_roots.append(os.path.realpath("/x/qq/control"))

            real_root = os.path.realpath(run_root)
            allowed = any(real_root.startswith(vr) for vr in valid_roots)
            if not allowed:
                self._send_json({
                    "ok": False,
                    "error": "invalid_run_root",
                    "message": "run_root is outside configured runs/control directories",
                }, status=403)
                return

            # Check origin.json exists
            if not os.path.isfile(os.path.join(run_root, "state", "origin.json")):
                self._send_json({
                    "ok": False,
                    "error": "no_origin_metadata",
                    "message": "Run has no origin metadata — cannot send callback",
                }, status=400)
                return

            # Check terminal
            status = get_run_terminal_status(run_root)
            if not status.terminal:
                self._send_json({
                    "ok": False,
                    "error": "not_terminal",
                    "status": status.status,
                    "message": f"Run is not in a terminal state (current: {status.status})",
                }, status=400)
                return

            # Check callback URL configured
            cb_url = _resolve_per_run_callback_url(run_root)
            if not cb_url:
                cfg = load_completion_callback_config()
                cb_url = cfg.url
            if not cb_url:
                self._send_json({
                    "ok": False,
                    "error": "callback_not_configured",
                    "message": "No callback URL configured for this run",
                }, status=400)
                return

            # Parse callback URL for response
            from urllib.parse import urlparse
            parsed_cb = urlparse(cb_url)

            # Send callback (force=True bypasses cooldown)
            state = maybe_send_terminal_callback(run_root, force=force)

            if state is None:
                self._send_json({
                    "ok": False,
                    "error": "callback_send_failed",
                    "message": "Callback send returned None",
                }, status=500)
                return

            # Build response (never expose token)
            resp = {
                "ok": state.state == "sent",
                "state": state.state,
                "run_id": state.run_id,
                "status": state.status,
                "callback_url_host": parsed_cb.hostname or "",
                "callback_url_port": parsed_cb.port or (443 if parsed_cb.scheme == "https" else 80),
                "attempts": state.attempts,
            }
            if state.last_error:
                resp["last_error"] = state.last_error

            self._send_json(resp, status=200)

        except Exception:
            import traceback
            traceback.print_exc()
            self._send_json({
                "ok": False,
                "error": "internal_error",
                "message": "An unexpected error occurred",
            }, status=500)

    def _handle_create_run(self, legacy_endpoint: bool = False, endpoint_path: str = RUNS_API_PATH):
        """Handle POST /api/qonqrete/runs (canonical) and legacy alias.

        Safe exception wrapper: any unexpected exception returns JSON 500,
        never "Empty reply from server".
        """
        try:
            self.__handle_create_run_impl(legacy_endpoint=legacy_endpoint, endpoint_path=endpoint_path)
        except Exception:
            # Log traceback to stderr in dev, but never leak to API response
            traceback.print_exc()
            self._send_json(
                {"ok": False, "error": "internal_error", "message": "An unexpected error occurred"},
                status=500,
            )

    def __handle_create_run_impl(self, legacy_endpoint: bool = False, endpoint_path: str = RUNS_API_PATH):
        """Implementation of run creation — isolated for safe exception wrapping."""

        # Load config
        config = load_obelisk_config_from_env()
        if not config.enabled:
            self._send_json(
                {"ok": False, "error": "ingest_disabled", "message": "QonQrete runs API is not enabled"},
                status=503,
            )
            return

        # Auth
        auth_header = self.headers.get("Authorization")
        if not check_auth(auth_header, config):
            self._send_json({"ok": False, "error": "unauthorized"}, status=401)
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json(
                {"ok": False, "error": "empty_body", "message": "Request body is empty"},
                status=400,
            )
            return

        try:
            body = self.rfile.read(content_length)
            data = json.loads(body)
        except (json.JSONDecodeError, Exception) as e:
            self._send_json(
                {"ok": False, "error": "invalid_json", "message": str(e)},
                status=400,
            )
            return

        if not isinstance(data, dict):
            self._send_json(
                {"ok": False, "error": "invalid_payload", "message": "Payload must be a JSON object"},
                status=400,
            )
            return

        # Get client IP if available
        client_ip = self.client_address[0] if self.client_address else None

        # Detect if task_text key exists in the payload; if missing, raise early
        if "task_text" not in data:
            self._send_json(
                {"ok": False, "error": "missing_task_text", "message": "task_text is required and must not be empty"},
                status=400,
            )
            return

        # Build request
        try:
            # Extract yolo from payload
            yolo_payload = data.get("yolo")
            if yolo_payload is not None:
                yolo_payload = bool(yolo_payload)

            result = create_external_run_trigger(
                source=data.get("source") or "manual-api",
                raw_transcription=data.get("raw_transcription") or "",
                task_text=data.get("task_text", ""),
                mode=data.get("mode", ""),
                target=data.get("target", ""),
                trigger=data.get("trigger", "qonqrete"),
                source_channel=data.get("source_channel"),
                sender_id=data.get("sender_id"),
                sender_display=data.get("sender_display"),
                chat_id=data.get("chat_id"),
                message_id=data.get("message_id"),
                transcription_id=data.get("transcription_id"),
                sender_name=data.get("sender_name"),
                chat_title=data.get("chat_title"),
                task_title=data.get("task_title"),
                reply_to=data.get("reply_to"),
                callback_url=data.get("callback_url"),
                callback_token=data.get("callback_token"),
                callback_token_ref=data.get("callback_token_ref"),
                obelisk=data.get("obelisk"),
                delimiter=data.get("delimiter"),
                received_at=data.get("received_at"),
                metadata=data.get("metadata"),
                config=config,
                request_ip=client_ip,
                endpoint_path=RUNS_API_PATH,
                legacy_endpoint=legacy_endpoint,
                yolo=yolo_payload,
            )
        except ValidationError as e:
            self._send_json(
                {"ok": False, "error": e.error, "message": e.message},
                status=e.status,
            )
            return

        # Map results to HTTP responses
        if not result.ok:
            status_map = {
                "unauthorized": 401,
                "target_not_allowed": 403,
                "sender_not_allowed": 403,
                "run_already_active": 409,
                "invalid_mode": 400,
                "invalid_trigger": 400,
                "missing_source": 400,
                "missing_raw_transcription": 400,
                "missing_trigger": 400,
                "missing_mode": 400,
                "missing_target": 400,
                "missing_task_text": 400,
                "empty_task_text": 400,
                "missing_sender_id": 400,
                "task_too_long": 400,
                "invalid_characters": 400,
                "relative_path_not_allowed": 403,
                "launch_failed": 500,
            }
            status = status_map.get(result.error, 500)
            response = {"ok": False, "error": result.error, "message": result.message}
            extra_hdrs = None
            if legacy_endpoint:
                response["deprecated_endpoint"] = True
                response["canonical_endpoint"] = RUNS_API_PATH
                extra_hdrs = {"Deprecation": "true", "Link": '</api/qonqrete/runs>; rel="successor-version"'}
            self._send_json(response, status=status, extra_headers=extra_hdrs)
            return

        # Build common response fields
        common = {
            "endpoint": RUNS_API_PATH,
        }
        extra_hdrs = None
        if legacy_endpoint:
            common["deprecated_endpoint"] = True
            common["canonical_endpoint"] = RUNS_API_PATH
            extra_hdrs = {"Deprecation": "true", "Link": '</api/qonqrete/runs>; rel="successor-version"'}

        if result.duplicate:
            self._send_json({
                **common,
                "ok": True,
                "duplicate": True,
                "run_id": result.run_id,
                "task_path": result.task_path,
                "target_path": result.target_path,
                "message": result.message,
            }, status=200, extra_headers=extra_hdrs)
            return

        if result.queued:
            self._send_json({
                **common,
                "ok": True,
                "started": False,
                "queued": True,
                "run_id": result.run_id,
                "run_root": result.run_root,
                "events_path": result.events_path,
                "queue_position": result.queue_position,
                "task_path": result.task_path,
                "target_path": result.target_path,
                "mode": result.mode,
                "runner": result.runner,
                "command_preview": result.command_preview,
                "dashboard_url": result.dashboard_url or self._get_dashboard_url(),
                "resolved_target_kind": result.resolved_target_kind,
                "source": getattr(result, "source", ""),
                "source_channel": getattr(result, "source_channel", ""),
                "completion_callback_configured": getattr(result, "completion_callback_configured", False),
                "yolo": getattr(result, "yolo", None),
            }, status=202, extra_headers=extra_hdrs)
            return

        if result.started:
            resp = {
                **common,
                "ok": True,
                "started": True,
                "queued": False,
                "run_id": result.run_id,
                "run_root": result.run_root,
                "events_path": result.events_path,
                "task_path": result.task_path,
                "target_path": result.target_path,
                "mode": result.mode,
                "runner": result.runner,
                "command_preview": result.command_preview,
                "dashboard_url": result.dashboard_url or self._get_dashboard_url(),
                "resolved_target_kind": result.resolved_target_kind,
                "source": getattr(result, "source", ""),
                "source_channel": getattr(result, "source_channel", ""),
                "completion_callback_configured": getattr(result, "completion_callback_configured", False),
                "yolo": getattr(result, "yolo", None),
            }
            if result.runner == "tmux":
                resp["tmux_session"] = result.tmux_session
                resp["attach_command"] = result.attach_command
            elif result.runner == "local_exec":
                if result.pid:
                    resp["pid"] = result.pid
                if getattr(result, "stdout_log", ""):
                    resp["stdout_log"] = result.stdout_log
                    resp["stderr_log"] = result.stderr_log

            self._send_json(resp, status=202, extra_headers=extra_hdrs)
            return

        self._send_json({**common, "ok": False, "error": "internal_error"}, status=500)

    # -------------------------------------------------------------------
    # Landing page helpers (unchanged from original)
    # -------------------------------------------------------------------
    def _fmt_elapsed(self, seconds: float) -> str:
        if seconds < 0:
            seconds = 0
        total = int(seconds)
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _model_display_code(self, code: str) -> str:
        lower = (code or "").lower()
        if "flash" in lower:
            return "fla-T" if "thinking" in lower else "fla"
        elif "pro" in lower:
            return "pro-T" if "thinking" in lower else "pro"
        return code if code else "?"

    def _landing_page(self) -> str:
        # The full landing page HTML is very long. We keep it identical
        # to the original. For brevity, we import it from a helper or
        # keep the original inline. Since we can't easily split it out
        # without major refactoring, we'll load the original from a
        # helper module if available, or keep it here.
        # Check if we have a pre-generated landing page file
        landing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_landing_page.html")
        if os.path.isfile(landing_path):
            with open(landing_path, "r") as f:
                return f.read()
        # Fallback: build the landing page from the original api.py backup
        # This is a simplified placeholder that keeps the SPA functional
        return _build_landing_page()


# ---------------------------------------------------------------------------
# Landing page builder (minimal clone of original for the in-memory SPA)
# ---------------------------------------------------------------------------

def _build_landing_page() -> str:
    """Build the landing page HTML. Extracted from original api.py."""
    # We keep the full landing page from the original api.py.
    # Since the original is ~2200 lines and mostly HTML/JS,
    # we embed it here. It's identical to the original.
    return _LANDING_PAGE_HTML.replace('QQVERSION', __version__)

# The full landing page is very long. We embed it verbatim.
_LANDING_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>briQsQope – QonQrete Dashboard</title>
<style>
/* ====== QONQRETE INDUSTRIAL THEME ====== */
:root {
  --bg-deep: #070909; --bg-metal: #0b0d0d; --bg-panel: #101313;
  --metal-dark: #181b1b; --metal-mid: #202322; --metal-light: #2a2d2b;
  --bevel-edge: #3b3f3d; --bevel-hi: #555955;
  --constr-orange: #d87a18; --constr-orange2: #e08a1f; --constr-amber: #f59e0b;
  --constr-yellow: #d6a42b; --constr-yellow2: #f0b429;
  --hazard-black: #050505;
  --ok-green: #34c759; --ok-green2: #3fb950;
  --alarm-red: #ff3b30; --alarm-red2: #f85149;
  --text-muted: #a7aba6; --text-main: #d7d3c7;
  --cyan-accent: #39d2c0; --pink-accent: #db61a2;
  --font-industrial: Impact,"Arial Narrow","Roboto Condensed","DIN Condensed",sans-serif;
  --font-mono: "SF Mono","Fira Code","Fira Mono",Menlo,Consolas,monospace;
  --font-ui: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --font-industrial-readable: "Roboto Condensed","Arial Narrow","Segoe UI",Helvetica,Arial,sans-serif;
  --font-digital: "Share Tech Mono","OCR A Std","Eurostile","Bank Gothic","Rajdhani","SFMono-Regular","SF Mono","Fira Code",Menlo,Consolas,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--bg-deep);color:var(--text-main);font-family:var(--font-ui);
  font-size:13px;line-height:1.5;overflow:hidden;height:100vh;
  background-image:url('/briQsQope-bg.jpg');background-size:cover;background-position:center;background-blend-mode:overlay;
}
a{color:var(--constr-amber);text-decoration:none}
a:hover{text-decoration:underline}

/* ── Reusable industrial elements ── */
.metal-panel{
  background:var(--metal-dark);border:2px solid var(--bevel-edge);
  position:relative;
}
.metal-panel::before{
  content:'';position:absolute;inset:0;border:1px solid var(--bevel-hi);
  pointer-events:none;opacity:0.2;
}
.metal-plate{
  background:var(--metal-mid);border:1px solid var(--bevel-edge);
  position:relative;
}
.metal-plate::after{
  content:'';position:absolute;inset:1px;border:1px solid rgba(255,255,255,0.03);
  pointer-events:none;
}
.orange-plaque{
  background:linear-gradient(135deg,var(--constr-orange),var(--constr-amber));
  color:var(--hazard-black);font-family:var(--font-industrial);font-weight:700;
  text-transform:uppercase;letter-spacing:1px;
  border:1px solid var(--bevel-edge);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.3),inset 0 -1px 0 rgba(0,0,0,0.4);
}
.inset-display{
  background:var(--hazard-black);border:1px solid var(--bevel-edge);
  color:var(--constr-amber);font-family:var(--font-mono);
  box-shadow:inset 0 2px 4px rgba(0,0,0,0.6);
}
.hazard-stripe{
  background:repeating-linear-gradient(-45deg,var(--constr-amber),var(--constr-amber) 4px,var(--hazard-black) 4px,var(--hazard-black) 8px);
  border:1px solid var(--bevel-edge);
}
.rivet{position:relative}
.rivet::before,.rivet::after{
  content:'';position:absolute;width:4px;height:4px;border-radius:50%;
  background:radial-gradient(circle,var(--bevel-hi) 30%,var(--bevel-edge) 70%);
  border:1px solid var(--metal-dark);
}

/* ── TOP BROWSER COCKPIT BAR ── */
.qq-industrial-shell{display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* ── NAV DECK ── */
.nav-deck{
  display:flex;align-items:center;gap:0;height:44px;
  background:linear-gradient(180deg,var(--metal-mid) 0%,var(--metal-dark) 100%);
  border-bottom:2px solid var(--bevel-edge);flex-shrink:0;padding:0;
}
.nav-brand-block{
  display:flex;align-items:center;gap:8px;padding:0 12px;
  background:var(--metal-dark);height:100%;
  border-right:1px solid var(--bevel-edge);
}
.nav-brand-block img{height:30px;max-width:190px;width:auto;object-fit:contain;object-position:left center;filter:drop-shadow(0 0 2px rgba(216,122,24,0.5))}
.nav-brand-label{
  font-family:var(--font-industrial-readable);font-size:14px;font-weight:600;
  color:var(--constr-orange);text-transform:uppercase;letter-spacing:1px;
}
.nav-tabs{display:flex;height:100%;gap:0}
.nav-tab{
  padding:0 18px;height:100%;display:flex;align-items:center;justify-content:center;
  background:var(--metal-dark);color:var(--text-muted);
  font-family:var(--font-industrial-readable);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.4px;
  cursor:pointer;border:none;border-right:1px solid var(--bevel-edge);
  position:relative;transition:background 0.15s;
}
.nav-tab:hover{background:var(--metal-mid);color:var(--constr-amber)}
.nav-tab.active{
  background:linear-gradient(180deg,var(--constr-orange2) 0%,var(--constr-orange) 100%);
  color:var(--hazard-black);font-weight:700;
  box-shadow:inset 0 2px 4px rgba(0,0,0,0.3);
}
.nav-tab.active::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:3px;
  background:var(--hazard-black);
}
/* BGP3: RUNS is a SQUARE yellow monitor/session icon button (no text label).
   Square via width/height + aspect-ratio, yellow icon via currentColor inherited
   from the button color. Preserves the generic .nav-tab hover/active behavior. */
.nav-sessions-btn{
  width:32px;height:32px;aspect-ratio:1/1;align-self:center;
  padding:0;margin:0 6px;color:var(--constr-amber);
  display:flex;align-items:center;justify-content:center;
  border:1px solid var(--bevel-edge);border-radius:0;background:var(--metal-dark);
}
.nav-sessions-btn .nav-sessions-icon{display:block;color:var(--constr-amber);flex-shrink:0;}
.nav-sessions-btn:hover{background:var(--metal-mid);color:var(--constr-amber);}
.nav-sessions-btn.active{background:linear-gradient(180deg,var(--constr-orange2) 0%,var(--constr-orange) 100%);color:var(--hazard-black);}
.nav-spacer{flex:1;min-width:0;overflow:hidden}
.qonqrete-transmission{
  height:28px;margin:8px 12px;
  background:var(--hazard-black);
  border:1px solid var(--bevel-edge);
  position:relative;
  box-shadow:inset 0 1px 3px rgba(0,0,0,0.8);
  overflow:hidden;
}
.qonqrete-transmission::before{
  content:'';position:absolute;top:0;left:0;width:4px;height:100%;
  background:linear-gradient(180deg,rgba(216,122,24,0.25),rgba(216,122,24,0.05),rgba(216,122,24,0.25));
  z-index:1;pointer-events:none;
}
.qonqrete-transmission::after{
  content:'';position:absolute;top:0;right:0;width:4px;height:100%;
  background:linear-gradient(180deg,rgba(216,122,24,0.25),rgba(216,122,24,0.05),rgba(216,122,24,0.25));
  z-index:1;pointer-events:none;
}
.transmission-viewport{
  position:relative;height:100%;overflow:hidden;
  mask-image:linear-gradient(to right,transparent 0%,black 30px,black calc(100% - 30px),transparent 100%);
  -webkit-mask-image:linear-gradient(to right,transparent 0%,black 30px,black calc(100% - 30px),transparent 100%);
}
.transmission-track{
  display:flex;align-items:center;height:100%;white-space:nowrap;
  will-change:transform;
}
.phrase-group{
  display:flex;align-items:center;flex-shrink:0;gap:18px;padding:0 10px;
}
.phrase-item{
  font-family:var(--font-digital);font-size:10.5px;font-weight:500;
  color:var(--constr-orange);
  text-transform:uppercase;letter-spacing:0.6px;
  white-space:nowrap;flex-shrink:0;
  text-shadow:0 0 1px rgba(216,122,24,0.3);
}
.phrase-sep{
  font-family:var(--font-digital);font-size:9px;
  color:var(--bevel-edge);flex-shrink:0;
  letter-spacing:1px;
}
.qonqrete-transmission .transmission-viewport{
  animation-play-state:running;
}
.qonqrete-transmission.paused .transmission-viewport .transmission-track{
  animation-play-state:paused;
}
@media(prefers-reduced-motion:reduce){
  .transmission-viewport{overflow-x:auto;}
  .transmission-track{animation:none!important;}
}
@media(max-width:1000px){
  .qonqrete-transmission{display:none}
}
/* A1-A4: nav-shell. .nav-conn-block hosts the single live Act:X action bar
   (#nav-action, setActionStatus) in place of the legacy CONNECTED indicator;
   flex-shrink:0 keeps the Act: label from wrapping/losing layout. */
.nav-conn-block{
  display:flex;align-items:center;gap:8px;padding:0 14px;height:100%;
  background:var(--metal-dark);border-left:1px solid var(--bevel-edge);flex-shrink:0;
}
.nav-action{
  font-family:var(--font-industrial-readable);font-size:10px;text-transform:uppercase;
  letter-spacing:0.5px;white-space:nowrap;
}
.nav-action-label{color:var(--bevel-hi)}
.nav-action-value{color:var(--constr-amber)}
.nav-action.err{color:var(--alarm-red)}
.nav-action.err .nav-action-label,.nav-action.err .nav-action-value{color:var(--alarm-red)}
.nav-action.good .nav-action-value{color:var(--ok-green2)}

/* A10 + BGP2: Total + Agent times share ONE nav-time-block (no divider between
   them). A single outer border-left separates the merged block from the preceding
   nav element. The Total and Agent sub-groups are separated only by an INVISIBLE
   spacer (nav-time-subsep) so no line/divider appears between them. */
.nav-time-block{
  display:flex;align-items:center;gap:6px;padding:0 10px;height:100%;
  background:var(--metal-dark);border-left:1px solid var(--bevel-edge);flex-shrink:0;
  font-family:var(--font-industrial-readable);font-size:10px;text-transform:uppercase;
  letter-spacing:0.5px;color:var(--text-muted);white-space:nowrap;
}
.nav-time-value{font-family:var(--font-digital);font-size:13px;font-weight:700;color:var(--constr-amber);}
.nav-time-value.green{color:var(--ok-green2)}
/* Invisible separator between the Total and Agent sub-groups inside the merged
   nav-time-block — intentionally borderless/transparent so nothing renders. */
.nav-time-subsep{width:6px;height:1px;flex-shrink:0;background:transparent;}

/* -- NAV PROGRESS (top-right PROGRESS: %) -- */
/* BGP1: shrink the top-right PROGRESS block to ~75% of its former width
   (padding 14px->8px and flex gap 8px->6px) so the nav-deck no longer overflows. */
.nav-progress-block{
  display:flex;align-items:center;gap:6px;padding:0 8px;height:100%;
  background:var(--metal-dark);border-left:1px solid var(--bevel-edge);
  font-family:var(--font-industrial-readable);font-size:10px;text-transform:uppercase;
  letter-spacing:0.5px;color:var(--text-muted);
  position:relative;flex-shrink:0;
}
.nav-progress-icon{color:var(--bevel-hi);font-weight:700;white-space:nowrap;}
.nav-progress-value{font-family:var(--font-digital);font-size:14px;font-weight:700;min-width:38px;text-align:right;color:var(--text-muted);}
.nav-progress-divider{color:var(--bevel-edge);}
.nav-progress-block.pulse .nav-progress-value{animation:progress-pulse 0.6s ease-out;}
.nav-progress-block.done .nav-progress-value,.nav-progress-block.green .nav-progress-value{
  color:var(--ok-green2) !important;text-shadow:0 0 12px var(--ok-green2);
  box-shadow:0 0 12px var(--ok-green2);
}
@keyframes progress-pulse{
  0%{transform:scale(1);}
  50%{transform:scale(1.25);}
  100%{transform:scale(1);}
}


/* ── RUN STATUS DECK ── */
.run-status-deck{
  background:var(--metal-dark);border-bottom:2px solid var(--bevel-edge);
  flex-shrink:0;padding:0;
}







.run-status-row2{
  display:flex;align-items:center;gap:0;padding:3px 12px 5px;
  background:var(--hazard-black);border-top:1px solid var(--bevel-edge);
  font-size:11px;flex-wrap:wrap;
}
.telemetry-item{
  display:flex;align-items:center;gap:4px;padding:0 10px;
  border-right:1px solid var(--bevel-edge);
}
.telemetry-item:last-child{border-right:none}
.telemetry-lbl{
  color:var(--text-muted);font-family:var(--font-industrial-readable);
  font-weight:600;text-transform:uppercase;font-size:9px;letter-spacing:0.35px;
}
.telemetry-val{
  color:var(--constr-amber);font-family:var(--font-mono);font-weight:600;font-size:11px;
}
.telemetry-val.good{color:var(--ok-green2)}
.telemetry-val.bad{color:var(--alarm-red)}
.telemetry-val.waiting{color:var(--constr-yellow2)}
.telemetry-val.total-count{color:var(--constr-amber)}
.telemetry-run-item{
  min-width:260px;flex:0 0 auto;
}
.telemetry-run-id{
  display:inline-block;min-width:210px;max-width:none;
  overflow:visible;text-overflow:clip;white-space:nowrap;
}

/* ── MAIN WORK YARD ── */
.workyard-main{flex:1 1 auto;min-height:180px;min-width:0;overflow:hidden;display:flex;position:relative}
.ticket-yard{
  display:flex;gap:0;height:100%;width:100%;overflow:hidden;
  padding:6px;gap:6px;
}
.ticket-bay{
  flex:1;display:flex;flex-direction:column;
  background:var(--metal-dark);border:2px solid var(--bevel-edge);
  position:relative;overflow:hidden;min-width:0;
}
.ticket-bay::before{
  content:'';position:absolute;top:0;left:0;width:8px;height:8px;
  background:var(--constr-amber);clip-path:polygon(0 0,100% 0,0 100%);
  z-index:2;
}
.ticket-bay::after{
  content:'';position:absolute;top:0;right:0;width:8px;height:8px;
  background:var(--constr-amber);clip-path:polygon(100% 0,100% 100%,0 0);
  z-index:2;
}
.ticket-bay .bay-corner-bl{
  position:absolute;bottom:0;left:0;width:8px;height:8px;
  background:var(--constr-amber);clip-path:polygon(0 100%,0 0,100% 100%);
  z-index:2;
}
.ticket-bay .bay-corner-br{
  position:absolute;bottom:0;right:0;width:8px;height:8px;
  background:var(--constr-amber);clip-path:polygon(100% 100%,0 100%,100% 0);
  z-index:2;
}
.bay-header{
  padding:10px 12px;display:flex;align-items:center;gap:10px;flex-shrink:0;
  background:linear-gradient(180deg,var(--constr-orange) 0%,var(--constr-amber) 100%);
  border-bottom:2px solid var(--bevel-edge);
}
.bay-header-icon{
  font-size:20px;color:var(--hazard-black);font-weight:800;
}
.bay-header-label{
  font-family:var(--font-industrial-readable);font-size:13px;font-weight:600;
  color:var(--hazard-black);text-transform:uppercase;letter-spacing:1px;
}
.bay-header-count{
  margin-left:auto;background:var(--hazard-black);color:var(--constr-amber);
  font-family:var(--font-mono);font-size:13px;font-weight:700;
  padding:1px 10px;border:1px solid rgba(0,0,0,0.3);
}
.bay-scroll{
  flex:1;overflow-y:auto;padding:8px;
  background:var(--bg-panel);
}
.bay-scroll::-webkit-scrollbar{width:5px}
.bay-scroll::-webkit-scrollbar-track{background:var(--hazard-black)}
.bay-scroll::-webkit-scrollbar-thumb{background:var(--constr-orange);border-radius:2px}

/* ── Empty column cybersquid ── */
.empty-bay{
  text-align:center;padding:24px 8px;color:var(--text-muted);
  display:flex;flex-direction:column;align-items:center;
}
.empty-bay .cybersquid-sm{width:70px;height:70px;margin-bottom:6px;opacity:0.7}
.empty-bay .empty-label{font-family:var(--font-industrial);text-transform:uppercase;font-size:11px;letter-spacing:1px;color:var(--text-muted);}

/* ── Group cards (metal ticket) ── */
.group-card{
  background:var(--metal-dark);border:1px solid var(--constr-orange);
  padding:10px;margin-bottom:6px;cursor:pointer;
  position:relative;transition:border-color 0.15s;
}
.group-card:hover{border-color:var(--constr-amber);box-shadow:0 0 8px rgba(216,122,24,0.15);}
.group-card::before{
  content:'';position:absolute;top:0;left:0;width:6px;height:6px;
  background:var(--constr-orange);clip-path:polygon(0 0,100% 0,0 100%);
}
.group-title{
  font-family:var(--font-industrial-readable);font-size:12px;font-weight:600;text-transform:uppercase;
  letter-spacing:0.4px;margin-bottom:4px;display:flex;align-items:center;gap:6px;
  color:var(--text-main);
}
.group-desc{font-size:11px;color:var(--text-muted);margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.group-status{
  font-size:9px;padding:1px 6px;font-family:var(--font-industrial-readable);text-transform:uppercase;
  letter-spacing:0.25px;
  background:var(--ok-green2);color:var(--hazard-black);font-weight:600;
  line-height:1.2;
}
.group-status.status-planned{background:var(--pink-accent);}
.group-status.status-building,.group-status.status-in_progress,.group-status.status-picked_up,.group-status.status-active{background:var(--constr-amber);}
.group-status.status-reviewing,.group-status.status-built,.group-status.status-ready_for_review,.group-status.status-validating{background:var(--cyan-accent);}
.group-status.status-repair_needed,.group-status.status-failed{background:var(--alarm-red);}
.group-status.status-done{background:var(--ok-green2);}
.group-weight{font-size:10px;color:var(--constr-amber);margin-left:auto;font-family:var(--font-mono);}
.briq-list{display:flex;flex-wrap:wrap;gap:3px}
.briq-item{
  display:flex;align-items:center;gap:2px;font-size:10px;padding:1px 6px;
  background:var(--hazard-black);border:1px solid var(--bevel-edge);
}
.briq-icon{font-size:9px;color:var(--constr-amber)}
.briq-title{color:var(--text-muted)}

/* ── DECK RESIZER ── */
:root{
  --bottom-deck-height:200px;
  --deck-resizer-height:8px;
}
.deck-resizer{
  width:100%;height:var(--deck-resizer-height);flex-shrink:0;
  background:linear-gradient(180deg,var(--metal-dark),var(--metal-mid),var(--metal-dark));
  border-top:1px solid var(--bevel-edge);border-bottom:1px solid var(--bevel-edge);
  cursor:row-resize;
  display:flex;align-items:center;justify-content:center;
  position:relative;z-index:10;
  transition:background 0.15s;
}
.deck-resizer:hover,.deck-resizer:active,.deck-resizer.dragging{
  background:linear-gradient(180deg,var(--metal-mid),var(--metal-light),var(--metal-mid));
}
.deck-resizer::after{
  content:'';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:120px;height:2px;
  background:linear-gradient(90deg,transparent 0%,var(--constr-orange) 10%,var(--constr-orange) 90%,transparent 100%);
  border-radius:1px;
}
.deck-resizer::before{
  content:'';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:60px;height:4px;
  background:linear-gradient(90deg,transparent,var(--constr-orange) 20%,var(--constr-orange) 80%,transparent);
  border-radius:2px;opacity:0.6;
}
.deck-resizer:focus-visible{
  outline:2px solid var(--constr-orange);outline-offset:-1px;
}
body.deck-resizing{
  user-select:none;-webkit-user-select:none;
  cursor:row-resize;
}
body.deck-resizing .deck-resizer{background:linear-gradient(180deg,var(--metal-mid),var(--metal-light),var(--metal-mid));}

/* ── BOTTOM INSTRUMENT DECK ── */
.bottom-instrument-deck{
  display:flex;gap:6px;padding:6px;height:var(--bottom-deck-height);flex:0 0 var(--bottom-deck-height);
  background:var(--metal-dark);border-top:none;
}






.event-log-panel{
  flex:1;display:flex;flex-direction:column;
  background:var(--hazard-black);border:2px solid var(--bevel-edge);
  overflow:hidden;min-width:0;
  /* BGP9: guarantee the terminal keeps a usable minimum width even when the
     enlarged squid image wants more horizontal room. */
  min-width:340px;
}
.event-log-header{
  padding:4px 12px;display:flex;align-items:center;gap:10px;
  background:linear-gradient(180deg,var(--metal-light) 0%,var(--metal-dark) 100%);
  border-bottom:1px solid var(--bevel-edge);flex-shrink:0;
}
.event-log-header .log-label{
  font-family:var(--font-industrial-readable);font-size:11px;text-transform:uppercase;
  letter-spacing:1px;color:var(--constr-orange);font-weight:700;
}
.event-log-header .log-clear{
  margin-left:auto;cursor:pointer;font-size:10px;color:var(--text-muted);
  background:var(--metal-dark);border:1px solid var(--bevel-edge);
  padding:1px 8px;font-family:var(--font-industrial);text-transform:uppercase;
}
.event-log-header .log-clear:hover{color:var(--constr-amber);border-color:var(--constr-amber);}
.event-log-body{
  flex:1;overflow-y:auto;padding:4px 10px;font-family:var(--font-mono);font-size:10px;line-height:1.6;
}
.event-log-body::-webkit-scrollbar{width:4px}
.event-log-body::-webkit-scrollbar-track{background:transparent}
.event-log-body::-webkit-scrollbar-thumb{background:var(--constr-orange);border-radius:2px}
.term-line{padding:1px 0;white-space:pre-wrap;word-break:break-all}
.term-ts{color:var(--constr-amber);margin-right:6px}
.term-type{color:var(--cyan-accent);margin-right:6px}

/* BGP9: the big cybersquid area is height-constrained (matches the event-log
   height) but NO LONGER fixed-width. It uses flex:0 1 auto so its width follows
   the image containment and shrinks before the event log does. Residual tradeoff:
   at very small deck heights the squid may look small, and at very large deck
   heights it can occupy more horizontal room — but the event-log retains its
   min-width (340px) so the terminal stays usable. */
.big-mascot-area{
  height:calc(var(--bottom-deck-height) - 12px);
  min-width:0;flex:0 1 auto;display:flex;align-items:center;justify-content:center;
  position:relative;
}
.big-mascot-area{flex-direction:column}
/* BGP9: scale image to the container height; width follows the aspect ratio and
   never exceeds the available space (no cropping via object-fit:contain). */
.big-mascot-area img{height:100%;width:auto;max-width:100%;object-fit:contain}
/* BGP7: spinner sits ON the squid in its top-left corner, displaced downward by
   ~1.5x its own height and rightward by ~1x its own height (unit = --mascot-unit,
   set by JS to the loader's rendered height/font-size in px). */
.mascot-loader{
  position:absolute;top:calc(4px + 1.5 * var(--mascot-unit, 13px));left:calc(4px + 1 * var(--mascot-unit, 13px));
  right:auto;bottom:auto;text-align:left;line-height:1;z-index:2;
  font-size:var(--mascot-font, 12px);
  font-family:var(--font-mono);color:var(--constr-amber);
  text-shadow:0 0 6px rgba(245,158,11,.6);white-space:nowrap;
}

/* ── INLINE CYBERSQUID SVG ── */
.cybersquid-sm svg,.cybersquid-big svg{width:100%;height:100%}
.alarm-eye{fill:var(--alarm-red);animation:alarmPulse 2s infinite}
@keyframes alarmPulse{0%,100%{opacity:1}50%{opacity:0.4}}

/* ── Panel views (agents, tasks, config) ── */
#panel-view{display:none;flex:1;min-height:0;overflow:hidden;flex-direction:column;background:var(--bg-panel)}
#panel-view.active{display:flex}
.panel-section{background:var(--metal-dark);border:1px solid var(--bevel-edge);display:flex;flex-direction:column;min-height:0;overflow:hidden}
.panel-section-header{padding:6px 10px;background:var(--metal-mid);border-bottom:1px solid var(--bevel-edge);font-family:var(--font-industrial-readable);font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--constr-orange);flex-shrink:0;}
.panel-section-body{padding:10px;font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;word-break:break-word;overflow-wrap:break-word;max-height:400px;overflow-y:auto;color:var(--text-muted);}
#agents-panel{display:flex;flex-direction:column;min-height:0;overflow:hidden;flex:1;height:100%;gap:6px}
.agent-grid{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:6px;height:100%;min-height:0}
.agent-pane{background:var(--metal-dark);border:1px solid var(--bevel-edge);display:flex;flex-direction:column;overflow:hidden;min-height:0}
.agent-pane{transition:box-shadow .2s,border-color .2s;}
.agent-pane-header{padding:5px 10px;background:var(--metal-mid);border-bottom:1px solid var(--bevel-edge);font-family:var(--font-industrial-readable);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--pane-accent, var(--constr-amber));}
.agent-pane-body{flex:1;overflow-y:auto;padding:6px 10px;font-family:var(--font-mono);font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--text-muted);}
.agent-pane.agent-active{
  border-color:var(--constr-amber);
  box-shadow:0 0 10px rgba(245,158,11,.35);
}
/* A6: per-role terminal colors on near-black */
.agent-pane.qla{--pane-accent:var(--cyan-accent)}
.agent-pane.ins{--pane-accent:var(--pink-accent)}
.agent-pane.con{--pane-accent:var(--constr-amber)}
.agent-pane.spq{--pane-accent:var(--ok-green2)}
.agent-pane .agent-pane-body{background:#000000;}
.agent-pane .agent-pane-body,
.agent-pane .agent-pane-body .agent-line,
.agent-pane .agent-pane-body .agent-info,
.agent-pane .agent-pane-body .agent-error,
.agent-pane .agent-pane-body .agent-tool,
.agent-pane .agent-pane-body .agent-thought,
.agent-pane .agent-pane-body .agent-ts{
  color:var(--pane-accent, var(--text-muted));
}
.agent-live-dot{
  color:var(--ok-green2);animation:live-pulse 1.2s ease-in-out infinite;
  font-size:10px;vertical-align:middle;display:inline-block;
}
@keyframes live-pulse{
  0%,100%{opacity:1;}
  50%{opacity:.2;}
}
.agent-line{font-family:var(--font-mono);font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text-main);}
.agent-error{color:var(--alarm-red);}
.agent-tool{color:var(--constr-amber);}
.agent-thought{color:var(--pink-accent);}
.agent-info{color:var(--text-main);}
.agent-ts{color:var(--bevel-hi);font-size:10px;font-family:var(--font-digital);}
.task-section{margin-bottom:10px}
.task-label{font-family:var(--font-industrial);font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--constr-orange);margin-bottom:4px;}
.task-content{font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;word-break:break-word;background:var(--hazard-black);padding:8px;border:1px solid var(--bevel-edge);overflow-y:auto;color:var(--text-muted);}
/* A8: Tasks page full-height 50/50 vertical split with independent scrollbars */
#tasks-panel{display:flex;flex-direction:column;height:100%;overflow:hidden}
#tasks-panel .task-section{flex:1 1 50%;min-height:0;display:flex;flex-direction:column;margin-bottom:0}
#tasks-panel .task-label{flex-shrink:0}
#tasks-panel .task-content{flex:1 1 auto;overflow-y:auto;min-height:0;word-break:break-word;max-height:none;outline:none}
#tasks-panel .task-content.focused{border-color:var(--constr-amber);box-shadow:0 0 8px rgba(245,158,11,.35);}
#tasks-panel .task-content:focus-visible{border-color:var(--constr-amber);box-shadow:0 0 8px rgba(245,158,11,.5);}
/* A9 + BGP4: config panel — near-black background with readable JSON.
   BGP4 fixes scrolling: the outer #config-panel clips (overflow:hidden) so the
   .panel-section must be flex:1 with a BOUNDED height (flex-basis:0 + min-height:0)
   and overflow:hidden, and the .panel-section-body flex-fills with flex-basis:0,
   min-height:0, max-height:none and its own overflow-y:auto so the full config
   content is reachable by scrolling (never truncated by the base max-height:400px). */
#config-panel{background:#0b0b0d;overflow:hidden;min-height:0}
#config-panel .panel-section{background:#0f1012;border-color:#2a2d2b;flex:1 1 0;min-height:0;overflow:hidden}
#config-panel .panel-section-body{background:#0b0b0d;color:#c9d0cb;max-height:none;flex:1 1 0;min-height:0;overflow-y:auto;overflow-x:hidden;overflow-wrap:break-word;padding:10px 12px 24px;}
#config-content{background:#0b0b0d;color:#c9d0cb;font-family:var(--font-mono);font-size:12px;
  white-space:pre-wrap;word-break:break-word;overflow-wrap:break-word;overflow-x:hidden;}
#config-content strong{color:var(--constr-amber);font-family:var(--font-industrial);
  text-transform:uppercase;font-size:10px;letter-spacing:1px;}
#config-content pre,#config-content code{background:#0d0e10;color:#e8e4d8;border:1px solid #2a2d2b;padding:12px;
  border-radius:4px;overflow-x:hidden;line-height:1.6;font-family:var(--font-mono);font-size:12px;
  white-space:pre-wrap;overflow-wrap:break-word;word-break:break-word;}
#config-content .json-key{color:#7fd4f4}
#config-content .json-string{color:#a8d5a2}
#config-content .json-number{color:#f0b26b}
#config-content .json-boolean{color:#d79ae6}
#config-content .json-null{color:#9aa0a6}

/* ── Overlay ── */
#overlay{display:none;position:fixed;inset:0;background:rgba(5,5,5,0.85);z-index:100;align-items:center;justify-content:center}
#overlay.active{display:flex}
#overlay-content{
  background:var(--metal-dark);border:2px solid var(--constr-orange);
  width:90vw;max-width:800px;max-height:80vh;overflow-y:auto;padding:0;
  display:flex;flex-direction:column;
}
/* A5: agent live-tail overlay */
.overlay-agent-header{
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
  padding:8px 14px;background:var(--metal-mid);border-bottom:1px solid var(--bevel-edge);
  font-family:var(--font-industrial);font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--pane-accent, var(--constr-amber));
}
.overlay-close{
  background:var(--metal-dark);color:var(--text-main);border:1px solid var(--bevel-edge);
  padding:3px 10px;cursor:pointer;font-family:var(--font-industrial);font-size:12px;
}
.overlay-close:hover{color:var(--alarm-red);border-color:var(--alarm-red)}
.overlay-agent-body{
  flex:1;overflow-y:auto;padding:10px 14px;min-height:0;
  font-family:var(--font-mono);font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;
  background:#000000;
}
.overlay-content.qla{--pane-accent:var(--cyan-accent)}
.overlay-content.ins{--pane-accent:var(--pink-accent)}
.overlay-content.con{--pane-accent:var(--constr-amber)}
.overlay-content.spq{--pane-accent:var(--ok-green2)}
.overlay-agent-body.qlarifier{color:var(--cyan-accent)}
.overlay-agent-body.instruqtor{color:var(--pink-accent)}
.overlay-agent-body.construqtor{color:var(--constr-amber)}
.overlay-agent-body.inspeqtor{color:var(--ok-green2)}

/* ── Global scrollbars ── */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--hazard-black)}
::-webkit-scrollbar-thumb{background:var(--bevel-edge);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--constr-orange)}

/* ── Icons for columns ── */
.icon-planned{color:var(--pink-accent)!important}
.icon-build{color:var(--constr-amber)!important}
.icon-review{color:var(--cyan-accent)!important}
.icon-repair{color:var(--constr-amber)!important}
.icon-done{color:var(--ok-green2)!important}
.col-icon{font-weight:800}

/* ── Responsive ── */
@media(max-width:1200px){
  .big-mascot-area{display:none}

  .ticket-yard{gap:4px;padding:4px}
  .nav-tab{padding:0 10px;font-size:10px}
}
</style>
</head>
<body data-version="QQVERSION">
<div class="qq-industrial-shell">


<!-- ── NAV DECK ── -->
<div class="nav-deck">
  <div class="nav-brand-block">
    <img src="/QonQrete-briQsQope.png" alt="QonQrete briQsQope" onerror="var s=this;var d=document.createElement('span');d.className='nav-brand-label';d.textContent='QONQRETE briQsQope';s.parentNode.replaceChild(d,s);">
  </div>
  <div class="nav-tabs">
    <button onclick="switchView('dashboard')" id="nav-dashboard" class="nav-tab active">BOARD</button>
    <button onclick="switchView('agents')" id="nav-agents" class="nav-tab">Agents</button>
    <button onclick="switchView('tasks')" id="nav-tasks" class="nav-tab">Tasks</button>
    <button onclick="switchView('config')" id="nav-config" class="nav-tab">Config</button>
    <button onclick="openSessionSelector()" id="nav-sessions" class="nav-tab nav-sessions-btn" title="Sessions/Runs" aria-label="Sessions/Runs"><svg class="nav-sessions-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg></button>
  </div>
  <div class="nav-spacer">
    <div class="qonqrete-transmission" id="qonqrete-ticker" aria-live="off" role="marquee" aria-label="QonQrete transmission banner">
      <div class="transmission-viewport">
        <div class="transmission-track" id="transmission-track">
        </div>
      </div>
    </div>
  </div>
  <div class="nav-conn-block">
    <span class="nav-action" id="nav-action"><span class="nav-action-label">Act:</span><span class="nav-action-value">&mdash;</span></span>
  </div>
  <div class="nav-time-block" id="nav-time-block">
    <span class="nostyle" style="color:var(--bevel-hi);font-weight:700;">Total:</span>
    <span class="nav-time-value" id="nav-total-time">00:00</span>
    <span class="nav-time-subsep" aria-hidden="true"></span>
    <span class="nostyle" style="color:var(--bevel-hi);font-weight:700;">Agent:</span>
    <span class="nav-time-value" id="nav-agent-time">00:00</span>
  </div>
  <div class="nav-progress-block" id="nav-progress-block">
    <span class="nav-progress-icon">PROGRESS:</span>
    <span class="nav-progress-value" id="nav-progress">0%</span>
    <span class="nav-progress-divider">|</span>
  </div>
</div>

<!-- ── RUN STATUS DECK ── -->
<div id="current-run-panel" class="run-status-deck" style="display:none">
  <div class="run-status-row2" id="statsbar">
    <div class="telemetry-item telemetry-run-item">
      <span class="telemetry-lbl">Run:</span>
      <span class="telemetry-val telemetry-run-id" id="live-run-id">—</span>
    </div>
    <div class="telemetry-item">
      <span class="telemetry-lbl">YOLO:</span>
      <span class="telemetry-val" id="live-yolo">—</span>
    </div>
    <div class="telemetry-item"><span class="telemetry-lbl">Status:</span><span class="telemetry-val" id="live-status" style="color:var(--text-muted)">idle</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Agent:</span><span class="telemetry-val" id="live-agent-name">—</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Model:</span><span class="telemetry-val" id="live-model">—</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Action:</span><span class="telemetry-val" id="live-action">Waiting for run</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Cycle=</span><span class="telemetry-val" id="live-cycle">—/—</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Total:</span><span class="telemetry-val" id="live-total-time">00:00</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Agent:</span><span class="telemetry-val" id="live-agent-time">00:00</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Progress:</span><span class="telemetry-val good" id="live-progress">0%</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">Groups:</span><span class="telemetry-val" id="live-groups-done">0</span><span class="telemetry-lbl">/</span><span class="telemetry-val total-count" id="live-total-groups">—</span></div>
    <div class="telemetry-item"><span class="telemetry-lbl">BriQs:</span><span class="telemetry-val" id="live-briqs-done">0</span><span class="telemetry-lbl">/</span><span class="telemetry-val total-count" id="live-total-briqs">—</span></div>
  </div>
</div>

<!-- ── MAIN WORK YARD ── -->
<div class="workyard-main" id="main-area">
  <div class="ticket-yard" id="col-view">
    <div class="ticket-bay" id="col-planned">
      <div class="bay-header">
        <span class="bay-header-icon col-icon icon-planned">📋</span>
        <span class="bay-header-label">Planned</span>
        <span class="bay-header-count col-count">0</span>
      </div>
      <div class="bay-scroll col-scroll"></div>
      <div class="bay-corner-bl"></div><div class="bay-corner-br"></div>
    </div>
    <div class="ticket-bay" id="col-building">
      <div class="bay-header">
        <span class="bay-header-icon col-icon icon-build">🔧</span>
        <span class="bay-header-label">Build/Repair</span>
        <span class="bay-header-count col-count">0</span>
      </div>
      <div class="bay-scroll col-scroll"></div>
      <div class="bay-corner-bl"></div><div class="bay-corner-br"></div>
    </div>
    <div class="ticket-bay" id="col-review">
      <div class="bay-header">
        <span class="bay-header-icon col-icon icon-review">🎯</span>
        <span class="bay-header-label">Review</span>
        <span class="bay-header-count col-count">0</span>
      </div>
      <div class="bay-scroll col-scroll"></div>
      <div class="bay-corner-bl"></div><div class="bay-corner-br"></div>
    </div>
    <div class="ticket-bay" id="col-done">
      <div class="bay-header">
        <span class="bay-header-icon col-icon icon-done">✅</span>
        <span class="bay-header-label">Done</span>
        <span class="bay-header-count col-count">0</span>
      </div>
      <div class="bay-scroll col-scroll"></div>
      <div class="bay-corner-bl"></div><div class="bay-corner-br"></div>
    </div>
  </div>
  <div id="panel-view">
    <div id="agents-panel" style="display:none;flex:1;flex-direction:column;gap:6px;min-height:0;height:100%">
      <div class="agent-grid" style="height:100%">
        <div class="agent-pane qla" id="pane-qlarifier" style="cursor:pointer" onclick="openAgentOverlay('qlarifier')" title="Open live tail — Qlarifier"><div class="agent-pane-header">🔮 Qlarifier</div><div class="agent-pane-body"></div></div>
        <div class="agent-pane ins" id="pane-instruqtor" style="cursor:pointer" onclick="openAgentOverlay('instruqtor')" title="Open live tail — instruQtor"><div class="agent-pane-header">📋 instruQtor</div><div class="agent-pane-body"></div></div>
        <div class="agent-pane con" id="pane-construqtor" style="cursor:pointer" onclick="openAgentOverlay('construqtor')" title="Open live tail — construQtor"><div class="agent-pane-header">🏗️ construQtor</div><div class="agent-pane-body"></div></div>
        <div class="agent-pane spq" id="pane-inspeqtor" style="cursor:pointer" onclick="openAgentOverlay('inspeqtor')" title="Open live tail — inspeQtor"><div class="agent-pane-header">🔍 inspeQtor</div><div class="agent-pane-body"></div></div>
      </div>
    </div>
    <div id="tasks-panel" style="display:none;flex:1;flex-direction:column;gap:6px;min-height:0;height:100%">
      <div class="task-section" id="task-original-section" onclick="focusTaskPane('original')"><div class="task-label">Original Task</div><div class="task-content focused" id="tasks-original" tabindex="0">Loading...</div></div>
      <div class="task-section" id="task-enhanced-section" onclick="focusTaskPane('enhanced')"><div class="task-label">Enhanced Task</div><div class="task-content" id="tasks-enhanced" tabindex="0">Loading...</div></div>
    </div>
    <div id="config-panel" style="display:none;flex:1;flex-direction:column;gap:6px;min-height:0;overflow:hidden">
      <div class="panel-section"><div class="panel-section-header">Configuration</div><div class="panel-section-body"><div class="config-json" id="config-content">Loading...</div></div></div>
    </div>
  </div>
</div>

<!-- ── DECK RESIZER ── -->
<div id="deck-resizer" class="deck-resizer" role="separator" aria-orientation="horizontal" aria-label="Resize ticket board and event log" aria-valuemin="130" aria-valuemax="600" aria-valuenow="200" tabindex="0"></div>

<!-- ── BOTTOM INSTRUMENT DECK ── -->
<div class="bottom-instrument-deck">
<!-- Event log -->
  <div class="event-log-panel" id="terminal">
    <div class="event-log-header" id="term-header">
      <span class="log-label">EVENT LOG ▼</span>
      <span class="log-clear" onclick="document.getElementById('term-body').innerHTML=''">Clear</span>
    </div>
    <div class="event-log-body" id="term-body">
      <div class="placeholder-msg" style="text-align:center;color:var(--text-muted);padding:24px">Waiting for events...</div>
    </div>
  </div>

  <!-- Big cybersquid -->
  <div class="big-mascot-area">
    <div class="mascot-loader" id="mascot-loader" aria-hidden="true"></div>
    <img src="/qonqrete-bottom-right.jpg" alt="QonQrete" style="height:100%;width:auto;max-width:100%;object-fit:contain;">
  </div>

</div>

</div><!-- /qq-industrial-shell -->

<div id="overlay"><div id="overlay-content"></div></div>

<!-- ── INLINE CYBERSQUID SVG ── -->
<svg style="display:none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="sq-body-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3b3f3d"/><stop offset="100%" stop-color="#181b1b"/>
    </linearGradient>
    <linearGradient id="sq-armor-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#e08a1f"/><stop offset="100%" stop-color="#d87a18"/>
    </linearGradient>
  </defs>
  <g id="cybersquid-svg">
    <!-- Tentacles -->
    <path d="M18 58 Q14 72 8 80" fill="none" stroke="#2a2d2b" stroke-width="3" stroke-linecap="round"/>
    <path d="M25 60 Q24 74 20 82" fill="none" stroke="#3b3f3d" stroke-width="3" stroke-linecap="round"/>
    <path d="M32 58 Q35 72 40 80" fill="none" stroke="#2a2d2b" stroke-width="3" stroke-linecap="round"/>
    <path d="M38 56 Q44 68 50 76" fill="none" stroke="#3b3f3d" stroke-width="3" stroke-linecap="round"/>
    <!-- Body -->
    <ellipse cx="28" cy="42" rx="16" ry="18" fill="url(#sq-body-grad)" stroke="#555955" stroke-width="1.5"/>
    <!-- Armor plates -->
    <rect x="16" y="32" width="8" height="6" rx="1" fill="#d87a18" stroke="#555955" stroke-width="0.5"/>
    <rect x="32" y="32" width="8" height="6" rx="1" fill="#d87a18" stroke="#555955" stroke-width="0.5"/>
    <rect x="20" y="26" width="16" height="5" rx="1" fill="url(#sq-armor-grad)" stroke="#555955" stroke-width="0.5"/>
    <!-- Bolts -->
    <circle cx="18" cy="34" r="1.2" fill="#555955"/>
    <circle cx="38" cy="34" r="1.2" fill="#555955"/>
    <circle cx="18" cy="48" r="1.2" fill="#555955"/>
    <circle cx="38" cy="48" r="1.2" fill="#555955"/>
    <!-- Eye panel -->
    <rect x="22" y="18" width="12" height="10" rx="1" fill="#050505" stroke="#555955" stroke-width="1"/>
    <!-- Red alarm eye -->
    <rect x="25" y="21" width="6" height="4" rx="0.5" fill="#ff3b30" class="alarm-eye"/>
    <!-- Small indicator dots -->
    <circle cx="20" cy="20" r="1" fill="#34c759"/>
    <circle cx="36" cy="20" r="1" fill="#34c759"/>
  </g>
</svg>

<script>
// ====== INLINE SVG CYBERSQUID RENDERER ======
(function() {
  var svgSrc = document.getElementById('cybersquid-svg');
  var svgNS = 'http://www.w3.org/2000/svg';
  function renderSquid(size) {
    var svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 56 84');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.innerHTML = svgSrc.innerHTML;
    return svg;
  }
  // Replace placeholders
  var smallEls = document.querySelectorAll('.cybersquid-sm');
  for (var i = 0; i < smallEls.length; i++) {
    var parent = smallEls[i];
    if (parent.textContent.trim() === 'MASCOT_SMALL') {
      parent.innerHTML = '';
      parent.appendChild(renderSquid('100%'));
    }
  }
  var bigEls = document.querySelectorAll('.cybersquid-big');
  for (var j = 0; j < bigEls.length; j++) {
    var parent2 = bigEls[j];
    if (parent2.textContent.trim() === 'MASCOT_BIG') {
      parent2.innerHTML = '';
      parent2.appendChild(renderSquid('100%'));
    }
  }
})();

// ====== HELPERS ======
function normalizeModelCode(model) {
  if (!model) return '—';
  var mc = String(model);
  var lower = mc.toLowerCase();
  if (mc === 'fla' || mc === 'fla-T' || mc === 'pro' || mc === 'pro-T') return mc;
  if (lower.indexOf('flash') >= 0) return lower.indexOf('thinking') >= 0 ? 'fla-T' : 'fla';
  if (lower.indexOf('pro') >= 0) return lower.indexOf('thinking') >= 0 ? 'pro-T' : 'pro';
  return mc === '?' ? '—' : mc;
}
function modelDisplayBracketed(model) {
  var code = normalizeModelCode(model);
  if (code === '\u2014' || code === '?') return code;
  if (code.charAt(0) === '[' && code.charAt(code.length - 1) === ']') return code;
  return '[' + code + ']';
}
function agentDisplay(role) {
  return {
    qlarifier: 'Qlarifier',
    instruqtor: 'instruQtor',
    construqtor: 'construQtor',
    inspeqtor: 'inspeQtor'
  }[role] || role || '—';
}
function agentColor(role) {
  return {
    qlarifier: 'var(--cyan-accent)',
    instruqtor: 'var(--pink-accent)',
    construqtor: 'var(--constr-amber)',
    inspeqtor: 'var(--ok-green2)'
  }[role] || 'var(--text-muted)';
}
function setProgressDisplay(value) {
  var el = document.getElementById('live-progress');
  var pct = 0;
  if (typeof value === 'number') {
    // Truncate numeric inputs (e.g. effective_progress_pct like 37.5) so the
    // web PROGRESS shows the same integer the TUI truncates to (tick-for-tick parity).
    pct = Math.floor(value);
  } else {
    var m = String(value || '0').match(/-?\d+/);
    pct = m ? parseInt(m[0], 10) : 0;
  }
  pct = Math.max(0, Math.min(100, pct));
  // Keep ALL existing #live-progress behavior unchanged
  if (el) {
    el.textContent = pct + '%';
    el.className = 'telemetry-val';
    if (pct <= 0) el.style.color = 'var(--alarm-red)';
    else if (pct < 95) el.style.color = 'var(--constr-amber)';
    else el.style.color = 'var(--ok-green2)';
  }
  // Update the top-right #nav-progress ("PROGRESS: XX%") with color coding + pulse
  var navEl = document.getElementById('nav-progress');
  if (navEl) {
    var oldTxt = navEl.textContent;
    var newTxt = pct + '%';
    if (oldTxt !== newTxt) { navEl.textContent = newTxt; }
    var pBlock = document.getElementById('nav-progress-block');
    if (pBlock) {
      pBlock.classList.remove('pulse');
      if (oldTxt && oldTxt !== newTxt) { void pBlock.offsetWidth; pBlock.classList.add('pulse'); }
    }
    navEl.style.color = 'var(--text-muted)';
    navEl.style.boxShadow = 'none';
    navEl.style.textShadow = 'none';
    if (pct >= 100) { navEl.style.color = 'var(--ok-green2)'; navEl.style.textShadow = '0 0 8px var(--ok-green2)'; navEl.style.boxShadow = '0 0 10px var(--ok-green2)'; }
    else if (pct >= 75) { navEl.style.color = 'var(--ok-green2)'; }
    else if (pct >= 40) { navEl.style.color = 'var(--constr-amber)'; }
    else if (pct > 0) { navEl.style.color = 'var(--constr-orange)'; }
    else { navEl.style.color = 'var(--text-muted)'; }
  }
}

var allGroups = [];
var allAgentOutputs = [];
var currentView = 'dashboard';
var sseReady = false;
var termBodyEl = null;
var isIdleMode = true;

// ====== LIVE AGENT OUTPUT STREAMING ======
var liveAgentLines = {
  qlarifier: [],
  instruqtor: [],
  construqtor: [],
  inspeqtor: []
};
var liveAgentInitialized = false;
var currentActiveAgent = '';
// A10: track the most recently observed active agent from BOTH the poll path and
// SSE so the Agent timer resets exactly once per agent handoff (not per poll).
var lastHandoffAgent = '';
var lastAgentOutputEvent = null;              // tracks last-output-event ({role, ts}) for seeding/backfill detection
var liveAgentModel = {};                      // per-role model backfill cache
var LIVE_AGENT_REFRESH_COOLDOWN_MS = 1000;    // guard: don't let poll overwrite fresh live stream
var lastLiveAgentUpdate = {};                 // role -> Date.now() of last live pane render

// ====== TIMERS ======
(function() {
  var runStartTs = 0;
  var agentStartTs = 0;
  var totalPaused = false;
  var runDone = false;
  var frozenTotalSecs = -1;
  var frozenAgentSecs = -1;
  var runMaxTimeSeconds = 0;
  function fmtElapsed(s) {
    if (s < 0) s = 0;
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
    if (h > 0) return h + ':' + String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
    return String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
  }
  function fmtTimeLimit(s) {
    if (!s || s <= 0) return '∞';
    return fmtElapsed(s);
  }
  function renderRunTime(elapsedSeconds) {
    return fmtElapsed(elapsedSeconds) + ' / ' + fmtTimeLimit(runMaxTimeSeconds);
  }
  var totalEls = function() { return [document.getElementById('live-total-time'), document.getElementById('nav-total-time')]; };
  var agentEls = function() { return [document.getElementById('live-agent-time'), document.getElementById('nav-agent-time')]; };
  function writeClocks() {
    var i;
    if (runDone) {
      var tot = fmtElapsed(frozenTotalSecs >= 0 ? frozenTotalSecs : 0);
      var agt = fmtElapsed(frozenAgentSecs >= 0 ? frozenAgentSecs : 0);
      var tes = totalEls(); for (i = 0; i < tes.length; i++) { if (tes[i]) { tes[i].textContent = tot; tes[i].style.color = 'var(--ok-green2)'; } }
      var aes = agentEls(); for (i = 0; i < aes.length; i++) { if (aes[i]) { aes[i].textContent = agt; aes[i].style.color = 'var(--ok-green2)'; } }
      return;
    }
    var tot = runStartTs ? fmtElapsed((Date.now() / 1000) - runStartTs) : fmtElapsed(0);
    var agt = agentStartTs ? fmtElapsed((Date.now() / 1000) - agentStartTs) : fmtElapsed(0);
    var te = totalEls(); for (i = 0; i < te.length; i++) { if (te[i]) { te[i].textContent = tot; te[i].style.color = ''; } }
    var ae = agentEls(); for (i = 0; i < ae.length; i++) { if (ae[i]) { ae[i].textContent = agt; ae[i].style.color = ''; } }
  }
  window.setRunMaxTimeSeconds = function(s) { runMaxTimeSeconds = s || 0; };
  window.resetRunTimeForNewRun = function(startedAt, maxTimeSecs) {
    runStartTs = startedAt || (Date.now() / 1000);
    agentStartTs = Date.now() / 1000;
    runMaxTimeSeconds = maxTimeSecs || 0;
    totalPaused = false;
    runDone = false;
    frozenTotalSecs = -1;
    frozenAgentSecs = -1;
    window._totalTimeFrozen = false;
    window._timerInitialized = true;
  };
  window.resetAgentTime = function() { agentStartTs = Date.now() / 1000; if (!runDone) { var aes = agentEls(); for (var i = 0; i < aes.length; i++) { if (aes[i]) aes[i].style.color = ''; } } };
  // A15: freeze Total + Agent once at FULLY_DONE / terminal state
  window.freezeTotalTime = function(totalSecs) {
    if (window._totalTimeFrozen) return;
    window._totalTimeFrozen = true;
    runDone = true;
    frozenTotalSecs = totalSecs != null ? totalSecs : (runStartTs ? ((Date.now() / 1000) - runStartTs) : 0);
    frozenAgentSecs = agentStartTs ? ((Date.now() / 1000) - agentStartTs) : 0;
  };
  // Alias for callers that pass a computed wall-clock total
  window.markRunDone = window.freezeTotalTime;
  setInterval(function() { if (totalPaused && !runDone) return; writeClocks(); }, 250);
})();

// ====== VIEW SWITCHING ======
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.nav-tab').forEach(function(b) { b.classList.remove('active'); });
  var btn = document.getElementById('nav-' + view); if (btn) btn.classList.add('active');
  var colView = document.getElementById('col-view');
  var panelView = document.getElementById('panel-view');
  var agentsPanel = document.getElementById('agents-panel');
  var tasksPanel = document.getElementById('tasks-panel');
  var configPanel = document.getElementById('config-panel');
  colView.style.display = 'none';
  panelView.classList.remove('active');
  if (agentsPanel) agentsPanel.style.display = 'none';
  if (tasksPanel) tasksPanel.style.display = 'none';
  if (configPanel) configPanel.style.display = 'none';
  if (view === 'dashboard') {
    colView.style.display = '';
    updateBoardFromModel();
  } else if (view === 'agents') {
    panelView.classList.add('active');
    if (agentsPanel) agentsPanel.style.display = '';
    // Seed liveAgentLines from the read model the first time we enter the view
    if (!liveAgentInitialized && allAgentOutputs) {
      var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
      agents.forEach(function(agent) {
        var agentData = null;
        if (Array.isArray(allAgentOutputs)) {
          var filtered = allAgentOutputs.filter(function(o) { return o.role === agent; });
          if (filtered.length > 0) agentData = filtered[filtered.length - 1];
        } else if (allAgentOutputs[agent]) {
          agentData = allAgentOutputs[agent];
        }
        if (agentData && agentData.lines && agentData.lines.length > 0 && (!liveAgentLines[agent] || liveAgentLines[agent].length === 0)) {
          liveAgentLines[agent] = agentData.lines.slice();
        }
      });
      liveAgentInitialized = true;
    }
    renderAgentsPage();
    if (currentActiveAgent) highlightActiveAgent(currentActiveAgent);
  } else if (view === 'tasks') {
    panelView.classList.add('active');
    if (tasksPanel) tasksPanel.style.display = '';
    updateBoardFromModel();
  } else if (view === 'config') {
    panelView.classList.add('active');
    if (configPanel) configPanel.style.display = '';
    loadConfig();
  }
}

function highlightJson(jsonText) {
  var txt = String(jsonText);
  txt = txt.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // Keys (strings followed by colon)
  txt = txt.replace(/("(?:\\.|[^"\\])*")(\s*:)/g, '<span class="json-key">$1</span>$2');
  // Strings (only ones not already wrapped — approximate by matching values after colon or array items)
  txt = txt.replace(/(:\s*)("(?:\\.|[^"\\])*")/g, '$1<span class="json-string">$2</span>');
  // Numbers / booleans / null: single-pass replace that skips any text already inside a
  // wrapped json-key or json-string span, so digits inside string values are NOT recolored.
  txt = txt.replace(
    /<(?:span class="json-key"|span class="json-string")>[\s\S]*?<\/span>|(\btrue\b|\bfalse\b|\bnull\b|\b\d+\.?\d*\b)/g,
    function(m, token) {
      if (!token) return m;              // match was inside an existing key/string span: keep as-is
      if (/^(true|false)$/.test(token)) return '<span class="json-boolean">' + token + '</span>';
      if (token === 'null') return '<span class="json-null">null</span>';
      return '<span class="json-number">' + token + '</span>';
    }
  );
  return txt;
}

function loadConfig() {
  var el = document.getElementById('config-content');
  if (el) el.innerHTML = 'Loading...';
  fetch('/api/qonqrete/config')
    .then(function(r) {
      if (!r.ok) {
        return r.json().catch(function() { return {}; }).then(function(body) {
          var msg = (body && body.error) ? body.error : ('HTTP ' + r.status);
          throw new Error(msg);
        });
      }
      return r.json();
    })
    .then(function(cfg) {
      var el2 = document.getElementById('config-content');
      if (!el2) return;
      // If the endpoint surfaced an error object, show it clearly instead of a blank panel.
      if (cfg && cfg.error && typeof cfg.error === 'string' && !cfg.config) {
        el2.innerHTML = '<div style="text-align:center;padding:24px;color:var(--alarm-red);">Failed to load config: ' + cfg.error + '</div>';
        return;
      }
      var redacted = cfg.redacted_keys || [];
      var sourcesHtml = '<div style="margin-bottom:10px"><strong>Sources:</strong><pre>';
      sourcesHtml += highlightJson(JSON.stringify(cfg.sources || [], null, 2)) + '</pre></div>';
      var configHtml = '<div><strong>Config:</strong><pre>';
      configHtml += highlightJson(JSON.stringify(cfg.config || {}, null, 2)) + '</pre></div>';
      var html = sourcesHtml;
      if (redacted.length) {
        html += '<div style="margin-bottom:10px"><strong>Redacted keys:</strong> <span style="color:var(--constr-amber)">' + redacted.join(', ') + '</span></div>';
      }
      html += configHtml;
      el2.innerHTML = html;
    })
    .catch(function(err) {
      var el3 = document.getElementById('config-content');
      if (el3) el3.innerHTML = '<div style="text-align:center;padding:24px;color:var(--alarm-red);">Failed to load config: ' + (err && err.message ? err.message : String(err)) + '</div>';
    });
}

function setActionStatus(status) {
  var el = document.getElementById('nav-action');
  if (!el) return;
  var label = 'Act:';
  var value;
  var err = false;
  var good = false;
  // Normalize any terminal done/fully_done spelling to the literal FULLY_DONE
  if (status) {
    var up = String(status).toUpperCase();
    if (up === 'FULLY_DONE' || up === 'FULLY DONE' || up === 'DONE' || up === 'COMPLETED') {
      status = 'FULLY_DONE';
    }
  }
  if (!status) {
    value = '\u2014';
  } else if (status === 'error' || status === 'reconnecting') {
    value = status === 'reconnecting' ? 'RECONNECTING' : status.toUpperCase();
    err = true;
  } else if (status === 'FULLY_DONE') {
    value = 'FULLY_DONE';
    good = true;
  } else if (status === 'connected') {
    value = 'CONNECTED';
  } else {
    // Run action status (Planning / Clarifying / Building / Reviewing / ...)
    value = String(status);
    if (status === 'FAILED' || status === 'BLOCKED' || status === 'STOPPED') err = true;
  }
  el.innerHTML = '<span class="nav-action-label">' + label + '</span><span class="nav-action-value">' + value + '</span>';
  el.className = err ? 'nav-action err' : (good ? 'nav-action good' : 'nav-action');
}

// BGP5: drop/redact any agent env-debug leak line before it can harm the DOM.
function _stripEnvLeak(s) {
  return /QQV_ROLE=/.test(String(s));
}

function addTermLine(ts, type, detail) {
  var body = document.getElementById('term-body');
  if (!body) return;
  // BGP5: never render an agent env-debug leak line into the log.
  if (_stripEnvLeak((detail||'') + ' ' + (type||''))) return;
  var line = document.createElement('div');
  line.className = 'term-line';
  var typeColor = 'var(--cyan-accent)';
  if (type === 'connected' || type === 'system' || type === 'retarget') typeColor = 'var(--ok-green2)';
  if (type === 'error' || type === 'connection' || type.indexOf('fail') >= 0) typeColor = 'var(--alarm-red)';
  if (type === 'run.completed' || type.indexOf('done') >= 0) typeColor = 'var(--ok-green2)';
  line.innerHTML = '<span class="term-ts">' + ts + '</span><span class="term-type" style="color:' + typeColor + '">' + type + '</span>' + detail;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function openGroupOverlay(gid) {
  var overlay = document.getElementById('overlay');
  var content = document.getElementById('overlay-content');
  var g = allGroups.find(function(x) { return (x.safe_id || x.id) === gid; });
  if (!g) return;
  var html = '<div style="padding:16px"><h3>' + (g.title || gid) + '</h3>';
  html += '<p style="color:var(--text-muted)">Status: ' + (g.status || '?') + '</p>';
  html += '<p>' + (g.description || '') + '</p>';
  html += '<h4 style="margin-top:12px">BriQs</h4>';
  (g.briqs || []).forEach(function(b) {
    var icon = {done:'✅',needs_repair:'🔧',failed:'❌',in_progress:'🔄',building:'🔨'}[b.status] || '⏳';
    html += '<div>' + icon + ' <strong>' + (b.title || '') + '</strong> — ' + (b.status || '?') + '</div>';
    if (b.description) html += '<div style="color:var(--text-muted);margin-left:24px;font-size:12px">' + b.description + '</div>';
  });
  html += '</div>';
  content.innerHTML = html;
  overlay.classList.add('active');
}

document.getElementById('overlay').addEventListener('click', function(e) {
  if (e.target === this) closeAgentOverlay();
});

// ====== A5: clickable agent panes -> full-screen live-tail overlay ======
var focusedTaskPane = 'original';
var agentTailTimer = null;

function focusTaskPane(which) {
  focusedTaskPane = which;
  var origSec = document.getElementById('task-original-section');
  var enhSec = document.getElementById('task-enhanced-section');
  var orig = document.getElementById('tasks-original');
  var enh = document.getElementById('tasks-enhanced');
  if (which === 'original') {
    if (origSec) origSec.classList.add('focused');
    if (enhSec) enhSec.classList.remove('focused');
    if (orig) orig.classList.add('focused');
    if (enh) enh.classList.remove('focused');
    if (orig && typeof orig.focus === 'function') orig.focus();
  } else {
    if (enhSec) enhSec.classList.add('focused');
    if (origSec) origSec.classList.remove('focused');
    if (enh) enh.classList.add('focused');
    if (orig) orig.classList.remove('focused');
    if (enh && typeof enh.focus === 'function') enh.focus();
  }
}

function agentOutputLines(role) {
  var lines = [];
  if (liveAgentLines && liveAgentLines[role] && liveAgentLines[role].length > 0) {
    lines = lines.concat(liveAgentLines[role]);
  }
  var agentData = null;
  if (allAgentOutputs) {
    if (Array.isArray(allAgentOutputs)) {
      var filtered = allAgentOutputs.filter(function(o) { return o.role === role; });
      if (filtered.length > 0) agentData = filtered[filtered.length - 1];
    } else if (allAgentOutputs[role]) {
      agentData = allAgentOutputs[role];
    }
  }
  if (agentData && agentData.lines && agentData.lines.length > 0 && lines.length === 0) {
    lines = agentData.lines.slice();
  }
  // BGP5: drop any agent env-debug leak line from rendering.
  return lines.filter(function(l) { return !_stripEnvLeak((l && l.text) || ''); });
}

function agentOutputText(role) {
  var lines = agentOutputLines(role);
  return lines.map(function(l) {
    var t = l.text != null ? String(l.text) : '';
    return (l.ts !== null && l.ts !== undefined) ? ('[' + String(l.ts) + '] ' + t) : t;
  }).join('\n');
}

function renderAgentTail(role) {
  var body = document.getElementById('overlay-agent-body');
  if (!body) return;
  body.textContent = agentOutputText(role);
  body.scrollTop = body.scrollHeight;
}

function startAgentTail(role) {
  stopAgentTail();
  renderAgentTail(role);
  agentTailTimer = setInterval(function() { renderAgentTail(role); }, 500);
}

function stopAgentTail() {
  if (agentTailTimer) { clearInterval(agentTailTimer); agentTailTimer = null; }
}

function closeAgentOverlay() {
  stopAgentTail();
  var ov = document.getElementById('overlay');
  if (ov) ov.classList.remove('active');
  var content = document.getElementById('overlay-content');
  if (content) {
    content.classList.remove('qla','ins','con','spq');
    content.innerHTML = '';
  }
  // Restore the 2x2 agent grid underneath
  if (typeof renderAgentsPage === 'function') renderAgentsPage();
}

function openAgentOverlay(role) {
  var ov = document.getElementById('overlay');
  var content = document.getElementById('overlay-content');
  var label = { qlarifier:'Qlarifier', instruqtor:'instruQtor', construqtor:'construQtor', inspeqtor:'inspeQtor' }[role] || role;
  var accentClass = { qlarifier:'qla', instruqtor:'ins', construqtor:'con', inspeqtor:'spq' }[role] || '';
  if (!content) return;
  content.innerHTML =
    '<div class="overlay-agent-header">' +
      '<span>' + escapeHtml(label) + ' — LIVE TAIL</span>' +
      '<button class="overlay-close" onclick="closeAgentOverlay()">✕</button>' +
    '</div>' +
    '<pre class="overlay-agent-body ' + escapeHtml(role) + '" id="overlay-agent-body"></pre>';
  content.classList.remove('qla','ins','con','spq');
  if (accentClass) content.classList.add(accentClass);
  if (ov) ov.classList.add('active');
  startAgentTail(role);
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    var ov = document.getElementById('overlay');
    if (ov && ov.classList.contains('active')) closeAgentOverlay();
  }
});

function updateAgentPaneLive(role) {
  var pane = document.getElementById('pane-' + role);
  if (!pane) return;
  var body = pane.querySelector('.agent-pane-body');
  if (!body) return;

  var lines = liveAgentLines[role] || [];
  if (lines.length === 0) return;

  // Cooldown guard: do NOT re-render panes freshly updated via live streaming
  // (the caller may still run highlightActiveAgent separately).
  if ((Date.now() - (lastLiveAgentUpdate[role] || 0)) < LIVE_AGENT_REFRESH_COOLDOWN_MS) {
    return;
  }
  lastLiveAgentUpdate[role] = Date.now(); // stamp before rendering so a fresh poll won't clobber

  var isActive = (role === currentActiveAgent);
  var maxLines = isActive ? 80 : 50;
  // BGP5: never render an env-debug leak line into a pane.
  lines = lines.filter(function(l) { return !_stripEnvLeak((l && l.text) || ''); });
  var recentLines = lines.slice(-maxLines);

  var header = pane.querySelector('.agent-pane-header');
  if (header) {
    var modelTxt = '';
    var agentData = null;
    if (allAgentOutputs) {
      if (Array.isArray(allAgentOutputs)) {
        var filtered = allAgentOutputs.filter(function(o) { return o.role === role; });
        if (filtered.length > 0) agentData = filtered[filtered.length - 1];
      } else {
        agentData = allAgentOutputs[role];
      }
    }
    if (agentData && agentData.model) modelTxt = ' (' + agentData.model + ')';
    else if (liveAgentModel[role]) modelTxt = ' (' + liveAgentModel[role] + ')';
    var base = {qlarifier:'🔮 Qlarifier', instruqtor:'📋 instruQtor', construqtor:'🏗️ construQtor', inspeqtor:'🔍 inspeQtor'}[role] || role;
    var want = base + modelTxt;
    var dot = header.querySelector('.agent-live-dot');
    if (isActive) {
      header.innerHTML = escapeHtml(want) + ' <span class="agent-live-dot">●</span>';
    } else {
      if (dot) header.innerHTML = escapeHtml(want);
      else header.textContent = want;
    }
  }

  var html = recentLines.map(function(l) {
    var prefix = l.ts ? '<span class="agent-ts">[' + escapeHtml(String(l.ts)) + ']</span> ' : '';
    var cssClass = 'agent-line';
    var lvl = String(l.level || 'info').toLowerCase();
    if (lvl === 'error' || lvl === 'stderr') cssClass += ' agent-error';
    else if (lvl === 'tool' || (l.event && l.event.indexOf('tool') >= 0)) cssClass += ' agent-tool';
    else if (lvl === 'thought' || l.event === 'agent_thought') cssClass += ' agent-thought';
    else cssClass += ' agent-info';
    return '<div class="' + cssClass + '">' + prefix + escapeHtml(String(l.text != null ? l.text : '')) + '</div>';
  }).join('');

  body.innerHTML = html;
  body.scrollTop = body.scrollHeight;
}

function highlightActiveAgent(role) {
  var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
  agents.forEach(function(a) {
    var pane = document.getElementById('pane-' + a);
    if (!pane) return;
    var header = pane.querySelector('.agent-pane-header');
    if (!header) return;
    if (a === role) {
      pane.classList.add('agent-active');
      var dot = header.querySelector('.agent-live-dot');
      if (!dot) {
        var baseText = header.textContent.replace(/\s*●\s*$/, '').trim();
        header.innerHTML = escapeHtml(baseText) + ' <span class="agent-live-dot">●</span>';
      }
    } else {
      pane.classList.remove('agent-active');
      var dot2 = header.querySelector('.agent-live-dot');
      if (dot2) {
        header.textContent = header.textContent.replace(/\s*●\s*$/, '').trim();
      }
    }
  });
}

function renderAgentsPage() {
  var agents = ['qlarifier','instruqtor','construqtor','inspeqtor'];
  agents.forEach(function(agent) {
    var pane = document.getElementById('pane-' + agent);
    if (!pane) return;
    var body = pane.querySelector('.agent-pane-body');
    if (!body) return;

    // Cooldown guard: do not overwrite panes freshly updated via live streaming
    var lastUpdate = lastLiveAgentUpdate[agent] || 0;
    if ((Date.now() - lastUpdate) < LIVE_AGENT_REFRESH_COOLDOWN_MS &&
        liveAgentLines[agent] && liveAgentLines[agent].length > 0) {
      return; // live data is fresher; keep it
    }

    // Prefer live data for the current active agent
    if (agent === currentActiveAgent && liveAgentLines[agent] && liveAgentLines[agent].length > 0) {
      updateAgentPaneLive(agent);
      return;
    }

    // Fall back to read-model data (agent_outputs keyed by role)
    var agentData = null;
    if (liveAgentLines[agent] && liveAgentLines[agent].length > 0) {
      // Completed / accumulated live lines for inactive agents: render via live path too
      updateAgentPaneLive(agent);
      return;
    }
    if (allAgentOutputs) {
      if (Array.isArray(allAgentOutputs)) {
        // Legacy array format: filter by role
        var filtered = allAgentOutputs.filter(function(o) { return o.role === agent; });
        if (filtered.length > 0) agentData = filtered[filtered.length - 1];
      } else {
        // Dict/object format: keyed by role
        agentData = allAgentOutputs[agent];
      }
    }

    if (!agentData) {
      body.textContent = (agentData && agentData.status === 'waiting') ? 'Waiting to start...' : 'No output yet.';
      return;
    }

    // Update header with model info (preserve any .agent-live-dot span while applying the label)
    var header = pane.querySelector('.agent-pane-header');
    if (header && agentData.model) {
      var baseLabel = ({qlarifier:'🔮 Qlarifier', instruqtor:'📋 instruQtor', construqtor:'🏗️ construQtor', inspeqtor:'🔍 inspeQtor'}[agent] || agent);
      var headerHtml = escapeHtml(baseLabel) + (agentData.model ? ' (' + escapeHtml(agentData.model) + ')' : '');
      if (agent === currentActiveAgent) headerHtml += ' <span class="agent-live-dot">●</span>';
      header.innerHTML = headerHtml;
    }

    var lines = agentData.lines || [];
    if (lines.length === 0) {
      // Show status if no output lines yet
      var statusMap = {waiting:'Waiting to start...', active:'Running...', completed:'Completed.'};
      body.textContent = statusMap[agentData.status] || 'No output yet.';
      return;
    }

    // Seed liveAgentLines from the read model if the live buffer is empty
    if (!liveAgentLines[agent] || liveAgentLines[agent].length === 0) {
      liveAgentLines[agent] = agentData.lines.slice();
    }

    // Show last output lines (up to 50) with the same per-level coloring as live
    var recentLines = lines.slice(-50);
    var html = recentLines.map(function(l) {
      var prefix = l.ts ? '<span class="agent-ts">[' + escapeHtml(String(l.ts)) + ']</span> ' : '';
      var cssClass = 'agent-line';
      var lvl = String(l.level || 'info').toLowerCase();
      if (lvl === 'error' || lvl === 'stderr') cssClass += ' agent-error';
      else if (lvl === 'tool' || (l.event && l.event.indexOf('tool') >= 0)) cssClass += ' agent-tool';
      else if (lvl === 'thought' || l.event === 'agent_thought') cssClass += ' agent-thought';
      else cssClass += ' agent-info';
      return '<div class="' + cssClass + '">' + prefix + escapeHtml(String(l.text != null ? l.text : '')) + '</div>';
    }).join('');
    body.innerHTML = html;
    body.scrollTop = body.scrollHeight;
  });
}

function updateBoardFromModel() {
  fetch('/api/qonqrete/read-model?_refresh=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(model) {
      if (model && model.build_groups) {
        allGroups = model.build_groups;
        refreshTicketBoard(model.build_groups);
      }
      if (model && model.metrics) updateMetrics(model.metrics, model.run);
      if (model && model.run) updateRunState(model.run);
      if (model && model.agent_outputs) {
        allAgentOutputs = model.agent_outputs;
        if (currentView === 'agents') renderAgentsPage();
      }
      if (model && model.task) {
        var origEl = document.getElementById('tasks-original');
        var enhEl = document.getElementById('tasks-enhanced');
        if (origEl) origEl.textContent = model.task.original_user_task || model.task.raw_text || 'No original task';
        if (enhEl) enhEl.textContent = model.task.enhanced_clarified_task || model.task.clarified_text || 'No enhanced task';
      }
    }).catch(function(err) {});
}

function updateMetrics(m, run) {
  var el;
  el = document.getElementById('live-total-groups'); if (el && m.total_groups !== undefined) el.textContent = m.total_groups;
  el = document.getElementById('live-groups-done'); if (el && m.groups_done !== undefined) el.textContent = m.groups_done;
  el = document.getElementById('live-total-briqs'); if (el && m.total_briqs !== undefined) el.textContent = m.total_briqs;
  el = document.getElementById('live-briqs-done'); if (el && m.briqs_done !== undefined) el.textContent = m.briqs_done;
  if (run) {
    var maxCycles = run.max_cycles_display || ((run.max_cycles && run.max_cycles > 0) ? String(run.max_cycles) : '\u221E');
    var cycleStr = (run.cycle || 1) + '/' + maxCycles;
    el = document.getElementById('live-cycle'); if (el) el.textContent = cycleStr;
    if (run.max_time_seconds && run.max_time_seconds > 0 && typeof window.setRunMaxTimeSeconds === 'function') {
      window.setRunMaxTimeSeconds(run.max_time_seconds);
    }
    setProgressDisplay(m.effective_progress_pct !== undefined && m.effective_progress_pct !== null ? m.effective_progress_pct : (run && run.status === 'done' ? 100 : (m.groups_done || 0) / (m.total_groups || 1) * 100));
  }
}

function updateRunState(run) {
  var statusEl = document.getElementById('live-status');
  if (statusEl) {
    statusEl.textContent = run.status || 'running';
    var sc = {clarifying:'#22d3ee',planning:'#e879f9',building:'#facc15',harnessing:'#fb923c',reviewing:'#c084fc',repairing:'#f87171',done:'var(--ok-green2)',aborted:'var(--alarm-red)',failed:'var(--alarm-red)',running:'var(--constr-amber)',starting:'var(--constr-amber)',started:'var(--constr-amber)'};
    statusEl.style.color = sc[run.status] || 'var(--text-muted)';
  }
  var idEl = document.getElementById('live-run-id'); if (idEl && run.run_id) { idEl.textContent = run.run_id; idEl.title = run.run_id; }
  var actionEl = document.getElementById('live-action');
  // A fully-done terminal run must show FULLY_DONE green even if the persisted
  // action_status is stale (e.g. 'Evaluating the result') — drive off the verdict.
  var fullyDone = (String(run.action_status).toUpperCase() === 'FULLY_DONE' ||
                   String(run.status).toUpperCase() === 'FULLY_DONE' ||
                   String(run.status).toLowerCase() === 'done' ||
                   String(run.status).toLowerCase() === 'completed' ||
                   String(run.final_verdict).toUpperCase() === 'FULLY_DONE');
  if (fullyDone) run.action_status = 'FULLY_DONE';
  if (run.action_status) {
    if (actionEl) {
      actionEl.textContent = run.action_status;
      actionEl.className = 'telemetry-val';
      if (run.action_status === 'FULLY_DONE') actionEl.className = 'telemetry-val good';
      else if (run.action_status === 'FAILED' || run.action_status === 'BLOCKED') actionEl.className = 'telemetry-val bad';
    }
    // Mirror the live action into the top-right Act: bar (A2)
    if (typeof setActionStatus === 'function') setActionStatus(run.action_status);
  }
  var agentEl = document.getElementById('live-agent-name');
  if (run.active_agent) {
    // A10: reset the Agent timer exactly once per agent handoff, keyed off the active
    // agent *change* (mirrors TUI reset_active_time()). Guard against duplicate resets
    // when SSE (active_agent_changed) and the poll path both observe the same handoff.
    if (run.active_agent !== lastHandoffAgent) {
      lastHandoffAgent = run.active_agent;
      if (typeof window.resetAgentTime === 'function') window.resetAgentTime();
    }
    currentActiveAgent = run.active_agent;
    if (agentEl) {
      agentEl.textContent = agentDisplay(run.active_agent);
      agentEl.style.color = agentColor(run.active_agent);
    }
    // Highlight the active agent pane when the agents view is visible
    if (currentView === 'agents' && typeof highlightActiveAgent === 'function') {
      highlightActiveAgent(currentActiveAgent);
    }
  }
  var modelEl = document.getElementById('live-model');
  if (modelEl && run.model_code) modelEl.textContent = modelDisplayBracketed(run.model_code);
  else if (modelEl && run.model) modelEl.textContent = modelDisplayBracketed(run.model);
  else if (modelEl && run.active_model) modelEl.textContent = modelDisplayBracketed(run.active_model);
  if (run.started_at && run.started_at > 0 && typeof window.resetRunTimeForNewRun === 'function' && !window._timerInitialized) {
    window.resetRunTimeForNewRun(run.started_at, run.max_time_seconds);
  }
  var terminalStates = ['done','aborted','failed','fully_done'];
  var isFullyDone = (run.action_status === 'FULLY_DONE' || String(run.status).toUpperCase() === 'FULLY_DONE');
  var isTerminal = (isFullyDone || terminalStates.indexOf(String(run.status).toLowerCase()) >= 0);
  if (isTerminal) {
    if (!window._totalTimeFrozen) {
      if (typeof window.freezeTotalTime === 'function') {
        // A15: freeze at the true final Total. Prefer a server started_at anchor, else
        // fall back to the cached monotonic runStartTs so the frozen value is stable.
        if (run.started_at && run.started_at > 0) {
          window.freezeTotalTime((Date.now() / 1000) - run.started_at);
        } else {
          window.freezeTotalTime(null);
        }
      }
    }
    // Stop the braille-snake loader (A14) and freeze Agent too
    if (typeof window.stopMascotLoader === 'function') window.stopMascotLoader();
  } else if (run.started_at) {
    // A14: animate the loader while the run is active
    if (typeof window.startMascotLoader === 'function') window.startMascotLoader();
  }
  var cycleEl2 = document.getElementById('live-cycle');
  if (cycleEl2 && run.cycle !== undefined) {
    var maxCycles2 = run.max_cycles_display || ((run.max_cycles && run.max_cycles > 0) ? String(run.max_cycles) : '\u221E');
    cycleEl2.textContent = (run.cycle || 1) + '/' + maxCycles2;
  }
}

function refreshTicketBoard(groups) {
  var cols = {
    'planned': {title:'Planned', statuses:['planned','pending','queued']},
    'building': {title:'Build/Repair', statuses:['picked_up','building','in_progress','active','repair_needed','needs_repair','repairing','failed_validation']},
    'review': {title:'Review', statuses:['built','build_done','build_complete','ready_for_review','pending_review','reviewing','review_needed','validating','validation_all_pass','validation_passed','validation_failed','validation_needed','validating_in_progress','inspection','inspecting','needs_review','awaiting_review']},
    'done': {title:'Done', statuses:['done','completed','merged','finalized','accepted','valid_done','fully_done','success','inspeqtor_approved','approved']}
  };
  for (var colKey in cols) {
    var col = cols[colKey];
    var colDiv = document.getElementById('col-' + colKey);
    if (!colDiv) continue;
    var scrollDiv = colDiv.querySelector('.bay-scroll') || colDiv.querySelector('.col-scroll');
    if (!scrollDiv) continue;
    var countSpan = colDiv.querySelector('.bay-header-count') || colDiv.querySelector('.col-count');
    // Bay header counts are group-ticket counts, not individual briQ counts.
    var matching = groups.filter(function(g) { return col.statuses.indexOf(g.status) >= 0; });
    if (countSpan) countSpan.textContent = matching.length;
    var html = '';
    if (matching.length === 0) {
      html = '<div class="empty-bay"><div class="cybersquid-sm" style="width:70px;height:70px"></div><div class="empty-label">No tickets</div></div>';
      setTimeout(function() {
        var squids = colDiv.querySelectorAll('.cybersquid-sm');
        for (var si = 0; si < squids.length; si++) {
          if (squids[si].querySelector('svg')) continue;
          var svgSrc = document.getElementById('cybersquid-svg');
          if (!svgSrc) continue;
          var svgNS = 'http://www.w3.org/2000/svg';
          var svg = document.createElementNS(svgNS, 'svg');
          svg.setAttribute('viewBox', '0 0 56 84');
          svg.setAttribute('width', '100%');
          svg.setAttribute('height', '100%');
          svg.innerHTML = svgSrc.innerHTML;
          squids[si].innerHTML = '';
          squids[si].appendChild(svg);
        }
      }, 10);
    } else {
      matching.forEach(function(g) {
        var gid = g.safe_id || g.id || '';
        var gstatus = g.status || 'planned';
        var weight = g.progress_weight_pct != null ? (' ' + g.progress_weight_pct.toFixed(0) + '%') : '';
        html += '<div class="group-card" data-group-id="' + gid + '" onclick="openGroupOverlay(\'' + gid + '\')" tabindex="0" role="button"><div class="group-title">' + (g.title || gid) + ' <span class="group-status status-' + gstatus + '">' + gstatus + '</span><span class="group-weight">' + weight + '</span></div>';
        html += '<div class="group-desc">' + (g.description || '').slice(0, 120) + '</div>';
        html += '<div class="briq-list">';
        (g.briqs || []).forEach(function(b) {
          var s = b.status || '';
          var icon = {done:'✅',needs_repair:'🔧',failed:'❌',in_progress:'🔄',building:'🔨'}[s] || '⏳';
          html += '<div class="briq-item"><span class="briq-icon">' + icon + '</span><span class="briq-title">' + (b.title || '') + '</span></div>';
        });
        html += '</div></div>';
      });
    }
    scrollDiv.innerHTML = html;
  }
}

// ====== IDLE MODE ======
function setIdleState() {
  isIdleMode = true;
  var el;
  el = document.getElementById('live-run-id'); if (el) el.textContent = '\u2014';
  el = document.getElementById('live-status'); if (el) { el.textContent = 'idle'; el.style.color = 'var(--text-muted)'; }
  el = document.getElementById('live-agent-name'); if (el) { el.textContent = '\u2014'; el.style.color = ''; }
  el = document.getElementById('live-model'); if (el) el.textContent = '\u2014';
  el = document.getElementById('live-action'); if (el) { el.textContent = 'Waiting for run'; el.className = 'telemetry-val'; }
  if (typeof setActionStatus === 'function') setActionStatus('Waiting for run');
  el = document.getElementById('live-cycle'); if (el) el.textContent = '\u2014/\u2014';
  el = document.getElementById('live-total-time'); if (el) { el.textContent = '00:00'; el.style.color = ''; }
  el = document.getElementById('live-agent-time'); if (el) { el.textContent = '00:00'; el.style.color = ''; }
  el = document.getElementById('nav-total-time'); if (el) { el.textContent = '00:00'; el.style.color = ''; }
  el = document.getElementById('nav-agent-time'); if (el) { el.textContent = '00:00'; el.style.color = ''; }
  if (typeof window.stopMascotLoader === 'function') window.stopMascotLoader();
  setProgressDisplay(0);
  var npr2 = document.getElementById('nav-progress-block');
  if (npr2) { npr2.classList.remove('done', 'green', 'pulse'); }
  var npel2 = document.getElementById('nav-progress');
  if (npel2) { npel2.style.textShadow = 'none'; npel2.style.boxShadow = 'none'; }
  el = document.getElementById('live-total-groups'); if (el) el.textContent = '—';
  el = document.getElementById('live-groups-done'); if (el) el.textContent = '0';
  el = document.getElementById('live-total-briqs'); if (el) el.textContent = '—';
  el = document.getElementById('live-briqs-done'); if (el) el.textContent = '0';
  setYoloDisplay(null);
  ['planned','building','review','done'].forEach(function(c) {
    var colDiv = document.getElementById('col-' + c);
    if (colDiv) {
      var scrollDiv = colDiv.querySelector('.bay-scroll') || colDiv.querySelector('.col-scroll');
      if (scrollDiv) scrollDiv.innerHTML = '<div class="empty-bay"><div class="cybersquid-sm" style="width:70px;height:70px"></div><div class="empty-label">No tickets</div></div>';
      var countSpan = colDiv.querySelector('.bay-header-count') || colDiv.querySelector('.col-count');
      if (countSpan) countSpan.textContent = '0';
    }
  });
  var body = document.getElementById('term-body');
  if (body) { body.innerHTML = '<div class="placeholder-msg" style="text-align:center;color:var(--text-muted);padding:24px">Connected \u2014 waiting for run</div>'; }
}

var lastActiveRunId = null;
function checkIdleMode() {
  fetch('/api/qonqrete/health')
    .then(function(r) { return r.json(); })
    .then(function(h) {
      if (!h.active_run_root || !h.active_run_id) {
        if (lastActiveRunId !== null) {
          lastActiveRunId = null;
          setIdleState();
          reconnectSSE();
        } else if (!isIdleMode) {
          setIdleState();
        }
      } else {
        isIdleMode = false;
        if (h.active_run_id !== lastActiveRunId) {
          lastActiveRunId = h.active_run_id;
          reconnectSSE();
          var body = document.getElementById('term-body');
          if (body) { var placeholder = body.querySelector('.placeholder-msg'); if (placeholder) placeholder.remove(); }
          if (sseReady) {
            addTermLine(new Date().toISOString().slice(11,19), 'retarget', 'Switched to run ' + h.active_run_id);
          }
          setTimeout(updateBoardFromModel, 200);
        } else {
          var body2 = document.getElementById('term-body');
          if (body2) { var placeholder2 = body2.querySelector('.placeholder-msg'); if (placeholder2) placeholder2.remove(); }
        }
      }
    }).catch(function() {});
}

function reconnectSSE() {
  if (window._sseInstance) {
    window._sseInstance.close();
    window._sseInstance = null;
  }
  sseReady = false;
  initSSE();
}
setTimeout(updateCurrentRunPanel, 600);

// ====== Session Selector ======
function openSessionSelector() {
  document.getElementById('session-modal').style.display = 'flex';
  refreshSessions();
}
function closeSessionSelector() {
  document.getElementById('session-modal').style.display = 'none';
}
function escapeHtml(str) {
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}
function fmtLocalTs(ts) {
  var d = new Date((ts || 0) * 1000);
  var rh = function(n) { return String(n).padStart(2, '0'); };
  return rh(d.getHours()) + ':' + rh(d.getMinutes()) + ':' + rh(d.getSeconds());
}
function refreshSessions() {
  var list = document.getElementById('session-list');
  list.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px;">Scanning sessions...</div>';
  fetch('/api/qonqrete/sessions')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok || !data.sessions || data.sessions.length === 0) {
        list.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px;">No sessions found</div>';
        return;
      }
      var linkedId = data.linked_run_id;
      var html = '';
      data.sessions.forEach(function(s) {
        var isLinked = s.run_id === linkedId;
        var linkStatus = s.link_status || (isLinked ? 'linked' : (s.selectable !== false ? 'resolved' : 'tmux_only_unresolved'));
        var selectable = s.selectable !== false;
        var borderColor = isLinked ? 'var(--constr-amber)' : (linkStatus === 'tmux_only_unresolved' ? '#f59e0b' : 'var(--bevel-edge)');
        var bgColor = isLinked ? 'var(--metal-mid)' : 'var(--metal-dark)';
        var stateColors = {running:'#4ade80',starting:'#facc15',started:'#4ade80',finished:'#8b949e',failed:'#ef4444',stale:'#6b7280'};
        var sc = stateColors[s.state] || '#8b949e';
        html += '<div style="background:' + bgColor + ';border:1px solid ' + borderColor + ';padding:12px;">';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">';
        html += '<span style="font-family:monospace;font-size:13px;color:var(--constr-amber);">' + escapeHtml((s.run_id || '').slice(0, 20)) + '</span>';
        html += '<div style="display:flex;gap:4px;align-items:center;">';
        if (linkStatus) html += '<span style="font-size:9px;color:var(--text-muted);background:rgba(0,0,0,0.2);padding:1px 5px;">' + escapeHtml(linkStatus) + '</span>';
        html += '<span style="font-size:11px;color:' + sc + ';background:rgba(0,0,0,0.3);padding:2px 8px;">' + escapeHtml(s.state || 'unknown') + '</span>';
        html += '</div></div>';
        html += '<div style="font-size:11px;color:var(--text-muted);display:flex;flex-wrap:wrap;gap:8px;">';
        if (s.runner) html += '<span>Runner: ' + escapeHtml(s.runner) + '</span>';
        if (s.yolo !== undefined && s.yolo !== null) html += '<span>YOLO: ' + (s.yolo ? 'ON' : 'OFF') + '</span>';
        if (s.tmux_session) html += '<span>tmux: ' + escapeHtml(s.tmux_session) + '</span>';
        html += '<span>Source: ' + escapeHtml(s.source || 'unknown') + '</span>';
        html += '</div>';
        if (s.run_root) html += '<div style="font-size:10px;color:var(--text-muted);margin-top:4px;">Root: ' + escapeHtml(s.run_root) + '</div>';
        if (s.events_path) html += '<div style="font-size:10px;color:var(--text-muted);">Events: ' + escapeHtml(s.events_path) + '</div>';
        if (s.target_path) html += '<div style="font-size:10px;color:var(--text-muted);">Target: ' + escapeHtml(s.target_path) + '</div>';
        html += '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">';
        if (!isLinked && selectable) {
          html += '<button data-action="select" data-run-id="' + (s.run_id || '') + '" style="background:var(--constr-orange);color:#000;border:none;padding:4px 12px;cursor:pointer;font-size:12px;font-weight:bold;font-family:var(--font-industrial);text-transform:uppercase;">Select</button>';
        } else if (isLinked) {
          html += '<span style="color:var(--constr-amber);font-size:11px;font-weight:bold;">&check; Linked</span>';
        }
        if (s.attach_command) {
          html += '<button data-action="copy" data-copy-value="' + (s.attach_command || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;') + '" style="background:var(--metal-dark);color:var(--text-main);border:1px solid var(--bevel-edge);padding:4px 10px;cursor:pointer;font-size:12px;">Copy Attach</button>';
        }
        if (s.run_root) {
          html += '<button data-action="copy" data-copy-value="' + (s.run_root || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;') + '" style="background:var(--metal-dark);color:var(--text-main);border:1px solid var(--bevel-edge);padding:4px 10px;cursor:pointer;font-size:12px;">Copy Root</button>';
        }
        if (s.events_path) {
          html += '<button data-action="copy" data-copy-value="' + (s.events_path || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;') + '" style="background:var(--metal-dark);color:var(--text-main);border:1px solid var(--bevel-edge);padding:4px 10px;cursor:pointer;font-size:12px;">Copy Events</button>';
        }
        if (linkStatus === 'tmux_only_unresolved') {
          html += '<button data-action="adopt" data-tmux="' + (s.tmux_session || '') + '" style="background:#f59e0b;color:#000;border:none;padding:4px 12px;cursor:pointer;font-size:12px;font-weight:bold;font-family:var(--font-industrial);text-transform:uppercase;">Adopt</button>';
        }
        html += '</div></div>';
      });
      list.innerHTML = html;
    }).catch(function(e) {
      list.innerHTML = '<div style="color:var(--alarm-red);text-align:center;padding:20px;">Error loading sessions</div>';
    });
}

function selectSession(runId) {
  fetch('/api/qonqrete/sessions/select', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({run_id: runId})
  }).then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        closeSessionSelector();
        reconnectSSE();
        setTimeout(updateBoardFromModel, 200);
        setTimeout(checkIdleMode, 500);
        addTermLine(new Date().toISOString().slice(11,19), 'system', 'Switched to run ' + runId);
      } else {
        alert('Failed to switch: ' + (data.message || 'unknown error'));
      }
    }).catch(function(e) {
      alert('Error switching session');
    });
}

function openAdoptForm(tmuxSession) {
  var runRoot = prompt('Enter the run_root path for tmux session ' + tmuxSession + ':');
  if (!runRoot) return;
  var eventsPath = prompt('Enter events_path (default: run_root/events.jsonl):', runRoot + '/events.jsonl');
  if (!eventsPath) return;
  var targetPath = prompt('Enter target_path (optional):', '');
  var taskPath = prompt('Enter task_path (optional):', '');
  var payload = {
    tmux_session: tmuxSession,
    run_root: runRoot,
    events_path: eventsPath
  };
  if (targetPath) payload.target_path = targetPath;
  if (taskPath) payload.task_path = taskPath;
  fetch('/api/qonqrete/sessions/adopt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  }).then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.ok) {
        closeSessionSelector();
        reconnectSSE();
        setTimeout(updateBoardFromModel, 200);
        setTimeout(checkIdleMode, 500);
        addTermLine(new Date().toISOString().slice(11,19), 'system', 'Adopted tmux session: ' + tmuxSession);
        alert('Session adopted successfully!');
      } else {
        alert('Adopt failed: ' + (data.message || 'unknown error'));
      }
    }).catch(function(e) {
      alert('Error adopting session');
    });
}

function copyToClipboard(text) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  addTermLine(new Date().toISOString().slice(11,19), 'system', 'Copied: ' + text.slice(0, 60));
}

// ====== Current Run Panel ======
// ====== Current Run helpers ======
function isUsefulText(v) {
  if (v === null || v === undefined) return false;
  var s = String(v).trim();
  if (!s) return false;
  return ['—', '-', '--', '---', 'unknown', 'Unknown', 'UNKNOWN', 'null', 'undefined'].indexOf(s) < 0;
}

function setTextOrHide(id, text, prefix) {
  var el = document.getElementById(id);
  if (!el) return;
  if (!isUsefulText(text)) {
    el.textContent = '';
    el.style.display = 'none';
    return;
  }
  el.textContent = (prefix || '') + text;
  el.style.display = '';
}

function setYoloDisplay(value) {
  var el = document.getElementById('live-yolo');
  if (!el) return;
  if (value === true) {
    el.textContent = 'ON';
    el.style.color = 'var(--ok-green2)';
  } else if (value === false) {
    el.textContent = 'OFF';
    el.style.color = 'var(--text-muted)';
  } else {
    el.textContent = '—';
    el.style.color = 'var(--text-muted)';
  }
}

function updateCurrentRunPanel() {
  fetch('/api/qonqrete/current-run')
    .then(function(r) { return r.json(); })
    .then(function(cr) {
      var panel = document.getElementById('current-run-panel');
      if (!panel) return;

      if (!cr.exists) {
        panel.style.display = 'none';
        setYoloDisplay(null);
        return;
      }

      panel.style.display = '';

      if (cr.run_id) {
        var runEl = document.getElementById('live-run-id');
        if (runEl) {
          runEl.textContent = cr.run_id;
          runEl.title = cr.run_id;
        }
      }

      setYoloDisplay(cr.yolo);
    }).catch(function() {});
}

var _origCheckIdleMode = checkIdleMode;
checkIdleMode = function() {
  fetch('/api/qonqrete/health')
    .then(function(r) { return r.json(); })
    .then(function(h) {
      if (!h.active_run_root || !h.active_run_id) {
        if (lastActiveRunId !== null) {
          lastActiveRunId = null;
          setIdleState();
          reconnectSSE();
        } else if (!isIdleMode) {
          setIdleState();
        }
      } else {
        isIdleMode = false;
        if (h.active_run_id !== lastActiveRunId) {
          lastActiveRunId = h.active_run_id;
          reconnectSSE();
          var body = document.getElementById('term-body');
          if (body) { var placeholder = body.querySelector('.placeholder-msg'); if (placeholder) placeholder.remove(); }
          if (sseReady) {
            addTermLine(new Date().toISOString().slice(11,19), 'retarget', 'Switched to run ' + h.active_run_id);
          }
          setTimeout(updateBoardFromModel, 200);
        }
      }
    }).catch(function() {});
};

// ====== SSE ======
function initSSE() {
  if (window._sseInstance) {
    window._sseInstance.close();
  }
  var es = new EventSource('/api/qonqrete/events/stream');
  window._sseInstance = es;
  var reconnecting = false;

  es.onopen = function() {
    setActionStatus('connected');
    if (!sseReady) {
      sseReady = true;
      addTermLine(new Date().toISOString().slice(11,19), 'connected', 'SSE stream connected');
    }
    checkIdleMode();
    setTimeout(updateBoardFromModel, 100);
  };

  es.onerror = function() {
    setActionStatus('reconnecting');
    sseReady = false;
    if (!reconnecting) { addTermLine('--:--:--', 'connection', 'SSE connection lost, retrying...'); reconnecting = true; }
    setTimeout(function() { reconnecting = false; }, 5000);
  };

  var _boardDebounce = null;
  function debouncedBoardRefresh() {
    if (_boardDebounce) clearTimeout(_boardDebounce);
    _boardDebounce = setTimeout(function() { updateBoardFromModel(); }, 300);
  }

  es.onmessage = function(e) {
    var data;
    try { data = JSON.parse(e.data); } catch(err) { return; }
    var evtType = data.type || 'message';
    var ts = new Date((data.ts || 0) * 1000).toISOString().slice(11, 19);
    var detail = '';
    var keyFields = ['message','text','name','role','model','status','score','cycle','exit_code','reason','action_status','verdict'];
    for (var i = 0; i < keyFields.length; i++) {
      var k = keyFields[i];
      if (data[k] !== undefined) {
        var v = data[k]; if (typeof v === 'object') v = JSON.stringify(v).slice(0, 80); else v = String(v).slice(0, 80);
        detail += k + '=' + v + ' ';
      }
    }
    if (!detail) {
      for (var k2 in data) {
        if (['ts','run_id','type'].indexOf(k2) >= 0) continue;
        var v2 = data[k2]; if (typeof v2 === 'object') v2 = JSON.stringify(v2).slice(0, 80); else v2 = String(v2).slice(0, 80);
        detail += k2 + '=' + v2 + ' '; if (detail.length > 200) break;
      }
    }
    if (sseReady) addTermLine(ts, evtType, detail);

    // ---- Route agent output events into live agent panes (real-time streaming) ----
    var outputEventTypes = [
      'stream.output', 'agent.output', 'output.line',
      'agent_call.output', 'stream.line', 'stream_chunk',
      'agent.stream', 'agent_log', 'stderr.line', 'stdout.line',
      'agent_thought', 'agent_tool_call',
      'tool_call.start', 'tool.input', 'tool_call.result', 'tool.output'
    ];
    if (outputEventTypes.indexOf(evtType) >= 0) {
      var liveRole = data.role || data.active_agent || currentActiveAgent || '';
      if (liveRole && liveAgentLines[liveRole]) {
        var lts = '';
        if (data.ts && data.ts > 0) {
          lts = fmtLocalTs(data.ts);
        }
        var ltext = data.text || data.output || data.line || data.input || data.result || data.message || '';
        if (typeof ltext === 'object' && ltext !== null) ltext = JSON.stringify(ltext);
        ltext = String(ltext == null ? '' : ltext);
        if (ltext && String(ltext).trim() && !_stripEnvLeak(ltext)) {
          // Map level: error-ish -> error, tool-ish -> tool, thought -> thought, else info
          var lvl = data.level || 'info';
          var lvlS = String(lvl).toLowerCase();
          if (lvlS === 'stderr' || evtType === 'stderr.line' || (evtType === 'agent_log' && lvlS === 'error')) lvlS = 'error';
          else if (evtType === 'agent_thought') lvlS = 'thought';
          else if (evtType.indexOf('tool') >= 0) lvlS = 'tool';
          liveAgentLines[liveRole].push({
            ts: lts,
            text: String(ltext).trim(),
            level: lvlS,
            event: evtType
          });
          // Cap ~500 lines per agent to keep memory bounded
          if (liveAgentLines[liveRole].length > 500) {
            liveAgentLines[liveRole] = liveAgentLines[liveRole].slice(-500);
          }
          lastAgentOutputEvent = { role: liveRole, ts: data.ts };
          // Render live only when the agents view is visible (re-apply highlight too)
          if (currentView === 'agents') {
            updateAgentPaneLive(liveRole);
            if (currentActiveAgent) highlightActiveAgent(currentActiveAgent);
          }
        }
      }
    }

    switch (evtType) {
      case 'active_agent_changed': {
        if (data.role) {
          lastHandoffAgent = data.role;
          currentActiveAgent = data.role;
          var el = document.getElementById('live-agent-name');
          if (el) { el.textContent = agentDisplay(data.role); el.style.color = agentColor(data.role); }
          if (currentView === 'agents' && typeof highlightActiveAgent === 'function') {
            highlightActiveAgent(currentActiveAgent);
            updateAgentPaneLive(currentActiveAgent);
          }
        }
        if (data.model) {
          var el2 = document.getElementById('live-model'); if (el2) el2.textContent = modelDisplayBracketed(data.model);
        }
        if (window.qonqreteStateOverlay) window.qonqreteStateOverlay(data.role === 'instruqtor' ? 'Planning' : (data.role === 'construqtor' ? 'Building' : 'Clarifying'), data.role || '');
        // A10: reset the Agent timer on every active-agent handoff. Also sync
        // lastHandoffAgent below so the subsequent poll path does not double-reset.
        if (typeof window.resetAgentTime === 'function') window.resetAgentTime();
        break;
      }
      case 'action_status_changed': {
        if (data.action_status) {
          var ael = document.getElementById('live-action');
          if (ael) {
            // Never surface a ready-to-review status on the GUI. Coerce the
            // forbidden literal to "Building" before writing it to the DOM.
            var liveStatus = data.action_status;
            if (liveStatus === 'Ready for review' || liveStatus === 'ready_for_review') {
              liveStatus = 'Building';
            }
            ael.textContent = liveStatus;
            ael.className = 'telemetry-val';
            if (liveStatus === 'FULLY_DONE') ael.className = 'telemetry-val good';
            else if (liveStatus === 'FAILED' || liveStatus === 'BLOCKED') ael.className = 'telemetry-val bad';
          }
          if (typeof setActionStatus === 'function') setActionStatus(data.action_status); if (window.qonqreteStateOverlay) window.qonqreteStateOverlay(data.action_status, data.role || data.agent || '');
        }
        break;
      }
      case 'run.completed': {
        var sel = document.getElementById('live-status'); if (sel) { sel.textContent = 'done'; sel.style.color = 'var(--ok-green2)'; }
        setProgressDisplay(100);
        // Force the top-right #nav-progress to 100% green with persistent glow
        var navDoneEl = document.getElementById('nav-progress');
        if (navDoneEl) {
          navDoneEl.textContent = '100%';
          navDoneEl.style.color = 'var(--ok-green2)';
          navDoneEl.style.textShadow = '0 0 12px var(--ok-green2)';
          navDoneEl.style.boxShadow = '0 0 12px var(--ok-green2)';
        }
        var navDoneBlock = document.getElementById('nav-progress-block');
        if (navDoneBlock) {
          navDoneBlock.classList.add('green', 'done');
          navDoneBlock.classList.remove('pulse');
          void navDoneBlock.offsetWidth;
          navDoneBlock.classList.add('pulse');
        }
        var ael2 = document.getElementById('live-action'); if (ael2) { ael2.textContent = 'FULLY_DONE'; ael2.className = 'telemetry-val good'; }
        // A15: freeze Total + Agent at the terminal FULLY_DONE moment (idempotent guard inside freezeTotalTime).
        if (typeof window.freezeTotalTime === 'function') window.freezeTotalTime(null);
        if (typeof window.stopMascotLoader === 'function') window.stopMascotLoader();
        if (typeof setActionStatus === 'function') setActionStatus('FULLY_DONE'); if (window.qonqreteStateOverlay) window.qonqreteStateOverlay('FULLY_DONE','');
        break;
      }
      case 'run.aborted': {
        var sel2 = document.getElementById('live-status'); if (sel2) { sel2.textContent = 'aborted'; sel2.style.color = 'var(--alarm-red)'; }
        if (typeof window.stopMascotLoader === 'function') window.stopMascotLoader();
        break;
      }
      case 'run.failed': {
        var sel3 = document.getElementById('live-status'); if (sel3) { sel3.textContent = 'failed'; sel3.style.color = 'var(--alarm-red)'; }
        if (typeof window.stopMascotLoader === 'function') window.stopMascotLoader();
        break;
      }
      case 'run.started': {
        // Fresh run: reset the live agent buffers so stale output from a previous run is cleared
        liveAgentLines = { qlarifier: [], instruqtor: [], construqtor: [], inspeqtor: [] };
        liveAgentInitialized = false;
        lastAgentOutputEvent = null;
        liveAgentModel = {};
        lastLiveAgentUpdate = {};
        currentActiveAgent = '';
        if (typeof window.resetRunTimeForNewRun === 'function') window.resetRunTimeForNewRun(data.ts || (Date.now() / 1000), data.max_time_seconds || 0);
        var rel;
        rel = document.getElementById('live-status'); if (rel) { rel.textContent = 'running'; rel.style.color = 'var(--constr-amber)'; }
        setProgressDisplay(0);
        // Clear any persisted "done"/green glow from a previous run
        var npr = document.getElementById('nav-progress-block');
        if (npr) { npr.classList.remove('done', 'green', 'pulse'); }
        var npel = document.getElementById('nav-progress');
        if (npel) { npel.style.textShadow = 'none'; npel.style.boxShadow = 'none'; }
        rel = document.getElementById('live-cycle'); if (rel) { var mc2 = data.max_cycles_display || ((data.max_cycles && data.max_cycles > 0) ? String(data.max_cycles) : '\u221E'); rel.textContent = '1/' + mc2; }
        if (data.yolo !== undefined && typeof setYoloDisplay === 'function') setYoloDisplay(data.yolo);
        rel = document.getElementById('live-action'); if (rel) { rel.textContent = 'Preparing'; rel.className = 'telemetry-val waiting'; }
        if (typeof setActionStatus === 'function') setActionStatus('Preparing'); if (window.qonqreteStateOverlay) window.qonqreteStateOverlay('Preparing','qlarifier');
        rel = document.getElementById('live-total-groups'); if (rel) rel.textContent = '—';
        rel = document.getElementById('live-groups-done'); if (rel) rel.textContent = '0';
        rel = document.getElementById('live-total-briqs'); if (rel) rel.textContent = '—';
        rel = document.getElementById('live-briqs-done'); if (rel) rel.textContent = '0';
        if (data.run_id) { rel = document.getElementById('live-run-id'); if (rel) { rel.textContent = data.run_id; rel.title = data.run_id; } }
        ['planned','building','review','done'].forEach(function(c) {
          var colDiv = document.getElementById('col-' + c);
          if (colDiv) {
            var scrollDiv = colDiv.querySelector('.bay-scroll') || colDiv.querySelector('.col-scroll');
            if (scrollDiv) scrollDiv.innerHTML = '<div class="empty-bay"><div class="cybersquid-sm" style="width:70px;height:70px"></div><div class="empty-label">No tickets</div></div>';
            var countSpan = colDiv.querySelector('.bay-header-count') || colDiv.querySelector('.col-count');
            if (countSpan) countSpan.textContent = '0';
          }
        });
        sseReady = true;
        if (typeof window.startMascotLoader === 'function') window.startMascotLoader();
        var body = document.getElementById('term-body');
        if (body) { var placeholder = body.querySelector('.placeholder-msg'); if (placeholder) placeholder.remove(); }
        setTimeout(function() { updateBoardFromModel(); }, 300);
        break;
      }
    }
    debouncedBoardRefresh();
  };

  setInterval(function() { checkIdleMode(); updateBoardFromModel(); updateCurrentRunPanel(); }, 2000);
  setTimeout(function() { checkIdleMode(); updateBoardFromModel(); }, 500);
}
initSSE();
setTimeout(updateCurrentRunPanel, 600);

// ====== QONQRETE PHRASE TICKER ======
var QONQRETE_BANNER_PHRASES = [
  "Controlling the void since HTTP 404.",
  "We don't write apps. We pour them into production.",
  "Autonomy mixed fresh, reinforced with bad intentions.",
  "From vague prompt to hardened QonQrete\u2014no adult supervision required.",
  "Release the cybersquid. The backlog owes us money.",
  "Blueprints are temporary. Fully autonomous construQtion is forever.",
  "Built in the dark. Inspected under harsher lighting.",
  "Your requirements entered the yard. Something stronger came back.",
  "Measure twice. Spawn agents. Demolish assumptions.",
  "Turning TODO graveyards into fully operational infrastructure.",
  "No cowboy coding\u2014only industrial-grade squid wrangling.",
  "We monkeypatch reality, then make inspeQtor review the diff.",
  "Concrete logic. Reinforced prompts. Questionable machinery.",
  "The cybersquid reviewed your architecture and is quietly disappointed.",
  "One prompt in. Entire application out. Sanity sold separately.",
  "Autonomous by design. Unreasonably QonQrete by nature.",
  "Built from tickets, caffeine, and unresolved cosmic pressure.",
  "We don't fight technical debt. We encase it in load-bearing QonQrete.",
  "Constructing tomorrow with tools that probably shouldn't be awake.",
  "Fully done means FULLY_DONE. Anything else goes back into the mixer."
];

function initQonQreteTicker() {
  var track = document.getElementById('transmission-track');
  var ticker = document.getElementById('qonqrete-ticker');
  if (!track || !ticker) return;

  var phrases = QONQRETE_BANNER_PHRASES;
  var phraseIndex = 0;
  var currentItem = null;
  var animationTimer = null;
  var paused = false;

  // Clear any existing content
  track.innerHTML = '';

  // Create a single phrase element that we'll reuse
  currentItem = document.createElement('span');
  currentItem.className = 'phrase-item phrase-solo';
  track.appendChild(currentItem);

  // Insert keyframes if not already present
  if (!document.getElementById('ticker-keyframes')) {
    var styleSheet = document.createElement('style');
    styleSheet.id = 'ticker-keyframes';
    styleSheet.textContent =
      '@keyframes scrollPhraseIn{0%{transform:translateX(100%)}100%{transform:translateX(0)}}' +
      '@keyframes scrollPhraseOut{0%{transform:translateX(0)}100%{transform:translateX(calc(-100% - 40px))}}';
    document.head.appendChild(styleSheet);
  }

  // Add solo-phrase styling if not already present
  if (!document.getElementById('ticker-solo-style')) {
    var soloStyle = document.createElement('style');
    soloStyle.id = 'ticker-solo-style';
    soloStyle.textContent =
      '.phrase-solo{position:absolute;top:50%;right:0;transform:translateY(-50%);}' +
      '.phrase-solo.entering{animation:scrollPhraseIn 0.6s ease-out forwards;}' +
      '.phrase-solo.holding{transform:translateX(0) translateY(-50%);}' +
      '.phrase-solo.exiting{animation:scrollPhraseOut 10s linear forwards;}';
    document.head.appendChild(soloStyle);
  }

  function showNextPhrase() {
    if (paused) {
      // Retry after a short delay
      animationTimer = setTimeout(showNextPhrase, 200);
      return;
    }

    // Set the next phrase
    currentItem.textContent = phrases[phraseIndex];
    phraseIndex = (phraseIndex + 1) % phrases.length;

    // Reset position: start off-screen right, invisible
    currentItem.classList.remove('entering', 'holding', 'exiting');
    currentItem.style.opacity = '1';

    // Phase 1: Enter from right
    void currentItem.offsetWidth; // force reflow
    currentItem.classList.add('entering');

    // After entering (0.6s), hold briefly then exit
    animationTimer = setTimeout(function() {
      if (paused) {
        animationTimer = setTimeout(function() {
          currentItem.classList.remove('entering');
          currentItem.classList.add('holding');
          startExit();
        }, 200);
        return;
      }

      currentItem.classList.remove('entering');
      currentItem.classList.add('holding');

      // Hold for readability (1.2s) then start exiting
      animationTimer = setTimeout(function() {
        if (paused) {
          animationTimer = setTimeout(startExit, 200);
          return;
        }
        startExit();
      }, 1200);
    }, 600);
  }

  function startExit() {
    currentItem.classList.remove('holding');
    void currentItem.offsetWidth;
    currentItem.classList.add('exiting');

    // After exiting (10s for slow scroll), show next
    animationTimer = setTimeout(function() {
      if (paused) {
        animationTimer = setTimeout(function() {
          currentItem.classList.remove('exiting');
          showNextPhrase();
        }, 200);
        return;
      }
      currentItem.classList.remove('exiting');
      showNextPhrase();
    }, 10000);
  }

  // Pause on hover
  ticker.addEventListener('mouseenter', function() {
    paused = true;
    if (currentItem) {
      currentItem.style.animationPlayState = 'paused';
    }
  });
  ticker.addEventListener('mouseleave', function() {
    paused = false;
    if (currentItem) {
      currentItem.style.animationPlayState = 'running';
    }
  });
  ticker.addEventListener('focusin', function() {
    paused = true;
    if (currentItem) {
      currentItem.style.animationPlayState = 'paused';
    }
  });
  ticker.addEventListener('focusout', function() {
    paused = false;
    if (currentItem) {
      currentItem.style.animationPlayState = 'running';
    }
  });

  // Start the cycle
  showNextPhrase();
}
// ====== DECK RESIZER ======
function calculateDeckResizeBounds() {
  var shell = document.querySelector('.qq-industrial-shell');
  if (!shell) return {min: 130, max: 600};
  var shellHeight = shell.clientHeight;
  // Sum heights of fixed children
  var fixedHeight = 0;
  var children = shell.children;
  for (var i = 0; i < children.length; i++) {
    var c = children[i];
    if (c.classList.contains('workyard-main') || c.classList.contains('bottom-instrument-deck') || c.id === 'deck-resizer') continue;
    if (c.offsetHeight > 0 && getComputedStyle(c).display !== 'none') {
      fixedHeight += c.offsetHeight;
    }
  }
  var resizerH = document.getElementById('deck-resizer');
  var rH = resizerH ? resizerH.offsetHeight : 8;
  var minWorkyard = 180;
  var minDeck = 130;
  var availableH = shellHeight - fixedHeight - rH;
  var maxDeck = Math.max(minDeck, availableH - minWorkyard);
  return {min: minDeck, max: maxDeck};
}

function applyBottomDeckHeight(h) {
  var bounds = calculateDeckResizeBounds();
  h = Math.max(bounds.min, Math.min(bounds.max, h));
  if (isNaN(h) || h <= 0) h = 200;
  h = Math.round(h);
  document.documentElement.style.setProperty('--bottom-deck-height', h + 'px');
  // Update ARIA
  var resizer = document.getElementById('deck-resizer');
  if (resizer) {
    resizer.setAttribute('aria-valuemin', bounds.min);
    resizer.setAttribute('aria-valuemax', bounds.max);
    resizer.setAttribute('aria-valuenow', h);
  }
  // BGP9: do NOT set a fixed width on the big cybersquid area — its width now
  // follows the image containment via flex (min-width:0). We only keep driving a
  // sizing 'unit' so the overlay spinner keeps tracking the squid size.
  var bigArea = document.querySelector('.big-mascot-area');
  if (bigArea) {
    // Reference width for scaling the overlays (still derived from deck height).
    var scaledW = Math.max(80, Math.min(180, h * 0.9));
    // A14/BGP7/BGP6: the loader uses one pixel 'unit' (--mascot-unit) and one
    // font-size (--mascot-font) so the spinner's em-based offset uses the SAME
    // unit (the spinner's rendered height). Removal of the fixed width leaves the
    // squid able to grow to the event-log height without taking fixed horizontal
    // room; the event log keeps its own min-width so the terminal stays usable.
    var unit = Math.max(10, scaledW * 0.12);
    document.documentElement.style.setProperty('--mascot-unit', unit + 'px');
    document.documentElement.style.setProperty('--mascot-font', unit + 'px');
    var ldEl = document.getElementById('mascot-loader');
    if (ldEl) ldEl.style.fontSize = unit + 'px';
  }
  return h;
}

// ====== A14 + BGP6: horizontal braille-snake loader over the squid ======
var BRAILLE_SNAKE = [
  '\u28c0','\u28c4','\u28c6','\u28c7','\u28e7','\u28f7','\u28ff','\u28fe',
  '\u28f6','\u28e7','\u28c7','\u28c6','\u28c4','\u28c0','\u2800'
];
var mascotLoaderTimer = null;
var mascotLoaderIdx = 0;
var mascotLoaderEl = null;
// _ensureMascotLoaderEl() returns the loader element, re-creating it (and
// re-attaching it to the bottom .big-mascot-area) if it
// has been removed or re-rendered by a deck refresh. This is what keeps the
// braille-snake alive across run-status polls: a transient DOM re-render can
// never permanently kill the interval.
function _ensureMascotLoaderEl() {
  var el = document.getElementById('mascot-loader');
  if (el) {
    mascotLoaderEl = el;
    return el;
  }
  // Element is missing — try to find a .mascot-loader left anywhere in the doc.
  var found = document.querySelector('.mascot-loader');
  if (found && found.id === 'mascot-loader') {
    mascotLoaderEl = found;
    return found;
  }
  if (found && !found.id) {
    found.id = 'mascot-loader';
    mascotLoaderEl = found;
    return found;
  }
  // Nothing left — re-create it inside the big squid area so the spinner
  // resumes at the exact right spot.
  var bigArea = document.querySelector('.big-mascot-area');
  if (!bigArea) { mascotLoaderEl = null; return null; }
  var fresh = document.createElement('div');
  fresh.className = 'mascot-loader';
  fresh.id = 'mascot-loader';
  fresh.setAttribute('aria-hidden', 'true');
  // Keep the same font-size scaling so the snake matches the squid size.
  var unit = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--mascot-unit'), 10);
  if (unit) fresh.style.fontSize = unit + 'px';
  // Append it into the big squid area so z-order/layout stays consistent and
  // the braille-snake resumes at the exact right spot.
  bigArea.appendChild(fresh);
  mascotLoaderEl = fresh;
  return fresh;
}

function mascotLoaderTick() {
  try {
    var el = _ensureMascotLoaderEl();
    if (el) {
      el.textContent = BRAILLE_SNAKE[mascotLoaderIdx % BRAILLE_SNAKE.length];
    }
    // Always advance the frame so a transient missing-element tick never stalls
    // the cadence. The interval is ONLY cleared from stopMascotLoader() /
    // genuine terminal-idle paths — never from within a tick.
    mascotLoaderIdx++;
  } catch (e) {
    // BGP6: a transient DOM/parse error must NEVER kill the spinner interval —
    // keep advancing the frame so the cadence stays 120ms.
    try { mascotLoaderIdx++; } catch (_e) {}
  }
}
function startMascotLoader() {
  // Re-establish the DOM element first so a re-render can't hide the spinner.
  var el = _ensureMascotLoaderEl();
  // BGP6: if a stale interval is still around (or was stopped spuriously),
  // ALWAYS clear it first so re-starts are never swallowed by a guard. This
  // also guarantees no DUPLICATE setInterval ever stacks.
  if (mascotLoaderTimer) { clearInterval(mascotLoaderTimer); mascotLoaderTimer = null; }
  if (!el) return;
  mascotLoaderTick();
  mascotLoaderTimer = setInterval(mascotLoaderTick, 120);
}
function stopMascotLoader() {
  // BGP6: this is invoked ONLY from explicit terminal states (done/aborted/failed)
  // and run-reset. It must never be called spuriously mid-run, and because
  // startMascotLoader now always clears stale timers, any stray stop can no
  // longer permanently suppress the spinner.
  if (mascotLoaderTimer) { clearInterval(mascotLoaderTimer); mascotLoaderTimer = null; }
  var el = document.getElementById('mascot-loader');
  if (el) el.textContent = '';
}
window.startMascotLoader = startMascotLoader;
window.stopMascotLoader = stopMascotLoader;

function storeBottomDeckHeight(h) {
  try {
    localStorage.setItem('qonqrete.bottomDeckHeight.v1', String(Math.round(h)));
  } catch(e) {}
}

function loadStoredBottomDeckHeight() {
  try {
    var raw = localStorage.getItem('qonqrete.bottomDeckHeight.v1');
    if (raw !== null) {
      var v = parseFloat(raw);
      if (!isNaN(v) && isFinite(v) && v > 0 && v < 10000) {
        return v;
      }
    }
  } catch(e) {}
  return 200;
}

function initDeckResizer() {
  var resizer = document.getElementById('deck-resizer');
  if (!resizer) return;

  // Restore saved height
  var savedH = loadStoredBottomDeckHeight();
  var appliedH = applyBottomDeckHeight(savedH);

  // Set up pointer events for drag
  var startY, startHeight;

  function onPointerDown(e) {
    if (e.button !== 0 && e.pointerType === 'mouse') return; // primary only for mouse
    e.preventDefault();
    startY = e.clientY;
    startHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bottom-deck-height')) || 200;
    resizer.setPointerCapture(e.pointerId);
    resizer.classList.add('dragging');
    document.body.classList.add('deck-resizing');
  }

  function onPointerMove(e) {
    if (!resizer.hasPointerCapture(e.pointerId)) return;
    var dy = startY - e.clientY; // upward = positive
    var newH = startHeight + dy;
    applyBottomDeckHeight(newH);
  }

  function onPointerUp(e) {
    if (!resizer.hasPointerCapture && !resizer.classList.contains('dragging')) return;
    resizer.classList.remove('dragging');
    document.body.classList.remove('deck-resizing');
    try { resizer.releasePointerCapture(e.pointerId); } catch(ex) {}
    var finalH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bottom-deck-height')) || 200;
    storeBottomDeckHeight(finalH);
  }

  resizer.addEventListener('pointerdown', onPointerDown);
  resizer.addEventListener('pointermove', onPointerMove);
  resizer.addEventListener('pointerup', onPointerUp);
  resizer.addEventListener('pointercancel', onPointerUp);
  resizer.addEventListener('lostpointercapture', onPointerUp);

  // Keyboard accessibility
  resizer.addEventListener('keydown', function(e) {
    var current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bottom-deck-height')) || 200;
    var step = e.shiftKey ? 40 : 14;
    var newH = current;
    if (e.key === 'ArrowUp') { newH = current + step; e.preventDefault(); }
    else if (e.key === 'ArrowDown') { newH = current - step; e.preventDefault(); }
    else if (e.key === 'Home') { var b = calculateDeckResizeBounds(); newH = b.min; e.preventDefault(); }
    else if (e.key === 'End') { var b = calculateDeckResizeBounds(); newH = b.max; e.preventDefault(); }
    else return;
    newH = applyBottomDeckHeight(newH);
    storeBottomDeckHeight(newH);
  });

  // Double-click resets to default
  resizer.addEventListener('dblclick', function(e) {
    e.preventDefault();
    applyBottomDeckHeight(200);
    storeBottomDeckHeight(200);
  });

  // Re-clamp on window resize
  var resizeTimeout;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(function() {
      var current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bottom-deck-height')) || 200;
      applyBottomDeckHeight(current);
    }, 100);
  });

  // Observe current-run panel changes
  var runPanel = document.getElementById('current-run-panel');
  if (runPanel) {
    var observer = new MutationObserver(function() {
      var current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bottom-deck-height')) || 200;
      applyBottomDeckHeight(current);
    });
    observer.observe(runPanel, {attributes: true, attributeFilter: ['style']});
  }
}

// Initialize after DOM is ready
initQonQreteTicker();
initDeckResizer();

</script>

<!-- Session Selector Modal -->
<div id="session-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(5,5,5,0.85);z-index:9999;align-items:center;justify-content:center;">
  <div style="background:var(--metal-dark);border:2px solid var(--constr-orange);max-width:700px;width:90%;max-height:80vh;overflow-y:auto;padding:20px;color:var(--text-main);">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h2 style="margin:0;font-size:18px;color:var(--constr-amber);font-family:var(--font-industrial);text-transform:uppercase;letter-spacing:1px;">QonQrete Sessions</h2>
      <button onclick="closeSessionSelector()" style="background:none;border:none;color:var(--text-muted);font-size:24px;cursor:pointer;">&times;</button>
    </div>
    <div id="session-list" style="display:flex;flex-direction:column;gap:8px;">Loading sessions...</div>
<script>
(function() {
  var list = document.getElementById('session-list');
  if (list) {
    list.addEventListener('click', function(e) {
      var target = e.target;
      while (target && target !== list) {
        if (target.tagName === 'BUTTON') {
          var action = target.getAttribute('data-action');
          if (action === 'select') {
            var runId = target.getAttribute('data-run-id');
            if (runId) selectSession(runId);
          } else if (action === 'copy') {
            var val = target.getAttribute('data-copy-value');
            if (val) copyToClipboard(val);
          } else if (action === 'adopt') {
            var tmuxName = target.getAttribute('data-tmux');
            if (tmuxName) openAdoptForm(tmuxName);
          }
          break;
        }
        target = target.parentElement;
      }
    });
  }
})();
</script>
    <div style="margin-top:12px;text-align:right;">
      <button onclick="refreshSessions()" style="background:var(--metal-dark);color:var(--text-main);border:1px solid var(--bevel-edge);padding:6px 14px;cursor:pointer;font-family:var(--font-industrial);text-transform:uppercase;">Refresh</button>
      <button onclick="closeSessionSelector()" style="background:var(--metal-dark);color:var(--text-muted);border:1px solid var(--bevel-edge);padding:6px 14px;cursor:pointer;margin-left:8px;font-family:var(--font-industrial);text-transform:uppercase;">Close</button>
    </div>
  </div>
</div>

<style>
#qonqrete-state-overlay{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;
background:rgba(5,7,8,.88);backdrop-filter:blur(5px);text-align:center}
#qonqrete-state-overlay .qso-card{padding:34px 44px;border:1px solid var(--bevel-edge);border-radius:18px;background:var(--bg-panel);
box-shadow:0 0 50px rgba(0,0,0,.7);min-width:min(520px,88vw)}
#qonqrete-state-overlay img{width:150px;height:150px;object-fit:contain;display:block;margin:0 auto 18px}
#qonqrete-state-overlay h2{font-family:var(--font-industrial);font-size:28px;letter-spacing:1px;color:var(--constr-amber);margin-bottom:8px}
#qonqrete-state-overlay p{color:var(--text-muted);font-size:15px}
#qonqrete-state-overlay.done h2{color:var(--ok-green2)}
</style>
<div id="qonqrete-state-overlay" aria-live="polite">
 <div class="qso-card"><img src="/qonqrete-bottom-right.jpg" alt="QonQrete cybersquid">
 <h2 id="qso-title">PREPARING TASKS</h2><p id="qso-text">Qlarifier is preparing and enhancing the task…</p></div>
</div>
<script>
(function(){
 function qso(title,text,show,done){
   var o=document.getElementById('qonqrete-state-overlay'); if(!o)return;
   document.getElementById('qso-title').textContent=title;
   document.getElementById('qso-text').textContent=text;
   o.classList.toggle('done',!!done); o.style.display=show?'flex':'none';
 }
 window.qonqreteStateOverlay=function(status,role){
   var s=String(status||'').toLowerCase(), r=String(role||'').toLowerCase();
   if(s==='fully_done'||s==='done'||s==='completed'){qso('FULLY_DONE','QonQrete has finished the run. The yard is complete.',true,true);return}
   if(s.indexOf('plan')>=0||r==='instruqtor'){qso('PREPARING TICKETS','instruQtor is preparing the tickets for the board…',true,false);return}
   if(s.indexOf('build')>=0||r==='construqtor'){qso('','',false,false);return}
   if(s.indexOf('clarif')>=0||r==='qlarifier'||s==='preparing'||s==='pending'){qso('PREPARING TASKS','Qlarifier is preparing and enhancing the task…',true,false);return}
   if(s===''){return}
 };
})();
</script>
</body>
</html>
"""



## ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = 30


def main():
    parser = argparse.ArgumentParser(description="briQsQope local API server")
    parser.add_argument("--run-root", default=None, help="Path to QonQrete run root (legacy)")
    parser.add_argument("--control-root", default=None, help="Path to QonQrete control root (contains current-run.json)")
    parser.add_argument("--repo-root", default=None, help="Repository root directory (for display)")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=31337, help="Listen port")
    args = parser.parse_args()

    # Resolve run_root: --control-root takes precedence, then --run-root
    # In control-root mode, the server uses the control root as run_root
    # and resolves the active run via current-run.json at request time.
    if args.control_root:
        run_root = os.path.abspath(os.path.expanduser(args.control_root))
    elif args.run_root:
        run_root = os.path.abspath(os.path.expanduser(args.run_root))
    else:
        print("error: either --run-root or --control-root is required", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(run_root):
        print(f"error: root not found: {run_root}", file=sys.stderr)
        sys.exit(1)

    # Detect control-root mode: either --control-root was given, or
    # run_root contains (or can contain) current-run.json
    is_control_root = bool(args.control_root)
    if not is_control_root:
        current_run_path = os.path.join(run_root, "current-run.json")
        if os.path.isfile(current_run_path):
            is_control_root = True
        else:
            # Also check parent paths for current-run.json
            parent = os.path.dirname(run_root)
            for _ in range(3):
                if os.path.isfile(os.path.join(parent, "current-run.json")):
                    is_control_root = True
                    # Note: keep run_root as-is, control-root detection
                    # is handled at request time by checking current-run.json
                    break
                parent = os.path.dirname(parent)
                if parent == "/":
                    break

    # Resolve initial events_path
    events_path = os.path.join(run_root, "events.jsonl")
    if is_control_root:
        # In control-root mode, resolve active events_path from current-run.json
        current_run_path = os.path.join(run_root, "current-run.json")
        if os.path.isfile(current_run_path):
            try:
                with open(current_run_path, "r") as f:
                    cr = json.load(f)
                active_events = cr.get("events_path")
                if active_events:
                    events_path = active_events
                elif cr.get("run_root"):
                    events_path = os.path.join(cr["run_root"], "events.jsonl")
            except (json.JSONDecodeError, OSError):
                pass

    tailer = EventTailer(events_path)

    BriQsQopeHandler.run_root = run_root
    BriQsQopeHandler.repo_root = args.repo_root or os.path.dirname(run_root)
    BriQsQopeHandler.tailer = tailer
    BriQsQopeHandler.control_root = run_root if is_control_root else ""
    BriQsQopeHandler.control_root_mode = is_control_root

    server = ThreadingHTTPServer((args.host, args.port), BriQsQopeHandler)
    mode_label = "control-root" if BriQsQopeHandler.control_root_mode else "run-root"
    print(f"briQsQope API server starting on {args.host}:{args.port} (https://web.qonqrete.sh)")
    print(f"Root: {run_root} ({mode_label} mode)")
    print(f"Events: {events_path}")
    print("Server type: ThreadingHTTPServer (supports concurrent connections)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
