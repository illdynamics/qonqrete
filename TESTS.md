# QonQrete Functional Tests

This document outlines a comprehensive suite of functional tests designed to validate the entire QonQrete application. These tests cover the command-line interface, core orchestration logic, agent behaviors, configuration options, and edge cases.

## 1. Environment and Setup Tests

### 1.1. `qonqrete.sh` CLI

-   [ ] **`init` Command**:
    -   [x] Run `./qonqrete.sh init`. Verify Docker builds the `qonqrete-qage` image successfully.
    -   [ ] Run `./qonqrete.sh init --msb`. Verify Microsandbox builds the `qonqrete-qage` image successfully.
    -   [ ] Run `./qonqrete.sh init` without Docker or `msb` installed. Verify it exits with a clear error message.
-   [x] **`run` Command**:
    -   [x] Run `./qonqrete.sh run` without `OPENAI_API_KEY` and `GOOGLE_API_KEY` environment variables set. Verify it fails with a "API Keys missing" error.
    -   [x] Run `./qonqrete.sh run` with API keys set. Verify a `qage_<timestamp>` directory is created in `worqspace/`.
    -   [x] Verify the new `qage` directory contains copies of `config.yaml`, `pipeline_config.yaml`, and `cyqle1_tasq.md` (a copy of the original `tasq.md`).
    -   [x] Delete `worqspace/tasq.md` and run `./qonqrete.sh run`. Verify it quits and tells us it's missing the `tasq.md` file.
-   [x] **`clean` Command**:
    -   [x] With `qage_*` directories present, run `./qonqrete.sh clean`. When prompted with "[y/N]", enter "n". Verify directories are not deleted.
    -   [x] Run `./qonqrete.sh clean` again. When prompted, enter "y". Verify all `qage_*` directories are deleted.
    -   [x] Run `./qonqrete.sh clean` when no `qage_*` directories exist. Verify it prints a "No 'qage_*' directories found" message and exits.
-   [x] **Command-Line Flags**:
    -   [ ] Test each flag individually: `./qonqrete.sh run --auto`, `--user`, `--tui`, `--mode security`, `--briq-sensitivity 7`, `--msb`, `--docker`, `--wonqrete`. Verify the corresponding arguments are passed to `qrane.py`.
    -   [ ] Test short versions of flags: `-a`, `-u`, `-t`, `-m security`, `-b 7`, `-s`, `-d`, `-w`.
    -   [x] Test using `--auto` and `--user` together. Verify the script exits with a "mutually exclusive" error message.
    -   [ ] Test a combination of flags: `./qonqrete.sh run --auto --tui --mode enterprise -b 3`.
    -   [ ] Test overriding `pipeline_config.yaml` (`microsandbox: true`) with `./qonqrete.sh run --docker`.
-   [x] **Help and Version**:
    -   [x] Run `./qonqrete.sh --help` and `-h`. Verify the help message is displayed and includes the new `--user` flag.
    -   [x] Run `./qonqrete.sh --version` and `-V`. Verify the version from the `VERSION` file is displayed.
-   [x] **Pre-flight Checks**:
    -   [x] Temporarily rename `config.yaml` and run `./qonqrete.sh run`. Verify the system exits with a clear error.
    -   [x] Temporarily rename `pipeline_config.yaml` and run `./qonqrete.sh run`. Verify the system exits with a clear error.

## 2. Core Orchestration (`Qrane`) Tests

### 2.1. Run Modes
-   [ ] **Manual Mode (Default)**:
    -   [ ] Run a task. Verify the system pauses at the "CheQpoint" after each cycle.
    -   [ ] At the CheQpoint, press 'q'. Verify the system continues to the next cycle.
    -   [ ] At the CheQpoint, press 'x'. Verify the system quits gracefully.
    -   [ ] At the CheQpoint, press 't'. Verify `$EDITOR` opens with the `reqap.md` file. After closing the editor, verify the prompt is shown again.
