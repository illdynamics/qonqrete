# QonQrete Release Notes

## v0.2.3-alpha (Current)

This is a bug fix and user experience release that addresses a critical crash and improves the readability of the console output.

### Fixes & Improvements
-   **Critical Bug Fix**: Fixed a `NameError: name 'logger' is not defined` crash in `qrane.py` that occurred during TUI mode execution.
-   **Output Formatting**:
    -   Standardized all `Qrane` and `gateQeeper` log messages to have consistent formatting and spacing.
    -   The "User Interrupt" message is now properly formatted and colored yellow for better visibility.
    -   Replaced a generic `[INFO]` seeding message with a properly attributed `Qrane` log line.

## v0.2.2-alpha

This was a major refactoring release focused on improving the internal architecture for better efficiency, modularity, and robustness.

### New Features & Improvements
-   **Dynamic Pipeline Loading**: The `Qrane` orchestrator now dynamically reads the `pipeline_config.yaml` to construct the agent execution loop at runtime.
-   **Centralized Path Management**: All file and directory path logic has been centralized into the new `qrane/paths.py` module.
-   **Pre-flight Checks**: The orchestrator now performs a "pre-flight check" at startup to verify external CLI dependencies.
-   **TUI State Persistence**: The TUI now buffers its logs to correctly restore the screen state after using an external editor.

## v0.2.1-alpha

This release focused on internal refinements, making the project versioning more dynamic and improving the user experience during the build phase.

### New Features & Improvements
-   **Dynamic Versioning**: The project version is now sourced from a single `VERSION` file.
-   **Integrated Docker Output**: The `init` command now streams Docker build output directly into the TUI.

## v0.2.0-alpha

This release focused on significant user interface enhancements, performance improvements, and the integration of an alternative sandboxing environment.

### New Features & Improvements
-   **TUI Enhancements**: Included a raw log view, fullscreen mode, new key shortcuts, and improved colors.
-   **Faster Default Models**: Default models updated to `gpt-4o-mini` and `gemini-2.5-flash`.
-   **Microsandbox (MSB) Integration**: Added support for `msb` as a Docker alternative.
-   **Documentation**: Added the `--auto` flag to the `README.md`.

## v0.1.1-alpha

This was an early alpha release focused on improving the user interface and overall project structure.

### New Features & Improvements
-   **TUI Mode**: Introduced a new Text-based User Interface (`--tui` flag).
-   **Workspace Cleaning**: Added a `./qonqrete.sh clean` command.

## v0.1.0

The initial public alpha release of QonQrete.
