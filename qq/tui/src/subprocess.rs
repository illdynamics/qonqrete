use crate::events::TypedEvent;
use chrono::Utc;
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use tokio::sync::mpsc;

use crate::messages::AppMessage;

/// Spawn a subprocess, capture stdout+stderr line by line, and send lines
/// as CommandOutput / CommandError events through the message channel.
#[allow(dead_code)]
pub async fn run_command(
    cmd_str: &str,
    tx: mpsc::UnboundedSender<AppMessage>,
) -> anyhow::Result<i32> {
    // Split into shell-like tokens (basic whitespace splitting)
    let parts: Vec<&str> = cmd_str.split_whitespace().collect();
    if parts.is_empty() {
        return Ok(0);
    }

    let program = parts[0];
    let args = &parts[1..];

    // Emit tool_start event
    let _ = tx.send(AppMessage::Event(TypedEvent::ToolStart {
        timestamp: Utc::now(),
        source: "shell".into(),
        text: cmd_str.to_string(),
    }));

    let mut child = Command::new(program)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| anyhow::anyhow!("Failed to spawn '{}': {}", cmd_str, e))?;

    let stdout = child.stdout.take().expect("stdout pipe");
    let stderr = child.stderr.take().expect("stderr pipe");

    let tx_out = tx.clone();
    let tx_err = tx.clone();

    // Read stdout lines in a blocking thread
    let stdout_handle = std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    let _ = tx_out.send(AppMessage::Event(TypedEvent::CommandOutput {
                        timestamp: Utc::now(),
                        text: l,
                    }));
                }
                Err(_) => break,
            }
        }
    });

    // Read stderr lines in a blocking thread
    let stderr_handle = std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    let _ = tx_err.send(AppMessage::Event(TypedEvent::CommandError {
                        timestamp: Utc::now(),
                        text: l,
                    }));
                }
                Err(_) => break,
            }
        }
    });

    stdout_handle.join().ok();
    stderr_handle.join().ok();

    let status = child.wait()?;
    let code = status.code();

    // Emit tool_end event
    let _ = tx.send(AppMessage::Event(TypedEvent::ToolEnd {
        timestamp: Utc::now(),
        source: "shell".into(),
        exit_code: code,
    }));

    Ok(code.unwrap_or(-1))
}
