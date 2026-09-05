use crate::cli::Cli;
use crate::commands::{self, ParsedCommand};
use crate::config::{self, AppConfig};
use crate::events::{EventWriter, TypedEvent};
use crate::input::{self, InputAction};
use crate::layout::{self};
use crate::messages::{self, AppMessage};
use crate::qq_events;
use crate::status::StatusState;
use crate::status_script::{self, StatuslineResult};
use crate::theme::QonQreteTheme;
use crate::widgets::{
    command_palette::CommandPalette,
    diagnostics::DiagnosticsPanel,
    help_modal::HelpModal,
    input_box::InputBox,
    output_view::OutputView,
    status_bar::StatusBarWidget,
    status_bar::model_display_code,
};
use crossterm::event::{self, Event as CEvent};
use ratatui::{
    backend::CrosstermBackend,
    layout::Rect,
    Terminal,
};
use std::io;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use uuid::Uuid;

/// Main application state and runtime
pub struct App {
    pub config: AppConfig,
    pub theme: QonQreteTheme,
    pub status: StatusState,
    pub output_view: OutputView,
    pub input_box: InputBox,
    pub event_writer: EventWriter,
    pub tx: mpsc::UnboundedSender<AppMessage>,
    pub rx: mpsc::UnboundedReceiver<AppMessage>,
    pub show_help: bool,
    pub show_command_palette: bool,
    pub show_diagnostics: bool,
    pub last_statusline_result: Option<StatuslineResult>,
    pub debug_log_path: Option<PathBuf>,
    pub mode: String,
    /// Track when first Ctrl+C/ESC interrupt was received for two-step quit
    pub last_interrupt: Option<Instant>,
    /// Model per agent — updated from QqConfig and kept for auto-switching
    pub agent_models: std::collections::HashMap<String, String>,
}

/// Map an internal role name to its display name
fn agent_display_name(role: &str) -> String {
    match role.to_lowercase().as_str() {
        "qlarifier" | "qualifier" => "Qlarifier".into(),
        "instruqtor" => "instruQtor".into(),
        "construqtor" => "construQtor".into(),
        "inspeqtor" => "inspeQtor".into(),
        "sqavenger" => "sQavenger".into(),
        "attraqtor" => "attraQtor".into(),
        "qontroller" => "Qontroller".into(),
        other => other.to_string(),
    }
}

/// Map display name back to lowercase role key for model lookup
fn role_key(display_name: &str) -> Option<String> {
    match display_name.to_lowercase().as_str() {
        "qlarifier" | "qualifier" => Some("qlarifier".into()),
        "instruqtor" => Some("instruqtor".into()),
        "construqtor" => Some("construqtor".into()),
        "inspeqtor" => Some("inspeqtor".into()),
        other => Some(other.to_lowercase()),
    }
}

impl App {
    pub fn new(
        config: AppConfig,
        theme: QonQreteTheme,
        event_writer: EventWriter,
        debug_log_path: Option<PathBuf>,
    ) -> Self {
        let session_id = Uuid::new_v4().to_string()[..8].to_string();
        let status = StatusState::new(
            config.agent.name.clone(),
            config.agent.model.clone(),
            config.agent.budget,
            64,  // max_cycles — will be updated from qq events
            session_id,
        );
        let (tx, rx) = messages::channel();

        Self {
            config,
            theme,
            status,
            output_view: OutputView::new(),
            input_box: InputBox::new(),
            event_writer,
            tx,
            rx,
            show_help: false,
            show_command_palette: false,
            show_diagnostics: false,
            last_statusline_result: None,
            debug_log_path,
            mode: "interactive".into(),
            last_interrupt: None,
            agent_models: std::collections::HashMap::new(),
        }
    }

    pub fn push_event(&mut self, typed: &TypedEvent) {
        let event = typed.to_generic_event();
        self.output_view.push_event(event.clone());
        self.event_writer.write_typed(typed);
    }

    /// Handle a Ctrl+C Interrupt with two-step logic.
    /// First Ctrl+C: send SIGINT to agent, show warning.
    /// Second Ctrl+C within 1.5s: hard-quit TUI immediately.
    /// Returns true if the TUI should quit.
    fn handle_interrupt(&mut self) -> bool {
        let now = Instant::now();
        if let Some(last) = self.last_interrupt {
            if now.duration_since(last) < Duration::from_millis(1500) {
                // Second press within window — force quit
                let _ = self.tx.send(AppMessage::ForceQuit);
                return true;
            }
        }
        // Always update the timestamp so double-tap works
        self.last_interrupt = Some(now);
        // Send interrupt signal via message channel
        let _ = self.tx.send(AppMessage::ChildInterrupt);
        // Show interruption message in output
        self.output_view.push_raw_output(
            "system",
            "\u{26a0} Ctrl+C pressed \u{2014} interrupting agent... Press again within 1.5s to force-quit TUI.",
            false,
        );
        self.status.set_phase("interrupting");
        false
    }