-   [x] **Autonomous Mode (`--auto`)**:
    -   [x] Run with `--auto`. Verify the system runs through cycles without user interaction.
    -   [x] In `config.yaml`, set `auto_cycle_limit: 2`. Run in auto mode. Verify the system stops after cycle 2 with a "Max cyQle limit hit" message.
    -   [ ] Set `auto_cycle_limit: 0`. Verify it runs until the task is complete or it fails.

### 2.2. Cheqpoint Configuration (`config.yaml`)
-   [ ] **`cheqpoint: true` (Default)**:
    -   [ ] Set `cheqpoint: true` in `config.yaml`. Run `./qonqrete.sh run`. Verify it runs in user-gated mode.
    -   [ ] With `cheqpoint: true`, run `./qonqrete.sh run --auto`. Verify it correctly overrides the config and runs in autonomous mode.
-   [ ] **`cheqpoint: false`**:
    -   [ ] Set `cheqpoint: false` in `config.yaml`. Run `./qonqrete.sh run`. Verify it runs in autonomous mode by default.
    -   [ ] With `cheqpoint: false`, run `./qonqrete.sh run --user`. Verify it correctly overrides the config and runs in user-gated mode.

### 2.3. Cycle and File Management
-   [x] **I/O Flow**: After a successful cycle 1, verify that `cyqle1_reqap.md` is correctly used to generate `cyqle2_tasq.md`.
-   [x] **Header Promotion**: Check the content of `cyqle2_tasq.md`. It must contain a header with the "Assessment" status from the previous cycle.
-   [x] **Agent Failure**: Introduce an error in an agent script (e.g., `sys.exit(1)` in `construqtor.py`). Run the system. Verify the cycle fails and the orchestration stops with an error message.
-   [x] **Logging**: For a successful run, inspect `struqture/`. Verify a log file exists for each agent for each cycle (e.g., `cyqle1_instruqtor.log`).

## 3. Agent Configuration and Behavior

### 3.1. Dynamic Pipeline (`pipeline_config.yaml`)
-   [x] **Remove Agent**:
    -   [x] Comment out the `inspeqtor` agent from the config. Run one cycle. Verify the system stops after `construqtor` and waits at the CheQpoint (it may complain about a missing `reqap` file, this is expected).
-   [x] **Reorder Agents (Failure Test)**:
    -   [x] Swap the `construqtor` and `instruqtor` blocks in the config. Run the system. Verify it fails immediately because `construqtor` cannot find its required `briq.d/` input. This confirms the order is respected.
### 3.2. Agent Settings (`config.yaml`)
-   [x] **Swap Providers**:
    -   [x] Change `instruqtor`'s provider to `gemini`. Run a cycle. Verify `gemini` is called for the planning phase.
    -   [x] Change `construqtor`'s provider to `openai`. Run a cycle. Verify `sgpt` is called for the execution phase.
-   [x] **Swap Models**:
    -   [x] Change `inspeqtor`'s model to a different, valid OpenAI model. Verify the new model is used.
-   [x] **Operational Modes**:
    -   [x] Set `mode: security` in `config.yaml`. Run a task to generate a Python script. Inspect the AI's output to verify it includes security-conscious code (e.g., input validation).
    -   [ ] Set `mode: enterprise`. Verify the output includes docstrings, logging, and error handling.
-   [x] **Briq Sensitivity**:
    -   [x] Set `briq_sensitivity: 0` (Atomic). Use a complex `tasq.md`. Verify `instruqtor` generates a large number of briq files.
    -   [x] Set `briq_sensitivity: 9` (Monolithic). Use the same `tasq.md`. Verify `instruqtor` generates very few (ideally 1) briq files.

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
-   [x] **Invalid `tasq.md` Content**:
    -   [x] Fill `tasq.md` with non-UTF-8 characters, symbols, and mixed languages (`"你好 RÄtsel"`, etc.).
    -   [x] Run the system. Verify that the file is read and passed to the AI without crashing the `instruqtor`.
