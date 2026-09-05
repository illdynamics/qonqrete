use ratatui::style::Color;

/// QonQrete color palette — ANSI 256
/// Matches the user's PS1 colors: orange/yellow/grey on black
#[derive(Debug)]
pub struct QonQreteTheme {
    pub ascii_mode: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)]
pub enum QonQreteColor {
    DarkFrame,
    SteelGrey,
    ConcreteLightGrey,
    Gold,
    EmberOrange,
    FireRed,
    BloodRed,
    WarmYellow,
    White,
    Black,
}

impl QonQreteColor {
    pub fn to_ratatui(self) -> Color {
        match self {
            QonQreteColor::DarkFrame => Color::Indexed(236),
            QonQreteColor::SteelGrey => Color::Indexed(244),
            QonQreteColor::ConcreteLightGrey => Color::Indexed(250),
            QonQreteColor::Gold => Color::Indexed(220),
            QonQreteColor::EmberOrange => Color::Indexed(202),
            QonQreteColor::FireRed => Color::Indexed(196),
            QonQreteColor::BloodRed => Color::Indexed(160),
            QonQreteColor::WarmYellow => Color::Indexed(228),
            QonQreteColor::White => Color::Indexed(15),
            QonQreteColor::Black => Color::Indexed(0),
        }
    }
}

/// Per-agent icons (prompt-crane.md spec)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentIcon {
    Qlarifier,   // ¿Q?
    InstruQtor,  // ⊢Q⇢
    ConstruQtor, // ⟬Q⟭
    InspeQtor,   // ⧉Q⌖
    Qualifier,   // ⦿Q✓
}

impl AgentIcon {
    pub fn as_str(&self) -> &'static str {
        match self {
            AgentIcon::Qlarifier => "\u{00BF}Q\u{003F}",    // ¿Q?
            AgentIcon::InstruQtor => "\u{22A2}Q\u{21E2}",    // ⊢Q⇢
            AgentIcon::ConstruQtor => "\u{27EC}Q\u{27ED}",   // ⟬Q⟭
            AgentIcon::InspeQtor => "\u{29C9}Q\u{2316}",     // ⧉Q⌖
            AgentIcon::Qualifier => "\u{29BF}Q\u{2713}",     // ⦿Q✓
        }
    }

    pub fn from_role(role: &str) -> Self {
        match role.to_lowercase().as_str() {
            "qlarifier" => AgentIcon::Qlarifier,
            "instruqtor" => AgentIcon::InstruQtor,
            "construqtor" => AgentIcon::ConstruQtor,
            "inspeqtor" => AgentIcon::InspeQtor,
            "qualifier" => AgentIcon::Qualifier,
            _ => AgentIcon::Qlarifier, // default
        }
    }
}

impl QonQreteTheme {
    pub fn new(ascii_mode: bool) -> Self {
        Self { ascii_mode }
    }

    #[allow(dead_code)]


    pub fn is_ascii(&self) -> bool {
        self.ascii_mode
    }

    #[allow(dead_code)]


    pub fn ascii(&self) -> bool {
        self.ascii_mode
    }

    pub fn frame_start(&self) -> &'static str {
        if self.ascii_mode { "+-" } else { "\u{256d}\u{2500}" }
    }
    pub fn frame_end(&self) -> &'static str {
        if self.ascii_mode { "-+" } else { "\u{2500}\u{256e}" }
    }

    pub fn bar_body(&self) -> &'static str {
        "\u{2500}" // ─ always (works in ASCII fallback too)
    }
    pub fn bar_sep(&self) -> &'static str {
        if self.ascii_mode { "." } else { "\u{00b7}" } // ·
    }
    pub fn qq(&self) -> &'static str {
        if self.ascii_mode { "QQ" } else { "\u{a756}\u{a756}" } // ꝖꝖ
    }
    pub fn chevrons_right(&self) -> &'static str {
        if self.ascii_mode { ">>>" } else { "\u{276f}\u{276f}\u{276f}" } // ❯❯❯
    }
    pub fn chevrons_left(&self) -> &'static str {
        if self.ascii_mode { "<<<" } else { "\u{276e}\u{276e}\u{276e}" } // ❮❮❮
    }
    #[allow(dead_code)]

    #[allow(dead_code)]
    pub fn lightning(&self) -> &'static str {
        if self.ascii_mode { "!!" } else { "\u{21af}\u{21af}" } // ↯↯
    }
    #[allow(dead_code)]
    pub fn lightning_single(&self) -> &'static str {
        if self.ascii_mode { "!" } else { "\u{21af}" } // ↯
    }
    #[allow(dead_code)]
    pub fn approx(&self) -> &'static str {
        if self.ascii_mode { "~" } else { "\u{2248}" } // ≈
    }

    pub fn spinner_frames(&self) -> &'static [&'static str] {
        if self.ascii_mode {
            &["|", "/", "-", "\\"]
        } else {
            &["\u{2801}", "\u{2803}", "\u{2807}", "\u{2847}", "\u{28c7}",
              "\u{28e7}", "\u{28f7}", "\u{28ff}", "\u{287f}", "\u{283f}",
              "\u{281f}", "\u{281b}", "\u{2819}", "\u{2809}"]
        }
    }


    // ─── Colors by role ───

    pub fn color_frame(&self) -> Color {
        QonQreteColor::DarkFrame.to_ratatui()
    }
    pub fn color_bracket(&self) -> Color {
        QonQreteColor::SteelGrey.to_ratatui()
    }
    pub fn color_qq(&self) -> Color {
        QonQreteColor::Gold.to_ratatui()
    }
    pub fn color_agent_name(&self) -> Color {
        QonQreteColor::WarmYellow.to_ratatui()
    }
    pub fn color_spinner(&self) -> Color {
        QonQreteColor::EmberOrange.to_ratatui()
    }
    #[allow(dead_code)]

    pub fn color_label(&self) -> Color {
        QonQreteColor::SteelGrey.to_ratatui()
    }
    pub fn color_model_value(&self) -> Color {
        QonQreteColor::Gold.to_ratatui()
    }
    pub fn color_cycle_value(&self) -> Color {
        QonQreteColor::FireRed.to_ratatui()
    }
    pub fn color_time_value(&self) -> Color {
        QonQreteColor::EmberOrange.to_ratatui()
    }
    #[allow(dead_code)]

    pub fn color_budget_value(&self) -> Color {
        QonQreteColor::Gold.to_ratatui()
    }
    pub fn color_progress_value(&self) -> Color {
        QonQreteColor::EmberOrange.to_ratatui()
    }
    // TUI-BGP10: live action-status value color (amber). Overridden to green in
    // status_bar when the run reaches FULLY_DONE/terminal_reached.
    pub fn color_action_value(&self) -> Color {
        QonQreteColor::WarmYellow.to_ratatui()
    }
}