    /// Handle a SafeInterrupt (ESC key) — stop the agent, never quit the TUI.
    fn handle_safe_interrupt(&mut self) {
        let _ = self.tx.send(AppMessage::ChildInterrupt);
        self.output_view.push_raw_output(
            "system",
            "\u{23ce} ESC pressed \u{2014} safely interrupting agent. TUI stays open.",
            false,
        );
        self.status.set_phase("interrupting");
    }

    /// Update model code when agent switches, using stored per-agent models
    fn update_model_for_agent(&mut self, agent_name: &str) {
        if let Some(key) = role_key(agent_name) {
            if let Some(model) = self.agent_models.get(&key) {
                self.status.model_code = model.clone();
            }
        }
    }

    /// Run the interactive TUI mode
    pub async fn run_interactive(
        &mut self,
        terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
        cli: &Cli,
    ) -> anyhow::Result<()> {
        self.mode = "interactive".into();
        self.apply_cli_overrides(cli);

        // Agent indicator legend (no Ql·In·Cn·Ip — removed per request)
        self.output_view.push_raw_output(
            "system",
            "Agents: \u{00BF}Q\u{003F} Qlarifier  \u{22A2}Q\u{21E2} instruQtor  \u{27EC}Q\u{27ED} construQtor  \u{29C9}Q\u{2316} inspeQtor  \u{29BF}Q\u{2713} Qualifier",
            false,
        );

        let spinner_interval = Duration::from_millis(
            cli.refresh_ms.unwrap_or(self.config.ui.spinner_refresh_ms),
        );
        let status_refresh = Duration::from_millis(
            cli.status_refresh_ms
                .unwrap_or(self.config.statusline.refresh_interval_ms),
        );

        let statusline_cmd = cli
            .status_command
            .clone()
            .or_else(|| self.config.statusline.command.clone());

        self.main_event_loop(terminal, spinner_interval, status_refresh, statusline_cmd)
            .await
    }

