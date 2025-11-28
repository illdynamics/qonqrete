# QonQrete Documentation

**Version:** `v0.2.1-alpha` (See `VERSION` file for the canonical version).

This document provides a comprehensive overview of the QonQrete Secure AI Construction Loop System.

## Table of Contents
- [Architecture](#architecture)
- [Workflow](#workflow)
- [Configuration](#configuration)
- [Getting Started](#getting-started)
- [Terminology](#terminology)

## Architecture

QonQrete is a multi-agent orchestration system designed for secure, observable, and human-in-the-loop software construction.

### Core Components

-   **Qrane (`qrane/`)**: The host-layer orchestrator that runs on your machine. It manages the `Qage` lifecycle, the command-line interface, and the overall workflow.
-   **Qage (`Dockerfile`, `Sandboxfile`)**: A secure container that acts as a sandbox for the AI agents. It can be run with Docker (default) or Microsandbox.
-   **worQer (`worqer/`)**: The AI agents that perform the core tasks of planning, executing, and reviewing. There are three types of `worQer` agents:
    -   **instruQtor**: The Planner. It takes a high-level task and breaks it down into a series of smaller, actionable steps called `briQ`s.
    -   **construQtor**: The Executor. It takes the `briQ`s and executes them, generating code and other artifacts in the `qodeyard/` directory.
    -   **inspeQtor**: The Reviewer. It reviews the work of the `construQtor`, assesses its quality, and provides a summary and suggestions for the next cycle in a `reQap` file.
-   **worQspace (`worqspace/`)**: A shared directory that acts as the communication bridge between the `Qrane` and the `Qage`. It contains all configuration, tasks, and generated agent data.

## Workflow

The QonQrete system operates in a `cyQle` that consists of three main phases:

1.  **Plan**: The `instruQtor` reads the `tasq.md` file and creates a series of `briQ` files.
2.  **Execute**: The `construQtor` reads the `briQ` files and executes them, generating code in the `qodeyard/` directory.
3.  **Review**: The `inspeQtor` reviews the code and creates a `reQap.md` file with an assessment and suggestions for the next `cyQle`.

After each `cyQle`, the system pauses at a **CheQpoint**, and the user (the **gateQeeper**) is prompted to review the `reQap.md` file and decide whether to continue, tweak the instructions, or quit.

## Configuration

The behavior of the QonQrete system can be configured in the `worqspace/` directory.

-   **`config.yaml`**:
    -   **`auto_cycle_limit`**: The maximum number of `cyQle`s to run in autonomous mode. `0` means infinite.
    -   **`agents`**: The AI models to be used by the `instruQtor`, `construQtor`, and `inspeQtor`. The defaults are now set to faster models (`gpt-4o-mini` and `gemini-2.5-flash`).
-   **`pipeline_config.yaml`**:
    -   **`microsandbox`**: Set to `true` to make Microsandbox (`msb`) the default container runtime instead of Docker.

## Getting Started

To get started with QonQrete, please see the **[QUICKSTART.md](./QUICKSTART.md)** guide.

## Terminology

For a complete list of the terminology used in the QonQrete system, please see the **[TERMINOLOGY.md](./TERMINOLOGY.md)** file.
