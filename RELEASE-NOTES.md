# QonQrete Release Notes

## v0.4.1-alpha (Current)

This release focuses on hardening the agent prompts and parsing logic to ensure more reliable and secure behavior.

### Agent Logic Improvements
-   **instruQtor (Planner)**:
    -   **Robust Parsing**: The agent can now correctly parse `<briq>` tags with or without a `title` attribute, making it more resilient to variations in AI output.
    -   **Anti-Summarization Prompt**: The prompt now explicitly forbids the AI from summarizing the `tasQ`, ensuring that critical technical details (like Regex patterns or mappings) are preserved during the task breakdown.
-   **construQtor (Executor)**:
    -   **Hardened Prompt**: The agent's prompt has been significantly hardened to prevent it from executing code. It is now explicitly instructed to *only* generate code and scripts, never to run them.

## v0.4.0-alpha

This was a major feature release that introduced sophisticated controls over agent behavior and task decomposition, alongside significant internal code refinements.

### New Features & Improvements
-   **Operational Modes**: Agents now operate with specific "personas" (e.g., `enterprise`, `security`).
-   **Briq Sensitivity**: The `instruQtor` now accepts a granularity setting (0-9).
-   **Path Regression Fix**: Resolved a critical bug in the dynamic pipeline logic.
-   **Code Refinements**: Widespread refactoring for readability and compactness.

## v0.3.0-alpha

This release introduced a branding update and refined the internal versioning mechanism.

## v0.2.7-alpha

This was a hotfix release that addressed a critical `IndentationError`.

## v0.2.6-alpha

This was a user experience release focused on TUI robustness.

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
