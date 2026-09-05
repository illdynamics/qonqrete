use chrono::{DateTime, Duration, Utc};
use serde::Serialize;
use crate::qq_events::AgentRole;

/// The canonical status model for the QonQrete status bar
#[derive(Debug, Clone, Serialize)]
pub struct StatusState {
    pub agent_name: String,
    pub model_code: String,
    pub cycle: u64,
    pub max_cycles: u64,
    pub session_started_at: DateTime<Utc>,
    pub active_started_at: Option<DateTime<Utc>>,
    pub last_activity_at: Option<DateTime<Utc>>,
    pub budget: u64,
    pub progress: Option<f64>,
    pub total_groups: u64,
    pub groups_done: u64,
    pub total_briqs: u64,
    pub briqs_done: u64,
    pub phase: String,
    pub spinner_index: usize,
    pub child_status: ChildStatus,
    pub last_exit_code: Option<i32>,
    pub last_exit_symbol: Option<String>,
    pub action_status: Option<String>,
    pub cost: Option<f64>,
    pub context_percent: Option<f64>,
    pub session_id: String,
    pub cwd: String,
    pub hostname: String,
    /// Total paused active time so far (so we can resume accounting across
    /// active/inactive transitions)
    pub accumulated_active: Duration,
    /// Frozen wall-clock total once the run reaches a terminal (FULLY_DONE) state.
    pub frozen_total: Option<Duration>,
    /// True once the run reaches a terminal (FULLY_DONE) state.
    pub terminal_reached: bool,
    /// Per-agent status indicators
    pub agents: AgentIndicators,
    /// Chunks/bytes count for current active agent call
    pub chunks: u64,
    pub bytes_out: u64,
    pub bytes_err: u64,
}

/// Per-agent indicator states for the sticky status bar.
#[derive(Debug, Clone, Serialize)]
pub struct AgentIndicators {
    pub qlarifier: AgentState,
    pub instruqtor: AgentState,
    pub construqtor: AgentState,
    pub inspeqtor: AgentState,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum AgentState {
    Idle,
    Running,
    Done,
    Failed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[allow(dead_code)]
pub enum ChildStatus {
    Idle,
    Running,
    Finished,
    Failed,
    Interrupted,
}

impl std::fmt::Display for ChildStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ChildStatus::Idle => write!(f, "idle"),
            ChildStatus::Running => write!(f, "running"),
            ChildStatus::Finished => write!(f, "finished"),
            ChildStatus::Failed => write!(f, "failed"),
            ChildStatus::Interrupted => write!(f, "interrupted"),
        }
    }
}

impl Default for AgentIndicators {
    fn default() -> Self {
        Self {
            qlarifier: AgentState::Idle,
            instruqtor: AgentState::Idle,
            construqtor: AgentState::Idle,
            inspeqtor: AgentState::Idle,
        }
    }
}

impl AgentIndicators {
    pub fn set_state(&mut self, role: AgentRole, state: AgentState) {
        match role {
            AgentRole::Qlarifier => self.qlarifier = state,
            AgentRole::InstruQtor => self.instruqtor = state,
            AgentRole::ConstruQtor => self.construqtor = state,
            AgentRole::InspeQtor => self.inspeqtor = state,
        }
    }

    /// Return compact per-agent display characters.
    /// Each character represents one agent's state:
    ///   '·' = idle, spinners use current frame, '✓' = done, '↯' = failed
    #[allow(dead_code)]

    pub fn compact_chars(&self, spinner_frame: char) -> Vec<(AgentRole, char)> {
        vec![
            (AgentRole::Qlarifier, self.state_char(self.qlarifier, spinner_frame)),
            (AgentRole::InstruQtor, self.state_char(self.instruqtor, spinner_frame)),
            (AgentRole::ConstruQtor, self.state_char(self.construqtor, spinner_frame)),
            (AgentRole::InspeQtor, self.state_char(self.inspeqtor, spinner_frame)),
        ]
    }

    #[allow(dead_code)]


    fn state_char(&self, state: AgentState, spinner: char) -> char {
        match state {
            AgentState::Idle => '·',
            AgentState::Running => spinner,
            AgentState::Done => '\u{2713}',    // ✓
            AgentState::Failed => '\u{21af}',  // ↯
        }
    }

    /// ASCII fallback characters
    #[allow(dead_code)]

    pub fn compact_chars_ascii(&self) -> Vec<(AgentRole, char)> {
        vec![
            (AgentRole::Qlarifier, self.state_ascii(self.qlarifier)),
            (AgentRole::InstruQtor, self.state_ascii(self.instruqtor)),
            (AgentRole::ConstruQtor, self.state_ascii(self.construqtor)),
            (AgentRole::InspeQtor, self.state_ascii(self.inspeqtor)),
        ]
    }

    #[allow(dead_code)]


    fn state_ascii(&self, state: AgentState) -> char {
        match state {
            AgentState::Idle => '.',
            AgentState::Running => '*',
            AgentState::Done => '+',
            AgentState::Failed => '!',
        }
    }
}

