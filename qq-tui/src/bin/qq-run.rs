//! qq-run — lightweight non-TTY subprocess runner for qq-tui exec mode.
//!
//! Usage: qq-run [--jsonl] -- <command> [args...]

use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use chrono::Utc;

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let mut jsonl_mode = false;
    let mut cmd_start = 1;

    for (i, arg) in args.iter().enumerate().skip(1) {
        if arg == "--jsonl" {
            jsonl_mode = true;
            cmd_start = i + 1;
        } else if arg == "--" {
            cmd_start = i + 1;
            break;
        }
    }

    if cmd_start >= args.len() {
        eprintln!("Usage: qq-run [--jsonl] -- <command> [args...]");
        std::process::exit(1);
    }

    let program = &args[cmd_start];
    let cmd_args = &args[cmd_start + 1..];

    let mut child = Command::new(program)
        .args(cmd_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;

    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();

    // Read and emit stdout
    let stdout_reader = BufReader::new(stdout);
    for line in stdout_reader.lines() {
        match line {
            Ok(l) => {
                if jsonl_mode {
                    let ev = serde_json::json!({
                        "type": "command_output",
                        "timestamp": Utc::now().to_rfc3339(),
                        "text": l
                    });
                    println!("{}", serde_json::to_string(&ev)?);
                } else {
                    println!("{}", l);
                }
            }
            Err(_) => break,
        }
    }

    // Read and emit stderr
    let stderr_reader = BufReader::new(stderr);
    for line in stderr_reader.lines() {
        match line {
            Ok(l) => {
                if jsonl_mode {
                    let ev = serde_json::json!({
                        "type": "command_error",
                        "timestamp": Utc::now().to_rfc3339(),
                        "text": l
                    });
                    eprintln!("{}", serde_json::to_string(&ev)?);
                } else {
                    eprintln!("{}", l);
                }
            }
            Err(_) => break,
        }
    }

    let status = child.wait()?;
    if jsonl_mode {
        let ev = serde_json::json!({
            "type": "tool_end",
            "timestamp": Utc::now().to_rfc3339(),
            "exit_code": status.code()
        });
        println!("{}", serde_json::to_string(&ev)?);
    }

    std::process::exit(status.code().unwrap_or(1));
}
