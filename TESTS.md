# QonQrete Functional Tests

This document outlines a comprehensive suite of functional tests designed to validate the entire QonQrete application. These tests cover the command-line interface, core orchestration logic, agent behaviors, configuration options, and edge cases.

## 1. Environment and Setup Tests

### 1.1. `qonqrete.sh` CLI

-   [ ] **`init` Command**:
    -   [ ] Run `./qonqrete.sh init`. Verify Docker builds the `qonqrete-qage` image successfully.
    -   [ ] Run `./qonqrete.sh init --msb`. Verify Microsandbox builds the `qonqrete-qage` image successfully.
    -   [ ] Run `./qonqrete.sh init` without Docker or `msb` installed. Verify it exits with a clear error message.
-   [ ] **`run` Command**:
    -   [ ] Run `./qonqrete.sh run` without `OPENAI_API_KEY` and `GOOGLE_API_KEY` environment variables set. Verify it fails with a "API Keys missing" error.
    -   [ ] Run `./qonqrete.sh run` with API keys set. Verify a `qage_<timestamp>` directory is created in `worqspace/`.
    -   [ ] Verify the new `qage` directory contains copies of `config.yaml`, `pipeline_config.yaml`, and `tasq.md`.
    -   [ ] Delete `worqspace/tasq.md` and run `./qonqrete.sh run`. Verify a default `tasq.md` is created in the `qage` directory.
-   [ ] **`clean` Command**:
    -   [ ] With `qage_*` directories present, run `./qonqrete.sh clean`. When prompted with "[y/N]", enter "n". Verify directories are not deleted.
    -   [ ] Run `./qonqrete.sh clean` again. When prompted, enter "y". Verify all `qage_*` directories are deleted.
    -   [ ] Run `./qonqrete.sh clean` when no `qage_*` directories exist. Verify it prints a "No 'qage_*' directories found" message and exits.
-   [ ] **Command-Line Flags**:
    -   [ ] Test each flag individually: `./qonqrete.sh run --auto`, `--tui`, `--mode security`, `--briq-sensitivity 7`, `--msb`, `--docker`, `--wonqrete`. Verify the corresponding arguments are passed to `qrane.py`.
    -   [ ] Test short versions of flags: `-a`, `-t`, `-m security`, `-b 7`, `-s`, `-d`, `-w`.
    -   [ ] Test a combination of flags: `./qonqrete.sh run --auto --tui --mode enterprise -b 3`.
    -   [ ] Test overriding `pipeline_config.yaml` (`microsandbox: true`) with `./qonqrete.sh run --docker`.
-   [ ] **Help and Version**:
    -   [ ] Run `./qonqrete.sh --help` and `-h`. Verify the help message is displayed.
    -   [ ] Run `./qonqrete.sh --version` and `-V`. Verify the version from the `VERSION` file is displayed.
-   [ ] **Pre-flight Checks**:
    -   [ ] Temporarily rename `config.yaml` and run `./qonqrete.sh run`. Verify the system exits with a clear error. (Note: Pre-flight checks are currently optional in `qrane.py`).
    -   [ ] In a container without `sgpt` installed, run the system. Verify it exits with a "CLI tool... not found" error.

## 2. Core Orchestration (`Qrane`) Tests

### 2.1. Run Modes
-   [ ] **Manual Mode (Default)**:
    -   [ ] Run a task. Verify the system pauses at the "CheQpoint" after each cycle.
    -   [ ] At the CheQpoint, press 'q'. Verify the system continues to the next cycle.
    -   [ ] At the CheQpoint, press 'x'. Verify the system quits gracefully.
    -   [ ] At the CheQpoint, press 't'. Verify `$EDITOR` opens with the `reqap.md` file. After closing the editor, verify the prompt is shown again.
-   [ ] **Autonomous Mode (`--auto`)**:
    -   [ ] Run with `--auto`. Verify the system runs through cycles without user interaction.
    -   [ ] In `config.yaml`, set `auto_cycle_limit: 2`. Run in auto mode. Verify the system stops after cycle 2 with a "Max cyQle limit hit" message.
    -   [ ] Set `auto_cycle_limit: 0`. Verify it runs until the task is complete or it fails.
### 2.2. Cycle and File Management
-   [ ] **I/O Flow**: After a successful cycle 1, verify that `cyqle1_reqap.md` is correctly used to generate `cyqle2_tasq.md`.
-   [ ] **Header Promotion**: Check the content of `cyqle2_tasq.md`. It must contain a header with the "Assessment" status from the previous cycle.
-   [ ] **Agent Failure**: Introduce an error in an agent script (e.g., `sys.exit(1)` in `construqtor.py`). Run the system. Verify the cycle fails and the orchestration stops with an error message.
-   [ ] **Logging**: For a successful run, inspect `struqture/`. Verify a log file exists for each agent for each cycle (e.g., `cyqle1_instruqtor.log`).

## 3. Agent Configuration and Behavior

### 3.1. Dynamic Pipeline (`pipeline_config.yaml`)
-   [ ] **Remove Agent**:
    -   [ ] Comment out the `inspeqtor` agent from the config. Run one cycle. Verify the system stops after `construqtor` and waits at the CheQpoint (it may complain about a missing `reqap` file, this is expected).
