use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Full application configuration with precedence: CLI > env > file > defaults
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    #[serde(default)]
    pub agent: AgentConfig,
    #[serde(default)]
    pub ui: UiConfig,
    #[serde(default)]
    pub statusline: StatuslineConfig,
    #[serde(default)]
    pub events: EventsConfig,
    #[serde(default)]
    pub keys: KeysConfig,
    /// Path the config was loaded from (for display in diagnostics)
    #[serde(skip)]
    pub config_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    #[serde(default = "default_agent_name")]
    pub name: String,
    #[serde(default = "default_model")]
    pub model: String,
    #[serde(default = "default_budget")]
    pub budget: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UiConfig {
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default)]
    pub ascii: bool,
    #[serde(default = "default_true")]
    pub color: bool,
    #[serde(default = "default_spinner_refresh_ms")]
    pub spinner_refresh_ms: u64,
    #[serde(default = "default_status_refresh_ms")]
    pub status_refresh_ms: u64,
    #[serde(default = "default_true")]
    pub show_borders: bool,
    #[serde(default = "default_status_position")]
    pub status_position: String,
    /// TUI version string (e.g. "0.2.24"), set from CARGO_PKG_VERSION at build time
    #[serde(default = "default_version")]
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatuslineConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub command: Option<String>,
    #[serde(default = "default_status_refresh_ms")]
    pub refresh_interval_ms: u64,
    #[serde(default = "default_statusline_timeout_ms")]
    pub timeout_ms: u64,
    #[serde(default)]
    pub allow_ansi: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventsConfig {
    #[serde(default)]
    pub write_jsonl: bool,
    #[serde(default = "default_events_path")]
    pub path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeysConfig {
    #[serde(default = "default_key_quit")]
    pub quit: String,
    #[serde(default = "default_key_command_palette")]
    pub command_palette: String,
    #[serde(default = "default_key_help")]
    pub help: String,
}

// ─── Defaults ───

fn default_agent_name() -> String {
    "Qlarifier".into()
}
fn default_model() -> String {
    "?".into()
}
fn default_budget() -> u64 {
    26
}
fn default_theme() -> String {
    "qonqrete".into()
}
fn default_true() -> bool {
    true
}
fn default_spinner_refresh_ms() -> u64 {
    120
}
fn default_status_refresh_ms() -> u64 {
    1000
}
fn default_statusline_timeout_ms() -> u64 {
    300
}
fn default_status_position() -> String {
    "top".into()
}

fn default_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}
fn default_events_path() -> Option<String> {
    None
}
fn default_key_quit() -> String {
    "ctrl-c".into()
}
fn default_key_command_palette() -> String {
    "ctrl-p".into()
}
fn default_key_help() -> String {
    "?".into()
}


impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            name: default_agent_name(),
            model: default_model(),
            budget: default_budget(),
        }
    }
}

impl Default for UiConfig {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            ascii: false,
            color: true,
            spinner_refresh_ms: default_spinner_refresh_ms(),
            status_refresh_ms: default_status_refresh_ms(),
            show_borders: true,
            status_position: default_status_position(),
            version: default_version(),
        }
    }
}

impl Default for StatuslineConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            command: None,
            refresh_interval_ms: default_status_refresh_ms(),
            timeout_ms: default_statusline_timeout_ms(),
            allow_ansi: false,
        }
    }
}

impl Default for EventsConfig {
    fn default() -> Self {
        Self {
            write_jsonl: false,
            path: default_events_path(),
        }
    }
}

impl Default for KeysConfig {
    fn default() -> Self {
        Self {
            quit: default_key_quit(),
            command_palette: default_key_command_palette(),
            help: default_key_help(),
        }
    }
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            agent: AgentConfig {
                name: default_agent_name(),
                model: default_model(),
                budget: default_budget(),
            },
            ui: UiConfig {
                theme: default_theme(),
                ascii: false,
                color: true,
                spinner_refresh_ms: default_spinner_refresh_ms(),
                status_refresh_ms: default_status_refresh_ms(),
                show_borders: true,
                status_position: default_status_position(),
                version: default_version(),
            },
            statusline: StatuslineConfig {
                enabled: false,
                command: None,
                refresh_interval_ms: default_status_refresh_ms(),
                timeout_ms: default_statusline_timeout_ms(),
                allow_ansi: false,
            },
            events: EventsConfig {
                write_jsonl: false,
                path: default_events_path(),
            },
            keys: KeysConfig {
                quit: default_key_quit(),
                command_palette: default_key_command_palette(),
                help: default_key_help(),
            },
            config_path: None,
        }
    }
}

