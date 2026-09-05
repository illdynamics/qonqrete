use crate::status::{self, StatusState};
use crate::theme::{QonQreteTheme, AgentIcon};
use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
};
use unicode_width::UnicodeWidthStr;

/// The built-in QonQrete status bar widget
#[derive(Debug, Clone)]
pub struct StatusBarWidget<'a> {
    pub state: &'a StatusState,
    pub theme: &'a QonQreteTheme,
    pub statusline_override: Option<&'a str>,
    pub width: u16,
    /// TUI version string (for the [vX.X.X] segment next to QQ)
    pub version: &'a str,
}

impl<'a> StatusBarWidget<'a> {
    pub fn new(state: &'a StatusState, theme: &'a QonQreteTheme) -> Self {
        Self {
            state,
            theme,
            statusline_override: None,
            width: 80,
            version: "",
        }
    }

    pub fn with_override(mut self, line: &'a str) -> Self {
        self.statusline_override = Some(line);
        self
    }

    pub fn with_width(mut self, w: u16) -> Self {
        self.width = w;
        self
    }

    pub fn with_version(mut self, v: &'a str) -> Self {
        self.version = v;
        self
    }

    /// Render the status bar into a buffer at a given Rect
    pub fn render_full(&self, buf: &mut Buffer, area: Rect) {
        let line = if let Some(ov) = self.statusline_override {
            ov.to_string()
        } else {
            self.build_builtin_bar()
        };

        // build_builtin_bar already pads to self.width; truncate only as safety net
        let display_line = truncate_unicode(&line, area.width as usize);

        // Paint colored segments on top using QonQrete palette
        self.paint_colored_segments(buf, area, &display_line);
    }

    /// Three-part float layout (left / centered / right) on a single line:
    ///   Left:   ╭─[ꝖꝖ]─[vX.X.X]─❯❯❯ Qlarifier ⠛
    ///   Center: Cycle=N/Max=M · Total=MM:SS Agent=MM:SS · Progress: N%
    ///   Right:  · icon ❮❮❮─[code]──╮
    ///
    /// Left sticks to the left edge, right to the right edge, center is
    /// centered in the remaining space. Content is truncated gracefully
    /// when the terminal is too narrow.
    fn build_builtin_bar(&self) -> String {
        let t = self.theme;
        let s = self.state;

        let spinner_frames = t.spinner_frames();
        let spinner = if s.spinner_index < spinner_frames.len() {
            spinner_frames[s.spinner_index]
        } else {
            spinner_frames[0]
        };

        let pct = s.progress.unwrap_or(0.0);


        // Model code display (fla, fla-T, pro, pro-T)
        let model_display = model_display_code(&s.model_code);

        // Agent icon — auto-switches based on current agent name
        let icon = AgentIcon::from_role(&s.agent_name).as_str();

        // Version
        let version_str = if self.version.is_empty() { "?" } else { self.version };

        // Max cycles from max_cycles field (not budget)

        // ── Build three parts ──

        // Left part: frame, QQ, version, chevrons, agent name, spinner
        let left = format!(
            "{frame_start}[{qq}]{dash}[v{ver}]{dash}{chev_r} {agent} {spinner}",
            frame_start = t.frame_start(),
            qq = t.qq(),
            dash = t.bar_body(),
            ver = version_str,
            chev_r = t.chevrons_right(),
            agent = s.agent_name,
            spinner = spinner,
        );

        // Center part: cycle/max, times, progress
        let max_display = if s.max_cycles == 0 { "∞".to_string() } else { s.max_cycles.to_string() };
        let center = format!(
            "Cycle={cycle}/{max_display} {dot} Total={total} Agent={active} {dot} Progress: {pct}%",
            cycle = s.cycle,
            max_display = max_display,
            dot = t.bar_sep(),
            total = status::fmt_elapsed(s.total_elapsed_secs()),
            active = status::fmt_active(s.active_secs()),
            pct = pct as u64,
        );

        // Right part: action status, icon, chevrons left, model, frame end
        let action_text = s.action_status.as_deref().unwrap_or("");
        let right = if action_text.is_empty() {{
            format!(
                "{dot} {icon} {chev_l}{dash}[{model}]{dash}{frame_end}",
                dot = t.bar_sep(),
                icon = icon,
                chev_l = t.chevrons_left(),
                dash = t.bar_body(),
                model = model_display,
                frame_end = t.frame_end(),
            )
        }} else {{
            format!(
                "{dot} Act:{action} {dot} {icon} {chev_l}{dash}[{model}]{dash}{frame_end}",
                dot = t.bar_sep(),
                action = action_text,
                icon = icon,
                chev_l = t.chevrons_left(),
                dash = t.bar_body(),
                model = model_display,
                frame_end = t.frame_end(),
            )
        }};

        // ── Three-part float layout ──
        let w = self.width as usize;
        let left_w = left.chars().count();
        let center_w = center.chars().count();
        let right_w = right.chars().count();
        let sep: usize = 1; // minimum spaces between parts

        let min_needed = left_w + sep + right_w;
        if w < min_needed {
            // Too narrow for all three parts: show left only, truncated
            if left.chars().count() > w {
                format!("{}\u{2026}", left.chars().take(w.saturating_sub(1)).collect::<String>())
            } else {
                format!("{:width$}", left, width = w)
            }
        } else {
            // Space available for the center region (accounting for separators)
            let center_region = w.saturating_sub(left_w + right_w + 2 * sep);
            if center_region >= center_w {
                // Center fits: pad evenly on both sides so it's centered
                let pad_left = (center_region - center_w) / 2;
                let pad_right = center_region - center_w - pad_left;
                format!(
                    "{}{}{}{}{}",
                    left,
                    " ".repeat(sep + pad_left),
                    center,
                    " ".repeat(pad_right + sep),
                    right,
                )
            } else if center_region >= 1 {
                // Center too wide: truncate center with ellipsis, keep separators
                let trim_center = if center_region > 1 {
                    format!("{}\u{2026}", center.chars().take(center_region - 1).collect::<String>())
                } else {
                    "\u{2026}".to_string()
                };
                format!(
                    "{}{}{}{}{}",
                    left,
                    " ".repeat(sep),
                    trim_center,
                    " ".repeat(sep),
                    right,
                )
            } else {
                // Not enough room even for a truncated center
                let pad = w.saturating_sub(left_w + right_w);
                format!("{}{}{}", left, " ".repeat(pad), right)
            }
        }
    }