impl StatusState {
    pub fn new(agent_name: String, model_code: String, budget: u64, max_cycles: u64, session_id: String) -> Self {
        let hostname = std::process::Command::new("hostname")
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|| "unknown".into());
        let cwd = std::env::current_dir()
            .ok()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|| ".".into());

        Self {
            agent_name,
            model_code,
            cycle: 1,
            max_cycles,
            session_started_at: Utc::now(),
            active_started_at: None,
            last_activity_at: None,
            budget,
            progress: None,
            total_groups: 0,
            groups_done: 0,
            total_briqs: 0,
            briqs_done: 0,
            phase: "starting".into(),
            spinner_index: 0,
            child_status: ChildStatus::Idle,
            last_exit_code: None,
            last_exit_symbol: None,
            action_status: None,
            cost: None,
            context_percent: None,
            session_id,
            cwd,
            hostname,
            accumulated_active: Duration::zero(),
            frozen_total: None,
            terminal_reached: false,
            agents: AgentIndicators::default(),
            chunks: 0,
            bytes_out: 0,
            bytes_err: 0,
        }
    }

    pub fn total_elapsed(&self) -> Duration {
        if let Some(frozen) = self.frozen_total {
            return frozen;
        }
        Utc::now() - self.session_started_at
    }

    pub fn active_time(&self) -> Duration {
        let mut active = self.accumulated_active;
        if let Some(started) = self.active_started_at {
            active = active + (Utc::now() - started);
        }
        active
    }

    pub fn total_elapsed_secs(&self) -> u64 {
        self.total_elapsed().num_seconds().max(0) as u64
    }

    pub fn active_secs(&self) -> u64 {
        self.active_time().num_seconds().max(0) as u64
    }

    /// Start active tracking (e.g. when a command begins)
    pub fn start_active(&mut self) {
        if self.active_started_at.is_none() {
            self.active_started_at = Some(Utc::now());
        }
        self.last_activity_at = Some(Utc::now());
        self.child_status = ChildStatus::Running;
    }

    /// Stop active tracking and accumulate the elapsed time
    pub fn stop_active(&mut self) {
        if let Some(started) = self.active_started_at.take() {
            self.accumulated_active = self.accumulated_active + (Utc::now() - started);
        }
        // Don't auto-set to Idle — let the caller decide based on outcome
    }

    /// Reset agent timer to zero without affecting total session time.
    /// Called when switching between Qlarifier → instruQtor → construQtor → inspeQtor
    /// so Agent time restarts from 00:00 while Total time keeps rolling.
    pub fn reset_active_time(&mut self) {
        self.active_started_at = Some(Utc::now());
        self.accumulated_active = Duration::zero();
        self.last_activity_at = Some(Utc::now());
    }

    pub fn mark_activity(&mut self) {
        self.last_activity_at = Some(Utc::now());
    }

    /// Freeze the Total timer at the current wall-clock elapsed time and stop
    /// the Active timer. Idempotent — subsequent calls are no-ops.
    pub fn freeze_total(&mut self) {
        if self.terminal_reached {
            return;
        }
        self.frozen_total = Some(self.total_elapsed());
        self.terminal_reached = true;
        self.stop_active();
    }

    pub fn set_phase(&mut self, phase: impl Into<String>) {
        self.phase = phase.into();
    }

    pub fn set_progress(&mut self, pct: f64) {
        self.progress = Some(pct.clamp(0.0, 100.0));
    }

    pub fn advance_spinner(&mut self, num_frames: usize) {
        self.spinner_index = (self.spinner_index + 1) % num_frames;
    }

    /// Advance the icon spinner (4-state: ◰ ◳ ◲ ◱)

    /// Build the JSON payload sent to the statusline command on stdin
    pub fn to_statusline_json(&self) -> serde_json::Value {
        serde_json::json!({
            "agent": {
                "name": self.agent_name,
                "model": self.model_code
            },
            "session": {
                "id": self.session_id,
                "cwd": self.cwd,
                "started_at": self.session_started_at.to_rfc3339(),
                "elapsed_seconds": self.total_elapsed_secs()
            },
            "status": {
                "cycle": self.cycle,
                "max_cycles": self.max_cycles,
                "phase": self.phase,
                "budget": self.budget,
                "progress": self.progress.unwrap_or(0.0),
                "active_seconds": self.active_secs()
            },
            "system": {
                "hostname": self.hostname,
                "shell": std::env::var("SHELL").unwrap_or_else(|_| "sh".into())
            }
        })
    }
}

/// Format seconds as mm:ss
pub fn fmt_duration(secs: u64) -> String {
    let m = secs / 60;
    let s = secs % 60;
    format!("{:02}:{:02}", m, s)
}

pub fn fmt_elapsed(secs: u64) -> String {
    fmt_duration(secs)
}

pub fn fmt_active(secs: u64) -> String {
    fmt_duration(secs)
}
