use std::path::PathBuf;
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

/// Initialize file-based debug logging.
/// Never prints to stdout or the TUI.
pub fn init_debug_log(path: Option<&str>) -> Option<PathBuf> {
    let path = path.map(|p| {
        if p.starts_with('~') {
            if let Ok(home) = std::env::var("HOME") {
                PathBuf::from(p.replacen('~', &home, 1))
            } else {
                PathBuf::from(p)
            }
        } else {
            PathBuf::from(p)
        }
    });

    if let Some(ref log_path) = path {
        if let Some(parent) = log_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let file_appender = tracing_appender::rolling::never(
            log_path.parent().unwrap_or(&PathBuf::from(".")),
            log_path.file_name()
                .and_then(|f| f.to_str())
                .unwrap_or("qq-tui-debug.log"),
        );
        let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);
        let filter = EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| EnvFilter::new("qq_tui=debug"));

        let subscriber = fmt::layer()
            .with_ansi(false)
            .with_target(true)
            .with_writer(non_blocking);

        let _ = tracing::subscriber::set_global_default(
            tracing_subscriber::registry().with(filter).with(subscriber),
        );

        tracing::info!("qq-tui debug log started");
        return Some(path.clone()?);
    }

    // No log file configured — use a no-op
    None
}
