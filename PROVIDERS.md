# QonQrete Provider Integration Analysis

This document analyzes the feasibility and process for integrating new AI/LLM providers into the QonQrete system, specifically focusing on Anthropic (Claude) and DeepSeek.

## Core Integration Architecture: `worqer/lib_ai.py`

The key to QonQrete's extensibility is the `worqer/lib_ai.py` module. It acts as an abstraction layer, translating a generic AI request from an agent into a specific command-line execution for a given provider.

-   **Current State**: It currently supports `openai` (via the `sgpt` CLI tool) and `gemini` (via the `@google/gemini-cli` npm package).
-   **Integration Pattern**: To add a new provider, the following steps are required:
    1.  Add the new provider's CLI tool to the `Dockerfile` and `Sandboxfile`.
    2.  Add a new `elif provider == 'new_provider':` block in `lib_ai.py`.
    3.  Construct the appropriate command and arguments list for the new provider's CLI tool.
    4.  Update the `worqspace/config.yaml` to allow agents to use the new provider.

This modular design means that the core logic of the agents (`instruQtor`, `construQtor`, etc.) does not need to be changed at all.

## Analysis of New Providers

Based on my research, both requested providers are excellent candidates for integration.

### 1. Anthropic (Claude Models: Sonnet, Opus)

-   **Feasibility**: **High**.
-   **Reasoning**: Anthropic provides an official, feature-rich CLI tool called `@anthropic-ai/claude-code`, which is available via `npm`. Its functionality is analogous to the `gemini` CLI, making it a natural fit for the existing architecture.
-   **Integration Steps**:
    1.  **Dockerfile/Sandboxfile**: Add `npm install -g @anthropic-ai/claude-code` to the installation steps.
    2.  **`lib_ai.py`**: Add an `elif provider == 'anthropic':` block. The code would construct a command like `['claude', 'prompt', '-m', model_name, full_prompt]`. (The exact arguments would need to be confirmed from the tool's `--help` output).
    3.  **`config.yaml`**: Users could then configure an agent like this:
        ```yaml
        instruqtor:
          provider: anthropic
          model: claude-3-5-sonnet-20240620
        ```
-   **Difficulty**: **Low**. The integration is straightforward and follows the established pattern.

### 2. DeepSeek

-   **Feasibility**: **High**.
-   **Reasoning**: DeepSeek maintains an official `deepseek-cli` tool, installable via `pip`. It is designed for similar code-generation and chat-based tasks.
-   **Integration Steps**:
    1.  **Dockerfile/Sandboxfile**: Add `pip3 install deepseek-cli` to the Python dependencies.
    2.  **`lib_ai.py`**: Add an `elif provider == 'deepseek':` block. The code would construct a command like `['deepseek', 'chat', '-m', model_name, '-p', full_prompt]`. (The exact arguments would need to be confirmed).
    3.  **`config.yaml`**: Users could then configure an agent like this:
        ```yaml
        instruqtor:
          provider: deepseek
          model: deepseek-coder
        ```
-   **Difficulty**: **Low**. Like the Claude integration, this is a simple extension of the existing abstraction layer.

---
**Conclusion**: The architectural design of `lib_ai.py` makes QonQrete highly extensible. Integrating both Claude and DeepSeek is not only possible but would be a low-effort, high-reward task that would significantly expand the system's capabilities.