    /// Run a child process inside the full TUI with live output capture.
    pub async fn run_child_session(
        &mut self,
        terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
        cli: &Cli,
        command: Vec<String>,
        qq_events_path: Option<String>,
        exit_when_done: bool,
    ) -> anyhow::Result<i32> {
        self.mode = "child-run".into();
        self.apply_cli_overrides(cli);

        if command.is_empty() {
            anyhow::bail!("run mode requires a command after --");
        }

        let program = command[0].clone();
        let mut args: Vec<String> = command[1..].to_vec();

        // Auto-detect or inject --run-root so both TUI and Python child agree on events.jsonl.
        // Priority:
        // 1. Explicit --run-root in args
        // 2. --repo-root flag → generate new run-root, inject --run-root
        // 3. --no-repo flag with positional repo path → generate new run-root, inject --run-root
        // 4. Last positional arg that looks like a directory → generate new run-root, inject --run-root
        let run_root: Option<String> = extract_flag_value(&args, "--run-root");
        let run_root = if let Some(rr) = run_root {
            Some(rr)
        } else if let Some(repo) = extract_flag_value(&args, "--repo-root") {
            let derived = derive_run_root(&repo);
            // Inject --run-root into args so the Python child uses the same path
            args.push("--run-root".to_string());
            args.push(derived.clone());
            Some(derived)
        } else {
            // Try to find repo path from positional args (for --no-repo or bare repo paths)
            let has_no_repo = args.iter().any(|a| a == "--no-repo");
            // Find the last positional argument that looks like a path (contains / or ~)
            let repo_from_pos: Option<String> = args.iter()
                .rev()
                .find(|a| !a.starts_with('-') && (a.contains('/') || a.starts_with('~')))
                .cloned();
            if let Some(repo) = repo_from_pos {
                if has_no_repo || std::path::Path::new(&shellexpand(&repo)).is_dir() {
                    let derived = derive_run_root(&repo);
                    // Inject --run-root so Python child uses the same path
                    args.push("--run-root".to_string());
                    args.push(derived.clone());
                    Some(derived)
                } else {
                    None
                }
            } else {
                None
            }
        };

        let startup_msg = format!("Launching: {} {}", program, args.join(" "));
        self.output_view.push_raw_output("system", &startup_msg, false);
        // Agent icon legend
        self.output_view.push_raw_output(
            "system",
            "Agents: \u{00BF}Q\u{003F} Qlarifier  \u{22A2}Q\u{21E2} instruQtor  \u{27EC}Q\u{27ED} construQtor  \u{29C9}Q\u{2316} inspeQtor  \u{29BF}Q\u{2713} Qualifier",
            false,
        );

        self.status.start_active();
        self.status.set_phase("qlarifier");

        let spinner_interval = Duration::from_millis(
            cli.refresh_ms.unwrap_or(self.config.ui.spinner_refresh_ms),
        );
        let status_refresh = Duration::from_millis(
            cli.status_refresh_ms
                .unwrap_or(self.config.statusline.refresh_interval_ms),
        );

        let statusline_cmd = cli
            .status_command
            .clone()
            .or_else(|| self.config.statusline.command.clone());

        // Resolve events path: explicit --qq-events > --run-root derivation
        let qq_events_path = qq_events_path.or_else(|| {
            run_root.as_ref().map(|rr| format!("{}/events.jsonl", rr))
        });

        // Spawn QonQrete event tailer if events path provided
        let events_done_tx: Option<tokio::sync::watch::Sender<bool>> = if let Some(ref path) = qq_events_path {
            let p = config::shellexpand_path(path);
            if !p.as_os_str().is_empty() {
                let tx_events = self.tx.clone();
                let (done_tx, done_rx) = tokio::sync::watch::channel(false);
                tracing::info!("Starting QonQrete event tailer: {}", p.display());
                tokio::spawn(async move {
                    qq_events::tail_qonqrete_events(p, tx_events, done_rx).await;
                });
                Some(done_tx)
            } else {
                None
            }
        } else {
            None
        };

        // Spawn child process with live output streaming
        let tx_child = self.tx.clone();
        let child_handle = tokio::spawn(async move {
            spawn_child_and_stream(program, args, tx_child).await
        });

        let mut child_exited = false;
        let mut child_exit_code: Option<i32> = None;
        let mut child_pid: Option<u32> = None;

        let mut last_spinner_tick = Instant::now();
        let mut last_status_tick = Instant::now();

        loop {
            // Process all pending app messages
            while let Ok(msg) = self.rx.try_recv() {
                let should_break = self.process_message(msg, &mut child_pid, &mut child_exited, &mut child_exit_code, &events_done_tx);
                if should_break {
                    break;
                }
            }

            if child_exited && exit_when_done {
                break;
            }

            // Poll terminal events
            if event::poll(Duration::from_millis(50))? {
                match event::read()? {
                    CEvent::Key(key) => {
                        let action = input::map_key(key);
                        match action {
                            InputAction::Quit => break,
                            InputAction::Kill => break,
                            InputAction::Interrupt => {
                                if self.handle_interrupt() {
                                    // Process pending ForceQuit to kill child before breaking
                                    while let Ok(msg) = self.rx.try_recv() {
                                        if let AppMessage::ForceQuit = msg {
                                            if let Some(pid) = child_pid {
                                                #[cfg(unix)]
                                                unsafe { libc::kill(pid as i32, libc::SIGKILL); }
                                            }
                                        }
                                    }
                                    child_exited = true;
                                    break;
                                }
                            }
                            InputAction::SafeInterrupt => {
                                self.handle_safe_interrupt();
                            }
                            InputAction::Help => {
                                self.show_help = !self.show_help;
                            }
                            InputAction::CloseModal => {
                                self.show_help = false;
                                self.show_command_palette = false;
                                self.show_diagnostics = false;
                            }
                            InputAction::CommandPalette => {
                                self.show_command_palette = !self.show_command_palette;
                            }
                            InputAction::Submit => {
                                let text = self.input_box.take_input();
                                if text.is_empty() {
                                    continue;
                                }
                                let cmd = commands::parse(&text);
                                match &cmd {
                                    ParsedCommand::Quit => break,
                                    ParsedCommand::Clear => {
                                        self.output_view.clear();
                                    }
                                    ParsedCommand::Help => {
                                        self.show_help = true;
                                    }
                                    ParsedCommand::Debug => {
                                        self.show_diagnostics = true;
                                    }
                                    _ => {}
                                }
                            }
                            InputAction::ScrollUp => {
                                self.output_view.scroll_up(1);
                            }
                            InputAction::ScrollDown => {
                                self.output_view.scroll_down(1);
                            }
                            InputAction::PageUp => {
                                self.output_view.page_up(10);
                            }
                            InputAction::PageDown => {
                                self.output_view.page_down(10);
                            }
                            InputAction::JumpTop => {
                                self.output_view.jump_top();
                            }
                            InputAction::JumpBottom => {
                                self.output_view.jump_bottom();
                            }
                            InputAction::ClearView => {
                                self.output_view.clear();
                            }
                            InputAction::PauseAutoScroll => {
                                if self.output_view.auto_scroll {
                                    self.output_view.auto_scroll = false;
                                } else {
                                    self.output_view.resume_auto_scroll();
                                }
                            }
                            InputAction::ShowDiagnostics => {
                                self.show_diagnostics = !self.show_diagnostics;
                            }
                            InputAction::ForceRedraw => {}
                            InputAction::Char(c) => {
                                self.input_box.push_char(c);
                            }
                            InputAction::Backspace => {
                                self.input_box.backspace();
                            }
                            _ => {}
                        }
                    }
                    CEvent::Resize(_cols, _rows) => {}
                    CEvent::Mouse(_) => {} // mouse permanently disabled (vim-style)
                    _ => {}
                }
            }

            // Timer ticks
            let now = Instant::now();
            if now.duration_since(last_spinner_tick) >= spinner_interval {
                let num_frames = self.theme.spinner_frames().len();
                self.status.advance_spinner(num_frames);
                last_spinner_tick = now;
            }

            if now.duration_since(last_status_tick) >= status_refresh {
                if let Some(ref cmd) = statusline_cmd {
                    let result = status_script::run_statusline(
                        cmd,
                        &self.status,
                        self.config.statusline.timeout_ms,
                        self.config.statusline.allow_ansi,
                    );
                    self.last_statusline_result = Some(result);
                }
                last_status_tick = now;
            }

            // Draw
            self.draw(terminal)?;
        }

        // Wait for child to finish if still running
        if !child_exited {
            let result = child_handle.await;
            if let Ok(code) = result {
                child_exit_code = code;
            }
        }

        if let Some(done_tx) = events_done_tx {
            let _ = done_tx.send(true);
        }

        let code = child_exit_code.unwrap_or(1);
        if code != 0 {
            return Ok(code);
        }
        Ok(0)
    }

