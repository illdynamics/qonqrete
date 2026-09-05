/// Python QonQrete event-log tailer.
use serde::Deserialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Seek, SeekFrom};
use std::path::PathBuf;
use std::time::Duration;
use tokio::sync::mpsc;

use crate::messages::AppMessage;

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct QqRuntimeEvent {
    pub ts: Option<f64>,
    #[serde(rename = "type")]
    pub event_type: String,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub call_id: Option<String>,
    #[serde(default)]
    pub previous_role: Option<String>,
    #[serde(default)]
    pub max_cycles: Option<u64>,
    #[serde(default)]
    pub models: Option<HashMap<String, String>>,
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub cycle: Option<u64>,
    #[serde(default)]
    pub score: Option<f64>,
    #[serde(default)]
    pub exit_code: Option<i32>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub action_status: Option<String>,
    #[serde(default)]
    pub stdout_bytes: Option<u64>,
    #[serde(default)]
    pub stderr_bytes: Option<u64>,
    #[serde(default)]
    pub chunks: Option<u64>,
    #[serde(default)]
    pub phase: Option<String>,
    #[serde(default)]
    pub provider: Option<String>,
    #[serde(default)]
    pub stream_agent_output: Option<bool>,
    #[serde(default)]
    pub verdict: Option<String>,
    // build_group fields
    #[serde(default)]
    pub build_group_id: Option<String>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub total_groups: Option<u64>,
    #[serde(default)]
    pub groups_done: Option<u64>,
    #[serde(default)]
    pub briq_id: Option<String>,
    // Backend-provided displayed progress (effective_progress_pct / displayed_pct)
    // so the TUI shows the same integer the web dashboard reads at the same moment.
    #[serde(default)]
    pub effective_progress_pct: Option<f64>,
    #[serde(default)]
    pub displayed_pct: Option<f64>,
    #[serde(flatten)]
    pub extra: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AgentRole {
    Qlarifier,
    InstruQtor,
    ConstruQtor,
    InspeQtor,
}

impl AgentRole {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "qlarifier" | "qlorifier" => Some(AgentRole::Qlarifier),
            "instruqtor" => Some(AgentRole::InstruQtor),
            "construqtor" => Some(AgentRole::ConstruQtor),
            "inspeqtor" => Some(AgentRole::InspeQtor),
            _ => None,
        }
    }

    #[allow(dead_code)]
    pub fn display_name(&self) -> &'static str {
        match self {
            AgentRole::Qlarifier => "Qlarifier",
            AgentRole::InstruQtor => "instruQtor",
            AgentRole::ConstruQtor => "construQtor",
            AgentRole::InspeQtor => "inspeQtor",
        }
    }

    #[allow(dead_code)]
    pub fn short_name(&self) -> &'static str {
        match self {
            AgentRole::Qlarifier => "Ql",
            AgentRole::InstruQtor => "In",
            AgentRole::ConstruQtor => "Cn",
            AgentRole::InspeQtor => "Ip",
        }
    }
}

/// Backend-provided displayed progress percent, if the event carries it
/// (effective_progress_pct preferred, then displayed_pct). This is the same
/// `displayed_pct` that qq/progress.py feeds the web read-model, so the TUI
/// shows the same integer as the web dashboard at the same moment.
impl QqRuntimeEvent {
    fn backend_progress_pct(&self) -> Option<f64> {
        self.effective_progress_pct.or(self.displayed_pct)
    }
}

