use crossterm::event::{KeyCode, KeyModifiers};

/// Configurable keybinding map (for future config-file customization)
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct Keymap {
    pub quit: KeyBinding,
    pub command_palette: KeyBinding,
    pub help: KeyBinding,
    pub close_modal: KeyBinding,
    pub page_up: KeyBinding,
    pub page_down: KeyBinding,
    pub jump_top: KeyBinding,
    pub jump_bottom: KeyBinding,
    pub clear_view: KeyBinding,
    pub force_redraw: KeyBinding,
    pub pause_auto_scroll: KeyBinding,
    pub show_diagnostics: KeyBinding,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct KeyBinding {
    pub code: KeyCode,
    pub modifiers: KeyModifiers,
}

impl Default for Keymap {
    fn default() -> Self {
        Self {
            quit: KeyBinding {
                code: KeyCode::Char('c'),
                modifiers: KeyModifiers::CONTROL,
            },
            command_palette: KeyBinding {
                code: KeyCode::Char('p'),
                modifiers: KeyModifiers::CONTROL,
            },
            help: KeyBinding {
                code: KeyCode::Char('?'),
                modifiers: KeyModifiers::NONE,
            },
            close_modal: KeyBinding {
                code: KeyCode::Esc,
                modifiers: KeyModifiers::NONE,
            },
            page_up: KeyBinding {
                code: KeyCode::PageUp,
                modifiers: KeyModifiers::NONE,
            },
            page_down: KeyBinding {
                code: KeyCode::PageDown,
                modifiers: KeyModifiers::NONE,
            },
            jump_top: KeyBinding {
                code: KeyCode::Home,
                modifiers: KeyModifiers::NONE,
            },
            jump_bottom: KeyBinding {
                code: KeyCode::End,
                modifiers: KeyModifiers::NONE,
            },
            clear_view: KeyBinding {
                code: KeyCode::Char('l'),
                modifiers: KeyModifiers::CONTROL,
            },
            force_redraw: KeyBinding {
                code: KeyCode::Char('r'),
                modifiers: KeyModifiers::CONTROL,
            },
            pause_auto_scroll: KeyBinding {
                code: KeyCode::Char('s'),
                modifiers: KeyModifiers::CONTROL,
            },
            show_diagnostics: KeyBinding {
                code: KeyCode::Char('g'),
                modifiers: KeyModifiers::CONTROL,
            },
        }
    }
}
