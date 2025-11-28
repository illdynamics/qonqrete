# QonQrete Release Notes

## v0.2.0-alpha (Current)

This release focuses on significant user interface enhancements, performance improvements through faster default models, and the integration of an alternative sandboxing environment.

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

## v0.1.1-alpha

This was an early alpha release focusing on improving the user interface and overall project structure.

### New Features & Improvements
-   **TUI Mode**: Introduced a new Text-based User Interface (`--tui` flag) for a more immersive and organized view of the agentic workflow. The TUI provides a split-screen view with a `Qommander` for input and a `Qonsole` for real-time log output.
-   **Workspace Cleaning**: Added a `./qonqrete.sh clean` command to safely remove all temporary `qage_*` run directories from the `worqspace`, making it easier to start fresh.
-   **Documentation Updates**:
    -   All documentation has been updated to reflect the new version.
    -   `TERMINOLOGY.md` now includes definitions for the new TUI components (`Qommander`, `Qonsole`).
    -   `README.md` and `QUICKSTART.md` now include instructions for using the new `--tui` flag and `clean` command.
-   **Code Refinements**: Minor internal improvements to logging output, including better alignment for agent name prefixes for improved readability.

## v0.1.0

The initial public alpha release of QonQrete.

### Core Features
-   **Agentic Workflow**: Established the core Plan-Execute-Review `cyQle` with three distinct agents (`instruQtor`, `construQtor`, `inspeQtor`).
-   **Secure Sandbox**: All agent execution takes place inside a Docker container (`Qage`) to ensure host system safety.
-   **File-Based Communication**: Agents communicate via markdown files in a shared `worqspace` directory, providing a transparent and auditable trail.
-   **Human-in-the-Loop**: Mandatory `CheQpoint` after each cycle for human review and approval.
-   **Autonomous Mode**: An `--auto` flag to run the system continuously without manual intervention.
-   **Configuration**: Agent models and cycle limits can be configured via `worqspace/config.yaml`.
-   **Comprehensive Documentation**: Initial versions of `README.md`, `QUICKSTART.md`, `TERMINOLOGY.md`, and `DOCUMENTATION.md` were created.
-   **Initial Project Setup**: All core scripts (`qonqrete.sh`, `qrane.py`, etc.) and project files were created and committed.