    /// Process a single AppMessage. Returns true if event loop should break.
    fn process_message(
        &mut self,
        msg: AppMessage,
        child_pid: &mut Option<u32>,
        child_exited: &mut bool,
        child_exit_code: &mut Option<i32>,
        events_done_tx: &Option<tokio::sync::watch::Sender<bool>>,
    ) -> bool {
        match msg {
            AppMessage::ChildStdout(line) => {
                self.output_view.push_raw_output("stdout", &line, false);
                self.status.mark_activity();
                false
            }
            AppMessage::ChildStderr(line) => {
                self.output_view.push_raw_stderr(&line);
                self.status.mark_activity();
                false
            }
            AppMessage::ChildPid(pid) => {
                *child_pid = Some(pid);
                false
            }
            AppMessage::ChildExited(code) => {
                *child_exited = true;
                *child_exit_code = Some(code);
                self.status.stop_active();
                self.status.last_exit_code = Some(code);
                self.status.child_status = if code == 0 {
                    crate::status::ChildStatus::Finished
                } else {
                    crate::status::ChildStatus::Failed
                };
                self.status.set_phase(if code == 0 { "done" } else { "failed" });
                if let Some(ref done_tx) = events_done_tx {
                    let _ = done_tx.send(true);
                }
                false
            }
            AppMessage::ChildInterrupt => {
                if let Some(pid) = *child_pid {
                    self.output_view.push_raw_output(
                        "system",
                        &format!("Sending SIGINT to child PID {}...", pid),
                        false,
                    );
                    #[cfg(unix)]
                    unsafe {
                        libc::kill(pid as i32, libc::SIGINT);
                    }
                    false
                } else {
                    // No child — quit
                    let _ = self.tx.send(AppMessage::Quit);
                    true
                }
            }
            AppMessage::ForceQuit => {
                if let Some(pid) = *child_pid {
                    #[cfg(unix)]
                    unsafe {
                        libc::kill(pid as i32, libc::SIGKILL);
                    }
                }
                true
            }
            AppMessage::Quit => true,
            AppMessage::Clear => {
                self.output_view.clear();
                false
            }
            AppMessage::ToggleAutoScroll => {
                if self.output_view.auto_scroll {
                    self.output_view.auto_scroll = false;
                } else {
                    self.output_view.resume_auto_scroll();
                }
                false
            }
            AppMessage::QqMaxCycles(mc) => {
                self.status.max_cycles = mc;
                false
            }
            AppMessage::QqConfig { models } => {
                // Store per-agent models for auto-switching
                for (role, model) in &models {
                    self.agent_models.insert(role.to_lowercase(), model_display_code(model));
                }
                // If we already have an active agent, update the model
                let key = role_key(&self.status.agent_name);
                if let Some(k) = key {
                    if let Some(model) = models.get(&k) {
                        self.status.model_code = model_display_code(model);
                    }
                }
                false
            }
            AppMessage::QqActiveAgent(role) => {
                self.status.agent_name = agent_display_name(&role);
                self.update_model_for_agent(&self.status.agent_name.clone());
                self.status.reset_active_time();
                false
            }
            AppMessage::QqActiveAgentWithModel { role, model } => {
                self.status.agent_name = agent_display_name(&role);
                if let Some(m) = model {
                    self.status.model_code = model_display_code(&m);
                } else {
                    self.update_model_for_agent(&self.status.agent_name.clone());
                }
                self.status.reset_active_time();
                false
            }
            AppMessage::QqAgentDone(role) => {
                self.status.agents.set_state(role, crate::status::AgentState::Done);
                false
            }
            AppMessage::QqAgentRunning(role) => {
                self.status.agents.set_state(role, crate::status::AgentState::Running);
                false
            }
            AppMessage::QqAgentFailed(role) => {
                self.status.agents.set_state(role, crate::status::AgentState::Failed);
                false
            }
            AppMessage::QqModel(model) => {
                self.status.model_code = model_display_code(&model);
                false
            }
            AppMessage::QqCycle(cycle) => {
                if cycle > self.status.cycle {
                    self.status.cycle = cycle;
                }
                false
            }
            AppMessage::QqProgress(pct) => {
                self.status.set_progress(pct);
                false
            }
            AppMessage::QqPhase(phase) => {
                // B3: freeze the Total timer at FULLY_DONE / successful completion
                if phase == "fully-done" || phase == "done" {
                    self.status.freeze_total();
                }
                if phase == "running" {
                    self.status.frozen_total = None;
                    self.status.terminal_reached = false;
                }
                self.status.set_phase(phase);
                false
            }
            AppMessage::QqExitCode(code) => {
                self.status.last_exit_code = Some(code);
                false
            }
            AppMessage::QqExitSymbol(sym) => {
                self.status.last_exit_symbol = Some(sym);
                false
            }
            AppMessage::QqActionStatus(action) => {
                // B3: freeze the Total timer at FULLY_DONE
                if action.to_lowercase() == "fully_done" {
                    self.status.freeze_total();
                }
                self.status.action_status = Some(action);
                false
            }
            AppMessage::QqAgentOutputBytes { role, stdout, stderr } => {
                if self.status.agent_name == role || self.status.agent_name == agent_display_name(&role) || self.status.agent_name.is_empty() {
                    self.status.agent_name = agent_display_name(&role);
                    // Auto-switch model
                    self.update_model_for_agent(&self.status.agent_name.clone());
                }
                self.status.bytes_out = stdout;
                self.status.bytes_err = stderr;
                self.status.chunks += 1;
                false
            }
            _ => false,
        }
    }

