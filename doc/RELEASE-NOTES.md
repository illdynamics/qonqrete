# QonQrete v0.8.0-beta Release Notes

This release introduces **Qontrabender** - a sophisticated policy-driven hybrid caching agent with Variable Fidelity, and a comprehensive `caching_policy.yaml` configuration system. This represents a major architectural enhancement to the context management system.

## ✨ New Features & Major Enhancements

### 1. Qontrabender - The Cache Bender 🌀

A new agent that manages hybrid caching with intelligent content classification:

- **Variable Fidelity**: Mixes MEAT (full code) + BONES (skeletons) based on file importance
- **Policy-Driven Configuration**: All behavior controlled via `caching_policy.yaml`
- **Multiple Operational Modes**: 6 pre-configured modes for different use cases
- **Schema Validation**: YAML validation prevents bad configuration from breaking the flow
- **Improved Volatile Detection**: Cycle-based, diff-based, git diff, and mtime fallback

### 2. Caching Policy System (`caching_policy.yaml`)

A comprehensive policy file that controls all caching behavior:

```yaml
# Select mode in config.yaml:
qontrabender:
  policy_file: "./caching_policy.yaml"
  mode: "local_smart"
```

#### Available Modes:

| Mode | Description | Remote Cache |
|------|-------------|--------------|
| `local_fast` | Ultra-fast, skeleton only, minimal I/O | ❌ |
| `local_smart` | Default - variable fidelity, best balance | ❌ |
| `cyber_bedrock` | Remote cache for stable bedrock | ✅ |
| `cyber_aggressive` | Aggressive caching, more churn | ✅ |
| `paranoid_mincloud` | Minimal cloud exposure, skeletons only | ✅ |
| `debug_repro` | Maximum audit logging | ❌ |

### 3. Fidelity Rules Engine

Configurable rules determine how each file is treated:

```yaml
fidelity:
  rules:
    - name: "stable_core_full"
      when:
        tier: "stable"
        core_score_gte: 0.65
        file_chars_lte: 200000
      use: "full"
    - name: "massive_skeleton"
      when:
        file_chars_gte: 220000
      use: "skeleton"
```

### 4. Improved Volatile Detection

Multiple signals for detecting "volatile" files (excluded from cache, sent fresh):

- **Changed Files Manifest**: Reads from `exeq.d/*_changed.md`
- **Git Diff**: Uses `git diff --name-only HEAD`
- **Briq Targets**: Files targeted by current briq
- **Mtime Fallback**: Files modified within configurable window

### 5. Core Score Classification

Files are scored based on:
- Dependency rank (50% weight)
- Symbol count (20% weight)
- Inbound references (20% weight)
- Documentation presence (10% weight)

### 6. New CLI Commands

```bash
# Check with specific mode
python qontrabender.py --mode local_smart

# Validate policy file
python qontrabender.py --validate

# List available modes
python qontrabender.py --modes

# Analyze file fidelity decisions
python qontrabender.py --analyze
```

### 7. SQLite Ledger Enhancements

- Mode tracking per cache entry
- Fidelity mix statistics
- Improved version history

### 8. Qache.d Structure

```
sqrapyard/qache.d/
├── manifest.json         # Local truth of cache state
├── ledger.db             # SQLite hash→cache_id mapping
├── .active_cache_id      # For lib_ai.py integration
├── sync.log              # Audit trail
├── decisions.log         # Detailed fidelity decisions (debug_repro mode)
└── payloads/
    └── payload_v*.txt    # Version history
```

## 🔧 Configuration Changes

### config.yaml Updates

```yaml
agents:
  qontrabender:
    provider: local
    model: qontrabender
    policy_file: "./caching_policy.yaml"
    mode: local_smart
```

### pipeline_config.yaml Updates

Qontrabender now accepts multiple inputs:
```yaml
- name: qontrabender
  script: qontrabender.py
  input: 
    - "bloq.d/"
    - "qodeyard/"
    - "qontext.d/"
  output: "sqrapyard/qache.d/"
```

## 🐛 Bug Fixes