-   [x] **Invalid Agent Output**:
    -   [x] Manually edit `instruqtor.py` to output malformed XML (no `<briq>` tags). Verify `instruqtor` logs a warning and creates a single fallback briq file containing the raw AI output.
    -   [x] Manually edit `construqtor.py` to not generate any code blocks. Verify the summary reports a "failure" for that briq.
-   [x] **Log Errors**:
    -   [x] Force an agent to crash with an unhandled Python exception.
    -   [x] Inspect the agent's log file in `struqture/` and the stderr output from `qrane`. Verify the full traceback is recorded.
-   [x] **Permissions**:
    -   [x] Change permissions of `worqspace/` to read-only (`chmod -R 444 worqspace`). Run `./qonqrete.sh run`. Verify it fails immediately with permission errors.

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

## 7. Provider & Model Matrix Tests

These tests validate that QonQrete can switch between multiple AI providers and their most common models without crashing, misrouting prompts, or corrupting artifacts.

### 7.1 Provider / Model Catalog (Reference)

Use these as the canonical test set (adjust model IDs if your adapter uses different names):

- **OpenAI**
  - Primary: `gpt-4o`
  - Secondary: `gpt-4o-mini`

- **Google / Gemini**
  - Primary: `gemini-2.5-flash`
  - Secondary: `gemini-2.5-pro`

- **DeepSeek**
  - Primary: `deepseek-chat`
  - Secondary: `deepseek-coder`

- **Claude**
  - Primary: `claude-3.5-sonnet`
  - Secondary: `claude-3.5-haiku`

All tests below assume the three agents are:

- `instruqtor`
- `construqtor`
- `inspeqtor`

### 7.2 Single-Provider / All-Agents Smoke Tests

For each checkbox, set **all three agents** in `config.yaml` to the given `provider` and `model`, then run a short tasq with:

- `./qonqrete.sh run --auto`
- Simple `tasq.md` that forces at least 1 full cyQle.

- [ ] All agents → **OpenAI / gpt-4o**
- [ ] All agents → **OpenAI / gpt-4o-mini**
- [ ] All agents → **Gemini / gemini-2.5-flash**
- [ ] All agents → **Gemini / gemini-2.5-pro**
- [ ] All agents → **DeepSeek / deepseek-chat**
- [ ] All agents → **DeepSeek / deepseek-coder**
- [ ] All agents → **Claude / claude-3.5-sonnet**
- [ ] All agents → **Claude / claude-3.5-haiku**

For each run, verify:

- [ ] CyQle completes without Python errors or provider API errors.
- [ ] `struqture/` contains logs for all 3 agents for the cyQle.
- [ ] `briq.d/`, `exeq.d/`, and `reqap.d/` contain the expected artifacts.

### 7.3 Per-Agent Provider Rotation (One Agent at a Time)

Goal: prove each **individual agent** can be swapped through all providers/models while the others stay stable.

For these tests, keep **two agents fixed** on a known-good combo  
(e.g. `openai / gpt-4o`) and rotate the third.

#### 7.3.1 instruqtor Provider/Model Sweep

- [ ] Fix `construqtor` and `inspeqtor` to `openai / gpt-4o`.
- [ ] For each `(provider, model)` in the catalog, set `instruqtor` and run `./qonqrete.sh run --auto`:

  - [ ] instruqtor → OpenAI / gpt-4o
  - [ ] instruqtor → OpenAI / gpt-4o-mini
  - [ ] instruqtor → Gemini / gemini-2.5-flash
  - [ ] instruqtor → Gemini / gemini-2.5-pro
  - [ ] instruqtor → DeepSeek / deepseek-chat
  - [ ] instruqtor → DeepSeek / deepseek-coder
  - [ ] instruqtor → Claude / claude-3.5-sonnet
  - [ ] instruqtor → Claude / claude-3.5-haiku

Verify:

