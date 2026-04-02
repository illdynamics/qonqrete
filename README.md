# QonQrete - Local-First Secure Agentic AI Construction Loop
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Visitors](https://komarev.com/ghpvc/?username=illdynamics-qonqrete&label=Visitors&color=ff3c00)
![Main Version](https://img.shields.io/github/v/release/illdynamics/qonqrete?label=Main)
![VS Code Version](https://img.shields.io/visual-studio-marketplace/v/QonQrete.qonqrete?label=VS%20Code)
![JetBrains Version](https://img.shields.io/jetbrains/plugin/v/30764-qonqrete?label=JetBrains)

![QonQrete](qonqrete.jpg)

QonQrete is a **deterministic AI software construction system** that runs a structured multi-agent loop inside a hardened container. It keeps a **single-image runtime**, treats `llamacpp` as an **external OpenAI-compatible HTTP runtime**, and separates **building**, **validation**, **evaluation**, and **stop/continue decisions**.

## Version

**Current repository version:** `v1.2.4`  
Canonical source of truth: `VERSION`

## Install QonQrete in your IDE

Install QonQrete directly in your IDE and deploy the hidden runtime into your workspace.

[![VS Code Extension](https://img.shields.io/badge/VS%20Code-Extension-blue?logo=visualstudiocode)](https://marketplace.visualstudio.com/items?itemName=QonQrete.qonqrete)
[![JetBrains Plugin](https://img.shields.io/badge/JetBrains-Plugin-orange?logo=jetbrains)](https://plugins.jetbrains.com/plugin/30764-qonqrete)

## What this repository contains

1. **QonQrete core CLI/runtime**: `qonqrete.sh`, `qrane/`, `worqer/`, `worqspace/`
2. **VS Code extension**: `vscode-extension/`
3. **IntelliJ / JetBrains plugin**: `intellij-plugin/`

> **v1.2.4** — Production-Ready: Auto-Cycle Mode, Forward IDE Compatibility, Full Offline Support

## Quick Start (IDE)

1. Install **QonQrete** from your IDE marketplace.
2. Run **Deploy to Workspace**.
3. Create `tasq.md` at the project root.
4. Run Tasq.

## Quick Start (CLI)

```bash
# Cloud-provider example
export OPENAI_API_KEY='...'

# Build the runtime
./qonqrete.sh init

# Run with auto-cycles
./qonqrete.sh run --auto --cyqles 0
```

## Core completion pipeline

```text
Qrystallizer → InstruQtor → ConstruQtor → Qualifier → InspeQtor → Qrane
```

What each stage owns:
- **Qrystallizer** anchors requirements in `qrystal.d/`.
- **InstruQtor** plans briqs and generates the QONTRACT.
- **ConstruQtor** builds code only.
- **Qualifier** runs **all deterministic validation and execution checks** and writes `quality.d/`.
- **InspeQtor** reads code changes, `quality.d/`, and requirement coverage derived from `qrystal.d/requirements.json` plus briq requirement IDs, then writes reqap markdown plus structured verdict JSON.
- **Qrane** decides whether to stop or continue from the structured verdict, not from markdown vibes.

Support utilities such as **CalQulator**, **Qontextor**, **Qompressor**, and **Qontrabender** may still run around that path, but they do **not** replace the completion authority above.

## Quality System

The legacy standalone local verifier has been removed. Validation is now centralized in **Qualifier**.

- **Builtin checks**: syntax, import, and lightweight deterministic checks run first.
- **Command checks**: build, test, and runtime commands run from Qualifier only.
- **Artifacts**: results land in `quality.d/cyqleN/report.json` and related logs.
- **Completion gate**: the system cannot finish when required Qualifier checks fail.

## Completion model

The source of truth is the structured verdict JSON in `reqap.d/`:
- `reqap.d/cyqleN_verdict.json`
- `reqap.d/latest_verdict.json`

QonQrete cannot finish if any required quality gate fails, including build failures, test failures, failed builtin checks, or failed guard checks. Requirement coverage now comes from the Qrystallizer ledger plus requirement IDs persisted on briqs. Markdown reqaps are human-readable output; the structured verdict is what drives stop/continue.

## Auto-cycles

`--cyqles 0` means **auto**. Qrane keeps cycling until the structured verdict says the work is complete, or until `options.auto_cycle_limit` is reached as the hard safety cap.

## Modes

- **`program`**: freeze execution scope to the explicit tasq plus canonical requirement ledger. Extra ideas belong in suggestions, not the execution backlog.
- **`innovative`**: complete the canonical requirement ledger first, then keep improvement ideas in an **optional enhancement backlog** unless they are explicitly promoted.

`Scope-Class: MANDATORY` briqs define completion. `Scope-Class: OPTIONAL_ENHANCEMENT` briqs stay optional and do not extend the stop condition.

## Providers

- **`provider: local`**: internal Python worker agent inside the QonQrete runtime. Deterministic/helper role.
- **`provider: llamacpp`**: external OpenAI-compatible HTTP endpoint for LLM inference.

They are **not** the same thing. `local` is an internal worker; `llamacpp` is an external runtime.

## Documentation

- [Quickstart](doc/QUICKSTART.md)
- [Architecture](doc/ARCHITECTURE.md)
- [Documentation](doc/DOCUMENTATION.md)
- [Terminology](doc/TERMINOLOGY.md)
- [Release Notes](doc/RELEASE-NOTES.md)

## Security

QonQrete is designed for security-sensitive environments:
- **Single-image runtime**: one runtime image, provider choice is config-driven.
- **Zero Host Execution**: AI-generated code stays inside the Qage.
- **Encrypted Credentials**: IDEs store API keys in your OS keychain, not in config files.
- **Path Jailing**: Agents are restricted to their assigned workspace directories.
- **Qualifier Gate**: only Qualifier is allowed to execute project validation commands.

## License

QonQrete is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
See [LICENSE](LICENSE).
