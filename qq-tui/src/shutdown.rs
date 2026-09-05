use crossterm::{
    cursor,
    execute,
    terminal::{self, LeaveAlternateScreen, disable_raw_mode},
};

/// Restore terminal state cleanly.
/// Must be called on exit to prevent leaving the terminal broken.
pub fn restore_terminal() {
    // Disable mouse capture if it was somehow enabled
    let _ = execute!(std::io::stdout(), crossterm::event::DisableMouseCapture);

    // Restore cursor visibility
    let _ = execute!(std::io::stdout(), cursor::Show);

    // Leave alternate screen if we entered it
    let _ = execute!(std::io::stdout(), LeaveAlternateScreen);

    // Disable raw mode
    let _ = disable_raw_mode();

    // Reset colors
    let _ = execute!(
        std::io::stdout(),
        crossterm::style::ResetColor
    );

    // Flush to make sure everything is written
    use std::io::Write;
    let _ = std::io::stdout().flush();
}

/// Register panic hook to restore terminal on crash
pub fn register_panic_hook() {
    let original_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        restore_terminal();
        original_hook(info);
    }));
}

/// Set up raw mode, alternate screen, cursor hiding for TUI.
/// Mouse capture is intentionally NOT enabled — mouse is disabled
/// permanently (vim-style: no mouse interactions except system-level
/// right-click copy/paste).
pub fn enter_tui_mode() -> anyhow::Result<()> {
    crossterm::terminal::enable_raw_mode()?;
    execute!(
        std::io::stdout(),
        terminal::EnterAlternateScreen,
        cursor::Hide,
        crossterm::event::DisableMouseCapture,
    )?;
    Ok(())
}
