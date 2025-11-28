# QonQrete Release Notes

## v0.2.5-alpha (Current)

This release addresses a critical agent failure and further refines the console user experience.

### Fixes & Improvements
-   **Critical Agent Fix**: Corrected a `NameError` in `qrane.py` that caused agent processes to fail immediately. The dynamic pipeline loading now correctly resolves function scope.
-   **Improved Error Visibility**: Enhanced headless mode (`run_agent`) to print the `stderr` of any agent that exits with a non-zero status code, making debugging significantly easier.
-   **Cosmetic & Formatting Fixes**:
    -   Corrected the console prefix in `qonqrete.sh` to properly display `aQQ` when running in `--auto` mode.
    -   Adjusted spacing and padding in `qrane.py` log prefixes for better alignment.

## v0.2.4-alpha

This was a documentation-focused release that consolidated the findings of the deep code inspection into the main project documentation.

### Documentation Updates
-   **Roadmap Consolidation**: The `COMING_SOON.md` file was enhanced to include recommendations for Modularity, Performance, Security, and Provider enhancements.
-   **Wild Ideas Integration**: Experimental ideas were moved into a new "Researching Features" section in `COMING_SOON.md`.
-   **Architecture Diagram**: The Mermaid diagram was moved directly into `DOCUMENTATION.md`.
-   **Cleanup**: All standalone analysis files were removed to de-clutter the project root.

## v0.2.3-alpha

This was a bug fix and user experience release.

### Fixes & Improvements
-   **Critical Bug Fix**: Fixed a `NameError` crash in `qrane.py` during TUI mode.
-   **Output Formatting**: Standardized all console log messages.

## v0.2.2-alpha

This was a major refactoring release focused on internal architecture.

### New Features & Improvements
-   **Dynamic Pipeline Loading**: `Qrane` now dynamically reads `pipeline_config.yaml`.
-   **Centralized Path Management**: Path logic was centralized into `qrane/paths.py`.
-   **Pre-flight Checks**: Added verification of external CLI dependencies.
-   **TUI State Persistence**: The TUI now correctly restores its log history.

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