    fn paint_colored_segments(&self, buf: &mut Buffer, area: Rect, line: &str) {
        let t = self.theme;
        let bg = ratatui::style::Color::Black;

        // First pass: set default foreground for all chars (warm yellow on black bg)
        for (x, ch) in line.chars().enumerate() {
            if x >= area.width as usize {
                break;
            }
            if let Some(cell) = buf.cell_mut((area.x + x as u16, area.y)) {
                cell.set_char(ch);
                cell.set_style(Style::default()
                    .fg(t.color_agent_name())
                    .bg(bg));
            }
        }

        // Paint ꝖꝖ/QQ gold
        if let Some(pos) = line.find(t.qq()) {
            for i in 0..t.qq().chars().count() {
                let idx = line[..pos].chars().count() + i;
                if idx < area.width as usize {
                    if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                        cell.set_style(Style::default()
                            .fg(t.color_qq())
                            .bg(bg));
                    }
                }
            }
        }

        // Paint version segment gold/orange: [vX.X.X]
        if let Some(pos) = line.find("[v") {
            if let Some(end_pos) = line[pos..].find(']') {
                let ver_end = pos + end_pos + 1;
                for idx in (line[..pos].chars().count())..(line[..ver_end].chars().count()) {
                    if idx < area.width as usize {
                        if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                            cell.set_style(Style::default()
                                .fg(t.color_progress_value())
                                .bg(bg));
                        }
                    }
                }
            }
        }

        // Paint spinner orange — match any braille or ASCII spinner char
        let spinner_frames = t.spinner_frames();
        for frame in spinner_frames {
            if let Some(pos) = line.find(*frame) {
                for i in 0..frame.chars().count() {
                    let idx = line[..pos].chars().count() + i;
                    if idx < area.width as usize {
                        if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                            cell.set_style(Style::default()
                                .fg(t.color_spinner())
                                .bg(bg));
                        }
                    }
                }
            }
        }

        // Paint agent icon (colored by agent role)
        let icon = AgentIcon::from_role(&self.state.agent_name).as_str();
        if let Some(pos) = line.find(icon) {
            let icon_color = agent_color_for_name(&self.state.agent_name);
            for i in 0..icon.chars().count() {
                let idx = line[..pos].chars().count() + i;
                if idx < area.width as usize {
                    if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                        cell.set_style(Style::default()
                            .fg(icon_color)
                            .bg(bg));
                    }
                }
            }
        }

        // Paint model code (fla, fla-T, pro, pro-T) in gold
        for model_label in &["fla", "fla-T", "pro", "pro-T"] {
            if let Some(pos) = line.find(model_label) {
                for i in 0..model_label.chars().count() {
                    let idx = line[..pos].chars().count() + i;
                    if idx < area.width as usize {
                        if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                            cell.set_style(Style::default()
                                .fg(t.color_model_value())
                                .bg(bg));
                        }
                    }
                }
            }
        }

        // Paint brackets and frame chars
        for (idx, ch) in line.chars().enumerate() {
            if idx >= area.width as usize {
                break;
            }
            if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                match ch {
                    '[' | ']' => {
                        cell.set_style(Style::default()
                            .fg(t.color_bracket())
                            .bg(bg));
                    }
                    '\u{256d}' | '\u{256e}' | '\u{2500}' => {
                        cell.set_style(Style::default()
                            .fg(t.color_frame())
                            .bg(bg));
                    }
                    '\u{276f}' | '\u{276e}' => {
                        cell.set_style(Style::default()
                            .fg(t.color_qq())
                            .bg(bg));
                    }
                    '\u{00b7}' => {
                        cell.set_style(Style::default()
                            .fg(ratatui::style::Color::Indexed(238))
                            .bg(bg));
                    }
                    _ => {}
                }
            }
        }

        // Paint label prefix values with correct colors
        for (prefix, color) in &[
            ("Cycle=", t.color_cycle_value()),
            ("Max=", t.color_cycle_value()),
            ("Total=", t.color_time_value()),
            ("Agent=", t.color_time_value()),
            ("Progress:", t.color_progress_value()),
            // TUI-BGP10: paint the live Act:<value>; value shown green on FULLY_DONE.
            ("Act:", t.color_action_value()),
        ] {
            if let Some(pos) = line.find(prefix) {
                let start = pos + prefix.len();
                // B3: paint the frozen Total green once the run reaches FULLY_DONE;
                // TUI-BGP10: also paint the Act value green when the run has finished
                // successfully (terminal_reached + FULLY_DONE).
                let fully_done_action = self.state.action_status.as_deref().map(|a| a.eq_ignore_ascii_case("FULLY_DONE")).unwrap_or(false);
                let color = if *prefix == "Total=" && self.state.terminal_reached {
                    ratatui::style::Color::Green
                } else if *prefix == "Act:" && self.state.terminal_reached && fully_done_action {
                    ratatui::style::Color::Green
                } else {
                    *color
                };
                for (i, ch) in line[start..].chars().enumerate() {
                    if ch == ' ' || ch == '%' || ch == '\u{00b7}' || ch == ']' || ch == '[' || ch == '\u{276e}' || ch == '\u{276f}' {
                        break;
                    }
                    let idx = line[..start].chars().count() + i;
                    if idx < area.width as usize {
                        if let Some(cell) = buf.cell_mut((area.x + idx as u16, area.y)) {
                            cell.set_style(Style::default()
                                .fg(color)
                                .bg(bg));
                        }
                    }
                }
            }
        }

    }
}

