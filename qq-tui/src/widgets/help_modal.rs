use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Widget, Wrap},
};

/// Help modal overlay
pub struct HelpModal;

impl HelpModal {
    pub fn render(buf: &mut Buffer, parent_area: Rect) {
        // Center a 50x20 modal
        let w = parent_area.width.min(50);
        let h = parent_area.height.min(20);
        let x = parent_area.x + (parent_area.width.saturating_sub(w)) / 2;
        let y = parent_area.y + (parent_area.height.saturating_sub(h)) / 2;
        let area = Rect::new(x, y, w, h);

        Clear.render(area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Help ")
            .border_style(Style::default().fg(Color::Indexed(220)))
            .style(Style::default().bg(Color::Indexed(236)).fg(Color::Indexed(250)));

        let inner = block.inner(area);
        block.render(area, buf);

        let help_text = vec![
            Line::from(""),
            Line::from("  Keybindings:"),
            Line::from("  Ctrl+C         Quit or interrupt"),
            Line::from("  Ctrl+P         Command palette"),
            Line::from("  ?              This help"),
            Line::from("  Esc            Close modal"),
            Line::from("  Enter          Submit input"),
            Line::from("  PageUp/Down    Scroll output"),
            Line::from("  Home/End       Jump top/bottom"),
            Line::from("  Ctrl+L         Clear view"),
            Line::from("  Ctrl+R         Force redraw"),
            Line::from("  Ctrl+S         Pause auto-scroll"),
            Line::from("  Ctrl+G         Diagnostics"),
            Line::from(""),
            Line::from("  Commands:"),
            Line::from("  /help          Show this help"),
            Line::from("  /quit          Exit qq-tui"),
            Line::from("  /clear         Clear output"),
            Line::from("  /status        Show status"),
            Line::from("  /debug         Diagnostics"),
            Line::from("  /run <cmd>     Run command"),
            Line::from("  /run-pty <cmd> Run in PTY mode"),
            Line::from("  /shell <cmd>   Run shell command"),
            Line::from("  /theme         Show theme info"),
            Line::from("  /filter <txt>  Filter output"),
            Line::from("  /save <path>   Save session"),
            Line::from("  /replay <path> Replay session"),
            Line::from(""),
            Line::from("  Press Esc to close"),
        ];

        let p = Paragraph::new(help_text).wrap(Wrap { trim: true });
        p.render(inner, buf);
    }
}