    fn apply_cli_overrides(&mut self, cli: &Cli) {
        if let Some(ref name) = cli.agent {
            self.status.agent_name = agent_display_name(name);
        }
        if let Some(ref model) = cli.model {
            self.status.model_code = model.clone();
        }
        if let Some(b) = cli.budget {
            self.status.budget = b;
        }
        if let Some(p) = cli.progress {
            self.status.set_progress(p);
        }
    }

    /// Main event loop shared by interactive and child-run modes
    async fn main_event_loop(
        &mut self,
        terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
        spinner_interval: Duration,
        status_refresh: Duration,
        statusline_cmd: Option<String>,
    ) -> anyhow::Result<()> {
        let mut last_spinner_tick = Instant::now();
        let mut last_status_tick = Instant::now();

        loop {
            while let Ok(msg) = self.rx.try_recv() {
                match msg {
                    AppMessage::Event(ev) => {
                        // Note: cycle must NOT increment on arbitrary tool/debug events.
                        // It is driven by QqCycle, which mirrors the backend's
                        // review->build handoff increment (inspeQtor -> construQtor).
                        self.push_event(&ev);
                    }
                    AppMessage::ChildInterrupt => {
                        self.output_view.push_raw_output(
                            "system",
                            "\u{26a0} Ctrl+C pressed \u{2014} no agent running. Press again within 1.5s to quit.",
                            false,
                        );
                    }
                    AppMessage::ForceQuit => return Ok(()),
                    AppMessage::Quit => return Ok(()),
                    AppMessage::Clear => {
                        self.output_view.clear();
                    }
                    AppMessage::ToggleAutoScroll => {
                        if self.output_view.auto_scroll {
                            self.output_view.auto_scroll = false;
                        } else {
                            self.output_view.resume_auto_scroll();
                        }
                    }
                    AppMessage::QqActiveAgent(role) => {
                        self.status.agent_name = agent_display_name(&role);
                        self.update_model_for_agent(&self.status.agent_name.clone());
                        self.status.reset_active_time();
                    }
                    AppMessage::QqActiveAgentWithModel { role, model } => {
                        self.status.agent_name = agent_display_name(&role);
                        if let Some(m) = model {
                            self.status.model_code = model_display_code(&m);
                        } else {
                            self.update_model_for_agent(&self.status.agent_name.clone());
                        }
                        self.status.reset_active_time();
                    }
                    AppMessage::QqAgentDone(role) => {
                        self.status.agents.set_state(role, crate::status::AgentState::Done);
                    }
                    AppMessage::QqAgentRunning(role) => {
                        self.status.agents.set_state(role, crate::status::AgentState::Running);
                    }
                    AppMessage::QqAgentFailed(role) => {
                        self.status.agents.set_state(role, crate::status::AgentState::Failed);
                    }
                    AppMessage::QqModel(model) => {
                        self.status.model_code = model_display_code(&model);
                    }
                    AppMessage::QqCycle(cycle) => {
                        if cycle > self.status.cycle {
                            self.status.cycle = cycle;
                        }
                    }
                    AppMessage::QqProgress(pct) => {
                        self.status.set_progress(pct);
                    }
                    AppMessage::QqPhase(phase) => {
                        // B3: freeze the Total timer at FULLY_DONE / successful completion
                        if phase == "fully-done" || phase == "done" {
                            self.status.freeze_total();
                        }
                        if phase == "running" {
                            self.status.frozen_total = None;
                            self.status.terminal_reached = false;
                        }
                        self.status.set_phase(phase);
                    }
                    AppMessage::QqExitCode(code) => {
                        self.status.last_exit_code = Some(code);
                    }
                    AppMessage::QqExitSymbol(sym) => {
                        self.status.last_exit_symbol = Some(sym);
                    }
                    AppMessage::QqActionStatus(action) => {
                        // B3: freeze the Total timer at FULLY_DONE
                        if action.to_lowercase() == "fully_done" {
                            self.status.freeze_total();
                        }
                        self.status.action_status = Some(action);
                    }
                    AppMessage::QqAgentOutputBytes { role, stdout, stderr } => {
                        self.status.bytes_out = stdout;
                        self.status.bytes_err = stderr;
                        self.status.chunks += 1;
                        if !role.is_empty() {
                            self.status.agent_name = agent_display_name(&role);
                            self.update_model_for_agent(&self.status.agent_name.clone());
                        }
                    }
                    AppMessage::QqMaxCycles(mc) => {
                        self.status.max_cycles = mc;
                    }
                    AppMessage::QqConfig { models } => {
                        for (role, model) in &models {
                            self.agent_models.insert(role.to_lowercase(), model_display_code(model));
                        }
                        let key = role_key(&self.status.agent_name);
                        if let Some(k) = key {
                            if let Some(model) = models.get(&k) {
                                self.status.model_code = model_display_code(model);
                            }
                        }
                    }
                    _ => {}
                }
            }

            if event::poll(Duration::from_millis(50))? {
                match event::read()? {
                    CEvent::Key(key) => {
                        let action = input::map_key(key);
                        match action {
                            InputAction::Quit => return Ok(()),
                            InputAction::Kill => return Ok(()),
                            InputAction::Interrupt => {
                                if self.handle_interrupt() {
                                    return Ok(());
                                }
                            }
                            InputAction::SafeInterrupt => {
                                self.handle_safe_interrupt();
                            }
                            InputAction::Help => {
                                self.show_help = !self.show_help;
                            }
                            InputAction::CloseModal => {
                                self.show_help = false;
                                self.show_command_palette = false;
                                self.show_diagnostics = false;
                            }
                            InputAction::CommandPalette => {
                                self.show_command_palette = !self.show_command_palette;
                            }
                            InputAction::Submit => {
                                let text = self.input_box.take_input();
                                if text.is_empty() {
                                    continue;
                                }
                                let cmd = commands::parse(&text);
                                match &cmd {
                                    ParsedCommand::Quit => return Ok(()),
                                    ParsedCommand::Clear => {
                                        self.output_view.clear();
                                    }
                                    ParsedCommand::Help => {
                                        self.show_help = true;
                                    }
                                    ParsedCommand::Debug => {
                                        self.show_diagnostics = true;
                                    }
                                    ParsedCommand::Run(args) if !args.is_empty() => {
                                        let _ = self.tx.send(AppMessage::RunCommand(args.clone()));
                                    }
                                    ParsedCommand::RunPty(args) if !args.is_empty() => {
                                        let _ = self.tx.send(AppMessage::RunPtyCommand(args.clone()));
                                    }
                                    ParsedCommand::Shell(args) if !args.is_empty() => {
                                        let _ = self.tx.send(AppMessage::RunCommand(args.clone()));
                                    }
                                    _ => {}
                                }
                                if let Some(ev) = commands::command_to_event(&cmd) {
                                    self.push_event(&ev);
                                }
                            }
                            InputAction::ScrollUp => {
                                self.output_view.scroll_up(1);
                            }
                            InputAction::ScrollDown => {
                                self.output_view.scroll_down(1);
                            }
                            InputAction::PageUp => {
                                self.output_view.page_up(10);
                            }
                            InputAction::PageDown => {
                                self.output_view.page_down(10);
                            }
                            InputAction::JumpTop => {
                                self.output_view.jump_top();
                            }
                            InputAction::JumpBottom => {
                                self.output_view.jump_bottom();
                            }
                            InputAction::ClearView => {
                                self.output_view.clear();
                            }
                            InputAction::PauseAutoScroll => {
                                if self.output_view.auto_scroll {
                                    self.output_view.auto_scroll = false;
                                } else {
                                    self.output_view.resume_auto_scroll();
                                }
                            }
                            InputAction::ShowDiagnostics => {
                                self.show_diagnostics = !self.show_diagnostics;
                            }
                            InputAction::ForceRedraw => {}
                            InputAction::Char(c) => {
                                self.input_box.push_char(c);
                            }
                            InputAction::Backspace => {
                                self.input_box.backspace();
                            }
                            _ => {}
                        }
                    }
                    CEvent::Resize(_cols, _rows) => {}
                    CEvent::Mouse(_) => {} // mouse permanently disabled (vim-style)
                    _ => {}
                }
            }

            let now = Instant::now();
            if now.duration_since(last_spinner_tick) >= spinner_interval {
                let num_frames = self.theme.spinner_frames().len();
                self.status.advance_spinner(num_frames);
                last_spinner_tick = now;
            }

            if now.duration_since(last_status_tick) >= status_refresh {
                if let Some(ref cmd) = statusline_cmd {
                    let result = status_script::run_statusline(
                        cmd,
                        &self.status,
                        self.config.statusline.timeout_ms,
                        self.config.statusline.allow_ansi,
                    );
                    self.last_statusline_result = Some(result);
                }
                last_status_tick = now;
            }

            self.draw(terminal)?;
        }
    }

