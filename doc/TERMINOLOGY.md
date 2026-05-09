# QonQrete Terminology

**Version:** `v1.4.4`

This document defines the main vocabulary used in the current repository.

## Core runtime terms

- **QonQrete** — the overall system: CLI runtime + orchestrator + agents + workspace model
- **Qrane** — the orchestrator process in `qrane/qrane.py`
- **worqer** — a worker/agent script in `worqer/`
- **Qrew** — the set of agents participating in a run
- **Qage** — an isolated run environment and its corresponding `qage_YYYYMMDD_HHMMSS` directory
- **worqspace** — shared configuration and runtime data directory

## Workflow terms

- **tasq** — the high-level task description
- **cyQle** — one full plan/build/review iteration
- **briq** — one atomic work item produced by InstruQtor
- **exeQ** — an execution summary emitted by ConstruQtor
- **reQap** — a review/recap emitted by InspeQtor
- **CheQpoint** — the point where QonQrete pauses for user continuation in user-gated mode
- **gateQeeper** — the human operator at the checkpoint

## Structural artifact terms

- **qodeyard** — current generated/modified code; primary truth source
- **briq.d** — briq files
- **exeq.d** — execution summaries
- **reqap.d** — review summaries
- **qontract.d** — contract material (`qontract.md` + `qontract.json`)
- **qontext.d** — structural context and relationship output
- **bloq.d** — compressed skeleton cache from Qompressor
- **qache.d** — Qontrabender cache payload area
- **struqture** — logs and event traces
- **seed-repo mode** — opt-in run mode that seeds current repository content into `qodeyard/` before build (legacy alias: `-s/--sqrapyard`)
- **Qonstruction** — a saved output snapshot under `worqspace/qonstructions/`

## Agent names

- **Qrystallizer** — cycle-1 task clarification and readiness stage
- **InstruQtor** — task planner and briq generator
- **CalQulator** — local token/cost estimator
- **ConstruQtor** — code generator / modifier
- **InspeQtor** — reviewer
- **Qontextor** — deterministic multi-language structural mapper and context graph builder
- **Qompressor** — deterministic multi-language structural skeletonizer (Python always first-class; shell/JS/TS/HTML/CSS first-class in the shipped/provisioned environment; optional Tree-sitter fallback)
- **Qontrabender** — variable-fidelity cache compositor
- **Qonfirmer** — deterministic contract verifier
- **Qualifier** — deterministic syntax/import verification helper

## Runtime/config terms

- **Operational mode** — run persona / mode such as `program`, `enterprise`, `security`, etc.
- **Briq sensitivity** — decomposition granularity; higher means more briqs in the current system design
- **Autonomous mode** — continue without user cheQpoints
- **User-gated mode** — pause at cheQpoints

## Runtime engine terms

- **Container engine** — Docker or Podman
- **Build backend** — the backend used to build the runtime image (for example `buildx` or plain build paths)

## IDE integration terms

- **VS Code extension** — the `vscode-extension/` project that wraps the repo-local QonQrete CLI workflow inside VS Code
- **IntelliJ plugin** — the `intellij-plugin/` project that wraps the repo-local QonQrete CLI workflow for JetBrains IDEs
- **repo-local workflow** — today’s actual model: the project contains `qonqrete.sh` and `worqspace/`, and the IDE integration detects that local project

## Important terminology honesty note

The current repository does **not** yet implement the fully centralized “single shared engine for many arbitrary repos” model. When the docs say VS Code or IntelliJ integration, they mean the bundled wrappers around the existing repo-local QonQrete workflow.
