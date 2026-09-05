use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use uuid::Uuid;

/// Structured event for everything displayed in the captured output view
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub timestamp: DateTime<Utc>,
    #[serde(default)]
    pub level: EventLevel,
    #[serde(default)]
    pub source: String,
    pub text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum EventLevel {
    #[default]
    Info,
    Debug,
    Warn,
    Error,
}

/// Discriminated event type for typed matching
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum TypedEvent {
    #[serde(rename = "user_input")]
    UserInput { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "assistant_message")]
    AssistantMessage { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "tool_start")]
    ToolStart { timestamp: DateTime<Utc>, source: String, text: String },
    #[serde(rename = "tool_output")]
    ToolOutput { timestamp: DateTime<Utc>, source: String, text: String },
    #[serde(rename = "tool_error")]
    ToolError { timestamp: DateTime<Utc>, source: String, text: String },
    #[serde(rename = "tool_end")]
    ToolEnd { timestamp: DateTime<Utc>, source: String, exit_code: Option<i32> },
    #[serde(rename = "system_message")]
    SystemMessage { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "status_update")]
    StatusUpdate { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "command_output")]
    CommandOutput { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "command_error")]
    CommandError { timestamp: DateTime<Utc>, text: String },
    #[serde(rename = "debug")]
    Debug { timestamp: DateTime<Utc>, text: String },
}

impl TypedEvent {
    pub fn timestamp(&self) -> DateTime<Utc> {
        match self {
            TypedEvent::UserInput { timestamp, .. }
            | TypedEvent::AssistantMessage { timestamp, .. }
            | TypedEvent::ToolStart { timestamp, .. }
            | TypedEvent::ToolOutput { timestamp, .. }
            | TypedEvent::ToolError { timestamp, .. }
            | TypedEvent::ToolEnd { timestamp, .. }
            | TypedEvent::SystemMessage { timestamp, .. }
            | TypedEvent::StatusUpdate { timestamp, .. }
            | TypedEvent::CommandOutput { timestamp, .. }
            | TypedEvent::CommandError { timestamp, .. }
            | TypedEvent::Debug { timestamp, .. } => *timestamp,
        }
    }

    pub fn to_generic_event(&self) -> Event {
        let (level, source, text) = match self {
            TypedEvent::UserInput { text, .. } => (EventLevel::Info, "user".into(), text.clone()),
            TypedEvent::AssistantMessage { text, .. } => {
                (EventLevel::Info, "assistant".into(), text.clone())
            }
            TypedEvent::ToolStart { source, text, .. } => {
                (EventLevel::Info, source.clone(), text.clone())
            }
            TypedEvent::ToolOutput { source, text, .. } => {
                (EventLevel::Info, source.clone(), text.clone())
            }
            TypedEvent::ToolError { source, text, .. } => {
                (EventLevel::Error, source.clone(), text.clone())
            }
            TypedEvent::ToolEnd { source, exit_code, .. } => (
                EventLevel::Info,
                source.clone(),
                format!("exit_code={:?}", exit_code),
            ),
            TypedEvent::SystemMessage { text, .. } => {
                (EventLevel::Info, "system".into(), text.clone())
            }
            TypedEvent::StatusUpdate { text, .. } => {
                (EventLevel::Debug, "status".into(), text.clone())
            }
            TypedEvent::CommandOutput { text, .. } => {
                (EventLevel::Info, "cmd".into(), text.clone())
            }
            TypedEvent::CommandError { text, .. } => {
                (EventLevel::Error, "cmd".into(), text.clone())
            }
            TypedEvent::Debug { text, .. } => (EventLevel::Debug, "debug".into(), text.clone()),
        };

        Event {
            id: Uuid::new_v4().to_string(),
            timestamp: self.timestamp(),
            level,
            source,
            text,
            metadata: None,
        }
    }
}

/// Append-only JSONL event writer
#[allow(dead_code)]
pub struct EventWriter {
    file: Option<File>,
    #[allow(dead_code)]
    path: Option<PathBuf>,
}

impl EventWriter {
    pub fn new(path: Option<PathBuf>) -> Self {
        let file = if let Some(ref p) = path {
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(p)
                .ok()
        } else {
            None
        };
        Self { file, path }
    }

    pub fn write_typed(&mut self, event: &TypedEvent) {
        if let Some(ref mut f) = self.file {
            if let Ok(line) = serde_json::to_string(event) {
                let _ = writeln!(f, "{}", line);
                let _ = f.flush(); // Safety-first: flush after each event
            }
        }
    }

    #[allow(dead_code)]
    pub fn write_event(&mut self, event: &Event) {
        if let Some(ref mut f) = self.file {
            if let Ok(line) = serde_json::to_string(event) {
                let _ = writeln!(f, "{}", line);
                let _ = f.flush();
            }
        }
    }

    #[allow(dead_code)]
    pub fn is_enabled(&self) -> bool {
        self.file.is_some()
    }
}

/// JSONL event reader for replay mode
pub struct EventReader {
    path: PathBuf,
}

impl EventReader {
    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }

    pub fn read_all(&self) -> anyhow::Result<Vec<TypedEvent>> {
        let f = File::open(&self.path)?;
        let reader = BufReader::new(f);
        let mut events = Vec::new();
        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<TypedEvent>(&line) {
                Ok(ev) => events.push(ev),
                Err(e) => {
                    // Log parse error but continue
                    eprintln!("qq-tui: JSONL parse error (skipping line): {}", e);
                }
            }
        }
        Ok(events)
    }
}