    /// Render the full TUI
    fn draw(
        &self,
        terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    ) -> anyhow::Result<()> {
        terminal.draw(|frame| {
            let area = frame.area();

            if let Some(warning) = layout::check_minimum_size(area.width, area.height) {
                let w = area.width.min(50) as u16;
                let h = 3;
                let x = (area.width.saturating_sub(w)) / 2;
                let y = (area.height.saturating_sub(h)) / 2;
                let warn_area = Rect::new(x, y, w, h);
                let p = ratatui::widgets::Paragraph::new(warning)
                    .style(ratatui::style::Style::default().fg(ratatui::style::Color::Indexed(196)))
                    .block(
                        ratatui::widgets::Block::default()
                            .borders(ratatui::widgets::Borders::ALL)
                            .border_style(
                                ratatui::style::Style::default()
                                    .fg(ratatui::style::Color::Indexed(196)),
                            ),
                    );
                frame.render_widget(p, warn_area);
                return;
            }

            let layout = layout::compute_layout(area);

            let status_line_override = self
                .last_statusline_result
                .as_ref()
                .filter(|r| r.success && !r.line.is_empty())
                .map(|r| r.line.as_str());

            let bar_widget = StatusBarWidget::new(&self.status, &self.theme)
                .with_version(&self.config.ui.version)
                .with_width(layout.status_bar.width);
            let bar_widget = if let Some(line) = status_line_override {
                bar_widget.with_override(line)
            } else {
                bar_widget
            };
            let status_buf = frame.buffer_mut();
            bar_widget.render_full(status_buf, layout.status_bar);

            self.output_view
                .render(frame.buffer_mut(), layout.output_view);

            self.input_box
                .render(frame.buffer_mut(), layout.input_box);

            if self.show_help {
                HelpModal::render(frame.buffer_mut(), area);
            }
            if self.show_command_palette {
                CommandPalette::render(frame.buffer_mut(), area);
            }
            if self.show_diagnostics {
                let diag = DiagnosticsPanel {
                    mode: self.mode.clone(),
                    terminal_size: (area.width, area.height),
                    is_tty: config::is_tty(),
                    config_path: self
                        .config
                        .config_path
                        .as_ref()
                        .map(|p| p.display().to_string())
                        .unwrap_or_else(|| "none".into()),
                    statusline_command: self
                        .config
                        .statusline
                        .command
                        .clone()
                        .unwrap_or_else(|| "none".into()),
                    last_statusline_duration_ms: self
                        .last_statusline_result
                        .as_ref()
                        .map(|r| r.duration_ms)
                        .unwrap_or(0),
                    last_statusline_error: self
                        .last_statusline_result
                        .as_ref()
                        .and_then(|r| r.error.clone()),
                    event_count: self.output_view.events.len(),
                    scroll_offset: self.output_view.scroll_offset,
                    current_phase: self.status.phase.clone(),
                    last_exit_code: self.status.last_exit_code,
                    debug_log_path: self
                        .debug_log_path
                        .as_ref()
                        .map(|p| p.display().to_string())
                        .unwrap_or_else(|| "none".into()),
                };
                diag.render(frame.buffer_mut(), area);
            }
        })?;
        Ok(())
    }

