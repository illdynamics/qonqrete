use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Widget},
};

/// The input box at the bottom of the TUI
#[derive(Debug, Clone, Default)]
pub struct InputBox {
    pub buffer: String,
    pub cursor_pos: usize,
    pub prompt: String,
}

impl InputBox {
    pub fn new() -> Self {
        Self {
            buffer: String::new(),
            cursor_pos: 0,
            prompt: "> ".into(),
        }
    }

    pub fn push_char(&mut self, c: char) {
        self.buffer.insert(self.cursor_pos, c);
        self.cursor_pos += 1;
    }

    pub fn backspace(&mut self) {
        if self.cursor_pos > 0 {
            self.cursor_pos -= 1;
            self.buffer.remove(self.cursor_pos);
        }
    }

    #[allow(dead_code)]


    pub fn cursor_left(&mut self) {
        if self.cursor_pos > 0 {
            self.cursor_pos -= 1;
        }
    }

    #[allow(dead_code)]


    pub fn cursor_right(&mut self) {
        if self.cursor_pos < self.buffer.len() {
            self.cursor_pos += 1;
        }
    }

    pub fn take_input(&mut self) -> String {
        let text = self.buffer.clone();
        self.buffer.clear();
        self.cursor_pos = 0;
        text
    }

    #[allow(dead_code)]


    pub fn set_buffer(&mut self, text: &str) {
        self.buffer = text.to_string();
        self.cursor_pos = self.buffer.len();
    }

    pub fn render(&self, buf: &mut Buffer, area: Rect) {
        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Command / Input ")
            .border_style(Style::default().fg(Color::Indexed(244)));

        let inner_area = block.inner(area);
        block.render(area, buf);

        let display = format!("{}{}", self.prompt, self.buffer);
        let cursor_pos = self.prompt.len() + self.cursor_pos;

        let paragraph = Paragraph::new(Line::from(vec![Span::styled(
            &display,
            Style::default().fg(Color::Indexed(250)),
        )]));

        paragraph.render(inner_area, buf);

        // Show cursor
        if cursor_pos < inner_area.width as usize {
            let cursor_x = inner_area.x + cursor_pos as u16;
            if cursor_x < area.right() {
                if let Some(cell) = buf.cell_mut((cursor_x, inner_area.y)) {
                    cell.set_style(Style::default().bg(Color::Indexed(250)).fg(Color::Indexed(0)));
                }
            }
        }
    }
}
