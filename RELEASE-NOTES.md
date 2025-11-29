# QonQrete Release Notes

## v0.4.0-alpha (Current)

This is a major feature release that introduces sophisticated controls over agent behavior and task decomposition, alongside significant internal code refinements.

### New Features & Improvements
-   **Operational Modes**: Agents now operate with specific "personas" passed via the `--mode` flag or `config.yaml`. This allows the user to guide agent output towards different priorities (e.g., `enterprise`, `security`, `performance`).
-   **Briq Sensitivity**: The `instruQtor` agent now accepts a `--briq-sensitivity` flag (0-9) or a `config.yaml` setting. This gives the user fine-grained control over how atomic or monolithic the task breakdown should be.
-   **Path Regression Fix**: Resolved a critical bug in the dynamic pipeline logic that caused incorrect path resolution for agent I/O.
-   **Code Refinements**: The entire Python and shell codebase has been significantly refactored for improved readability, compactness, and adherence to best practices.

## v0.3.0-alpha

This release introduced a branding update and refined the internal versioning mechanism.

### Features & Improvements
-   **Branding Update**: The `README.md` was updated to display `logo.png`.
-   **Versioning Refinement**: The build process was hardened to ensure a clean `VERSION` file.

## v0.2.7-alpha

This was a hotfix release that addressed a critical `IndentationError` in `qrane/qrane.py`.

## v0.2.6-alpha

This was a user experience release focused on TUI robustness, fixing the "flash and gone" issue.

## v0.2.5-alpha

This release fixed a critical agent `NameError` and improved console error visibility.

## v0.2.4-alpha

This was a documentation-focused release that consolidated inspection reports.

## v0.2.3-alpha

This was a bug fix release for a `NameError` crash in TUI mode.

## v0.2.2-alpha

This was a major refactoring release (dynamic pipeline, path management, pre-flight checks, TUI state persistence).

## v0.2.1-alpha
-   **Dynamic Versioning**: Centralized versioning in the `VERSION` file.
-   **Integrated Docker Output**: Streamed Docker build output into the TUI.

## v0.2.0-alpha
-   **TUI Enhancements**: Added raw log view, fullscreen mode, key shortcuts, and improved colors.
-   **Faster Default Models**: Updated default models.
-   **Microsandbox (MSB) Integration**: Added support for `msb`.

## v0.1.1-alpha
-   **TUI Mode**: Introduced the `--tui` flag.
-   **Workspace Cleaning**: Added the `clean` command.

## v0.1.0
-   The initial public alpha release of QonQrete.