- [ ] `briq.d/` is always produced and non-empty.
- [ ] No provider/model mismatch errors (e.g., unknown model, bad request).

#### 7.3.2 construqtor Provider/Model Sweep

- [ ] Fix `instruqtor` and `inspeqtor` to `openai / gpt-4o`.
- [ ] Sweep `construqtor` through the same `(provider, model)` list.

Verify:

- [ ] `exeq.d/cyqle{N}_summary.md` is produced.
- [ ] No provider/model errors and no missing briq input errors.

#### 7.3.3 inspeqtor Provider/Model Sweep

- [ ] Fix `instruqtor` and `construqtor` to `openai / gpt-4o`.
- [ ] Sweep `inspeqtor` through all `(provider, model)` combos.

Verify:

- [ ] `reqap.d/cyqle{N}_reqap.md` is produced and well-formed.
- [ ] No provider/model errors.

### 7.4 Mixed-Provider Matrix (Cross-Provider Triples)

This section aims to stress “mixed” setups where different agents talk to different providers.

Use the **primary models** only for this section:

- OpenAI: `gpt-4o`
- Gemini: `gemini-2.5-flash`
- DeepSeek: `deepseek-chat`
- Claude: `claude-3.5-sonnet`

#### 7.4.1 Key Cross-Provider Scenarios

For each test, set providers/models as specified, then run `./qonqrete.sh run --auto`:

- [ ] instruqtor: OpenAI / gpt-4o  
      construqtor: Gemini / gemini-2.5-flash  
      inspeqtor: OpenAI / gpt-4o

- [ ] instruqtor: Gemini / gemini-2.5-flash  
      construqtor: OpenAI / gpt-4o  
      inspeqtor: OpenAI / gpt-4o

- [ ] instruqtor: DeepSeek / deepseek-chat  
      construqtor: OpenAI / gpt-4o  
      inspeqtor: Claude / claude-3.5-sonnet

- [ ] instruqtor: OpenAI / gpt-4o  
      construqtor: DeepSeek / deepseek-chat  
      inspeqtor: Claude / claude-3.5-sonnet

- [ ] instruqtor: Claude / claude-3.5-sonnet  
      construqtor: Gemini / gemini-2.5-flash  
      inspeqtor: OpenAI / gpt-4o

- [ ] instruqtor: Gemini / gemini-2.5-flash  
      construqtor: DeepSeek / deepseek-chat  
      inspeqtor: Claude / claude-3.5-sonnet

Verify for each:

- [ ] No provider-specific tracebacks in logs.
- [ ] All expected artifacts (`briq.d/`, `exeq.d/`, `reqap.d/`) are present.
- [ ] `struqture/` logs show correct provider/model per agent.

#### 7.4.2 Full Provider Triple Matrix (Optional Exhaustive Sweep)

**Optional but ideal for automation:**

- [ ] Programmatically iterate over all triples  
      `(P_instruqtor, P_construqtor, P_inspeqtor)` in `{openai, gemini, deepseek, claude}^3`,  
      using primary models, and run a short cyQle.

Record for each:

- [ ] Whether the run completed successfully.
- [ ] Any provider/model-specific errors.
- [ ] Whether all three artifact directories were populated.

### 7.5 Model Variant Swaps Within a Provider

For each provider, validate swapping between its primary and secondary model with all agents set to the same provider.

Example for OpenAI:

- [ ] All agents → `openai / gpt-4o`
- [ ] All agents → `openai / gpt-4o-mini`
- [ ] Mixed models:  
      instruqtor: gpt-4o-mini, construqtor: gpt-4o, inspeqtor: gpt-4o-mini

Repeat equivalent tests for:

- [ ] Gemini (flash vs pro)
- [ ] DeepSeek (chat vs coder)
- [ ] Claude (sonnet vs haiku)

Verify:

- [ ] No “unknown model” or schema errors.
- [ ] Prompt/response handling still works (no parsing crashes).

