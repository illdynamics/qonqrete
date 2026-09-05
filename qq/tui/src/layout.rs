use ratatui::layout::{Constraint, Direction, Layout, Rect};

/// Layout configuration for the main TUI
#[derive(Debug, Clone)]
pub struct AppLayout {
    pub status_bar: Rect,
    pub output_view: Rect,
    pub input_box: Rect,
}

/// Minimum supported terminal: 80x20
pub const MIN_COLS: u16 = 80;
pub const MIN_ROWS: u16 = 20;

/// Compute the three main areas from the full terminal Rect
pub fn compute_layout(area: Rect) -> AppLayout {
    // Status bar: 1 row at top
    // Input box: 3 rows at bottom
    // Output view: remaining middle
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),  // status bar
            Constraint::Min(1),     // output (flexible)
            Constraint::Length(3),  // input
        ])
        .split(area);

    AppLayout {
        status_bar: chunks[0],
        output_view: chunks[1],
        input_box: chunks[2],
    }
}

/// Check if terminal is large enough
pub fn check_minimum_size(cols: u16, rows: u16) -> Option<String> {
    if cols < MIN_COLS || rows < MIN_ROWS {
        Some(format!(
            "Terminal too small ({}x{}). Minimum: {}x{}",
            cols, rows, MIN_COLS, MIN_ROWS
        ))
    } else {
        None
    }
}
