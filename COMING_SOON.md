# QonQrete - Upcoming Features

This document outlines the planned features and improvements for future releases of QonQrete, incorporating the findings from the "SherloNQ Wolmes" deep inspection.

## Planned Features

-   **instruQtor Sensitivity Control**:
    -   A new parameter will be introduced to control the sensitivity of the `instruQtor`'s tasq-splitting logic.
    -   This will allow users to define how granularly a high-level `tasQ` should be broken down into atomic `briQ` files, using a scale from 0 to 999.

-   **construQtor Run Modes**:
    -   Three new operational modes will be available for the `construQtor`: `--mode fast`, `--mode balanced`, and `--mode complex`.
    -   These modes will automatically select the most appropriate AI model for the task, balancing speed against the complexity of code generation.

---

## Roadmap for Future Enhancements

The following items are planned enhancements based on a deep analysis of the system's architecture and capabilities.

### Expanded LLM Provider Support

-   **Description**: The `worqer/lib_ai.py` abstraction layer makes it straightforward to add new providers. The following are planned for integration:
-   **Anthropic Claude 3.5 Sonnet**: Integration via the official `@anthropic-ai/claude-code` CLI.
-   **DeepSeek Coder**: Integration via the official `deepseek-cli`.

### Modularity Enhancements

-   **Generic Agent Interface**: Define a standardized command-line argument structure for all agents to make the orchestrator fully generic.
-   **Configurable Checkpoints**: Add a `checkpoint: true` flag to the agent definitions in `pipeline_config.yaml` to allow for configurable human-in-the-loop gates.

### Performance Enhancements

-   **Multi-Stage Docker Builds**: Optimize the `Dockerfile` and `Sandboxfile` to create smaller, more efficient runtime images, resulting in faster `init` times.
-   **Parallel Agent Execution**: For complex tasks, investigate parallel execution of independent `briQ` files to reduce overall cycle time.
-   **Refined TUI Rendering**: Implement a batched-update mechanism for TUI rendering to create a smoother experience with high-velocity logs.

### Security Hardening

-   **Reduced Container Privileges**: Implement a non-root user within the `Qage` container to reduce the potential impact of a container escape.
-   **Read-Only Mounts**: Enforce read-only mounts for the application source code in production runs to prevent self-modification by agents.

---
-   **General Enhancements**:
    -   Ongoing bug fixes and performance tweaks.
    -   Continuous security enhancements and hardening of the sandbox environment.