    pub async fn run_exec(command: Vec<String>) -> anyhow::Result<()> {
        if command.is_empty() {
            anyhow::bail!("exec mode requires a command");
        }
        let program = &command[0];
        let args = &command[1..];

        let output = std::process::Command::new(program)
            .args(args)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()?;

        use std::io::Write;
        std::io::stdout().write_all(&output.stdout)?;
        std::io::stderr().write_all(&output.stderr)?;

        let code = output.status.code().unwrap_or(1);
        if code != 0 {
            std::process::exit(code);
        }
        Ok(())
    }

    pub fn run_statusline_test(command: &str) -> anyhow::Result<()> {
        let status = StatusState::new(
            "Qlarifier".into(),
            "QON-7B".into(),
            26,
            64,  // max_cycles
            "test1234".into(),
        );

        println!("Running statusline command: {}", command);
        println!("Input JSON:");
        println!(
            "{}",
            serde_json::to_string_pretty(&status.to_statusline_json())?
        );
        println!();

        let result = status_script::run_statusline(command, &status, 3000, true);
        println!("--- Statusline output ---");
        println!("{}", result.line);
        println!("---");
        println!(
            "Success: {}, Duration: {}ms",
            result.success, result.duration_ms
        );
        if let Some(ref err) = result.error {
            println!("Error: {}", err);
        }
        Ok(())
    }
}

