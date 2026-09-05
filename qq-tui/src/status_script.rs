use crate::status::StatusState;
// use anyhow::Context;
use std::io::Write;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use strip_ansi_escapes::strip as strip_ansi;

/// Result of running the external statusline command
#[derive(Debug, Clone)]
pub struct StatuslineResult {
    pub line: String,
    pub success: bool,
    pub error: Option<String>,
    pub duration_ms: u64,
}

/// Run the external statusline command, passing session JSON on stdin.
/// Captures stdout (first line), applies timeout, sanitizes output,
/// falls back to empty on failure.
pub fn run_statusline(
    command: &str,
    state: &StatusState,
    timeout_ms: u64,
    allow_ansi: bool,
) -> StatuslineResult {
    let start = Instant::now();

    let json_input = state.to_statusline_json();
    let json_str = serde_json::to_string(&json_input).unwrap_or_else(|_| "{}".into());

    // Parse command into program + args
    let parts: Vec<&str> = command.split_whitespace().collect();
    if parts.is_empty() {
        return StatuslineResult {
            line: String::new(),
            success: false,
            error: Some("empty statusline command".into()),
            duration_ms: start.elapsed().as_millis() as u64,
        };
    }

    let program = parts[0];
    let args = &parts[1..];

    let mut child = match Command::new(program)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            return StatuslineResult {
                line: String::new(),
                success: false,
                error: Some(format!("spawn failed: {}", e)),
                duration_ms: start.elapsed().as_millis() as u64,
            };
        }
    };

    // Write JSON to stdin
    if let Some(mut stdin) = child.stdin.take() {
        if stdin.write_all(json_str.as_bytes()).is_err() {
            let _ = child.wait();
            return StatuslineResult {
                line: String::new(),
                success: false,
                error: Some("failed to write to statusline stdin".into()),
                duration_ms: start.elapsed().as_millis() as u64,
            };
        }
        // Close stdin so the command knows input is complete
        drop(stdin);
    }

    // Wait with timeout
    let timeout = Duration::from_millis(timeout_ms);
    let mut exit_success = false;

    // We need to do a blocking wait with timeout, and also read stdout
    // For simplicity, we use a short loop with try_wait + sleep
    // In a real production app this would use async I/O, but since the statusline
    // is expected to be fast (<300ms), a simple poll loop suffices.
    let mut waited = Duration::from_millis(0);
    let poll_step = Duration::from_millis(10);

    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                exit_success = status.success();
                break;
            }
            Ok(None) => {
                if waited >= timeout {
                    // Timeout — kill the child
                    let _ = child.kill();
                    let _ = child.wait();
                    break;
                }
                std::thread::sleep(poll_step);
                waited += poll_step;
            }
            Err(_) => break,
        }
    }

    let duration_ms = start.elapsed().as_millis() as u64;

    // Read captured stdout
    let output = match child.wait_with_output() {
        Ok(o) => o,
        Err(e) => {
            return StatuslineResult {
                line: String::new(),
                success: false,
                error: Some(format!("read output failed: {}", e)),
                duration_ms,
            };
        }
    };

    if !exit_success && !output.stdout.is_empty() {
        // Command failed but we may still have output — try to use it
    }

    if output.stdout.is_empty() {
        let stderr_msg = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return StatuslineResult {
            line: String::new(),
            success: false,
            error: if stderr_msg.is_empty() {
                Some("statusline produced no output".into())
            } else {
                Some(stderr_msg)
            },
            duration_ms,
        };
    }

    // Get first line of stdout
    let raw_output = String::from_utf8_lossy(&output.stdout);
    let first_line = raw_output.lines().next().unwrap_or("").trim().to_string();

    // Sanitize
    let line = if allow_ansi {
        first_line
    } else {
        // Strip ANSI escape sequences but keep printable characters
        let stripped = strip_ansi(first_line.as_bytes());
        String::from_utf8_lossy(&stripped).trim().to_string()
    };

    // Strip dangerous control codes (keep ANSI colors if allowed, but never
    // allow cursor movement)
    let line = sanitize_control_chars(&line);

    StatuslineResult {
        line,
        success: exit_success && !output.stdout.is_empty(),
        error: if exit_success || !output.stdout.is_empty() {
            None
        } else {
            Some(String::from_utf8_lossy(&output.stderr).trim().to_string())
        },
        duration_ms,
    }
}

/// Remove dangerous control sequences (cursor movement, screen manipulation)
/// while optionally preserving color codes
fn sanitize_control_chars(input: &str) -> String {
    // Remove common dangerous sequences:
    // - Cursor positioning (CSI ... H, CSI ... f)
    // - Cursor up/down/forward/back
    // - Save/restore cursor
    // - Clear screen/line
    // - Set scrolling region
    let mut result = String::with_capacity(input.len());
    let bytes = input.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == 0x1b && i + 1 < bytes.len() && bytes[i + 1] == b'[' {
            // CSI sequence — check the final byte
            let start = i;
            i += 2;
            while i < bytes.len() && !(0x40..=0x7e).contains(&bytes[i]) {
                i += 1;
            }
            if i < bytes.len() {
                let final_byte = bytes[i];
                match final_byte {
                    // 'm' = SGR (color) — permit
                    b'm' => {
                        result.push_str(&input[start..=i]);
                    }
                    // Everything else — strip (cursor movement, etc.)
                    _ => {
                        // skip
                    }
                }
                i += 1;
            }
        } else {
            result.push(bytes[i] as char);
            i += 1;
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_keeps_colors() {
        let input = "\x1b[31mred\x1b[0m";
        let out = sanitize_control_chars(input);
        assert_eq!(out, input);
    }

    #[test]
    fn test_sanitize_strips_cursor_movement() {
        let input = "\x1b[2J\x1b[H\x1b[10;5Htext";
        let out = sanitize_control_chars(input);
        assert_eq!(out, "text");
    }
}