/// Map a Python QonQrete event type to one or more `AppMessage`s.
pub fn event_to_messages(event: &QqRuntimeEvent) -> Vec<AppMessage> {
    let mut msgs = Vec::new();

    match event.event_type.as_str() {
        "config.loaded" => {
            if let Some(ref models) = event.models {
                let m: HashMap<String, String> = models
                    .iter()
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                msgs.push(AppMessage::QqConfig { models: m });
            }
            if let Some(mc) = event.max_cycles {
                msgs.push(AppMessage::QqMaxCycles(mc));
            }
            msgs.push(AppMessage::QqPhase("configured".into()));
        }

        "active_agent_changed" => {
            let role = event.role.clone().unwrap_or_default();
            let model = event.model.clone();
            msgs.push(AppMessage::QqActiveAgentWithModel {
                role: role.clone(),
                model: model.clone(),
            });
            // Also send the simple version for backward compat
            msgs.push(AppMessage::QqActiveAgent(role.clone()));
            if let Some(model) = model {
                msgs.push(AppMessage::QqModel(model));
            }
            if let Some(prev) = &event.previous_role {
                if let Some(r) = AgentRole::from_str(prev) {
                    msgs.push(AppMessage::QqAgentDone(r));
                }
            }
            if let Some(r) = AgentRole::from_str(&role) {
                msgs.push(AppMessage::QqAgentRunning(r));
            }
        }

        "agent.call.started" => {
            let role = event.role.clone().unwrap_or_default();
            if let Some(model) = &event.model {
                msgs.push(AppMessage::QqModel(model.clone()));
            }
            msgs.push(AppMessage::QqActiveAgent(role.clone()));
            if let Some(r) = AgentRole::from_str(&role) {
                msgs.push(AppMessage::QqAgentRunning(r));
            }
        }

        "agent.call.finished" => {
            let role = event.role.clone().unwrap_or_default();
            if let Some(r) = AgentRole::from_str(&role) {
                msgs.push(AppMessage::QqAgentDone(r));
            }
            if let Some(code) = event.exit_code {
                msgs.push(AppMessage::QqExitCode(code));
            }
            if let Some(stdout) = event.stdout_bytes {
                msgs.push(AppMessage::QqAgentOutputBytes {
                    role,
                    stdout,
                    stderr: event.stderr_bytes.unwrap_or(0),
                });
            }
        }

        "agent.call.failed" => {
            let role = event.role.clone().unwrap_or_default();
            if let Some(r) = AgentRole::from_str(&role) {
                msgs.push(AppMessage::QqAgentFailed(r));
            }
        }

        "review.verdict" => {
            if let Some(bpct) = event.backend_progress_pct() {
                msgs.push(AppMessage::QqProgress(bpct));
            } else if let Some(score) = event.score {
                msgs.push(AppMessage::QqProgress(score));
            }
            if let Some(verdict) = &event.verdict {
                match verdict.as_str() {
                    "FULLY_DONE" => {
                        msgs.push(AppMessage::QqPhase("fully-done".into()));
                        msgs.push(AppMessage::QqProgress(100.0));
                        // TUI-BGP10: surface FULLY_DONE in the Act: status so it does
                        // not hang on 'Evaluating the result' at successful completion.
                        msgs.push(AppMessage::QqActionStatus("FULLY_DONE".into()));
                    }
                    "NOT_DONE" => {
                        msgs.push(AppMessage::QqPhase("not-done".into()));
                    }
                    _ => {}
                }
            }
            if let Some(cycle) = event.cycle {
                msgs.push(AppMessage::QqCycle(cycle));
            }
        }

        "inspection_score_recorded" => {
            if let Some(bpct) = event.backend_progress_pct() {
                msgs.push(AppMessage::QqProgress(bpct));
            } else if let Some(score) = event.score {
                msgs.push(AppMessage::QqProgress(score));
            }
        }

        "build_group.completed" => {
            if let Some(groups_done) = event.groups_done {
                if let Some(total_groups) = event.total_groups {
                    msgs.push(AppMessage::QqBuildGroupCompleted { groups_done, total_groups });
                }
            }
            // Prefer the backend-provided displayed_pct; otherwise compute from
            // groups_done/total when the field is absent.
            if let Some(bpct) = event.backend_progress_pct() {
                msgs.push(AppMessage::QqProgress(bpct));
            } else if let (Some(done), Some(total)) = (event.groups_done, event.total_groups) {
                if total > 0 {
                    let pct = (done as f64 / total as f64) * 100.0;
                    msgs.push(AppMessage::QqProgress(pct));
                }
            }
            if let Some(cycle) = event.cycle {
                msgs.push(AppMessage::QqCycle(cycle));
            }
        }

        "build_group.started" => {
            if let Some(total_groups) = event.total_groups {
                msgs.push(AppMessage::QqTotalGroups(total_groups));
            }
            msgs.push(AppMessage::QqPhase("building".into()));
        }

        "plan.created" => {
            msgs.push(AppMessage::QqPhase("planned".into()));
            if let Some(total) = event.total_groups {
                msgs.push(AppMessage::QqTotalGroups(total));
            }
            // Try to extract total briqs count from plan data
            if let Some(plan) = event.extra.get("plan") {
                if let Some(briqs) = plan.get("briqs") {
                    if let Some(briqs_obj) = briqs.as_object() {
                        msgs.push(AppMessage::QqTotalBriQs(briqs_obj.len() as u64));
                    }
                }
            }
        }

        "briq.status_changed" => {
            let status = event.status.clone().unwrap_or_default();
            match status.as_str() {
                "done" | "completed" | "valid_done" | "fully_done" | "success" | "merged" => {
                    msgs.push(AppMessage::QqBriQCompleted);
                }
                "in_progress" | "building" => {
                    if let Some(role) = event.role.as_ref() {
                        if let Some(r) = AgentRole::from_str(role) {
                            msgs.push(AppMessage::QqAgentRunning(r));
                        }
                    }
                }
                "failed" | "needs_repair" => {
                    msgs.push(AppMessage::QqPhase("repair-needed".into()));
                }
                _ => {}
            }
        }

        "last_exit_status_updated" => {
            if let Some(code) = event.exit_code {
                msgs.push(AppMessage::QqExitCode(code));
            }
            if let Some(symbol) = &event.symbol {
                msgs.push(AppMessage::QqExitSymbol(symbol.clone()));
            }
        }

        "run.started" => {
            msgs.push(AppMessage::QqPhase("running".into()));
            if let Some(mc) = event.max_cycles {
                msgs.push(AppMessage::QqMaxCycles(mc));
            }
        }

        "harness.started" => {
            msgs.push(AppMessage::QqPhase("harnessing".into()));
        }
        "harness.completed" => {
            msgs.push(AppMessage::QqPhase("harness-ok".into()));
        }
        "harness.failed" => {
            msgs.push(AppMessage::QqPhase("harness-failed".into()));
        }

        "run.completed" => {
            msgs.push(AppMessage::QqPhase("done".into()));
            msgs.push(AppMessage::QqProgress(100.0));
            // TUI-BGP10: NORMALIZE the Act: status to FULLY_DONE on completion so the
            // bar never lingers on 'Evaluating the result' while Total freezes.
            msgs.push(AppMessage::QqActionStatus("FULLY_DONE".into()));
            for role in &[
                AgentRole::Qlarifier,
                AgentRole::InstruQtor,
                AgentRole::ConstruQtor,
                AgentRole::InspeQtor,
            ] {
                msgs.push(AppMessage::QqAgentDone(*role));
            }
        }

        "run.aborted" => {
            msgs.push(AppMessage::QqPhase("aborted".into()));
            msgs.push(AppMessage::QqExitCode(1));
        }

        "run.failed" => {
            msgs.push(AppMessage::QqPhase("failed".into()));
            msgs.push(AppMessage::QqExitCode(1));
        }

        "clarification.done" => {
            msgs.push(AppMessage::QqPhase("clarified".into()));
        }

        "clarification.questioned" => {
            msgs.push(AppMessage::QqPhase("clarifying".into()));
        }

        "stream_activity_updated" => {
            let role = event.role.clone().unwrap_or_default();
            if let Some(stdout) = event.stdout_bytes {
                msgs.push(AppMessage::QqAgentOutputBytes {
                    role,
                    stdout,
                    stderr: event.stderr_bytes.unwrap_or(0),
                });
            }
        }

        "repair.started" => {
            msgs.push(AppMessage::QqPhase("repairing".into()));
        }

        "repair.completed" => {
            msgs.push(AppMessage::QqPhase("repair-ok".into()));
        }

        "action_status_changed" => {
            if let Some(action) = &event.action_status {
                msgs.push(AppMessage::QqActionStatus(action.clone()));
            }
        }

        "workspace.created" | "workspace.committed" |
        "workspace.merge.started" | "workspace.merge.completed" => {
            // Track workspace activity — keep agent running
        }

        _ => {}
    }

    msgs
}

