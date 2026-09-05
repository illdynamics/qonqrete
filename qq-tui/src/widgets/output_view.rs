use crate::events::Event;
use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Widget, Wrap},
};

/// Scrollable output view that displays captured events
#[derive(Debug, Clone, Default)]
pub struct OutputView {
    pub events: Vec<Event>,
    pub scroll_offset: usize,
    pub auto_scroll: bool,
    pub filter_text: Option<String>,
}

/// Color palette matching Codex/CodeSeeq agent output styles
/// Based on user's QonQrete PS1 colors: orange/yellow/grey
mod palette {
    use ratatui::style::Color;
    // Agent role colors (matching Python streaming.py)
    pub const CYAN: Color       = Color::Indexed(51);    // Qlarifier
    pub const MAGENTA: Color    = Color::Indexed(201);   // instruQtor  
    pub const YELLOW: Color     = Color::Indexed(220);   // construQtor (gold)
    pub const GREEN: Color      = Color::Indexed(42);    // inspeQtor
    pub const BLUE: Color       = Color::Indexed(33);    // sQavenger
    pub const RED: Color        = Color::Indexed(196);   // attraqtor / errors
    pub const BRIGHT_MAGENTA: Color = Color::Indexed(207); // Qontroller
    pub const STEEL_GREY: Color = Color::Indexed(244);   // timestamps/labels
    pub const LIGHT_GREY: Color = Color::Indexed(250);   // general info
    pub const ORANGE: Color     = Color::Indexed(202);    // ember orange
    pub const WHITE: Color      = Color::Indexed(15);     // plain white
}

impl OutputView {
    pub fn new() -> Self {
        Self {
            events: Vec::new(),
            scroll_offset: 0,
            auto_scroll: true,
            filter_text: None,
        }
    }

    pub fn push_event(&mut self, event: Event) {
        self.events.push(event);
    }

    /// Push raw child process stdout output.
    /// Preserves ANSI color codes by parsing them into ratatui styles.
    pub fn push_raw_output(&mut self, source: &str, text: &str, is_error: bool) {
        let cleaned = strip_ansi(text);
        if cleaned.trim().is_empty() && !text.trim().is_empty() {
            // The line was only ANSI codes — skip
            return;
        }
        let event = Event {
            id: uuid::Uuid::new_v4().to_string(),
            timestamp: chrono::Utc::now(),
            level: if is_error {
                crate::events::EventLevel::Error
            } else {
                crate::events::EventLevel::Info
            },
            source: source.to_string(),
            text: cleaned,
            metadata: None,
        };
        self.events.push(event);
    }

    /// Push stderr output: try to detect agent-role-prefixed lines and
    /// render them with per-role colors instead of all red.
    pub fn push_raw_stderr(&mut self, text: &str) {
        let cleaned = strip_ansi(text);
        if cleaned.trim().is_empty() && !text.trim().is_empty() {
            return;
        }

        let (detected_role, is_error) = detect_agent_role(&cleaned);

        let event = Event {
            id: uuid::Uuid::new_v4().to_string(),
            timestamp: chrono::Utc::now(),
            level: if is_error {
                crate::events::EventLevel::Error
            } else {
                crate::events::EventLevel::Info
            },
            source: detected_role.unwrap_or_else(|| "stderr".to_string()),
            text: strip_agent_prefix(&cleaned),
            metadata: None,
        };
        self.events.push(event);
    }

    pub fn clear(&mut self) {
        self.events.clear();
        self.scroll_offset = 0;
    }

    pub fn scroll_up(&mut self, lines: usize) {
        self.auto_scroll = false;
        self.scroll_offset = self.scroll_offset.saturating_add(lines);
    }

    pub fn scroll_down(&mut self, lines: usize) {
        self.auto_scroll = false;
        self.scroll_offset = self.scroll_offset.saturating_sub(lines);
    }

    pub fn page_up(&mut self, page_lines: usize) {
        self.scroll_up(page_lines);
    }

    pub fn page_down(&mut self, page_lines: usize) {
        self.scroll_down(page_lines);
    }

    pub fn jump_top(&mut self) {
        self.auto_scroll = false;
        self.scroll_offset = self.events.len().saturating_sub(1);
    }

    pub fn jump_bottom(&mut self) {
        self.auto_scroll = true;
        self.scroll_offset = 0;
    }

    pub fn resume_auto_scroll(&mut self) {
        self.auto_scroll = true;
        self.scroll_offset = 0;
    }

    pub fn filtered_events(&self) -> Vec<&Event> {
        if let Some(ref filter) = self.filter_text {
            let f = filter.to_lowercase();
            self.events
                .iter()
                .filter(|e| {
                    e.text.to_lowercase().contains(&f)
                        || e.source.to_lowercase().contains(&f)
                })
                .collect()
        } else {
            self.events.iter().collect()
        }
    }

