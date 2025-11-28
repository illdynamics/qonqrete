# QonQrete - Upcoming Features

This document outlines the planned features and improvements for future releases of QonQrete.

## Planned Features

-   **instruQtor Sensitivity Control**:
    -   A new parameter will be introduced to control the sensitivity of the `instruQtor`'s tasq-splitting logic.
    -   This will allow users to define how granularly a high-level `tasQ` should be broken down into atomic `briQ` files, using a scale from 0 to 999.

-   **construQtor Run Modes**:
    -   Three new operational modes will be available for the `construQtor`: `--mode fast`, `--mode balanced`, and `--mode complex`.
    -   These modes will automatically select the most appropriate AI model for the task, balancing speed against the complexity of code generation.

-   **Expanded LLM Provider Support**:
    -   Integration with **Anthropic Claude 3.5 Sonnet** via the official `@anthropic-ai/claude-code` CLI.
    -   Integration with **DeepSeek Coder** models via the official `deepseek-cli`.

-   **General Enhancements**:
    -   Ongoing bug fixes and performance tweaks.
    -   Continuous security enhancements and hardening of the sandbox environment.
