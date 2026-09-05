"""Config loader: qq.yaml + providers.yaml + CLI + env overrides.

Providers manifest (config/providers.yaml) is the single source of truth for
provider capabilities and model lists.  Qq config (config/qq.yaml) picks
defaults: provider, role models, harness checks, runtime modes, max cycles.

Resolution order (last wins):
  1) qq config
  2) providers manifest (read-only validation reference)
  3) CLI arguments
  4) environment variables (fill missing only)
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_DEFAULT_QQ = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config", "qq.yaml"))
_DEFAULT_PROVIDERS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config", "providers.yaml"))

_ALLOWED_REASONING_EFFORTS = ("", "minimal", "low", "high", "max")


# ---------------------------------------------------------------------------
# Typed config shapes
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class ProviderDef:
    name: str
    kind: str
    status: str                    # implemented | stub
    supports_sessions: bool = False
    supports_interactive_tui: bool = False
    supports_exec_mode: bool = True
    supports_tools: bool = True
    supports_thinking_mode: bool = False
    default_model: str = ""
    models: List[str] = dataclasses.field(default_factory=list)
    repo: str = ""
    notes: str = ""

    @classmethod
    def from_manifest(cls, name: str, data: Dict[str, Any]) -> "ProviderDef":
        return cls(
            name=name, kind=data.get("kind", "cli"),
            status=data.get("status", "stub"),
            supports_sessions=data.get("supports_sessions", False),
            supports_interactive_tui=data.get("supports_interactive_tui", False),
            supports_exec_mode=data.get("supports_exec_mode", True),
            supports_tools=data.get("supports_tools", True),
            supports_thinking_mode=data.get("supports_thinking_mode", False),
            default_model=data.get("default_model", ""),
            models=data.get("models") or [],
            repo=data.get("repo", ""),
            notes=data.get("notes", ""),
        )


@dataclasses.dataclass
class HarnessCheckConfig:
    name: str
    command: str


@dataclasses.dataclass
class QqWebConfig:
    """Configuration for the briQsQope web dashboard.

    briQsQope is an optional read-only web dashboard that displays
    QonQrete build groups as kanban-board cards.  It must:
      - Never act as the controller of the loop system
      - Never be the source of truth
      - Be toggleable via config boolean
      - Run on 0.0.0.0 by default (port 31337)
    """
    enabled: bool = True
    start_with_run: bool = True
    hard_fail_on_dashboard_error: bool = False
    host: str = "0.0.0.0"
    port: int = 31337
    open_browser: bool = True
    source_of_truth: str = "qonqrete"
    mode: str = "local_read_model"
    publish_level: str = "briq_group"
    expose_briqs_as_subtasks: bool = True
    allow_briq_level_tickets: bool = False
    event_source_type: str = "events_jsonl"
    poll_interval_ms: int = 500
    sse_enabled: bool = True
    allow_create_epic_from_ui: bool = False
    allow_start_run_from_ui: bool = False
    allow_pause_run_from_ui: bool = False
    allow_cancel_run_from_ui: bool = False
    allow_manual_status_override: bool = False
    product_name: str = "briQsQope"
    parent_product_name: str = "QonQrete"



@dataclasses.dataclass
class ImageBackendConfig:
    """Image generation routing.

    provider may be ``auto``, ``openai``, ``gemini`` or ``gradio``.  Auto
    follows the configured agent provider: OpenAI/Codex -> OpenAI, Gemini ->
    Google GenAI, everything else -> the public FLUX Gradio Space.
    """
    provider: str = "auto"
    model: str = "auto"
    aspect_ratio: str = "1:1"
    resolution: str = "1K"
    format: str = "png"
    quality: str = ""
    cfg_scale: float = 7.5
    steps: int = 20
    safe_mode: bool = False
    hide_watermark: bool = False
    negative_prompt: str = ""
    style: str = ""
    seed: int = 0
    gradio_space: str = "black-forest-labs/FLUX.1-schnell"

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    @property
    def is_venice(self) -> bool:
        return False


@dataclasses.dataclass
class QqConfig:
    """Resolved runtime config after merging all sources."""
    # Provider / adapter
    provider: str = "chatgpt"
    codeseeq_bin: Optional[str] = None
    runtime_mode: str = "host"
    bridge_mode: str = "process"

    # Models per role
    model_qlarifier: str = "gpt-5.5"
    model_instruqtor: str = "gpt-5.5"
    model_construqtor: str = "gpt-5.5"
    model_inspeqtor: str = "gpt-5.5"

    # Reasoning effort for thinking models (low, high, max, or empty for default)
    reasoning_effort: str = ""

    # Per-role reasoning effort overrides. Empty means "use the global
    # `reasoning_effort` default / CLI override".
    reasoning_qlarifier: str = ""
    reasoning_instruqtor: str = ""
    reasoning_construqtor: str = ""
    reasoning_inspeqtor: str = ""

    # Temperature for non-thinking models (None = not set, use default)
    temperature: Optional[float] = None

    # Top-p for non-thinking models (None = not set, use default)
    top_p: Optional[float] = None

    # Loop tuning
    briq_sensitivity: int = 0
    max_cycles: int = 0
    max_time_seconds: int = 0
    max_parallel_build_groups: int = 8
    parallel_spawn_delay_seconds: float = 1.0

    # Harness
    harness_checks: List[HarnessCheckConfig] = dataclasses.field(default_factory=list)

    # Sandbox (bubblewrap OS-level filesystem containment)
    construqtor_sandbox: str = "required"  # required | auto | off
    sandbox_network: str = "host"         # host | none
    sandbox_debug: bool = False

    # Workspace safety
    review_on_harness_failure: bool = False
    allow_dirty: bool = False
    no_repo: bool = False

    # YOLO: non-interactive mode (no clarifications, no approvals)
    yolo: Optional[bool] = None  # None = use default cascade; True/False = explicit

    # CLI behaviour
    verbose: bool = False
    json_output: bool = False
    no_color: bool = False

    # Streaming
    stream_agent_output: bool = True
    stream_mode: str = "prefixed"    # prefixed | raw
    stream_stderr: bool = True
    stream_indicator: str = "stream"  # stream | spinner | none
    show_prompts: bool = False

    # Sticky status line
    stream_status_line: str = "off"  # off | bottom | top
    stream_line_prefix: str = "auto"  # auto | agent | stream | none

    # Agent color output mode
    agent_color_output: str = "agent"  # agent | original | none

    # Paths
    repo_root: str = "."
    run_root: Optional[str] = None
    config_path: str = ""
    providers_config_path: str = ""

    # Web dashboard
    qq_web: QqWebConfig = dataclasses.field(default_factory=QqWebConfig)

    # Image backend
    image_backend: ImageBackendConfig = dataclasses.field(default_factory=ImageBackendConfig)

    # Resolved providers manifest (read-only reference)
    providers: Dict[str, ProviderDef] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_providers(providers_path: Optional[str] = None) -> Dict[str, ProviderDef]:
    path = providers_path or _DEFAULT_PROVIDERS
    raw = _load_yaml(path)
    providers: Dict[str, ProviderDef] = {}
    for name, data in raw.get("providers", {}).items():
        providers[name] = ProviderDef.from_manifest(name, data)
    return providers


def _validate_reasoning_value(value: str, source: str) -> str:
    """Normalize and validate a reasoning-effort value."""
    value = (value or "").strip().lower()
    if value not in _ALLOWED_REASONING_EFFORTS:
        raise ValueError(
            f"Invalid reasoning effort '{value}' for {source}. "
            f"Use one of: low, high, max."
        )
    return value


def resolve_config(
    *,
    qq_path: Optional[str] = None,
    providers_path: Optional[str] = None,
    # CLI overrides
    provider: Optional[str] = None,
    codeseeq_bin: Optional[str] = None,
    runtime_mode: Optional[str] = None,
    bridge_mode: Optional[str] = None,
    model_qlarifier: Optional[str] = None,
    model_instruqtor: Optional[str] = None,
    model_construqtor: Optional[str] = None,
    model_inspeqtor: Optional[str] = None,
    briq_sensitivity: Optional[int] = None,
    max_cycles: Optional[int] = None,
    max_time_seconds: Optional[int] = None,
    max_parallel_build_groups: Optional[int] = None,
    parallel_spawn_delay_seconds: Optional[float] = None,
    repo_root: str = ".",
    run_root: Optional[str] = None,
    harness_checks: Optional[List[str]] = None,
    review_on_harness_failure: Optional[bool] = None,
    allow_dirty: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    json_output: bool = False,
    no_color: bool = False,
    stream_agent_output: Optional[bool] = None,
    stream_mode: str = "prefixed",
    stream_stderr: bool = True,
    stream_indicator: str = "stream",
    show_prompts: bool = False,
    stream_status_line: str = "off",
    stream_line_prefix: str = "auto",
    agent_color_output: Optional[str] = None,
    no_repo: bool = False,

    # YOLO: non-interactive mode (no clarifications, no approvals)
    yolo: Optional[bool] = None,  # None = use default cascade; True/False = explicit
    reasoning_effort: Optional[str] = None,
    temperature: Optional[float] = None,
    # Web dashboard
    web_enabled: Optional[bool] = None,
    web_host: Optional[str] = None,
    web_port: Optional[int] = None,
    web_open_browser: Optional[bool] = None,
    web_publish_level: Optional[str] = None,
    web_hard_fail: Optional[bool] = None,
    top_p_val: Optional[float] = None,
) -> QqConfig:
    """Resolve runtime configuration from all sources.

    CLI overrides beat config. Environment fills only missing/empty values.
    """
    # 1) load qq config
    spine_raw = _load_yaml(qq_path or _DEFAULT_QQ)
    models_raw = spine_raw.get("models", {}) or {}
    defaults_raw = spine_raw.get("defaults", {}) or {}

    # 2) load providers
    providers = load_providers(providers_path or _DEFAULT_PROVIDERS)

    # 3) env
    env_provider = os.environ.get("QQ_PROVIDER")
    env_codeseeq_bin = os.environ.get("QQ_CODESEEQ_BIN")
    env_runtime = os.environ.get("CODESEEQ_RUNTIME_MODE")
    env_bridge = os.environ.get("CODESEEQ_BRIDGE_MODE")
    env_agent_color = os.environ.get("QQ_AGENT_COLOR_OUTPUT")

    # 4) merge: qq defaults < env < CLI
    cfg = QqConfig()

    # provider
    cfg.provider = spine_raw.get("provider", "chatgpt")
    if env_provider:
        cfg.provider = env_provider
    if provider is not None:
        cfg.provider = provider
    if dry_run:
        cfg.provider = "mock"

    # codeseeq bin (env only if not set)
    cfg.codeseeq_bin = codeseeq_bin  # CLI
    if cfg.codeseeq_bin is None:
        cfg.codeseeq_bin = env_codeseeq_bin

    # runtime / bridge
    cfg.runtime_mode = runtime_mode or env_runtime or spine_raw.get("runtime_mode", "host")
    cfg.bridge_mode = bridge_mode or env_bridge or spine_raw.get("bridge_mode", "process")

    # models — resolve from qq defaults, CLI overrides, or provider defaults.
    # Each role accepts either the legacy flat form (`qlarifier: model-name`)
    # or the new structured form:
    #
    #     qlarifier:
    #       model: deepseek-v4-flash-thinking
    #       reasoning: high
    #
    pd = providers.get(cfg.provider)

    def _parse_model_entry(entry: Any, default: str) -> tuple:
        if isinstance(entry, str) and entry.strip():
            return entry.strip(), ""
        if isinstance(entry, dict):
            model = str(entry.get("model") or default).strip()
            reasoning = str(entry.get("reasoning") or "").strip().lower()
            return model, reasoning
        return default, ""

    def _resolve_role(cli_val: Optional[str], cfg_key: str, default: str) -> tuple:
        model_from_cfg, reasoning_from_cfg = _parse_model_entry(
            models_raw.get(cfg_key), default)
        model = cli_val or model_from_cfg or (
            pd.default_model if pd and pd.default_model else default)
        # Global CLI reasoning effort beats per-role config (CLI > config).
        reasoning = reasoning_effort if reasoning_effort is not None else reasoning_from_cfg
        reasoning = _validate_reasoning_value(
            reasoning, f"models.{cfg_key}.reasoning")
        return model, reasoning

    cfg.model_qlarifier, cfg.reasoning_qlarifier = _resolve_role(
        model_qlarifier, "qlarifier", "gpt-5.5")
    cfg.model_instruqtor, cfg.reasoning_instruqtor = _resolve_role(
        model_instruqtor, "instruqtor", "gpt-5.5")
    cfg.model_construqtor, cfg.reasoning_construqtor = _resolve_role(
        model_construqtor, "construqtor", "gpt-5.5")
    cfg.model_inspeqtor, cfg.reasoning_inspeqtor = _resolve_role(
        model_inspeqtor, "inspeqtor", "gpt-5.5")

    # loop
    cfg.briq_sensitivity = briq_sensitivity if briq_sensitivity is not None else defaults_raw.get("briq_sensitivity", 0)
    cfg.max_cycles = max_cycles if max_cycles is not None else defaults_raw.get("max_cycles", 0)
    cfg.max_time_seconds = max_time_seconds if max_time_seconds is not None else defaults_raw.get("max_time_seconds", 0)
    cfg.max_parallel_build_groups = (max_parallel_build_groups if max_parallel_build_groups is not None
                                      else defaults_raw.get("max_parallel_build_groups", 8))
    cfg.parallel_spawn_delay_seconds = (parallel_spawn_delay_seconds if parallel_spawn_delay_seconds is not None
                                        else defaults_raw.get("parallel_spawn_delay_seconds", 1.0))

    # harness checks
    cfg_checks = spine_raw.get("harness", {}).get("checks", [])
    for c in cfg_checks:
        cfg.harness_checks.append(HarnessCheckConfig(name=c.get("name", ""), command=c.get("command", "")))
    if harness_checks:
        for i, cmd in enumerate(harness_checks):
            cfg.harness_checks.append(HarnessCheckConfig(name=f"cli-check-{i}", command=cmd))

    # safety
    if review_on_harness_failure is not None:
        cfg.review_on_harness_failure = review_on_harness_failure
    else:
        cfg.review_on_harness_failure = spine_raw.get("review_on_harness_failure", False)
    cfg.allow_dirty = allow_dirty
    cfg.no_repo = no_repo

    # YOLO mode
    # Precedence: explicit CLI flag > env var > config file > default (False for CLI)
    if yolo is not None:
        cfg.yolo = yolo
    else:
        # Check env: QONQRETE_YOLO
        env_yolo = os.environ.get("QONQRETE_YOLO", "")
        if env_yolo in ("1", "true", "yes"):
            cfg.yolo = True
        elif env_yolo in ("0", "false", "no"):
            cfg.yolo = False
        else:
            # Check config file (qonqrete section)
            qonqrete_raw = spine_raw.get("qonqrete", {})
            cfg.yolo = qonqrete_raw.get("yolo", False)

    # Global reasoning effort (CLI override / fallback). Per-role values were
    # already resolved above; this keeps `cfg.reasoning_effort` available as
    # the global default for backwards compatibility.
    if reasoning_effort is not None:
        cfg.reasoning_effort = _validate_reasoning_value(
            reasoning_effort, "reasoning_effort")
    else:
        cfg.reasoning_effort = ""

    # temperature (non-thinking models only)
    cfg.temperature = temperature

    # top_p (non-thinking models only)
    cfg.top_p = top_p_val

    # CLI flags
    cfg.verbose = verbose
    cfg.json_output = json_output
    cfg.no_color = no_color

    # Streaming
    cfg.stream_agent_output = stream_agent_output if stream_agent_output is not None else defaults_raw.get("stream_agent_output", True)
    if stream_mode not in ("prefixed", "raw"):
        raise ValueError(f"Invalid stream mode '{stream_mode}'. Use 'prefixed' or 'raw'.")
    cfg.stream_mode = stream_mode
    cfg.stream_stderr = stream_stderr
    if stream_indicator is not None and stream_indicator not in ("stream", "spinner", "none"):
        raise ValueError(f"Invalid stream indicator '{stream_indicator}'. Use 'stream', 'spinner', or 'none'.")
    cfg.stream_indicator = stream_indicator if stream_indicator is not None else "stream"

    # Sticky status line & stream line prefix
    if stream_status_line not in ("off", "bottom", "top"):
        raise ValueError(f"Invalid stream_status_line '{stream_status_line}'. Use 'off', 'bottom', or 'top'.")
    cfg.stream_status_line = stream_status_line
    if stream_line_prefix is None:
        stream_line_prefix = "auto"
    if stream_line_prefix not in ("auto", "agent", "stream", "none"):
        raise ValueError(f"Invalid stream_line_prefix '{stream_line_prefix}'. Use 'auto', 'agent', 'stream', or 'none'.")
    cfg.stream_line_prefix = stream_line_prefix
    cfg.show_prompts = show_prompts

    # Agent color output mode
    if agent_color_output is not None:
        if agent_color_output not in ("agent", "original", "none"):
            raise ValueError(f"Invalid agent_color_output '{agent_color_output}'. Use 'agent', 'original', or 'none'.")
        cfg.agent_color_output = agent_color_output
    elif env_agent_color:
        if env_agent_color not in ("agent", "original", "none"):
            raise ValueError(f"Invalid QQ_AGENT_COLOR_OUTPUT '{env_agent_color}'. Use 'agent', 'original', or 'none'.")
        cfg.agent_color_output = env_agent_color
    else:
        # From qq config or default to "agent"
        cfg.agent_color_output = spine_raw.get("agent_color_output", "agent")

    # Web dashboard — config < env < CLI
    web_raw = spine_raw.get("qq_web", {})
    if web_raw:
        cfg.qq_web = QqWebConfig(
            enabled=web_raw.get("enabled", True),
            start_with_run=web_raw.get("start_with_run", True),
            hard_fail_on_dashboard_error=web_raw.get("hard_fail_on_dashboard_error", False),
            host=web_raw.get("host", "0.0.0.0"),
            port=web_raw.get("port", 31337),
            open_browser=web_raw.get("open_browser", False),
            source_of_truth=web_raw.get("source_of_truth", "qonqrete"),
            mode=web_raw.get("mode", "local_read_model"),
            publish_level=web_raw.get("publish_level", "briq_group"),
            expose_briqs_as_subtasks=web_raw.get("expose_briqs_as_subtasks", True),
            allow_briq_level_tickets=web_raw.get("allow_briq_level_tickets", False),
            event_source_type=web_raw.get("event_source", {}).get("type", "events_jsonl"),
            poll_interval_ms=web_raw.get("event_source", {}).get("poll_interval_ms", 500),
            sse_enabled=web_raw.get("event_source", {}).get("sse_enabled", True),
            allow_create_epic_from_ui=web_raw.get("controls", {}).get("allow_create_epic_from_ui", False),
            allow_start_run_from_ui=web_raw.get("controls", {}).get("allow_start_run_from_ui", False),
            allow_pause_run_from_ui=web_raw.get("controls", {}).get("allow_pause_run_from_ui", False),
            allow_cancel_run_from_ui=web_raw.get("controls", {}).get("allow_cancel_run_from_ui", False),
            allow_manual_status_override=web_raw.get("controls", {}).get("allow_manual_status_override", False),
            product_name=web_raw.get("branding", {}).get("product_name", "briQsQope"),
            parent_product_name=web_raw.get("branding", {}).get("parent_product_name", "QonQrete"),
        )

    # Env overrides
    if os.environ.get("QQ_WEB_ENABLED"):
        cfg.qq_web.enabled = os.environ.get("QQ_WEB_ENABLED", "true").lower() in ("1", "true", "yes")
    if os.environ.get("QQ_WEB_HOST"):
        cfg.qq_web.host = os.environ["QQ_WEB_HOST"]
    if os.environ.get("QQ_WEB_PORT"):
        try:
            cfg.qq_web.port = int(os.environ["QQ_WEB_PORT"])
        except ValueError:
            pass
    if os.environ.get("QQ_WEB_OPEN_BROWSER"):
        cfg.qq_web.open_browser = os.environ.get("QQ_WEB_OPEN_BROWSER", "false").lower() in ("1", "true", "yes")
    if os.environ.get("QQ_WEB_PUBLISH_LEVEL"):
        cfg.qq_web.publish_level = os.environ["QQ_WEB_PUBLISH_LEVEL"]

    # CLI overrides
    if web_enabled is not None:
        cfg.qq_web.enabled = web_enabled
    if web_host is not None:
        cfg.qq_web.host = web_host
    if web_port is not None:
        cfg.qq_web.port = web_port
    if web_open_browser is not None:
        cfg.qq_web.open_browser = web_open_browser
    if web_publish_level is not None:
        cfg.qq_web.publish_level = web_publish_level
    if web_hard_fail is not None:
        cfg.qq_web.hard_fail_on_dashboard_error = web_hard_fail

    # paths
    cfg.repo_root = os.path.abspath(repo_root)
    cfg.run_root = run_root
    cfg.config_path = qq_path or _DEFAULT_QQ

    # Image backend routing.  Kept in qq.yaml so runs and `generate-image`
    # share exactly the same configuration.
    image_raw = spine_raw.get("image_backend", {}) or {}
    if isinstance(image_raw, dict):
        ib = cfg.image_backend
        ib.provider = str(image_raw.get("provider", "auto"))
        ib.model = str(image_raw.get("model", "auto"))
        for key in ("aspect_ratio", "resolution", "format", "quality", "style", "negative_prompt", "gradio_space"):
            if key in image_raw:
                setattr(ib, key, str(image_raw[key]))
        for key in ("cfg_scale",):
            if key in image_raw:
                setattr(ib, key, float(image_raw[key]))
        for key in ("steps", "seed"):
            if key in image_raw:
                setattr(ib, key, int(image_raw[key]))
        for key in ("safe_mode", "hide_watermark"):
            if key in image_raw:
                setattr(ib, key, bool(image_raw[key]))

    cfg.providers_config_path = providers_path or _DEFAULT_PROVIDERS

    # providers ref
    cfg.providers = providers

    # validate
    _validate_config(cfg, providers)

    return cfg


def _validate_config(cfg: QqConfig, providers: Dict[str, ProviderDef]) -> None:
    """Validate that provider exists and models are declared.

    Skip model validation for the mock provider — it accepts any model name.
    """
    # Raw mode + sticky status line is incompatible
    if cfg.stream_mode == "raw" and cfg.stream_status_line != "off":
        raise ValueError(
            "Sticky status line is not supported with raw stream mode "
            "because it emits terminal control sequences."
        )

    if cfg.provider not in providers:
        raise ValueError(
            f"Unknown provider '{cfg.provider}'. "
            f"Known: {sorted(providers)}. Check config/providers.yaml."
        )

    pd = providers[cfg.provider]
    if pd.status == "stub" and cfg.provider != "mock":
        raise ValueError(
            f"Provider '{cfg.provider}' is a stub (not implemented). "
            f"Use --dry-run or switch to 'codeseeq'."
        )

    # Model validation — skip for mock
    if cfg.provider == "mock":
        return

    if pd.models:
        for role, model in [
            ("qlarifier", cfg.model_qlarifier),
            ("instruqtor", cfg.model_instruqtor),
            ("construqtor", cfg.model_construqtor),
            ("inspeqtor", cfg.model_inspeqtor),
        ]:
            if model not in pd.models:
                raise ValueError(
                    f"Model '{model}' for {role} is not in provider "
                    f"'{cfg.provider}' declared model list: {pd.models}. "
                    f"Add it to {cfg.providers_config_path} or use a listed model."
                )