/// Color for agent icon based on role
fn agent_color_for_name(name: &str) -> ratatui::style::Color {
    match name.to_lowercase().as_str() {
        "qlarifier" | "qualifier" => ratatui::style::Color::Indexed(51),   // cyan
        "instruqtor" => ratatui::style::Color::Indexed(201),                 // magenta
        "construqtor" => ratatui::style::Color::Indexed(220),               // gold
        "inspeqtor" => ratatui::style::Color::Indexed(42),                  // green
        "sqavenger" => ratatui::style::Color::Indexed(33),                  // blue
        "attraqtor" => ratatui::style::Color::Indexed(196),                 // red
        "qontroller" => ratatui::style::Color::Indexed(207),                // bright magenta
        _ => ratatui::style::Color::Indexed(228),                           // warm yellow
    }
}

/// Convert model code from deepseek-style names to display codes. Idempotent.
/// "deepseek-v4-flash" → "fla"
/// "deepseek-v4-flash-thinking" → "fla-T"
/// "deepseek-v4-pro" → "pro"
/// "deepseek-v4-pro-thinking" → "pro-T"
/// Falls back to trimmed unknown codes.
pub fn model_display_code(code: &str) -> String {
    let lower = code.to_lowercase();
    if lower == "fla" || lower == "f" || (lower.contains("flash") && !lower.contains("thinking")) {
        "fla".to_string()
    } else if lower == "fla-t" || lower == "ft" || (lower.contains("flash") && lower.contains("thinking")) {
        "fla-T".to_string()
    } else if lower == "pro" || lower == "p" || (lower.contains("pro") && !lower.contains("thinking") && !lower.contains("pro-t")) {
        "pro".to_string()
    } else if lower == "pro-t" || lower == "pt" || (lower.contains("pro") && lower.contains("thinking")) {
        "pro-T".to_string()
    } else if code.is_empty() || code == "?" {
        "?".to_string()
    } else {
        if code.len() > 8 {
            format!("{}\u{2026}", &code[..7])
        } else {
            code.to_string()
        }
    }
}

/// Truncate a string to `max_width` visual columns using Unicode width
fn truncate_unicode(s: &str, max_width: usize) -> String {
    let mut result = String::new();
    let mut w = 0;
    for ch in s.chars() {
        let cw = UnicodeWidthStr::width(ch.to_string().as_str());
        if w + cw > max_width {
            break;
        }
        result.push(ch);
        w += cw;
    }
    result
}
