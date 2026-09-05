use clap::{Parser, Subcommand};

/// qq-tui — QonQrete-style terminal UI framework for agent sessions
#[derive(Parser, Debug)]
#[command(name = "qq-tui", version, about, long_about = None)]
pub struct Cli {
    /// Agent name shown in the status bar
    #[arg(long, env = "QQ_AGENT_NAME")]
    pub agent: Option<String>,

    /// Model code shown in the status bar
    #[arg(long, env = "QQ_AGENT_MODEL_CODE")]
    pub model: Option<String>,

    /// Budget shown in the status bar
    #[arg(long, env = "QQ_B")]
    pub budget: Option<u64>,

    /// Initial progress percentage
    #[arg(long, env = "QQ_P")]
    pub progress: Option<f64>,

    /// Path to config file
    #[arg(long, env = "QQ_TUI_CONFIG")]
    pub config: Option<String>,

    /// Path to statusline command
    #[arg(long, env = "QQ_STATUSLINE_COMMAND")]
    pub status_command: Option<String>,

    /// Path to write JSONL events
    #[arg(long, env = "QQ_EVENTS_OUT")]
    pub events_out: Option<String>,

    /// Force ASCII mode (no Unicode)
    #[arg(long, env = "QQ_TUI_ASCII")]
    pub ascii: bool,

    /// Disable all color
    #[arg(long, env = "QQ_TUI_NO_COLOR")]
    pub no_color: bool,

    /// Debug log file path
    #[arg(long, env = "QQ_DEBUG_LOG")]
    pub debug_log: Option<String>,

    /// Spinner refresh interval in ms
    #[arg(long)]
    pub refresh_ms: Option<u64>,

    /// Status bar refresh interval in ms
    #[arg(long)]
    pub status_refresh_ms: Option<u64>,

    /// Top-level command / operating mode
    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// Replay a saved JSONL event stream in the UI
    Replay {
        /// Path to JSONL events file
        events_jsonl: String,

        /// Agent name
        #[arg(long)]
        agent: Option<String>,

        /// Model code
        #[arg(long)]
        model: Option<String>,

        /// Force ASCII mode
        #[arg(long)]
        ascii: bool,

        /// Disable color
        #[arg(long)]
        no_color: bool,

        /// Config file path
        #[arg(long)]
        config: Option<String>,
    },

    /// Run a child command inside the full TUI with live output capture
    /// and QonQrete event file tailing
    Run {
        /// Path to QonQrete events.jsonl to tail for status updates
        #[arg(long)]
        qq_events: Option<String>,

        /// Exit TUI automatically when the child process finishes
        #[arg(long, default_value_t = false)]
        exit_when_done: bool,

        /// Agent name
        #[arg(long)]
        agent: Option<String>,

        /// Model code (fla, fla-T, pro, pro-T)
        #[arg(long)]
        model: Option<String>,

        /// Command and its arguments (after --)
        #[arg(trailing_var_arg = true, required = true)]
        command: Vec<String>,
    },

    /// Run a command non-interactively (no TUI)
    Exec {
        /// Command and its arguments
        #[arg(trailing_var_arg = true, required = true)]
        command: Vec<String>,
    },

    /// Test a statusline command with sample JSON
    StatuslineTest {
        /// Path to statusline command/script
        command: String,
    },
}

impl Cli {
    /// Check if any mode that requires TUI is active
    #[allow(dead_code)]

    pub fn needs_tui(&self) -> bool {
        match &self.command {
            Some(Commands::Exec { .. }) => false,
            Some(Commands::StatuslineTest { .. }) => false,
            _ => true,
        }
    }
}
