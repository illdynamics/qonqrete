# QonQrete Documentation

**Version:** `v1.2.4`

This document is the technical reference for the `v1.2.4` repository snapshot.

## Table of contents
- [1. What QonQrete is](#1-what-qonqrete-is)
- [2. Core pipeline](#2-core-pipeline)
- [3. Quality system](#3-quality-system)
- [4. Artifacts and directories](#4-artifacts-and-directories)
- [5. Completion and stop conditions](#5-completion-and-stop-conditions)
- [6. Modes and auto-cycles](#6-modes-and-auto-cycles)
- [7. Providers](#7-providers)
- [8. IDE integrations](#8-ide-integrations)
- [9. Security model](#9-security-model)

## 1. What QonQrete is

QonQrete is a **structured AI construction loop** for autonomous software work inside a hardened container runtime. The architecture is intentionally split so that code generation, validation, evaluation, and stop/continue decisions are owned by different stages.

Key `v1.2.4` alignment points:
- **Qualifier is the single source of truth for execution validation**
- **Legacy standalone local verification has been removed**
- **Structured verdict JSON governs completion**
- **Single-image runtime remains**
- **`llamacpp` stays an external HTTP runtime**

## 2. Core pipeline

The core completion pipeline is:

**Qrystallizer → InstruQtor → ConstruQtor → Qualifier → InspeQtor → Qrane**

### 2.1 Qrystallizer
- runs on Cycle 1
- extracts requirements and assumptions
- writes `qrystal.d/`

### 2.2 InstruQtor
- plans briqs
- generates/updates the QONTRACT
- interprets `program` vs `innovative`

### 2.3 ConstruQtor
- writes code into `qodeyard/`
- records change summaries in `exeq.d/`
- does **not** run validation or tests

### 2.4 Qualifier
- runs builtin deterministic checks first
- runs configured build/test/runtime commands
- writes `quality.d/`
- is the **only** execution-validation authority

### 2.5 InspeQtor
- reads code changes, `quality.d/`, guard results, and requirement coverage derived from the Qrystallizer requirement ledger plus briq requirement IDs
- writes reqap markdown for humans
- writes verdict JSON for the machine decision path

### 2.6 Qrane
- reads structured verdict artifacts
- decides stop/continue/fail
- uses markdown as supporting output, not as the authoritative state signal

### 2.7 Support stages in the repo

The repository still contains support utilities like CalQulator, Qontextor, and Qompressor. They can still run in the broader runtime, but they are not the authoritative completion path.

## 3. Quality system

### 3.1 Why it exists

The quality system prevents fragmented validation paths. All deterministic validation and execution checks are centralized in Qualifier.

### 3.2 `quality.d/`

Qualifier writes cycle-scoped quality artifacts, typically under:

```text
quality.d/cyqleN/
```

Important artifact:
- `quality.d/cyqleN/report.json` — machine-readable summary of builtin checks, command checks, pass/fail state, and details

Typical command logs also live beside the report.

### 3.3 Builtin checks vs command checks

Qualifier handles two classes of checks:

**Builtin deterministic checks**
- syntax validation
- lightweight import/parsing validation
- project-structure / skeleton sanity checks

**Command checks**
- build commands
- test commands
- runtime/smoke commands

Builtin checks run before external commands.

### 3.4 Deterministic vs AI-judged logic

**Deterministic**
- builtin quality checks
- shell command exit codes and logs
- guard results
- structured verdict gating

**AI-judged**
- InspeQtor per-briq review
- InspeQtor meta-review text and recommendations

If deterministic quality fails, AI optimism does not override it.

## 4. Artifacts and directories

| Directory | Content | Role |
|-----------|---------|------|
| `qrystal.d/` | requirements, readiness, assumptions | requirement anchor |
| `tasq.d/` | `cyqleN_tasq.md` | cycle-specific task state |
| `qontract.d/` | contract artifacts | persistent rules/invariants |
| `qodeyard/` | generated code | canonical source of truth |
| `exeq.d/` | build/change summaries from ConstruQtor | generation trace |
| `quality.d/` | `report.json`, command logs | Qualifier validation evidence |
| `reqap.d/` | reqap markdown and verdict JSON | review + machine decision state |

### 4.1 `qrystal.d/`
`qrystal.d/` stores the requirement anchor created by Qrystallizer. It exists to reduce drift later in the loop, and InspeQtor now uses `requirements.json` together with briq requirement IDs to populate structured requirement coverage in the verdict JSON.

### 4.2 Reqap verdict JSON
The important structured verdict artifacts are:
- `reqap.d/cyqleN_verdict.json`
- `reqap.d/latest_verdict.json`

These carry fields such as overall assessment, stop recommendation, guard state, and quality state.

## 5. Completion and stop conditions

QonQrete uses a deterministic decision engine driven by verdict/state artifacts.

A run cannot finish successfully if any required quality gate failed. That includes:
- build failure
- test failure
- failed builtin quality checks
- failed guard checks

In practice, success requires the structured verdict to indicate that required quality and guard conditions passed. Human-readable markdown does not have final authority.

## 6. Modes and auto-cycles

### 6.1 `program` vs `innovative`
- **`program`**: freeze execution scope to the original tasq plus canonical requirement ledger. Extra ideas stay in suggestions only and must not become execution briqs.
- **`innovative`**: complete the canonical requirement ledger first, then keep extra ideas in an optional enhancement backlog until they are explicitly promoted.

Runtime scope is persisted on briqs with `Scope-Class: MANDATORY` or `Scope-Class: OPTIONAL_ENHANCEMENT`. Optional enhancement items are reviewed and reported, but they do not extend the mandatory stop condition.

### 6.2 `cycles = 0`
`0` means **auto**.

Operationally:
- the CLI/IDE sends `--cyqles 0`
- Qrane keeps cycling until the structured verdict says stop, or until `auto_cycle_limit` is hit as the hard safety cap
- `auto_cycle_limit` is the safety cap, not the same thing as a fixed manual cycle count

## 7. Providers

### 7.1 `local` vs `llamacpp`
- **`provider: local`** — internal Python worker agent inside the runtime
- **`provider: llamacpp`** — external OpenAI-compatible HTTP endpoint used for LLM inference

They are different mechanisms and should not be documented interchangeably.

### 7.2 Single-image runtime
QonQrete keeps one runtime image. Switching between cloud inference and `llamacpp` does not require a different QonQrete image.

## 8. IDE integrations

The VS Code and IntelliJ integrations manage a workspace-local hidden runtime in `.qonqrete/`.
- **Deploy**: installs the `v1.2.4` runtime
- **Init**: builds the `qonqrete-qage:1.2.4` image
- **Run**: syncs root `tasq.md` into the runtime
- **Config UX**: documents `cycles = 0` as auto and exposes `innovative`

## 9. Security model

- **Container isolation**: rootless/limited-capability runtime
- **Path jailing**: strict enforcement in `lib_security.py`
- **Credential protection**: IDEs inject secrets securely; they are not stored in plain config
- **Execution authority**: only Qualifier is allowed to execute validation commands

---
[README.md](../README.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [QUICKSTART.md](./QUICKSTART.md) | [RELEASE-NOTES.md](./RELEASE-NOTES.md)