    /// Get the color for a given event source (agent role).
    fn source_color(source: &str) -> Color {
        match source.to_lowercase().as_str() {
            "qlarifier" | "qualifier" => palette::CYAN,
            "instruqtor" => palette::MAGENTA,
            "construqtor" => palette::YELLOW,
            "inspeqtor" => palette::GREEN,
            "sqavenger" => palette::BLUE,
            "attraqtor" => palette::RED,
            "qontroller" => palette::BRIGHT_MAGENTA,
            "stdout" => palette::LIGHT_GREY,
            "stderr" => palette::ORANGE,
            "system" => palette::STEEL_GREY,
            "user" => palette::WHITE,
            "assistant" => palette::CYAN,
            _ => {
                let hash = source.bytes().fold(0u8, |a, b| a.wrapping_add(b));
                Color::Indexed(16 + (hash % 216))
            }
        }
    }

    pub fn render(&self, buf: &mut Buffer, area: Rect) {
        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Agent Output ")
            .border_style(Style::default().fg(Color::Indexed(244)));

        let inner_area = block.inner(area);
        block.render(area, buf);

        // Build event lines (wrapped text will be handled by Paragraph)
        let filtered = self.filtered_events();
        if filtered.is_empty() {
            let placeholder = Paragraph::new("Waiting for agent output...")
                .style(Style::default().fg(Color::Indexed(250)))
                .wrap(Wrap { trim: false });
            placeholder.render(inner_area, buf);
            return;
        }

        let all_lines = Self::build_event_lines(&filtered);

        // Compute scroll offset
        let total_lines = all_lines.len();
        let visible = inner_area.height as usize;
        let max_offset = total_lines.saturating_sub(visible);
        let offset = if self.auto_scroll {
            max_offset
        } else {
            self.scroll_offset.min(max_offset)
        };

        // Select visible lines
        let visible_lines: Vec<Line> = all_lines.into_iter().skip(offset).take(visible).collect();

        // Full-width rendering — no crane branding overlay
        let paragraph = Paragraph::new(visible_lines).wrap(Wrap { trim: true });
        paragraph.render(inner_area, buf);
    }

    /// Build ratatui Line objects from filtered events
    fn build_event_lines<'a>(filtered: &'a [&'a Event]) -> Vec<Line<'a>> {
        let mut lines: Vec<Line> = Vec::new();
        for event in filtered {
            let color = Self::source_color(&event.source);

            if event.source == "stdout" || event.source == "stderr" || event.source == "system" {
                let line = Line::from(Span::styled(&event.text, Style::default().fg(color)));
                lines.push(line);
            } else if is_agent_source(&event.source) {
                let line = Line::from(Span::styled(&event.text, Style::default().fg(color)));
                lines.push(line);
            } else {
                let prefix = format!(
                    "{} [{}] ",
                    event.timestamp.format("%H:%M:%S"),
                    event.source
                );
                let line = Line::from(vec![
                    Span::styled(prefix, Style::default().fg(palette::STEEL_GREY)),
                    Span::styled(&event.text, Style::default().fg(color)),
                ]);
                lines.push(line);
            }
        }
        lines
    }
}

/// Check if a source string is a known agent role (no prefix needed)
fn is_agent_source(source: &str) -> bool {
    matches!(
        source.to_lowercase().as_str(),
        "qlarifier" | "qualifier" | "instruqtor" | "construqtor" 
        | "inspeqtor" | "sqavenger" | "attraqtor" | "qontroller"
    )
}

/// Detect agent role from a line that may have a prefix like "[Qlarifier] stdout text"
fn detect_agent_role(line: &str) -> (Option<String>, bool) {
    let trimmed = line.trim();
    if !trimmed.starts_with('[') {
        return (None, false);
    }
    
    for role in &["Qlarifier", "instruQtor", "construQtor", "inspeQtor",
                   "Qualifier", "sQavenger", "attraQtor", "Qontroller"] {
        if trimmed.starts_with(&format!("[{}]", role)) {
            return (Some(role.to_string()), false);
        }
    }
    (None, true)  // unknown prefix = likely error
}

/// Strip the agent prefix like "[RoleName] stdout " from a line
fn strip_agent_prefix(line: &str) -> String {
    let trimmed = line.trim();
    for role in &["Qlarifier", "instruQtor", "construQtor", "inspeQtor",
                   "Qualifier", "sQavenger", "attraQtor", "Qontroller"] {
        let prefix = format!("[{}]", role);
        if let Some(rest) = trimmed.strip_prefix(&prefix) {
            let rest = rest.trim_start();
            for indicator in &["stdout", "stderr"] {
                if let Some(inner) = rest.strip_prefix(indicator) {
                    return inner.trim_start().to_string();
                }
            }
            return rest.trim_start().to_string();
        }
    }
    line.to_string()
}

/// Strip ANSI escape sequences from a string using the `strip-ansi-escapes` crate.
fn strip_ansi(text: &str) -> String {
    let bytes = strip_ansi_escapes::strip(text);
    String::from_utf8_lossy(&bytes).into_owned()
}
