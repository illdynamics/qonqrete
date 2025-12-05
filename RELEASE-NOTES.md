# Release Notes

## [v0.4.6-alpha] - 2025-12-05

### Added
- **User-Gated Mode Flag**: Introduced `--user` and `-u` flags to explicitly force user-gated `CheQpoint`s, overriding any default autonomous settings.
- **Configurable Default Mode**: Added an `auto_mode_default` boolean option to `pipeline_config.yaml`. This allows the user to define the default behavior of `CheQpoint`s (`true` for autonomous, `false` for user-gated) when no command-line flags are provided.

### Changed
- **CheQpoint Logic**: The `CheQpoint` system now follows a clear override hierarchy:
  1.  `--auto` or `--user` flags provide the highest level of control.
  2.  If no flags are used, the system falls back to the `auto_mode_default` setting in `pipeline_config.yaml`.

### Fixed
- **Mutually Exclusive Flags**: The system now exits with an error if both `--auto` and `--user` flags are used simultaneously, preventing conflicting states.
- **Merge Conflicts**: Resolved merge conflicts between the `main` and `feat/cheqpoint-config` branches.

---

## [v0.4.5-alpha] - 2025-12-04

### Changed
- **Logging Architecture**: The logging system has been re-architected. Raw, verbose output from each agent is now captured in `struqture/qonsole_<agent>.log`, while the main orchestrator logs high-level status changes (e.g., agent start/stop) to `struqture/events_<agent>.log`. This separates detailed debugging information from key lifecycle events.

### Fixed
- **Headless Mode Crash**: Fixed a critical "I/O operation on closed file" error that occurred in the non-TUI mode by ensuring all agent output streams are read before the process terminates.
- **Gatekeeper Assessment Parsing**: The `gateQeeper`'s parsing logic is now more robust. It uses a regular expression to find the "Assessment:" status anywhere in the `reqap.md` file, preventing the "Result: Unknown" bug caused by AI formatting inconsistencies.
- **`construqtor` Path Duplication**: The `construqtor` agent no longer creates nested `qodeyard/qodeyard` directories. It now automatically sanitizes filenames provided by the AI to strip any redundant `qodeyard/` prefixes.
- **`construqtor` AI Output Parsing**: The `construqtor`'s system prompt is now extremely strict, providing a clear example of the required output format. This, combined with simpler parsing logic, resolves failures caused by the AI not providing filenames in the markdown tag. The agent no longer creates an unwanted `construqted_code.txt` file.

---

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

## [v0.4.4-alpha] - 2025-12-02
### Changed
- **InstruQtor Sensitivity**: Implemented 10 distinct levels of granularity (0-9) for task breakdown.
- **Context Awareness**: InstruQtor now reads all files from `qodeyard` to provide full codebase context to the planner.
- **Sqrapyard Logging**: Improved logging for the sqrapyard seeding process to provide better visibility.
### Fixed
- **Instruqtor Logic**: Overhauled sensitivity logic for more reliable and predictable behavior.
- **Construqtor**: Fixed a bug that caused the `construqtor` agent to fail.
- **AI Reliability**: Implemented a robust retry mechanism in `lib_ai` to handle intermittent AI provider failures.
- **Container Workspace**: Isolated agent workspaces within the container and fixed a `NameError`.

## [v0.4.3-alpha] - 2025-12-02
### Added
- **Init Seeding**: `qonqrete.sh init` now copies contents from `sqrapyard` to `qodeyard` if available, enabling warm starts with existing code.

## [v0.4.2-alpha] - 2025-11-28
### Added
- **Architect Role**: Implemented an "Architect" role in the `instruqtor` to improve planning.
- **Micro-dosing**: Introduced a "micro-dosing" technique for better AI results.
### Fixed
- **Syntax Errors**: Addressed multiple syntax errors and regressions.

## [v0.4.1-alpha] - 2025-11-27
### Fixed
- **Critical Regressions**: Patched several syntax errors and regressions introduced in v0.4.0.
- **Pre-flight Checks**: Disabled pre-flight checks that were causing interference.

## [v0.4.0-alpha] - 2025-11-26
### Added
- **Operational Modes**: Agents now operate with specific "personas" passed via the `--mode` flag or `config.yaml`.
- **Briq Sensitivity**: The `instruQtor` agent now accepts a `--briq-sensitivity` flag (0-9) for fine-grained control over task breakdown.
- **TUI Overhaul**: Major improvements to the TUI.
### Fixed
- **Path Regression**: Resolved a critical bug in the dynamic pipeline logic that caused incorrect path resolution for agent I/O.
### Changed
- **Code Refinements**: Significant refactoring of the entire Python and shell codebase for improved readability and compactness.

## [v0.3.0-alpha] - 2025-11-25
### Changed
- **Branding**: Updated `README.md` to display the `logo.png`.
- **Versioning**: Hardened the build process to ensure a clean `VERSION` file.

## [v0.2.7-alpha] - 2025-11-24
### Fixed
- **Hotfix**: Addressed a critical `IndentationError` in `qrane/qrane.py`.

## [v0.2.6-alpha] - 2025-11-23
### Fixed
- **TUI Experience**: Fixed the "flash and gone" issue with the TUI.

## [v0.2.5-alpha] - 2025-11-22
### Fixed
- **Agent Stability**: Fixed a critical agent `NameError` and improved console error visibility.

## [v0.2.4-alpha] - 2025-11-21
### Changed
- **Documentation**: Consolidated inspection reports into `COMING_SOON.md` and `DOCUMENTATION.md`.

## [v0.2.3-alpha] - 2025-11-20
### Fixed
- **TUI Stability**: Fixed a `NameError` crash in TUI mode.

## [v0.2.2-alpha] - 2025-11-19
### Changed
- **Major Refactoring**:
    - Implemented a dynamic agent pipeline.
    - Centralized path management.
    - Added pre-flight checks for dependencies.
    - Implemented TUI state persistence.

## [v0.2.1-alpha] - 2025-11-18
### Added
- **Dynamic Versioning**: Centralized versioning in the `VERSION` file.
- **Integrated Docker Output**: Streamed Docker build output into the TUI.

## [v0.2.0-alpha] - 2025-11-17
### Added
- **TUI Enhancements**: Added raw log view, fullscreen mode, key shortcuts, and improved colors.
- **Microsandbox (MSB) Integration**: Added support for `msb`.
### Changed
- **AI Models**: Updated default models for faster performance.

## [v0.1.1-alpha] - 2025-11-14
### Added
- **TUI Mode**: Introduced the `--tui` flag for an interactive user interface.
- **Workspace Cleaning**: Added the `clean` command to `qonqrete.sh`.

## [v0.1.0-alpha] - 2025-11-12
- The initial public alpha release of Qonqrete.