- Fixed "Hollow Cache" problem where only skeletons were cached
- Improved file path handling for qontext.d lookups
- Better error handling for missing policy files

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DATA LAKE (Local)                                │
│                                                                         │
│   qodeyard/ (MEAT)           bloq.d/ (BONES)        qontext.d/ (SOUL)   │
│   ├── api.py (FULL)          ├── api.py (SKEL)      ├── api.q.yaml      │
│   └── lib.py (FULL)          └── lib.py (SKEL)      └── lib.q.yaml      │
│                                                                         │
│             │                        │                      │           │
│             └───────────┬────────────┴──────────────────────┘           │
│                         ▼                                               │
│              ┌───────────────────────┐                                  │
│              │    QONTRABENDER       │                                  │
│              │   "The Compositor"    │                                  │
│              ├───────────────────────┤                                  │
│              │ POLICY ENGINE:        │                                  │
│              │ 1. Read 'Soul'        │ ← qontext.d intelligence         │
│              │ 2. Filter 'Volatile'  │ ← multi-signal detection         │
│              │ 3. Evaluate Rules     │ ← fidelity rules engine          │
│              │ 4. Assemble & Hash    │                                  │
│              └──────────┬────────────┘                                  │
│                         ▼                                               │
│                   qache.d/ (The Ledger)                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Performance & Cost

- **Hollow Cache Prevention**: Variable fidelity ensures AI has full implementation where needed
- **Token Optimization**: Massive files use skeletons, saving tokens while preserving context
- **Cache Reuse**: Hash-based deduplication prevents redundant uploads
- **Flexible Modes**: Choose the right balance for your workflow

---

# QonQrete v0.7.0-beta Release Notes

This release introduces a major upgrade to the `qontextor` agent, enabling a fully local, deterministic, and highly detailed analysis of the codebase. This new "Local Qontextor Stack" significantly reduces reliance on AI for context generation, leading to massive cost savings, increased speed, and enhanced privacy.

## ✨ New Features & Major Enhancements

### 1. Fully Local `qontextor` Agent
The `qontextor` agent can now run in a completely local mode (`provider: local` in `config.yaml`), which is the new default. This mode uses a sophisticated stack of local analysis tools to build a deep understanding of the codebase without any AI calls.

### 2. The Local Qontextor Stack
The new local mode is powered by a multi-layered analysis stack:
- **Python AST:** For extracting the fundamental structure of the code (classes, functions, signatures).
- **Docstrings & Verb Heuristics:** To understand the purpose of code, either from existing documentation or by inferring it from function names.
- **Jedi:** For static analysis, providing type inference and cross-file relationship understanding.
- **PyCG:** To generate a comprehensive call graph, mapping out dependencies and execution flow.

### 3. Fast vs. Complex Local Modes
The local `qontextor` can be fine-tuned for speed or detail:
- **`local_mode: 'fast'`**: Provides a very fast analysis using AST, Jedi, and heuristics.
- **`local_mode: 'complex'`**: Enhances the analysis by using a local `sentence-transformers` model to create deep semantic embeddings of the code's purpose. This allows for more advanced context-aware operations.

### 4. `qontextor` CLI Helpers
The `qontextor` agent can now be invoked directly from the command line to query the generated context:
- `python3 worqer/qontextor.py --query "<search_term>"`: Performs a semantic search for symbols.
- `python3 worqer/qontextor.py --verb "<verb_pattern>"`: Finds symbols matching a verb pattern (e.g., `get_*`).
- `python3 worqer/qontextor.py --ripple "<symbol_name>"`: Analyzes the ripple effect of changing a symbol.

### 5. Enforced Verb Usage for `construQtor`
The `construQtor` agent's prompt has been updated to enforce strict naming conventions for functions and methods, ensuring that the generated code is more deterministic and easily parsable by the local `Qontextor`.

### 6. Increased Verbosity for Agents
`qompressor` and `qontextor` now provide more verbose output, printing each file they process. This makes their operation more transparent and easier to follow during a run.

## 🐛 Bug Fixes
- Fixed a `NameError` in the `inspeqtor` agent that was causing it to crash during the review phase.
- Fixed a `NameError` in the `qontextor` agent related to the `extract_first_sentence` function.
- Added a `docker system prune` command to `qonqrete.sh` to prevent "No space left on device" errors during the Docker build process.

## 🚀 Performance & Cost
- **Indexing Cost:** Reduced to **zero** when using the local `qontextor`.
- **Cost per Run:** Up to **25x cheaper** due to the massive reduction in tokens sent to AI providers for context.
- **Speed:** Approximately **3x faster** on average due to smaller prompts and local processing.

---

## [v0.6.3-beta] - 2025-12-19

### Added
- **Dynamic Local Agent Loader**: Implemented a dynamic local agent loader in `qrane/qrane.py`, allowing agents configured with `provider: local` in `config.yaml` to dynamically load and execute corresponding Python scripts from the `worqer` directory based on their `model` name.

