# QonQrete Agent Logic

This document details the operational logic for the QonQrete system, including the central orchestrator and the default `worQer` agents.

## Orchestrator Logic (`qrane/qrane.py`)

The `Qrane` is the heart of the system. As of `v0.2.2-alpha`, it functions as a dynamic pipeline runner.

-   **Dynamic Pipeline Loading**: On startup, the `Qrane` reads the `worqspace/pipeline_config.yaml` file. It iterates through the `agents` list defined in this file to build the execution pipeline for the cycle.
-   **Generic Execution**: For each agent in the pipeline, the orchestrator constructs the appropriate command-line arguments based on the `script`, `input`, and `output` fields in the config. It no longer has hardcoded knowledge of the `instruQtor` -> `construQtor` -> `inspeQtor` sequence.
-   **Centralized Paths**: It utilizes the `PathManager` class to resolve all file and directory paths, ensuring consistency throughout the run.
-   **Pre-flight Checks**: Before starting the cycle, it performs a check to ensure that all CLI tools required by the configured agents (e.g., `sgpt`, `gemini`) are available in the system's PATH.

## Default Agent Logic

The following describes the logic of the three default agents that constitute the standard QonQrete pipeline.

### Core Abstraction: `worqer/lib_ai.py`

All agents utilize a central library, `lib_ai.py`, to interact with AI models. This is a critical architectural component.

-   **Function**: It abstracts the specific command-line tools (`sgpt` for OpenAI, `gemini` for Google) into a single function, `run_ai_completion`.
-   **Mechanism**: It constructs and executes shell commands as subprocesses, streaming the output back to the calling agent.
-   **Extensibility**: This design is highly modular. To add a new provider (e.g., Claude), one would simply need to add a new condition to handle its specific CLI tool and parameters, without changing the agent logic itself.

### 1. `instruQtor` (The Planner)

-   **File**: `worqer/instruQtor.py`
-   **Purpose**: To decompose a high-level task (`tasQ.md`) into a series of small, actionable steps (`briQ.md` files).

### Logic Flow:
1.  **Input**: Reads the `tasQ.md` file for the current cycle.
2.  **Prompting**: Constructs a detailed prompt for the planner AI. This prompt instructs the AI to act as a senior engineer, break the task into atomic steps, and format the output as a single markdown document with strict `### Step N:` headers.
3.  **AI Invocation**: Passes this prompt to the `run_ai_completion` function in `lib_ai.py`, which calls the configured OpenAI model (`gpt-4o-mini` by default).
4.  **Parsing**: The returned markdown plan is parsed using a regular expression that splits the content based on the `### Step N:` headers. This results in a list of individual "Briqs".
5.  **Output**: Each "Briq" is saved as a separate markdown file (e.g., `cyqle1_tasq1_briq000_create_server.md`) in the `briq.d/` directory. The filename includes a semantic slug generated from the step's title for readability.

### 2. `construQtor` (The Executor)

-   **File**: `worqer/construQtor.py`
-   **Purpose**: To execute the steps outlined in the `briQ.md` files and generate the actual code and artifacts.

### Logic Flow:
1.  **Input**: Globs the `briq.d/` directory to find all `briQ.md` files for the current cycle.
2.  **Sequential Execution**: It iterates through the Briqs one by one in alphabetical order.
3.  **Context Building**: For each Briq, it constructs a prompt for the executor AI. This prompt includes:
    -   The instructions from the current `briQ.md` file.
    -   **Crucially**, a "soft-jail" instruction telling the AI that all file paths must be prefixed with `qodeyard/`.
    -   It also passes the entire `qodeyard/` directory as context, so the AI is aware of the files it has created in previous steps of the same cycle.
4.  **AI Invocation**: The prompt is passed to `run_ai_completion` in `lib_ai.py`, which calls the configured Gemini model (`gemini-2.5-flash` by default). The Gemini CLI's ability to directly modify the filesystem is used here.
5.  **Output**: A simple summary file (`exeq.d/cyqleN_summary.md`) is generated, indicating the success or failure of the execution phase. The primary output is the code and artifacts created within the `qodeyard/` directory.

### 3. `inspeQtor` (The Reviewer)

-   **File**: `worqer/inspeQtor.py`
-   **Purpose**: To review the work of the `construQtor` and provide feedback for the next cycle, creating the critical feedback loop.

### Logic Flow:
1.  **Input**: Reads the execution summary from `exeq.d/` and walks the entire `qodeyard/` directory to gather all generated file contents.
2.  **Context Building**: It assembles a comprehensive prompt for the reviewer AI. This prompt includes:
    -   The `construQtor`'s execution summary.
    -   The complete contents of every file generated in the `qodeyard`.
3.  **Prompting**: The prompt instructs the AI to act as a senior code reviewer. It must provide an `Assessment` (`Success`, `Partial`, `Failure`), a `Summary` of findings, and a bulleted list of `Suggestions` for the next cycle. The prompt encourages "visionary" suggestions that go beyond simple bug fixes.
4.  **AI Invocation**: The prompt is passed to `run_ai_completion` in `lib_ai.py`, which calls the configured OpenAI model (`gpt-4o-mini` by default).
5.  **Output**: The AI's response is written to `reqap.d/cyqleN_reqap.md`. This "reQap" file is what the user sees at the `CheQpoint` and, if approved, becomes the new `tasQ.md` for the subsequent cycle.
