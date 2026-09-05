mod app;
mod cli;
mod commands;
mod config;
mod events;
mod input;
mod keymap;
mod layout;
mod logging;
mod messages;
mod pty;
mod qq_events;
mod shutdown;
mod status;
mod status_script;
mod subprocess;
mod theme;
mod widgets;

use clap::Parser;
use cli::{Cli, Commands};
use config::{AppConfig, should_use_ascii};
use events::EventWriter;
use theme::QonQreteTheme;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    // Load config
    let config = AppConfig::load(cli.config.as_deref()).unwrap_or_else(|e| {
        eprintln!("qq-tui: config warning: {}", e);
        AppConfig::default()
    });

    // Init debug logging (to file only)
    let debug_log_path = logging::init_debug_log(cli.debug_log.as_deref());

    // Determine ASCII mode
    let ascii = should_use_ascii(&config, cli.ascii);
    let theme = QonQreteTheme::new(ascii);

    // Determine event output path
    let events_path = cli
        .events_out
        .clone()
        .or_else(|| config.events.path.clone())
        .map(|p| config::shellexpand_path(&p));

    let event_writer = EventWriter::new(events_path);

    // Dispatch based on mode
    match &cli.command {
        Some(Commands::Replay {
            events_jsonl, ..
        }) => {
            run_replay(events_jsonl, &config, &theme).await?;
        }

        Some(Commands::Run {
            qq_events,
            exit_when_done,
            command,
            ..
        }) => {
            // Run mode — requires TUI
            if !config::is_tty() {
                eprintln!("qq-tui: run mode requires a TTY. Use 'qq-tui exec -- <command>' for non-interactive mode.");
                std::process::exit(1);
            }

            shutdown::register_panic_hook();
            shutdown::enter_tui_mode()?;

            let backend = ratatui::backend::CrosstermBackend::new(std::io::stdout());
            let mut terminal = ratatui::Terminal::new(backend)?;

            let result = {
                let mut app = app::App::new(config.clone(), theme, event_writer, debug_log_path);
                app.run_child_session(
                    &mut terminal,
                    &cli,
                    command.clone(),
                    qq_events.clone(),
                    *exit_when_done,
                )
                .await
            };

            shutdown::restore_terminal();
            let exit_code = result?;
            if exit_code != 0 {
                std::process::exit(exit_code);
            }
        }

        Some(Commands::Exec { command }) => {
            app::App::run_exec(command.clone()).await?;
        }

        Some(Commands::StatuslineTest { command }) => {
            app::App::run_statusline_test(command)?;
        }

        None => {
            // Default: interactive mode
            if !config::is_tty() {
                eprintln!("qq-tui: stdout is not a TTY. Use 'qq-tui exec -- <command>' for non-interactive mode.");
                std::process::exit(1);
            }

            shutdown::register_panic_hook();
            shutdown::enter_tui_mode()?;

            let backend = ratatui::backend::CrosstermBackend::new(std::io::stdout());
            let mut terminal = ratatui::Terminal::new(backend)?;

            let result = {
                let mut app = app::App::new(config.clone(), theme, event_writer, debug_log_path);
                app.run_interactive(&mut terminal, &cli).await
            };

            shutdown::restore_terminal();
            result?;
        }
    }

    Ok(())
}

async fn run_replay(
    events_path: &str,
    config: &AppConfig,
    theme: &QonQreteTheme,
) -> anyhow::Result<()> {
    if !config::is_tty() {
        eprintln!("qq-tui: replay mode requires a TTY.");
        std::process::exit(1);
    }

    let path = config::shellexpand_path(events_path);
    let reader = events::EventReader::new(path);
    let typed_events = reader.read_all()?;

    shutdown::register_panic_hook();
    shutdown::enter_tui_mode()?;

    let backend = ratatui::backend::CrosstermBackend::new(std::io::stdout());
    let mut terminal = ratatui::Terminal::new(backend)?;

    let uid = uuid::Uuid::new_v4().to_string()[..8].to_string();
    let status = status::StatusState::new(
        config.agent.name.clone(),
        config.agent.model.clone(),
        config.agent.budget,
        64,  // max_cycles default for replay mode
        uid,
    );
    let mut output_view = widgets::output_view::OutputView::new();

    for te in &typed_events {
        output_view.push_event(te.to_generic_event());
    }

    let input_box = widgets::input_box::InputBox::new();

    loop {
        if crossterm::event::poll(std::time::Duration::from_millis(100))? {
            if let crossterm::event::Event::Key(key) = crossterm::event::read()? {
                if key.code == crossterm::event::KeyCode::Char('c')
                    && key.modifiers == crossterm::event::KeyModifiers::CONTROL
                    || key.code == crossterm::event::KeyCode::Esc
                {
                    break;
                }
                if key.code == crossterm::event::KeyCode::Down {
                    output_view.scroll_down(1);
                }
                if key.code == crossterm::event::KeyCode::Up {
                    output_view.scroll_up(1);
                }
                if key.code == crossterm::event::KeyCode::PageDown {
                    output_view.page_down(10);
                }
                if key.code == crossterm::event::KeyCode::PageUp {
                    output_view.page_up(10);
                }
            }
        }

        terminal.draw(|frame| {
            let area = frame.area();
            let l = layout::compute_layout(area);

            let bar_widget =
                widgets::status_bar::StatusBarWidget::new(&status, theme);
            let bar_widget = bar_widget.with_version(env!("CARGO_PKG_VERSION"));
            let status_buf = frame.buffer_mut();
            bar_widget.render_full(status_buf, l.status_bar);
            output_view.render(frame.buffer_mut(), l.output_view);
            input_box.render(frame.buffer_mut(), l.input_box);
        })?;
    }

    shutdown::restore_terminal();
    Ok(())
}