impl AppConfig {
    /// Load config from file, then override with environment variables.
    pub fn load(config_path: Option<&str>) -> Result<Self> {
        let mut cfg = AppConfig::default();

        // 1. Load from file if given or default path
        let resolved_path = if let Some(p) = config_path {
            let pb = shellexpand_path(p);
            cfg.config_path = Some(pb.clone());
            pb
        } else {
            let default_path = default_config_path();
            if default_path.exists() {
                cfg.config_path = Some(default_path.clone());
                default_path
            } else {
                // No config file found; proceed with defaults + env
                return Ok(Self::apply_env(cfg));
            }
        };

        let contents =
            std::fs::read_to_string(&resolved_path).context("Failed to read config file")?;
        let file_cfg: AppConfig =
            toml::from_str(&contents).context("Failed to parse config file")?;

        // Merge file config over defaults
        cfg.agent = file_cfg.agent;
        cfg.ui = file_cfg.ui;
        cfg.statusline = file_cfg.statusline;
        cfg.events = file_cfg.events;
        cfg.keys = file_cfg.keys;
        // Keep config_path from resolution

        Ok(Self::apply_env(cfg))
    }

    /// Apply environment variable overrides
    fn apply_env(mut cfg: Self) -> Self {
        if let Ok(v) = std::env::var("QQ_AGENT_NAME") {
            cfg.agent.name = v;
        }
        if let Ok(v) = std::env::var("QQ_AGENT_MODEL_CODE") {
            cfg.agent.model = v;
        }
        if let Ok(v) = std::env::var("QQ_B") {
            if let Ok(n) = v.parse() {
                cfg.agent.budget = n;
            }
        }
        if let Ok(v) = std::env::var("QQ_P") {
            // progress can be set but it's dynamic; we store it in the status
            // rather than config, but we note the env exists
            let _ = v;
        }
        if let Ok(v) = std::env::var("QQ_TUI_THEME") {
            cfg.ui.theme = v;
        }
        if let Ok(_) = std::env::var("QQ_TUI_ASCII") {
            cfg.ui.ascii = true;
        }
        if let Ok(_) = std::env::var("QQ_TUI_NO_COLOR") {
            cfg.ui.color = false;
        }
        if let Ok(v) = std::env::var("QQ_STATUSLINE_COMMAND") {
            cfg.statusline.enabled = true;
            cfg.statusline.command = Some(v);
        }
        if let Ok(v) = std::env::var("QQ_STATUSLINE_REFRESH_MS") {
            if let Ok(n) = v.parse() {
                cfg.statusline.refresh_interval_ms = n;
            }
        }
        if let Ok(v) = std::env::var("QQ_EVENTS_OUT") {
            cfg.events.write_jsonl = true;
            cfg.events.path = Some(v);
        }
        cfg
    }
}

fn default_config_path() -> PathBuf {
    shellexpand_path("~/.config/qq-tui/config.toml")
}

pub fn shellexpand_path(raw: &str) -> PathBuf {
    if raw.starts_with('~') {
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(raw.replacen('~', &home, 1));
        }
    }
    PathBuf::from(raw)
}

/// Determine whether to use ASCII mode
pub fn should_use_ascii(cfg: &AppConfig, cli_ascii: bool) -> bool {
    if cli_ascii {
        return true;
    }
    if cfg.ui.ascii {
        return true;
    }
    if let Ok(term) = std::env::var("TERM") {
        if term == "dumb" {
            return true;
        }
    }
    false
}

/// Determine if we are running in a TTY
pub fn is_tty() -> bool {
    crossterm::tty::IsTty::is_tty(&std::io::stdout())
        && crossterm::tty::IsTty::is_tty(&std::io::stdin())
}