/// Tail a JSONL file continuously, sending parsed events through the channel.
pub async fn tail_qonqrete_events(
    path: PathBuf,
    tx: mpsc::UnboundedSender<AppMessage>,
    done_rx: tokio::sync::watch::Receiver<bool>,
) {
    let max_wait = Duration::from_secs(30);
    let start = std::time::Instant::now();
    loop {
        if path.exists() {
            break;
        }
        if start.elapsed() > max_wait {
            tracing::warn!(
                "qq-tui: events file {} did not appear within {:?}",
                path.display(),
                max_wait
            );
            return;
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }

    let file = match File::open(&path) {
        Ok(f) => f,
        Err(e) => {
            tracing::error!("qq-tui: cannot open events file {}: {}", path.display(), e);
            return;
        }
    };

    let mut reader = BufReader::new(file);
    let mut last_size = 0u64;

    loop {
        if *done_rx.borrow() {
            let mut line = String::new();
            loop {
                line.clear();
                match reader.read_line(&mut line) {
                    Ok(0) => break,
                    Ok(_) => {
                        let trimmed = line.trim();
                        if !trimmed.is_empty() {
                            if let Ok(event) = serde_json::from_str::<QqRuntimeEvent>(trimmed) {
                                for msg in event_to_messages(&event) {
                                    let _ = tx.send(msg);
                                }
                            }
                        }
                    }
                    Err(_) => break,
                }
            }
            break;
        }

        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) => {
                if let Ok(meta) = std::fs::metadata(&path) {
                    let new_size = meta.len();
                    if new_size < last_size {
                        if reader.seek(SeekFrom::Start(0)).is_err() {
                            break;
                        }
                    }
                    last_size = new_size;
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
                continue;
            }
            Ok(_) => {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    match serde_json::from_str::<QqRuntimeEvent>(trimmed) {
                        Ok(event) => {
                            let etype = event.event_type.clone();
                            if etype == "active_agent_changed" || etype == "config.loaded" || etype == "review.verdict" || etype == "build_group.completed" {
                                tracing::info!(
                                    "qq-tui event: {} role={:?} model={:?} groups_done={:?}",
                                    etype,
                                    event.role,
                                    event.model,
                                    event.groups_done
                                );
                            }
                            for msg in event_to_messages(&event) {
                                if tx.send(msg).is_err() {
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            tracing::debug!("qq-tui: JSONL parse error: {} (line: {:?})", e, trimmed);
                        }
                    }
                }
                if let Ok(meta) = std::fs::metadata(&path) {
                    last_size = meta.len();
                }
            }
            Err(e) => {
                tracing::debug!("qq-tui: read error on events file: {}", e);
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_config_loaded() {
        let json = r#"{"ts": 1780000000.0, "run_id": "abc123", "type": "config.loaded", "models": {"qlarifier": "deepseek-v4-flash"}}"#;
        let ev: QqRuntimeEvent = serde_json::from_str(json).unwrap();
        assert_eq!(ev.event_type, "config.loaded");
        let msgs = event_to_messages(&ev);
        assert!(!msgs.is_empty());
    }

    #[test]
    fn test_parse_active_agent_changed() {
        let json = r#"{"ts": 1780000000.0, "run_id": "abc123", "type": "active_agent_changed", "role": "construqtor", "call_id": "call1", "previous_role": "instruqtor", "model": "deepseek-v4-pro"}"#;
        let ev: QqRuntimeEvent = serde_json::from_str(json).unwrap();
        assert_eq!(ev.event_type, "active_agent_changed");
        let msgs = event_to_messages(&ev);
        assert!(msgs.len() >= 4); // agent with model, agent, model, done + running
    }

    #[test]
    fn test_parse_review_verdict() {
        let json = r#"{"ts": 1780000000.0, "run_id": "abc123", "type": "review.verdict", "score": 68.5, "verdict": "NOT_DONE", "cycle": 2}"#;
        let ev: QqRuntimeEvent = serde_json::from_str(json).unwrap();
        assert_eq!(ev.event_type, "review.verdict");
        let msgs = event_to_messages(&ev);
        assert!(!msgs.is_empty());
    }

    #[test]
    fn test_parse_build_group_completed() {
        let json = r#"{"ts": 1780000000.0, "run_id": "abc123", "type": "build_group.completed", "build_group_id": "bg1", "name": "First Group", "groups_done": 1, "total_groups": 5, "cycle": 1}"#;
        let ev: QqRuntimeEvent = serde_json::from_str(json).unwrap();
        assert_eq!(ev.event_type, "build_group.completed");
        assert_eq!(ev.groups_done, Some(1));
        let msgs = event_to_messages(&ev);
        assert!(!msgs.is_empty());
    }
}
