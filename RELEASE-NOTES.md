# QonQrete Release Notes

## v0.3.0-alpha (Current)

This release introduces a branding update and refines the internal versioning mechanism.

### Features & Improvements
-   **Branding Update**: The `README.md` has been updated to display the new `logo.png` instead of the previous `splash.png`.
-   **Versioning Refinement**: The build process has been hardened to ensure the `VERSION` file contains only the semantic version string (e.g., `0.3.0-alpha`) without any `v` prefix, making it cleaner for scripts to parse. The `v` is now exclusively added where needed for display.

## v0.2.7-alpha

This was a hotfix release that addressed a critical syntax error.

### Fixes & Improvements
-   **Critical Bug Fix**: Fixed a fatal `IndentationError` in `qrane/qrane.py`.

## v0.2.6-alpha

This was a user experience release focused on TUI robustness.

### Fixes & Improvements
-   **TUI Stability**: Fixed the "flash and gone" issue.

## v0.2.5-alpha

This release addressed a critical agent failure and refined the console user experience.

### Fixes & Improvements
-   **Critical Agent Fix**: Corrected a `NameError` in `qrane.py`.
-   **Improved Error Visibility**: Enhanced headless mode to print agent `stderr`.
-   **Cosmetic & Formatting Fixes**: Corrected console prefixes and spacing.

## v0.2.4-alpha

This was a documentation-focused release that consolidated inspection reports into the main documentation.

## v0.2.3-alpha

This was a bug fix and user experience release that addressed a `NameError` crash in TUI mode.

## v0.2.2-alpha

This was a major refactoring release focused on internal architecture (dynamic pipeline, path management, pre-flight checks, TUI state persistence).

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
