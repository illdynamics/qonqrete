use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// What action a key event maps to
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InputAction {
    Interrupt,      // Ctrl+C (first press) — stop the agent (second press quits TUI)
    #[allow(dead_code)]
    Kill,           // Ctrl+C (second press in quick succession) — quit the TUI
    Quit,           // Ctrl+\ — immediate hard quit
    SafeInterrupt,  // ESC — safely stop only the agent, never quit TUI
    CommandPalette,
    Help,
    #[allow(dead_code)]
    CloseModal,
    Submit,
    ScrollUp,
    ScrollDown,
    PageUp,
    PageDown,
    JumpTop,
    JumpBottom,
    ClearView,
    ForceRedraw,
    PauseAutoScroll,
    ShowDiagnostics,
    Char(char),
    Backspace,
    #[allow(dead_code)]
    Enter,
    Tab,
    #[allow(dead_code)]
    Escape,
    None,
}

/// Convert a crossterm KeyEvent into an InputAction based on keybindings
pub fn map_key(event: KeyEvent) -> InputAction {
    match event {
        // Ctrl+C — first press interrupts agent, second press kills TUI
        KeyEvent {
            code: KeyCode::Char('c'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::Interrupt,

        // Ctrl+\ — immediate hard quit
        KeyEvent {
            code: KeyCode::Char('\\'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::Quit,

        // ESC — safe interrupt (stop only the agent, never quit the TUI)
        KeyEvent {
            code: KeyCode::Esc, ..
        } => InputAction::SafeInterrupt,

        // Ctrl+P — command palette
        KeyEvent {
            code: KeyCode::Char('p'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::CommandPalette,

        // ? — help
        KeyEvent {
            code: KeyCode::Char('?'),
            modifiers: KeyModifiers::NONE,
            ..
        } => InputAction::Help,

        // Enter
        KeyEvent {
            code: KeyCode::Enter,
            ..
        } => InputAction::Submit,

        // PageUp
        KeyEvent {
            code: KeyCode::PageUp,
            ..
        } => InputAction::PageUp,

        // PageDown
        KeyEvent {
            code: KeyCode::PageDown,
            ..
        } => InputAction::PageDown,

        // Home
        KeyEvent {
            code: KeyCode::Home,
            ..
        } => InputAction::JumpTop,

        // End
        KeyEvent {
            code: KeyCode::End, ..
        } => InputAction::JumpBottom,

        // Ctrl+L — clear
        KeyEvent {
            code: KeyCode::Char('l'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::ClearView,

        // Ctrl+R — redraw
        KeyEvent {
            code: KeyCode::Char('r'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::ForceRedraw,

        // Ctrl+S — pause auto-scroll
        KeyEvent {
            code: KeyCode::Char('s'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::PauseAutoScroll,

        // Ctrl+G — diagnostics
        KeyEvent {
            code: KeyCode::Char('g'),
            modifiers: KeyModifiers::CONTROL,
            ..
        } => InputAction::ShowDiagnostics,

        // Up arrow
        KeyEvent {
            code: KeyCode::Up, ..
        } => InputAction::ScrollUp,

        // Down arrow
        KeyEvent {
            code: KeyCode::Down,
            ..
        } => InputAction::ScrollDown,

        // Tab
        KeyEvent {
            code: KeyCode::Tab, ..
        } => InputAction::Tab,

        // Backspace
        KeyEvent {
            code: KeyCode::Backspace,
            ..
        } => InputAction::Backspace,

        // Printable characters
        KeyEvent {
            code: KeyCode::Char(c),
            modifiers: KeyModifiers::NONE | KeyModifiers::SHIFT,
            ..
        } => InputAction::Char(c),

        _ => InputAction::None,
    }
}
