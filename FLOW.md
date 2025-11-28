# QonQrete Execution Flows

This document traces the end-to-end execution flows of the QonQrete system, from user command to the completion of a cycle. This verification is based on a static analysis of the codebase.

## 1. Initialization Flow (`./qonqrete.sh init`)

1.  **User Input**: User executes `./qonqrete.sh init`. An optional `--msb` or `--docker` flag can be provided.
2.  **`qonqrete.sh`**: The script parses the `init` command.
3.  **Runtime Detection**: It checks for the `--msb` or `--docker` flags. If none are provided, it checks `pipeline_config.yaml` for a `microsandbox: true` setting. If not found, it defaults to Docker.
4.  **Container Build**:
    *   If the runtime is `docker`, it executes `docker build -t qonqrete-qage -f Dockerfile .`.
    *   If the runtime is `msb`, it executes `msb build . -t qonqrete-qage` (or `mbx`).
5.  **Result**: A container image named `qonqrete-qage` is created in the local registry of the selected runtime, ready for execution.

## 2. Main Execution Flow (`./qonqrete.sh run`)

1.  **User Input**: User executes `./qonqrete.sh run`. Optional flags like `--auto` and `--tui` can be included.
2.  **`qonqrete.sh`**:
    *   Parses the `run` command and any additional flags.
    *   Verifies that `OPENAI_API_KEY` and `GOOGLE_API_KEY` are exported in the shell.
    *   Reads the `VERSION` file and exports it as `QONQ_VERSION`.
    *   Creates a unique timestamped run directory inside `worqspace/` (e.g., `worqspace/qage_20251128_180000`).
    *   Copies `config.yaml`, `pipeline_config.yaml`, and the initial `tasq.md` into this new run directory. `tasq.md` is renamed to `cyqle1_tasq.md`.
    *   Constructs the `docker run` or `msb run` command. This includes mounting the new run directory to `/qonq` inside the container, mounting the local source code for development, and passing through API keys.
3.  **`qrane.py` (Inside the Container)**:
    *   The container starts and executes `qrane/qrane.py`.
    *   The orchestrator determines if it's in TUI or headless mode based on the `--tui` flag.
    *   It enters the main `while` loop, which represents a `cyQle`.
4.  **The `cyQle` Loop**:
    *   **`instruQtor` Run**: `qrane.py` executes `instruqtor.py` as a subprocess. The `instruQtor` reads `tasq.d/cyqleN_tasq.md` and generates `briQ.d/*.md` files.
    *   **`construQtor` Run**: `qrane.py` executes `construqtor.py` as a subprocess. The `construQtor` reads the `briQ.d/*.md` files and generates code in the `qodeyard/` directory.
    *   **`inspeQtor` Run**: `qrane.py` executes `inspeqtor.py` as a subprocess. The `inspeQtor` reads the `qodeyard/` contents and generates a `reqap.d/cyqleN_reqap.md` file.
5.  **The `CheQpoint`**:
    *   `qrane.py` reads the `reqap.md` file.
    *   **Headless Mode**: It prints the reQap to standard output and prompts the user for `[Q]ontinue`, `[T]weaQ`, or `[X]Quit`.
    *   **TUI Mode**: It displays the reQap in the top "Qommander" panel and waits for user input.
    *   **Auto Mode**: The check is bypassed, and the flow proceeds as if the user selected 'Qontinue'.
6.  **Loop Continuation**:
    *   If the user chooses to continue, `qrane.py` copies the content of the `reqap.md` to a new `tasq.d/cyqleN+1_tasq.md` file.
    *   The `while` loop increments the cycle counter and begins the next iteration.
7.  **Exit**: If the user quits, the `while` loop breaks, `qrane.py` finishes, and the container exits. `qonqrete.sh` completes its execution.

## 3. Cleanup Flow (`./qonqrete.sh clean`)

1.  **User Input**: User executes `./qonqrete.sh clean`.
2.  **`qonqrete.sh`**:
    *   The script searches the `worqspace/` directory for any subdirectories matching the pattern `qage_*`.
    *   It prompts the user for confirmation (`[y/N]`).
    *   If confirmed, it executes `rm -rf worqspace/qage_*`.
3.  **Result**: The `worqspace` is cleared of all previous run data, leaving only the core configuration files.
