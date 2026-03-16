# QonQrete Release Notes

## v1.1.9-stable

This release syncs the repository around the `v1.1.9-stable` state and reflects the biggest shift since `v1.0.4-stable`: **QonQrete is no longer just a core CLI runtime — the repo now also includes IDE integrations for VS Code and JetBrains tooling.**

## Headline changes since `v1.0.4-stable`

### Core runtime remains the foundation
The core runtime still centers on:
- `qonqrete.sh`
- Qrane orchestration
- QONTRACT enforcement
- qage-based isolated runs
- qodeyard / briq / reqap / exeq artifact flow
- resume / clean / qonstruction lifecycle

### VS Code extension was added and hardened
The repository now includes a bundled VS Code extension project.

Notable progression in the 1.0.5 → 1.1.x line:
- initial extension scaffolding and command integration
- sidebar, status bar, and config wizard
- run / resume / clean / init flows
- shell detection and verification
- more honest timeout / exit-state handling
- qage browsing and UX hardening
- packaging as a `.vsix`

### IntelliJ / JetBrains plugin was added
The repository now also includes an IntelliJ / JetBrains plugin project.

Current repo-level significance:
- tool window based integration path exists
- Gradle plugin project exists in-tree
- manual packaging / manual install path exists
- plugin hardening work is tracked in the repo changelog

## Version-by-version summary from `v1.0.4-stable`

### v1.0.4-stable
- contract-enforced pipeline
- multi-engine runtime auto-detection
- stronger QONTRACT / QontractGuard behavior
- qodeyard as primary code truth

### v1.0.5-stable
- VS Code extension added to the repository

### v1.0.6-stable → v1.1.5-stable
- repeated VS Code hardening passes
- better temp tasq handling
- better multi-root / run-state handling
- shell verification cleanup
- orphan recovery and status improvements

### v1.1.7-stable → v1.1.9-stable
- IntelliJ plugin work landed in-tree
- production-hardening passes captured in repo changelog
- wrapper/build/testing/config cleanup tracked for the plugin project

## Practical impact of the `v1.1.9-stable` repo snapshot

At this point the repository contains:
- a working core runtime
- a VS Code extension project
- an IntelliJ plugin project
- manual packaging/install flows for both IDE integrations

## Important honesty note

This release note intentionally describes the **repository state**.
It does **not** claim:
- official marketplace publication already happened
- centralized engine bootstrap flow already exists
- every experimental UI/runtime path is equally mature

Those are separate distribution/product layers beyond the core repo snapshot.
