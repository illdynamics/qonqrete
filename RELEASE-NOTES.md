# QonQrete Release Notes

## v0.2.6-alpha (Current)

This is a user experience release focused on improving the robustness of the Text-based User Interface (TUI).

### Fixes & Improvements
-   **TUI Stability**: Fixed the "flash and gone" issue where the TUI would appear and immediately disappear if a pre-run error occurred. The TUI will now remain open and wait for user input upon any critical crash or pre-flight check failure, ensuring that error messages are always visible and readable.

## v0.2.5-alpha

This release addressed a critical agent failure and further refines the console user experience.

### Fixes & Improvements
-   **Critical Agent Fix**: Corrected a `NameError` in `qrane.py` that caused agent processes to fail immediately.
-   **Improved Error Visibility**: Enhanced headless mode to print the `stderr` of any failing agent.
-   **Cosmetic & Formatting Fixes**: Corrected console prefixes and spacing for better alignment.

## v0.2.4-alpha

This was a documentation-focused release that consolidated the findings of the deep code inspection into the main project documentation.

## v0.2.3-alpha

This was a bug fix and user experience release that addressed a critical `NameError` crash in TUI mode and improved console output.

## v0.2.2-alpha

This was a major refactoring release focused on improving internal architecture, with dynamic pipeline loading, centralized path management, pre-flight checks, and TUI state persistence.

## v0.2.1-alpha
-   **Dynamic Versioning**: Centralized versioning in the `VERSION` file.
-   **Integrated Docker Output**: Streamed Docker build output into the TUI.

## v0.2.0-alpha
-   **TUI Enhancements**: Added raw log view, fullscreen mode, key shortcuts, and improved colors.
-   **Faster Default Models**: Updated default models to `gpt-4o-mini` and `gemini-2.5-flash`.
-   **Microsandbox (MSB) Integration**: Added support for `msb` as a Docker alternative.

## v0.1.1-alpha
-   **TUI Mode**: Introduced the Text-based User Interface (`--tui` flag).
-   **Workspace Cleaning**: Added the `./qonqrete.sh clean` command.

## v0.1.0
-   The initial public alpha release of QonQrete.