### Changed
- **`qrane.py`**: Modified `run_orchestration` to dynamically determine agent script paths for local providers.
- **`Dockerfile`**: Added `npm install -g @qwen-code/qwen-code@latest` to install the Qwen CLI tool, resolving the "Missing binary for command: qwen" error.
- **`lib_ai.py`**: Modified `_run_qwen` to pass prompts to the `qwen` CLI via standard input instead of command-line arguments, fixing the "Argument list too long" error.

### Fixed
- **`QWEN_API_KEY` Environment Variable**: Ensured `qonqrete.sh` passes `QWEN_API_KEY` to the container and `qrane/qrane.py` checks for its presence, resolving the "QWEN_API_KEY environment variable not set" error.
- **`construQtor` Briq Processing**: (Intended Fix): Implemented changes to improve `construQtor`'s handling of briqs. (Note: Full validation of this fix was hampered by external AI provider rate limit issues during testing.)

## [v0.6.2-beta] - 2025-12-18

### Added
- **"local" Provider**: Implemented a "local" provider for offline agents like `calqulator` and `qompressor` to make their offline nature explicit.
- **Qwen Model Testing**: Tested `qwen-turbo`, `qwen-coder`, and `qwen-max` models, with `qwen-max` proving to be the most capable for planning and code generation.

### Changed
- **Default Briq Format**: The `instruqtor` now defaults to a more reliable markdown-based format for briqs, with improved prompts and examples.

### Fixed
- **AI Reliability**: The new markdown format for briqs significantly improves the reliability of the `instruqtor` agent with various AI models.

### Chore
- **Version Bump**: Bumped version to `0.6.2`.

## [v0.6.1-beta] - 2025-12-16

### Added
- **Qwen Provider Integration**: Integrated the Qwen AI provider into the system.
  - Added a `_run_qwen` function to `worqer/lib_ai.py`.
  - Updated the `Dockerfile` to install the `@qwen-code/qwen-code` npm package.
  - Changed the default provider to `qwen` in `worqspace/config.yaml`.
- **New Documentation**: Added extensive documentation on core concepts:
  - `CONTEXT.md`: Explains the context mechanism.
  - `MEMORY.md`: Details the local memory mechanism.
  - `MINDSTACK.md`: Suggestions for the AI agent brain stack.
  - `MINDSTACK_ARCH.md`: Architecture of the brain stack.
  - `QWEN_90K_FIX.md`: Verification of Qwen's performance with large context.
  - `SKELETON.md`: Explains code skeletonization.

### Changed
- **Default Task**: Updated `worqspace/tasq.md` to a more complex task for better testing of the Qwen model.
- **Version**: Bumped version to `0.6.1`.

## [v0.6.0-beta] - 2025-12-13

### Added
- **Major Improvements: The Dual-Core Memory System**: This release introduces the **Qompressor** and **Qontextor** agents, forming a "Dual-Core" memory system that dramatically reduces cost and increases speed.

  **The Scenario:** A medium-sized project (50 files, ~10,000 lines of code).
  - **Raw Size:** ~100,000 Tokens.

  | Metric | Old Approach (Send Full Code) | New Approach (Dual-Core) | Improvement |
  | :--- | :--- | :--- | :--- |
  | **Context Sent** | 100,000 Tokens (Full Repo) | ~4,000 Tokens (Skeletons) | **~96% Reduction** |
  | **Indexing Cost** | N/A (Read raw) | Low (Uses compressed code to index) | **Optimized** |
  | **Cost per Run** | ~$0.25 (GPT-4o) | ~$0.01 (GPT-4o) | **25x Cheaper** |
  | **Speed** | Slow (Huge prompt processing) | Fast (Tiny prompt) | **~3x Faster** |
  | **Memory** | Persistent | Persistent & Infinite Context | **Upgraded** |

  **Summary: You are paying 4% of the cost for 100% of the intelligence.**

- **Qompressor (The Skeletonizer)**: Introduced a new agent that creates a low-token "skeleton" of the codebase in `bloq.d`. This provides architectural context to other agents with zero token cost.
- **Qontextor (The Symbol Mapper)**: Implemented an agent that uses AI to analyze the skeletonized code and generate a detailed, machine-readable YAML map of the codebase's symbols, purposes, and dependencies in `qontext.d`.
- **CalQulator (The Cost Estimator)**: Added a new agent that analyzes `briQ` files to provide a token and cost estimate for the upcoming `construqtor` cycle, annotating each `briQ` with its estimated cost.
- **FunQtions Library**: Added a new shared library `qrane/lib_funqtions.py` to house common utility functions like token estimation and cost calculation.

