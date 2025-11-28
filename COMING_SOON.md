# QonQrete - Upcoming Features

This document outlines the planned features and improvements for future releases of QonQrete.

## Planned Features

-   **instruQtor Sensitivity Control**: A parameter to control how granularly a task is split into steps.
-   **construQtor Run Modes**: Pre-defined modes (`fast`, `balanced`, `complex`) to automatically select the best AI model for a given task.

---

## Roadmap for Future Enhancements

The following items are planned enhancements based on a deep analysis of the system's architecture and capabilities.

### Expanded LLM Provider Support
-   **Anthropic Claude 3.5 Sonnet**: Integration via the official `@anthropic-ai/claude-code` CLI.
-   **DeepSeek Coder**: Integration via the official `deepseek-cli`.

### Modularity Enhancements
-   **Generic Agent Interface**: Define a standardized CLI argument structure for all agents.
-   **Configurable Checkpoints**: Add a `checkpoint: true` flag in `pipeline_config.yaml` to make human-in-the-loop gates optional per-step.

### Performance Enhancements
-   **Multi-Stage Docker Builds**: Optimize container images for faster `init` times.
-   **Parallel Agent Execution**: Investigate parallel execution of independent `briQ` files.
-   **Refined TUI Rendering**: Implement a batched-update mechanism for smoother logging.

### Security Hardening
-   **Reduced Container Privileges**: Implement a non-root user within the `Qage` container.
-   **Read-Only Mounts**: Enforce read-only mounts for application source code in production.

---

## Researching Features (Wild Ideas)

This section contains a series of "out-of-the-box" ideas for expanding the QonQrete system beyond its current scope.

-   **The "Evolvinator" Agent (`evolver`)**: A meta-agent that reads the `inspeQtor`'s suggestions and proposes changes to the other agents' prompts and logic to improve performance in subsequent cycles.

-   **Dynamic Qrew Composition**: Replace the static pipeline with a "Qrew Manifest" of specialized agents. The `instruQtor` would then tag each `briQ` with the required specialist, allowing the `Qrane` to act as a dispatcher.

-   **The "Auditor" Checkpoint**: An optional checkpoint *before* the `construQtor` runs, allowing the user to approve the generated plan before incurring API costs for code generation.

-   **"Live Qodeyard" TUI Integration**: A third TUI panel showing a real-time file tree of the `qodeyard` as the `construQtor` creates and modifies files.

-   **Git Integration Agent (`versioner`)**: An agent that automatically generates conventional commit messages based on the `inspeQtor`'s report and `git diff`, and includes the commit step as part of the `CheQpoint` approval.
