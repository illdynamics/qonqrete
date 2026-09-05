use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Widget, Wrap},
};

/// Command palette modal — shows quick commands
pub struct CommandPalette;

impl CommandPalette {
    pub fn render(buf: &mut Buffer, parent_area: Rect) {
        let w = parent_area.width.min(40);
        let h = 16;
        let x = parent_area.x + (parent_area.width.saturating_sub(w)) / 2;
        let y = parent_area.y + (parent_area.height.saturating_sub(h)) / 2;
        let area = Rect::new(x, y, w, h);

        Clear.render(area, buf);

        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Command Palette ")
            .border_style(Style::default().fg(Color::Indexed(202)))
            .style(Style::default().bg(Color::Indexed(236)).fg(Color::Indexed(250)));

        let inner = block.inner(area);
        block.render(area, buf);

        let items = vec![
            Line::from(""),
            Line::from("  Quick Commands:"),
            Line::from(""),
            Line::from("  /run cargo test     Run tests"),
            Line::from("  /run git status     Git status"),
            Line::from("  /shell zsh          Open shell"),
            Line::from("  /clear              Clear view"),
            Line::from("  /debug              Diagnostics"),
            Line::from("  /quit               Exit"),
            Line::from(""),
            Line::from("  Press Esc to close"),
        ];

        let p = Paragraph::new(items).wrap(Wrap { trim: true });
        p.render(inner, buf);
    }
}
