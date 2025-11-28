# QonQrete Release Notes

## v0.2.1-alpha (Current)

This release focuses on internal refinements, making the project versioning more dynamic and improving the user experience during the build phase.

### New Features & Improvements
-   **Dynamic Versioning**: The project version is now sourced from a single `VERSION` file. This version is passed as an environment variable (`QONQ_VERSION`) into the container and used by `qonqrete.sh` to ensure all components display a consistent version number.
-   **Integrated Docker Output**: The `init` command now streams Docker build output directly into the TUI, providing a seamless and unified user experience without leaving the interface.

## v0.2.0-alpha

This release focused on significant user interface enhancements, performance improvements through faster default models, and the integration of an alternative sandboxing environment.

### New Features & Improvements
-   **TUI Enhancements**:
    -   **Qonsole View**: The bottom panel in TUI mode now displays raw, unfiltered logs from the agents, providing deeper insight into their execution.
    -   **Fullscreen Qommander**: You can now press the `[Spacebar]` to toggle the visibility of the Qonsole, allowing the Qommander (main flow view) to use the full terminal screen.
    -   **New Key Shortcuts**: A helper bar is now present with shortcuts: `[Space]` to toggle the Qonsole, `[W]` for a fun mode, `[Esc]` to quit, and `[K]` to kill running agents.
    -   **Color Improvements**: The TUI now uses a more diverse and vibrant color palette to better distinguish between different agents and log levels.
-   **Faster Default Models**: The default models in `config.yaml` have been updated to prioritize speed and reduce costs:
    -   `instruQtor`: `gpt-4o-mini`
    -   `inspeQtor`: `gpt-4o-mini`
    -   `construQtor`: `gemini-2.5-flash`
-   **Microsandbox (MSB) Integration**:
    -   QonQrete can now be run using `msb` as an alternative to Docker for a more lightweight sandboxing experience.
    -   You can force the runtime environment using the `--msb` or `--docker` flags.
    -   The default runtime can be set in `worqspace/pipeline_config.yaml` by setting `microsandbox: true`.
-   **Documentation**: Added the `--auto` flag to the `README.md` `Getting Started` section.

## v0.1.1-alpha

This was an early alpha release focusing on improving the user interface and overall project structure.

### New Features & Improvements
-   **TUI Mode**: Introduced a new Text-based User Interface (`--tui` flag).
-   **Workspace Cleaning**: Added a `./qonqrete.sh clean` command.
-   **Documentation Updates**: Updated all docs for the new version and features.
-   **Code Refinements**: Minor internal improvements to logging output.

## v0.1.0

The initial public alpha release of QonQrete.

### Core Features
-   **Agentic Workflow**: Established the core Plan-Execute-Review `cyQle`.
-   **Secure Sandbox**: All agent execution takes place inside a Docker container.
-   **File-Based Communication**: Agents communicate via markdown files.
-   **Human-in-the-Loop**: Mandatory `CheQpoint` for human review.
-   **Autonomous Mode**: An `--auto` flag to run the system continuously.
-   **Configuration**: Agent models and cycle limits are configurable.
-   **Comprehensive Documentation**: Created `README.md`, `QUICKSTART.md`, etc.
-   **Initial Project Setup**: All core scripts and project files were created.
