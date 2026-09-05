use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Widget, Wrap},
};

/// Diagnostics panel showing internal state
pub struct DiagnosticsPanel {
    pub mode: String,
    pub terminal_size: (u16, u16),
    pub is_tty: bool,
    pub config_path: String,
    pub statusline_command: String,
    pub last_statusline_duration_ms: u64,
    pub last_statusline_error: Option<String>,
    pub event_count: usize,
    pub scroll_offset: usize,
    pub current_phase: String,
    pub last_exit_code: Option<i32>,
    pub debug_log_path: String,
}

impl DiagnosticsPanel {
    pub fn render(&self, buf: &mut Buffer, parent_area: Rect) {
        let w = parent_area.width.min(55);
        let h = parent_area.height.min(18);
        let x = parent_area.x + (parent_area.width.saturating_sub(w)) / 2;
        let y = parent_area.y + (parent_area.height.saturating_sub(h)) / 2;
        let area = Rect::new(x, y, w, h);

        Clear.render(area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Diagnostics ")
            .border_style(Style::default().fg(Color::Indexed(202)))
            .style(Style::default().bg(Color::Indexed(236)).fg(Color::Indexed(250)));

        let inner = block.inner(area);
        block.render(area, buf);

        let lines = vec![
            Line::from(""),
            Line::from(format!("  Mode:               {}", self.mode)),
            Line::from(format!(
                "  Terminal:           {}x{}",
                self.terminal_size.0, self.terminal_size.1
            )),
            Line::from(format!("  TTY:                {}", self.is_tty)),
            Line::from(format!("  Config:             {}", self.config_path)),
            Line::from(format!(
                "  Statusline cmd:     {}",
                self.statusline_command
            )),
            Line::from(format!(
                "  Statusline dur:     {}ms",
                self.last_statusline_duration_ms
            )),
            Line::from(format!(
                "  Statusline err:     {:?}",
                self.last_statusline_error
            )),
            Line::from(format!("  Events:             {}", self.event_count)),
            Line::from(format!(
                "  Scroll offset:      {}",
                self.scroll_offset
            )),
            Line::from(format!("  Phase:              {}", self.current_phase)),
            Line::from(format!(
                "  Last exit code:     {:?}",
                self.last_exit_code
            )),
            Line::from(format!("  Debug log:          {}", self.debug_log_path)),
            Line::from(""),
            Line::from("  Press Esc to close"),
        ];

        let p = Paragraph::new(lines).wrap(Wrap { trim: true });
        p.render(inner, buf);
    }
}
