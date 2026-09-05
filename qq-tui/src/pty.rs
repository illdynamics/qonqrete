use crate::events::TypedEvent;
use crate::messages::AppMessage;
use chrono::Utc;
use tokio::sync::mpsc;

/// PTY mode placeholder. This will spawn a command with a pseudo-terminal
/// and stream output into the TUI.
/// For now, we fall back to regular subprocess spawning and note that PTY
/// support requires the `portable-pty` crate which has platform-specific
/// details. The architecture is planned but the implementation is a
/// deferred feature.
#[allow(dead_code)]
pub async fn run_pty_command(
    cmd_str: &str,
    tx: mpsc::UnboundedSender<AppMessage>,
) -> anyhow::Result<i32> {
    // Emit a notice that PTY mode is not yet fully implemented,
    // then fall back to regular subprocess capture.
    let _ = tx.send(AppMessage::Event(TypedEvent::Debug {
        timestamp: Utc::now(),
        text: format!("PTY mode requested but not fully implemented — falling back to pipe mode: {}", cmd_str),
    }));

    // Delegate to subprocess module
    crate::subprocess::run_command(cmd_str, tx).await
}
