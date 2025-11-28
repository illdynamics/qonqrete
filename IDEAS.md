# QonQrete Wild Ideas Report

This document contains a series of "out-of-the-box" ideas for expanding the QonQrete system beyond its current scope.

## 1. The "Evolvinator" Agent (`evolver`)

-   **Concept**: A new, fourth agent that is added to the end of the standard pipeline. Its sole purpose is to optimize the *other agents*.
-   **Logic**:
    1.  The `evolver` reads the `reQap` from the `inspeQtor`, but instead of focusing on the generated code (`qodeyard`), it focuses on the *suggestions*.
    2.  It also reads the source code of the other three agents (`instruQtor.py`, `construQtor.py`, `inspeQtor.py`).
    3.  Its prompt is: "Based on the attached suggestions from a previous run and the source code of the agents themselves, generate a plan to modify the agents' prompts or logic to better achieve the user's goal in the next cycle."
    4.  The output would be a `git apply`-compatible patch file, which the user could choose to apply at the `CheQpoint`.
-   **Impact**: Creates a meta-feedback loop where the system not only improves its output, but improves *itself*.

## 2. Dynamic Qrew Composition

-   **Concept**: Instead of a fixed pipeline, the `Qrane` acts as a dispatcher for a pool of specialized agents.
-   **Logic**:
    1.  The `pipeline_config.yaml` is replaced by a `qrew_manifest.yaml` that defines a roster of available agents (e.g., `python_writer`, `react_component_builder`, `sql_query_generator`, `code_refactorer`, `test_case_writer`).
    2.  The `instruQtor`'s role is expanded. It not only creates the `briQ` files but also adds a metadata tag to each one, like `agent_required: python_writer`.
    3.  The `Qrane` reads the Briqs and, like a project manager, dispatches each one to the appropriate specialist agent from the Qrew.
-   **Impact**: Transforms QonQrete into a true multi-agent system, capable of assembling the right team for any given task on the fly.

## 3. The "Auditor" Checkpoint

-   **Concept**: A new, optional checkpoint that occurs *before* the `construQtor` execution phase.
-   **Logic**:
    1.  After the `instruQtor` generates all the `briQ` files, the system pauses.
    2.  The user is presented with the complete, step-by-step plan.
    3.  The user can then approve the plan, `tweaQ` the individual `briQ` files, or cancel the run *before* any code is generated or API costs for the expensive execution phase are incurred.
-   **Impact**: Provides a critical cost- and time-saving control point, ensuring that the user agrees with the AI's proposed plan of action before committing to it.

## 4. "Live Qodeyard" TUI Integration

-   **Concept**: A third panel is added to the TUI that provides a live, read-only view of the `qodeyard` directory structure.
-   **Logic**:
    1.  The `Qrane` uses a file-watching library (e.g., `watchdog`) to monitor the `qodeyard` directory for any changes.
    2.  When a file is created, modified, or deleted by the `construQtor`, the TUI's third panel is immediately updated to reflect the new file tree.
    3.  The user could navigate this tree with the arrow keys and select a file to view its contents in a pop-up window.
-   **Impact**: Massively improves observability, allowing the user to watch the project being built in real-time, file by file.

## 5. Git Integration Agent (`versioner`)

-   **Concept**: An agent that automatically handles version control.
-   **Logic**:
    1.  A new `versioner` agent is added to the pipeline after the `inspeQtor`.
    2.  It reads the `reQap.md` and the `git diff` of the `qodeyard`.
    3.  It uses an AI to generate a descriptive, conventional commit message based on the changes and the `inspeQtor`'s summary.
    4.  At the `CheQpoint`, the user is presented not only with the `reQap`, but also the proposed commit message. The `[Q]ontinue` action would first commit the changes and then start the next cycle.
-   **Impact**: Automates the development workflow to a professional standard, creating a self-documenting, version-controlled project history.
