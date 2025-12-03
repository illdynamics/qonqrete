# Release Notes

## [v0.4.5-alpha] - 2025-12-03
### Added
- **Sqrapyard Project Seeding**: On startup, `qonqrete.sh` now checks the persistent `worqspace/sqrapyard` directory. If it contains files, they are copied into the ephemeral run's `qodeyard` to serve as a starting point for the AI.
- **`tasq.md` Seeding**: If a `tasq.md` exists in `sqrapyard`, it will be used as the initial task for the first cycle.
- **Verbose Startup Logging**: The shell script now provides explicit logs about whether it is seeding a project from `sqrapyard` or starting a fresh tasq.
- **Pre-run Delay**: A 3-second delay has been added after the initial host logs are printed, giving the user time to read them before the container's splash screen appears.

### Changed
- **Ephemeral Workspaces**: `qonqrete.sh` now creates a unique, timestamped `qage_<timestamp>` directory for each run. This ensures that runs are isolated and no data persists between sessions unless explicitly saved by the user.
- **Agent Output Directory**: The `construqtor` agent is confirmed to write all code output exclusively to the `qodeyard` directory, with safeguards to prevent writing outside this directory.
- **Instruqtor Sensitivity**: Re-implemented 10 distinct levels of granularity (0-9) for task breakdown, controlled by the `QONQ_SENSITIVITY` environment variable.
- **Context Awareness**: Both the `instruqtor` and `construqtor` agents now read all files from the current `qodeyard` to provide full codebase context to the AI.

### Fixed
- **Stricter Path Sanitization**: The `construqtor` agent now forcibly removes any parent directory traversal attempts (`../`) from AI-generated filenames, providing a hard safeguard to ensure all code is written exclusively within the `qodeyard`.
- **Gatekeeper Assessment Parsing**: The `qrane` script now correctly parses the "Assessment" status from `reqap.md` files, preventing the "Result: Unknown" bug.
- **AI Filename Resilience**: The `construqtor` agent is now more resilient to the AI providing a language name (e.g., "python") as a filename, and will write to a default file in such cases.
- **Build Log Verbosity**: Empty lines are now filtered from the `docker build` output to provide a cleaner log.
- **Agent Log Completeness**: All output streams from all agents (including the mirrored AI output from `instruqtor`, `construqtor`, and `inspeqtor`) are now correctly captured in the log files located in the `struqture` directory.