-   [ ] **Reorder Agents (Failure Test)**:
    -   [ ] Swap the `construqtor` and `instruqtor` blocks in the config. Run the system. Verify it fails immediately because `construqtor` cannot find its required `briq.d/` input. This confirms the order is respected.
### 3.2. Agent Settings (`config.yaml`)
-   [ ] **Swap Providers**:
    -   [ ] Change `instruqtor`'s provider to `gemini`. Run a cycle. Verify `gemini` is called for the planning phase.
    -   [ ] Change `construqtor`'s provider to `openai`. Run a cycle. Verify `sgpt` is called for the execution phase.
-   [ ] **Swap Models**:
    -   [ ] Change `inspeqtor`'s model to a different, valid OpenAI model. Verify the new model is used.
-   [ ] **Operational Modes**:
    -   [ ] Set `mode: security` in `config.yaml`. Run a task to generate a Python script. Inspect the AI's output to verify it includes security-conscious code (e.g., input validation).
    -   [ ] Set `mode: enterprise`. Verify the output includes docstrings, logging, and error handling.
-   [ ] **Briq Sensitivity**:
    -   [ ] Set `briq_sensitivity: 0` (Atomic). Use a complex `tasq.md`. Verify `instruqtor` generates a large number of briq files.
    -   [ ] Set `briq_sensitivity: 9` (Monolithic). Use the same `tasq.md`. Verify `instruqtor` generates very few (ideally 1) briq files.

## 4. TUI Mode Tests (`--tui`)

-   [ ] **Window Management**:
    -   [ ] Start in TUI mode. Verify the split-screen view is shown by default.
    -   [ ] Press the `Space` bar. Verify the bottom "Qonsole" window disappears.
    -   [ ] Press `Space` again. Verify the "Qonsole" window reappears.
-   [ ] **Logging**:
    -   [ ] Verify high-level status messages from `Qrane` and agents appear in the top "Qommander" window.
    -   [ ] Verify raw agent logs and verbose output appear in the bottom "Qonsole" window.
    -   [ ] Verify agent names are color-coded correctly in the top window.
-   [ ] **Controls**:
    -   [ ] Press 'w'. Verify the top window title switches to "WoNQrete". Press 'w' again to switch back.
    -   [ ] During an agent run, press 'k'. Verify the agent process is killed and the TUI exits with a "Qilled" message.
    -   [ ] Press `Esc`. Verify the TUI exits gracefully.
-   [ ] **CheQpoint Input**:
    -   [ ] At a CheQpoint, verify the TUI prompts for input (`[Q]ontinue...`).
    -   [ ] Enter 't'. Verify the TUI is suspended and `$EDITOR` opens. After exiting, verify the TUI is restored correctly.

## 5. Edge Cases and Error Handling

-   [ ] **Large Tasq / I/O Stress Test**:
    -   [ ] Create a `tasq.md` that is extremely long and complex, requiring deep analysis.
    -   [ ] Run a full cycle. Monitor for I/O errors, prompt size limits with AI providers, or timeouts. Verify the system either completes or fails with a specific error message logged.
-   [ ] **Invalid `tasq.md` Content**:
    -   [ ] Fill `tasq.md` with non-UTF-8 characters, symbols, and mixed languages (`"你好 RÄtsel"`, etc.).
    -   [ ] Run the system. Verify that the file is read and passed to the AI without crashing the `instruqtor`.
-   [ ] **Invalid Agent Output**:
    -   [ ] Manually edit `instruqtor.py` to output malformed XML (no `<briq>` tags). Verify `instruqtor` logs a warning and creates a single fallback briq file containing the raw AI output.
    -   [ ] Manually edit `construqtor.py` to not generate any code blocks. Verify the summary reports a "failure" for that briq.
-   [ ] **Log Errors**:
    -   [ ] Force an agent to crash with an unhandled Python exception.
    -   [ ] Inspect the agent's log file in `struqture/` and the stderr output from `qrane`. Verify the full traceback is recorded.
-   [ ] **Permissions**:
    -   [ ] Change permissions of `worqspace/` to read-only (`chmod -R 444 worqspace`). Run `./qonqrete.sh run`. Verify it fails immediately with permission errors.

## 6. Multi-Platform Testing

-   [ ] **Windows**:
    -   [ ] On a Windows VM with Docker Desktop and Python 3 installed:
    -   [ ] Run `./qonqrete.sh init`.
    -   [ ] Run a full task cycle with `./qonqrete.sh run`.
    -   [ ] Test the `clean` command.
    -   [ ] *Note*: The `getch()` function in `qrane.py` may behave differently. Test manual mode CheQpoints.
-   [ ] **macOS**:
    -   [ ] On a macOS machine with Docker Desktop and Python 3:
    -   [ ] Run `./qonqrete.sh init`.
    -   [ ] Run a full task cycle with `./qonqrete.sh run`.
    -   [ ] Test TUI mode (`--tui`), as terminal behavior can differ.
-   [ ] **Microsandbox (`msb`)**:
    -   [ ] On a Linux machine with `msb` installed:
    -   [ ] Run `./qonqrete.sh init --msb`.
    -   [ ] Run a full task cycle using `./qonqrete.sh run --msb`.
    -   [ ] Set `microsandbox: true` in `pipeline_config.yaml` and run without the `--msb` flag to test the default detection.
