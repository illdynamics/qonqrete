# QonQrete Documentation

**Version:** `v0.1.0` (See `VERSION` file for the canonical version).

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
-   **Qage (`Dockerfile`)**: A secure Docker container that acts as a sandbox for the AI agents. All code generation and execution happens inside the `Qage`, preventing any impact on your host system.
-   **worQer (`worqer/`)**: The AI agents that perform the core tasks of planning, executing, and reviewing. There are three types of `worQer` agents:
    -   **instruQtor**: The Planner. It takes a high-level task and breaks it down into a series of smaller, actionable steps called `briQ`s.
    -   **construQtor**: The Executor. It takes the `briQ`s and executes them, generating code and other artifacts in the `qodeyard/` directory.
    -   **inspeQtor**: The Reviewer. It reviews the work of the `construQtor`, assesses its quality, and provides a summary and suggestions for the next cycle in a `reQap` file.
-   **worQspace (`worqspace/`)**: A shared directory that acts as the communication bridge between the `Qrane` and the `Qage`. It contains:
    -   `config.yaml`: The configuration file for the system.
    -   `tasq.md`: The initial high-level task for the agents.
    -   `briq.d/`: The directory where the `instruQtor` saves the `briQ` files.
    -   `exeq.d/`: The directory where the `construQtor` saves its execution summaries.
    -   `reqap.d/`: The directory where the `inspeQtor` saves its review files.
    -   `qodeyard/`: The directory where the `construQtor` generates the code and other artifacts.

## Workflow

The QonQrete system operates in a `cyQle` that consists of three main phases:

1.  **Plan**: The `instruQtor` reads the `tasq.md` file and creates a series of `briQ` files, which are detailed instructions for the `construQtor`.
2.  **Execute**: The `construQtor` reads the `briQ` files and executes them, generating code in the `qodeyard/` directory.
3.  **Review**: The `inspeQtor` reviews the code in the `qodeyard/` and the execution summary from the `construQtor`, and creates a `reQap.md` file with an assessment and suggestions for the next `cyQle`.

After each `cyQle`, the system pauses at a **CheQpoint**, and the user (the **gateQeeper**) is prompted to review the `reQap.md` file and decide whether to continue, tweak the instructions, or quit.

## Configuration

The behavior of the QonQrete system can be configured in the `worqspace/config.yaml` file. The following options are available:

-   **`auto_cycle_limit`**: The maximum number of `cyQle`s to run in autonomous mode. A value of `0` means the system will run until it reaches a `Success` state.
-   **`agents`**: The AI models to be used by the `instruQtor`, `construQtor`, and `inspeQtor`.

## Getting Started

To get started with QonQrete, please see the **[QUICKSTART.md](./QUICKSTART.md)** guide.

## Terminology

For a complete list of the terminology used in the QonQrete system, please see the **[TERMINOLOGY.md](./TERMINOLOGY.md)** file.