/// Spawn a child process and stream stdout/stderr lines to the app via the
/// message channel.
/// Simple tilde expansion for paths
fn shellexpand(path: &str) -> String {
    if path.starts_with('~') {
        if let Ok(home) = std::env::var("HOME") {
            return path.replacen('~', &home, 1);
        }
    }
    path.to_string()
}

/// Extract the value of a flag from a vec of command-line args.
/// Handles both `--flag value` and `--flag=value` forms.
fn extract_flag_value(args: &[String], flag: &str) -> Option<String> {
    let mut i = 0;
    while i < args.len() {
        if args[i] == flag && i + 1 < args.len() {
            return Some(args[i + 1].clone());
        }
        if args[i].len() > flag.len() + 1 && args[i].starts_with(flag) {
            let rest = &args[i][flag.len()..];
            if rest.starts_with('=') {
                return Some(rest[1..].to_string());
            }
        }
        i += 1;
    }
    None
}

/// Derive a run-root path from a repo-root, matching Python's default_run_root / generate_run_id.
/// Always generates a fresh unique run-id: <timestamp>-<uuid8>.
///
/// IMPORTANT: Python always creates a new run directory, so the TUI must derive a matching
/// new path — never try to find an existing run, or we'll watch the wrong events.jsonl.
fn derive_run_root(repo_root: &str) -> String {
    use chrono::Utc;
    let ts = Utc::now().format("%Y%m%d-%H%M%S");
    let short = uuid::Uuid::new_v4().to_string()[..8].to_string();
    std::path::Path::new(repo_root)
        .join(".qq")
        .join("runs")
        .join(format!("{}-{}", ts, short))
        .to_string_lossy()
        .to_string()
}

async fn spawn_child_and_stream(
    program: String,
    args: Vec<String>,
    tx: mpsc::UnboundedSender<AppMessage>,
) -> Option<i32> {
    use std::process::{Command, Stdio};
    use std::io::{BufRead, BufReader};

    let mut child = match Command::new(&program)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => {
            let pid = c.id();
            let _ = tx.send(AppMessage::ChildPid(pid));
            c
        }
        Err(e) => {
            let _ = tx.send(AppMessage::ChildStderr(format!(
                "Failed to spawn '{}': {}",
                program, e
            )));
            let _ = tx.send(AppMessage::ChildExited(-1));
            return Some(-1);
        }
    };

    let stdout = child.stdout.take().expect("stdout pipe");
    let stderr = child.stderr.take().expect("stderr pipe");

    let tx_stdout = tx.clone();
    let tx_stderr = tx.clone();

    let stdout_handle = std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    if tx_stdout.send(AppMessage::ChildStdout(l)).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    let stderr_handle = std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            match line {
                Ok(l) => {
                    if tx_stderr.send(AppMessage::ChildStderr(l)).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    stdout_handle.join().ok();
    stderr_handle.join().ok();

    let status = match child.wait() {
        Ok(s) => s,
        Err(e) => {
            let _ = tx.send(AppMessage::ChildStderr(format!(
                "Failed to wait on child: {}",
                e
            )));
            let _ = tx.send(AppMessage::ChildExited(-1));
            return Some(-1);
        }
    };

    let code = status.code().unwrap_or(-1);
    let _ = tx.send(AppMessage::ChildExited(code));
    Some(code)
}
