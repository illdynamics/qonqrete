# Release Notes

## [v0.6.0] - 2025-12-13

### Added
- **Qompressor (The Skeletonizer)**: Introduced a new agent that creates a low-token "skeleton" of the codebase in `bloq.d`. This provides architectural context to other agents with zero token cost.
- **Qontextor (The Symbol Mapper)**: Implemented an agent that uses AI to analyze the skeletonized code and generate a detailed, machine-readable YAML map of the codebase's symbols, purposes, and dependencies in `qontext.d`.
- **CalQulator (The Cost Estimator)**: Added a new agent that analyzes `briQ` files to provide a token and cost estimate for the upcoming `construqtor` cycle, annotating each `briQ` with its estimated cost.
- **FunQtions Library**: Added a new shared library `qrane/lib_funqtions.py` to house common utility functions like token estimation and cost calculation.

### Changed
- **Agent Architecture**: The `pipeline_config.yaml` is updated to include the new agents, allowing them to be dynamically included in the execution flow.
- **Configuration**: `worqspace/config.yaml` has been updated with sane defaults for the new agents.
- **Core WorQers**: The main agents (`instruQtor`, `construQtor`, `inspeQtor`) have been updated to integrate with the new architectural components and libraries.
- **Orchestration**: `qrane.py` has been updated to handle the new agents and their interactions within the pipeline.

### Removed
- (None)

### Fixed
- (None in this specific feature branch, focuses on new implementations)

## [v0.5.0-beta] - 2025-12-08

### Added
- **Comprehensive Test Suite**: Introduced a new `TESTS.md` file outlining a full suite of functional tests, including a provider and model matrix, mode and briq sensitivity matrix, and edge/regression scenarios.
- **Extensive Model Support**: Added and verified support for a wide range of new models from OpenAI, Google, Anthropic, and DeepSeek.

### Changed
- **Version**: Bumped version to `0.5.0` and updated the suffix to `-beta` to reflect the significant increase in test coverage and stability.

### Fixed
- **Gemini API `response.text` error**: A critical bug causing a crash when the Gemini API returned a blocked or empty response has been fixed by safely accessing the `chunk.text` attribute.
- **Assessment Parsing**: The logic for parsing the `inspeqtor`'s assessment has been made more robust to handle different output formats, ensuring consistent status reporting.

## [v0.4.9-alpha] - 2025-12-07

### Changed
- **DeepSeek Provider**: Replaced the non-functional `deepseek-cli` package with a custom provider implementation (`sqeleton/deepseek_provider.py`) that uses the official OpenAI client to communicate with the DeepSeek API. This approach is more reliable and aligns with DeepSeek's official documentation.

### Fixed
- **Environment Variable Handling**: The `qonqrete.sh` script now conditionally passes API keys to the container, preventing "unbound variable" errors when running with `set -u` and not all possible API keys are exported.

### Documentation
- **Local Dependencies**: Removed incorrect instructions from `README.md` that stated Python and related packages were required on the host. The system is fully containerized and only requires a shell and a container runtime (Docker or `msb`).
- **Roadmap**: Updated `COMING_SOON.md` to remove features that have already been implemented (Claude and DeepSeek provider support).
- **Suggestions**: Added a new `SUGGESTIONS.md` file containing a summary of findings from a code audit, with recommendations for improving performance, efficiency, and code quality.

### Testing
- **Functional Tests**: Performed a series of functional tests for the `qonqrete.sh` CLI, including run and clean commands, command-line flags, and pre-flight checks. The `TESTS.md` file has been updated to reflect the results.

---

## [v0.4.8-alpha] - 2025-12-06

### Added
- **DeepSeek Provider**: The system now supports DeepSeek models via the `deepseek-cli` tool.
- **Hybrid Provider Model**: The AI interaction library (`worqer/lib_ai.py`) now supports a hybrid model, using Python libraries for OpenAI, Gemini, and Anthropic, and a command-line tool for DeepSeek.

### Changed
- **Dynamic API Key Validation**: The `qrane.py` orchestrator now reads `config.yaml` to identify all required AI providers and validates that their corresponding API keys (`OPENAI_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`) are set in the environment. It will exit with a clear error message if any are missing.
- **Container Dependencies**: The `Dockerfile` has been updated to install the `deepseek-cli` Python package.

### Fixed
- **API Key Validation**: Removed the static, pre-emptive API key check from `qonqrete.sh`. The validation is now handled exclusively by the `qrane.py` orchestrator, which correctly checks for the required keys based on the providers listed in `config.yaml`.

---

## [v0.4.7-alpha] - 2025-12-06

### Added
- **Anthropic Claude Provider**: The system now supports Anthropic's Claude models as a configurable AI provider.
- **Unified Python Provider Interface**: The AI interaction library (`worqer/lib_ai.py`) has been refactored to use official Python clients for all providers (OpenAI, Google Gemini, and Anthropic), replacing the previous CLI-based approach.

### Changed
- **Container Dependencies**: The `Dockerfile` has been updated to install the `anthropic`, `openai`, and `google-generativeai` Python libraries, and the `shell-gpt` and `@google/gemini-cli` dependencies have been removed.
- **API Key Management**: The `qonqrete.sh` script now checks for and passes the `ANTHROPIC_API_KEY` environment variable to the container.

### Removed
- **CLI Pre-flight Checks**: The pre-flight check for `sgpt` and `gemini` CLIs in `qrane/qrane.py` has been removed as it is no longer relevant.

---

## [v0.4.6-alpha] - 2025-12-06

### Added
- **Configurable Execution Mode**: The default execution mode can now be controlled via a `cheqpoint` boolean in `worqspace/config.yaml`.
  - `cheqpoint: true` (default): The system runs in user-gated mode, pausing at each CheQpoint for user approval.
  - `cheqpoint: false`: The system runs in autonomous mode by default.
- **`--user` / `-u` Flag**: A new command-line flag to force user-gated mode, which overrides a `cheqpoint: false` setting in the configuration.

### Changed
- **Command-Line Flag Precedence**: The `--auto` and `--user` flags now have the highest precedence, allowing users to override the default mode set in `config.yaml` for any given run.
- **Mutual Exclusion for Flags**: The `--auto` and `--user` flags are now mutually exclusive. Using both at the same time will result in an error and prevent the system from running.

### Fixed
- **TUI Mode Crash**: Fixed a critical "I/O operation on closed file" error that occurred in the non-TUI mode by ensuring all agent output streams are read before the process terminates.
- **Gatekeeper Assessment Parsing**: The `gateQeeper`'s parsing logic is now more robust. It uses a regular expression to find the "Assessment:" status anywhere in the `reqap.md` file, preventing the "Result: Unknown" bug caused by AI formatting inconsistencies.
- **`construqtor` Path Duplication**: The `construqtor` agent no longer creates nested `qodeyard/qodeyard` directories. It now automatically sanitizes filenames provided by the AI to strip any redundant `qodeyard/` prefixes.
- **`construqtor` AI Output Parsing**: The `construqtor`'s system prompt is now extremely strict, providing a clear example of the required output format. This, combined with simpler parsing logic, resolves failures caused by the AI not providing filenames in the markdown tag. The agent no longer creates an unwanted `construqted_code.txt` file.

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