### Changed
- **Version Suffix**: Appended `-beta` to the version to signify the current pre-release status.
- **Agent Architecture**: The `pipeline_config.yaml` is updated to include the new agents, allowing them to be dynamically included in the execution flow.
- **Configuration**: `worqspace/config.yaml` has been updated with sane defaults for the new agents.

---

## [v0.5.0-beta] - 2025-12-08

### Added
- **Pipeline Optimization**: Introduced a streamlined pipeline for multi-agent orchestration.
- **Multi-Provider Support**: Added support for OpenAI, Anthropic, Google Gemini, and DeepSeek.

### Changed
- **Agent Communication**: Improved inter-agent communication via YAML-based file passing.
- **Default Configuration**: Updated default models for improved performance.

### Fixed
- **Memory Leaks**: Fixed memory issues in long-running sessions.
- **Container Isolation**: Improved Docker container isolation.

---

## [v0.4.6-beta] - 2025-12-05

### Changed
- **Logging Architecture**: The logging system has been re-architected. Raw, verbose output from each agent is now captured in `struqture/qonsole_<agent>.log`, while the main orchestrator logs high-level status changes (e.g., agent start/stop) to `struqture/events_<agent>.log`. This separates detailed debugging information from key lifecycle events.

### Fixed
- **Headless Mode Crash**: Fixed a critical "I/O operation on closed file" error that occurred in the non-TUI mode by ensuring all agent output streams are read before the process terminates.
- **Gatekeeper Assessment Parsing**: The `gateQeeper`'s parsing logic is now more robust. It uses a regular expression to find the "Assessment:" status anywhere in the `reqap.md` file, preventing the "Result: Unknown" bug caused by AI formatting inconsistencies.
- **`construqtor` Path Duplication**: The `construqtor` agent no longer creates nested `qodeyard/qodeyard` directories. It now automatically sanitizes filenames provided by the AI to strip any redundant `qodeyard/` prefixes.
- **`construqtor` AI Output Parsing**: The `construqtor`'s system prompt is now extremely strict, providing a clear example of the required output format. This, combined with simpler parsing logic, resolves failures caused by the AI not providing filenames in the markdown tag. The agent no longer creates an unwanted `construqted_code.txt` file.

---

## [v0.4.5-alpha] - 2025-12-03
### Added
- **Sqrapyard Project Seeding**: On startup, `qonqrete.sh` now checks the persistent `worqspace/sqrapyard` directory. If it contains files, they are copied into the ephemeral run's `qodeyard` to serve as a starting point for the AI.
- **`tasq.md` Seeding**: If a `tasq.md` exists in `sqrapyard`, it will be used as the initial task for the first cycle.
- **Verbose Startup Logging**: The shell script now provides explicit logs about whether it is seeding a project from `sqrapyard` or starting a fresh tasq.
- **Pre-run Delay**: A 3-second delay has been added after the initial host logs are printed, giving the user time to read them before the container's splash screen appears.

### Changed
- **Ephemeral Workspaces**: `qonqrete.sh` now creates a unique, timestamped `qage_<timestamp>` directory for each run. This ensures that runs are isolated and no data persists between sessions unless explicitly saved by the user.
- **Agent Output Directory**: The `construqtor` agent is confirmed to write all code output exclusively to the `qodeyard` directory, with safeguards to prevent writing outside this directory.
- **Instruqtor Sensitivity**: Re-implemented 10 distinct levels of granularity (0-9) for task breakdown, controlled by the `QONQ_SENSITIVITY` environment variable.
- **Context Awareness**: Both the `instruqtor` and `construqtor` agents now read all files from the current `qodeyard` to provide full codebase context to the AI.

### Fixed
- **Stricter Path Sanitization**: The `construqtor` agent now forcibly removes any parent directory traversal attempts (`../`) from AI-generated filenames, providing a hard safeguard to ensure all code is written exclusively within the `qodeyard`.
- **Gatekeeper Assessment Parsing**: The `qrane` script now correctly parses the "Assessment" status from `reqap.md` files, preventing the "Result: Unknown" bug.
- **AI Filename Resilience**: The `construqtor` agent is now more resilient to the AI providing a language name (e.g., "python") as a filename, and will write to a default file in such cases.
- **Build Log Verbosity**: Empty lines are now filtered from the `docker build` output to provide a cleaner log.
- **Agent Log Completeness**: All output streams from all agents (including the mirrored AI output from `instruqtor`, `construqtor`, and `inspeqtor`) are now correctly captured in the log files located in the `struqture` directory.

