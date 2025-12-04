# Release Notes

## [v0.4.6-alpha] - 2025-12-04
### Added
- **Configurable Cheqpoints**: Added a `cheqpoint: true` flag in `pipeline_config.yaml` to make human-in-the-loop gates optional per-step.
### Changed
- **Cheqpoint Overrides**: The `--auto` and `--user` CLI flags now override the `cheqpoint` configuration, allowing for forced autonomous or user-gated modes.
- **Terminology**: Renamed all instances of "checkpoint" to "cheqpoint" to align with project terminology.

## [v0.4.5-alpha] - 2025-12-03
### Changed
- **Briq Sensitivity**: Tuned the briq sensitivity prompts in the `instruqtor` to be approximately 50% less granular, providing more cohesive and manageable task breakdowns.
- **Logging**: Fixed a critical bug where the application would crash if the log directory did not exist. The `qrane` now ensures the directory is created before attempting to write logs.

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
- The initial public alpha release of QonQrete.
