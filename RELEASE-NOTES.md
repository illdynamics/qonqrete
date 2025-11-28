# QonQrete Release Notes

## v0.2.4-alpha (Current)

This is a documentation-focused release that consolidates the findings of the deep code inspection into the main project documentation for a cleaner and more centralized knowledge base.

### Documentation Updates
-   **Roadmap Consolidation**: The `COMING_SOON.md` file has been significantly enhanced. It now includes the detailed recommendations for Modularity, Performance, Security, and Provider enhancements that were previously in separate analysis files.
-   **Wild Ideas Integration**: The experimental "Wild Ideas" (e.g., Evolvinator Agent, Dynamic Qrew Composition) have been moved from a separate file into a new "Researching Features" section in `COMING_SOON.md`.
-   **Architecture Diagram**: The Mermaid architecture diagram has been moved from `ARCHITECTURE.md` directly into the `DOCUMENTATION.md` file for easier access.
-   **Cleanup**: All standalone analysis files (`MODULARITY.md`, `PERFORMANCE.md`, `IDEAS.md`, etc.) have been removed to de-clutter the project root.

## v0.2.3-alpha

This was a bug fix and user experience release that addressed a critical crash and improved the readability of the console output.

### Fixes & Improvements
-   **Critical Bug Fix**: Fixed a `NameError` crash in `qrane.py` that occurred during TUI mode execution.
-   **Output Formatting**: Standardized all console log messages for consistency and readability.

## v0.2.2-alpha

This was a major refactoring release focused on improving the internal architecture for better efficiency, modularity, and robustness.

### New Features & Improvements
-   **Dynamic Pipeline Loading**: The `Qrane` orchestrator now dynamically reads `pipeline_config.yaml` to construct the agent execution loop.
-   **Centralized Path Management**: All path logic was centralized into `qrane/paths.py`.
-   **Pre-flight Checks**: The orchestrator now verifies external CLI dependencies at startup.
-   **TUI State Persistence**: The TUI now correctly restores its log history after being suspended.

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
