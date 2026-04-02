# QonQrete Architecture

**Version:** `v1.2.2`

This document describes the current repository architecture as shipped in the `v1.2.2` snapshot.

## High-level model

QonQrete is split into three layers:

1. **Core runtime** — the CLI entrypoint, orchestrator, agents, config, and generated artifacts.
2. **Workspace data plane** — `worqspace/`, qages, qonstructions, and cycle artifacts.
3. **IDE integrations** — VS Code and IntelliJ / JetBrains wrappers around the CLI workflow.

## Top-level layout

```text
qonqrete/
├── qonqrete.sh                # Host entrypoint
├── qrane/                     # Orchestrator layer
├── worqer/                    # Agent and utility layer
├── worqspace/                 # Config + runtime data
├── doc/                       # Documentation set
├── vscode-extension/          # VS Code integration
└── intellij-plugin/           # JetBrains integration
```

## Runtime model

### `qonqrete.sh`
Responsibilities:
- command parsing (`init`, `run`, `resume`, `clean`)
- OS + container-engine detection
- qage creation and workspace seeding
- Qonstruction save / resume / clean flow
- surfacing the repository version from `VERSION`

### `qrane/`
Main files:
- `qrane.py` — orchestrator main loop with deterministic stop/continue logic
- `loader.py` — CLI/UI helper behavior
- `paths.py` — path manager
- `tui.py` — TUI implementation
- `lib_funqtions.py` — pricing helpers

Qrane:
- reads `worqspace/config.yaml`
- resolves final mode / sensitivity / cycle count
- treats `--cyqles 0` as auto-cycle mode
- validates required API keys for external providers
- runs the configured agent sequence
- decides stop/continue from structured verdict artifacts

## Core completion pipeline

```text
Qrystallizer → InstruQtor → ConstruQtor → Qualifier → InspeQtor → Qrane
```

### Stage ownership

#### Qrystallizer
- runs on Cycle 1
- extracts requirements, assumptions, and readiness data
- writes `qrystal.d/`

#### InstruQtor
- decomposes work into briqs
- generates/updates the QONTRACT
- applies the strict mode policy: `program` freezes execution scope, `innovative` separates mandatory scope from optional enhancement backlog

#### ConstruQtor
- builds code only
- writes source into `qodeyard/`
- records change/execution summaries in `exeq.d/`
- does **not** own execution validation

#### Qualifier
- **single source of truth for execution validation**
- runs builtin deterministic checks before external commands
- runs build/test/runtime commands from config
- writes `quality.d/cyqleN/report.json` plus logs

The legacy standalone local verifier has been removed. No separate local verification path remains as a first-class runtime concept.

#### InspeQtor
- reads code changes, `quality.d/`, QONTRACT/guard signals, and requirement coverage derived from `qrystal.d/requirements.json` plus persisted briq requirement IDs
- produces human-readable reqap markdown
- produces structured verdict JSON in `reqap.d/`
- cannot turn a cycle into `SUCCESS` when required quality gates failed

#### Qrane
- reads `reqap.d/cyqleN_verdict.json` and `reqap.d/latest_verdict.json`
- decides stop/continue/fail from structured state
- does not rely on markdown phrasing to determine completion

## Support utilities

The repo still includes support utilities outside the core completion authority:
- **CalQulator** — token/cost estimation
- **Qontextor** — semantic/structural context indexing
- **Qompressor** — code skeleton generation
- **Qontrabender** — context caching

These utilities may run before or after the core pipeline, but they do **not** replace the validation/evaluation/decision chain above.

## Artifact model

Each run gets a dedicated Qage directory: `worqspace/qage_YYYYMMDD_HHMMSS/`

### Main directories
- `qrystal.d/` — requirements, assumptions, readiness, and preflight artifacts
- `tasq.d/` — cycle-specific task material
- `briq.d/` — generated work units
- `qontract.d/` — human + machine-readable contract artifacts
- `qodeyard/` — generated / modified code, current truth source
- `exeq.d/` — ConstruQtor change and execution summaries
- `quality.d/` — Qualifier reports, command results, and logs
- `reqap.d/` — InspeQtor reqaps and structured verdict JSON
- `qontext.d/` — semantic / structural context hints
- `bloq.d/` — compressed structural skeletons

## Quality system

### `quality.d/`
Qualifier writes one directory per cycle:

```text
quality.d/
  cyqle1/
    report.json
    builtin_report.md
    <command logs>
```

`report.json` is the machine-readable record of builtin checks and command checks, including pass/fail state and details.

### Deterministic vs AI-judged logic
- **Deterministic**: builtin syntax/import/lightweight checks, command exit codes, guard results, and structured verdict gating
- **AI-judged**: InspeQtor per-briq review and meta-review text/reasoning

Deterministic failures override optimistic AI wording.

## Completion model

The primary source of truth is structured verdict JSON in `reqap.d/`, especially:
- `reqap.d/cyqleN_verdict.json`
- `reqap.d/latest_verdict.json`

A run cannot finish successfully when required quality gates failed. In practice that means build failures, test failures, failed builtin checks, or failed guard checks block `SUCCESS`.

## Auto-cycles

`--cyqles 0` means auto. Qrane keeps going until the structured verdict says the project is complete or the configured `auto_cycle_limit` safety cap is hit.

## Provider model

QonQrete keeps a **single-image runtime** and decouples inference from the image itself.

- **`provider: local`** — internal Python worker inside the runtime
- **`provider: llamacpp`** — external OpenAI-compatible HTTP runtime

`local` does not mean `llamacpp`.

## Security model

Important security properties:
- Qage container isolation (rootless Docker/Podman preferred)
- read-only root filesystem with writable workspace paths
- path validation and jail enforcement in `lib_security.py`
- only Qualifier may execute project validation commands

## Workspace deployment model

The IDE integrations deploy a hidden runtime into `.qonqrete/` and keep `tasq.md` user-facing at the workspace root.

- **Deploy**: installs the `v1.2.2` runtime into the workspace
- **Init**: builds `qonqrete-qage:1.2.2`
- **Run**: syncs the root task into the runtime and executes the loop

### Related docs

- [README.md](../README.md)
- [DOCUMENTATION.md](./DOCUMENTATION.md)
- [QUICKSTART.md](./QUICKSTART.md)
- [TERMINOLOGY.md](./TERMINOLOGY.md)
- [RELEASE-NOTES.md](./RELEASE-NOTES.md)
