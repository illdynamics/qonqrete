# QonQrete Release Notes

## v0.1.1-alpha (Current)

This is an early alpha release focusing on improving the user interface and overall project structure.

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
