use crate::events::TypedEvent;
use chrono::Utc;

/// Parsed command from the input box
#[derive(Debug, Clone)]
pub enum ParsedCommand {
    Help,
    Quit,
    Clear,
    Status,
    Debug,
    Run(String),
    RunPty(String),
    Shell(String),
    Theme,
    Ascii,
    Filter(String),
    Save(String),
    Replay(String),
    /// Not a command; user input being typed
    Text(String),
}

/// Parse a line from the input box
pub fn parse(input: &str) -> ParsedCommand {
    let trimmed = input.trim();
    if !trimmed.starts_with('/') {
        return ParsedCommand::Text(trimmed.to_string());
    }

    let (cmd, args) = match trimmed.find(' ') {
        Some(pos) => (&trimmed[1..pos], trimmed[pos + 1..].trim()),
        None => (&trimmed[1..], ""),
    };

    match cmd {
        "help" => ParsedCommand::Help,
        "quit" | "q" | "exit" => ParsedCommand::Quit,
        "clear" | "cls" => ParsedCommand::Clear,
        "status" | "stat" => ParsedCommand::Status,
        "debug" | "diag" => ParsedCommand::Debug,
        "run" => ParsedCommand::Run(args.to_string()),
        "run-pty" | "rpty" => ParsedCommand::RunPty(args.to_string()),
        "shell" | "sh" => ParsedCommand::Shell(args.to_string()),
        "theme" => ParsedCommand::Theme,
        "ascii" => ParsedCommand::Ascii,
        "filter" => ParsedCommand::Filter(args.to_string()),
        "save" => ParsedCommand::Save(args.to_string()),
        "replay" => ParsedCommand::Replay(args.to_string()),
        _ => ParsedCommand::Text(trimmed.to_string()),
    }
}

/// Convert a parsed command to a display event for the output view
pub fn command_to_event(cmd: &ParsedCommand) -> Option<TypedEvent> {
    let ts = Utc::now();
    match cmd {
        ParsedCommand::Help => Some(TypedEvent::SystemMessage {
            timestamp: ts,
            text: "Available commands: /help, /quit, /clear, /status, /debug, /run <cmd>, /run-pty <cmd>, /shell <cmd>, /theme, /ascii, /filter <text>, /save <path>, /replay <path>".into(),
        }),
        ParsedCommand::Clear => None, // handled in app directly
        ParsedCommand::Status => {
            Some(TypedEvent::StatusUpdate {
                timestamp: ts,
                text: "Status requested — use /debug for detailed status".into(),
            })
        }
        ParsedCommand::Debug => {
            Some(TypedEvent::Debug {
                timestamp: ts,
                text: "Opening diagnostics panel...".into(),
            })
        }
        ParsedCommand::Theme => Some(TypedEvent::SystemMessage {
            timestamp: ts,
            text: "Theme: qonqrete. Use --ascii flag for ASCII mode.".into(),
        }),
        ParsedCommand::Ascii => Some(TypedEvent::SystemMessage {
            timestamp: ts,
            text: "ASCII mode must be set at startup with --ascii flag.".into(),
        }),
        ParsedCommand::Text(ref t) => Some(TypedEvent::UserInput {
            timestamp: ts,
            text: t.clone(),
        }),
        ParsedCommand::Filter(ref f) => Some(TypedEvent::Debug {
            timestamp: ts,
            text: format!("Filter by: {}", f),
        }),
        ParsedCommand::Save(ref p) => Some(TypedEvent::SystemMessage {
            timestamp: ts,
            text: format!("Save requested to: {}", p),
        }),
        ParsedCommand::Replay(ref p) => Some(TypedEvent::SystemMessage {
            timestamp: ts,
            text: format!("Replay requested from: {}", p),
        }),
        _ => None, // Run/Shell handled by the application loop
    }
}
