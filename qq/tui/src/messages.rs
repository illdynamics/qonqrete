use crate::events::TypedEvent;
use crate::qq_events::AgentRole;
use std::collections::HashMap;
use tokio::sync::mpsc;

/// Application-level message passing channels
#[derive(Debug)]
#[allow(dead_code)]
pub enum AppMessage {
    /// A new typed event to display in the output view
    Event(TypedEvent),
    /// Raw child process stdout line (for TUI child-run mode)
    ChildStdout(String),
    /// Raw child process stderr line (for TUI child-run mode)
    ChildStderr(String),
    /// Child process PID for signal handling
    ChildPid(u32),
    /// Child process has exited
    ChildExited(i32),
    /// Interrupt child process (Ctrl+C first press, ESC)
    ChildInterrupt,
    /// Force-quit the TUI (Ctrl+C second press)
    ForceQuit,
    /// Request to run a subprocess command
    RunCommand(String),
    /// Request to run a PTY subprocess command
    RunPtyCommand(String),
    /// Request to quit the application
    Quit,
    /// Clear the output view
    Clear,
    /// Toggle auto-scroll
    ToggleAutoScroll,
    /// Force redraw
    Redraw,
    /// Show diagnostics
    ShowDiagnostics,
    /// Show help
    ShowHelp,
    /// Status bar update tick
    StatusTick,
    /// Spinner tick
    SpinnerTick,
    // ── QonQrete event messages ──
    /// Models config from config.loaded (role → model mapping)
    QqConfig { models: HashMap<String, String> },
    /// Active agent changed (role name)
    QqActiveAgent(String),
    /// Active agent changed with model info
    QqActiveAgentWithModel { role: String, model: Option<String> },
    /// An agent has finished its call
    QqAgentDone(AgentRole),
    /// An agent has started a call
    QqAgentRunning(AgentRole),
    /// An agent call failed
    QqAgentFailed(AgentRole),
    /// Model code update
    QqModel(String),
    /// Max cycles update
    QqMaxCycles(u64),
    /// Cycle number update
    QqCycle(u64),
    /// Progress/score percentage
    QqProgress(f64),
    /// Phase label
    QqPhase(String),
    /// Exit code
    QqExitCode(i32),
    /// Action status text (from action_status_changed events)
    QqActionStatus(String),
    /// Exit status symbol
    QqExitSymbol(String),
    /// Agent output byte counts
    QqAgentOutputBytes {
        role: String,
        stdout: u64,
        stderr: u64,
    },
    /// A build group completed (with total groups count so far)
    QqBuildGroupCompleted { groups_done: u64, total_groups: u64 },
    /// Total groups known (from plan)
    QqTotalGroups(u64),
    /// Total briQs known
    QqTotalBriQs(u64),
    /// A briQ completed
    QqBriQCompleted,
}

/// Channel capacity
#[allow(dead_code)]
pub const CHANNEL_CAPACITY: usize = 4096;

/// Create a message channel pair
pub fn channel() -> (mpsc::UnboundedSender<AppMessage>, mpsc::UnboundedReceiver<AppMessage>) {
    mpsc::unbounded_channel()
}