## [v0.4.4-alpha] - 2025-12-02
### Changed
- **InstruQtor Sensitivity**: Implemented 10 distinct levels of granularity (0-9) for task breakdown.
- **Context Awareness**: InstruQtor now reads all files from `qodeyard` to provide full codebase context to the planner.
- **Sqrapyard Logging**: Improved logging for the sqrapyard seeding process to provide better visibility.
### Fixed
- **Instruqtor Logic**: Overhauled sensitivity logic for more reliable and predictable behavior.
- **Construqtor**: Fixed a bug that caused the `construqtor` agent to fail.
- **AI Reliability**: Implemented a robust retry mechanism in `lib_ai` to handle intermittent AI provider failures.
- **Container Workspace**: Isolated agent workspaces within the container and fixed a `NameError`.

## [v0.4.3-alpha] - 2025-12-02
### Added
- **Init Seeding**: `qonqrete.sh init` now copies contents from `sqrapyard` to `qodeyard` if available, enabling warm starts with existing code.

## [v0.4.2-alpha] - 2025-11-28
### Added
- **Architect Role**: Implemented an "Architect" role in the `instruqtor` to improve planning.
- **Micro-dosing**: Introduced a "micro-dosing" technique for better AI results.
### Fixed
- **Syntax Errors**: Addressed multiple syntax errors and regressions.

## [v0.4.1-alpha] - 2025-11-27
### Fixed
- **Critical Regressions**: Patched several syntax errors and regressions introduced in v0.4.0.
- **Pre-flight Checks**: Disabled pre-flight checks that were causing interference.

## [v0.4.0-alpha] - 2025-11-26
### Added
- **Operational Modes**: Agents now operate with specific "personas" passed via the `--mode` flag or `config.yaml`.
- **Briq Sensitivity**: The `instruQtor` agent now accepts a `--briq-sensitivity` flag (0-9) for fine-grained control over task breakdown.
- **TUI Overhaul**: Major improvements to the TUI.
### Fixed
- **Path Regression**: Resolved a critical bug in the dynamic pipeline logic that caused incorrect path resolution for agent I/O.
### Changed
- **Code Refinements**: Significant refactoring of the entire Python and shell codebase for improved readability and compactness.

## [v0.3.0-alpha] - 2025-11-25
### Changed
- **Branding**: Updated `README.md` to display the `logo.png`.
- **Versioning**: Hardened the build process to ensure a clean `VERSION` file.

## [v0.2.7-alpha] - 2025-11-24
### Fixed
- **Hotfix**: Addressed a critical `IndentationError` in `qrane/qrane.py`.

## [v0.2.6-alpha] - 2025-11-23
### Fixed
- **TUI Experience**: Fixed the "flash and gone" issue with the TUI.

## [v0.2.5-alpha] - 2025-11-22
### Fixed
- **Agent Stability**: Fixed a critical agent `NameError` and improved console error visibility.

## [v0.2.4-alpha] - 2025-11-21
### Changed
- **Documentation**: Consolidated inspection reports into `COMING_SOON.md` and `DOCUMENTATION.md`.

## [v0.2.3-alpha] - 2025-11-20
### Fixed
- **TUI Stability**: Fixed a `NameError` crash in TUI mode.

## [v0.2.2-alpha] - 2025-11-19
### Changed
- **Major Refactoring**:
    - Implemented a dynamic agent pipeline.
    - Centralized path management.
    - Added pre-flight checks for dependencies.
    - Implemented TUI state persistence.

## [v0.2.1-alpha] - 2025-11-18
### Added
- **Dynamic Versioning**: Centralized versioning in the `VERSION` file.
- **Integrated Docker Output**: Streamed Docker build output into the TUI.

## [v0.2.0-alpha] - 2025-11-17
### Added
- **TUI Enhancements**: Added raw log view, fullscreen mode, key shortcuts, and improved colors.
- **Microsandbox (MSB) Integration**: Added support for `msb`.
### Changed
- **AI Models**: Updated default models for faster performance.

## [v0.1.1-alpha] - 2025-11-14
### Added
- **TUI Mode**: Introduced the `--tui` flag for an interactive user interface.
- **Workspace Cleaning**: Added the `clean` command to `qonqrete.sh`.

## [v0.1.0-alpha] - 2025-11-12
- The initial public alpha release of QonQrete.
