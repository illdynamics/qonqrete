# Smoke Task — Web Shell Nav Smoke Run

## Difficulty
Small

## Goal
Exercise the QonQrete harness end-to-end (clarify → plan → build → review)
so the per-run telemetry (Cycle, Progress, Total, Agent, Action, model) can
be cross-checked between the TUI cockpit and the briQsQope web dashboard.

## What You Will Build
A single self-contained Python script, `smoke_probe.py`, at the repository
root (the given repo_root) that prints a version string to stdout and exits 0.

## Requirements
- Use only the Python standard library.
- The script must be runnable via `python3 smoke_probe.py`.
- `python3 smoke_probe.py --version` prints a non-empty version string.
- An unrecognized flag prints a helpful error to stderr and exits non-zero.
- Do not create files outside the current repository root.

## Acceptance Criteria
- `python3 smoke_probe.py` prints `QonQrete smoke probe ready` and exits 0.
- `python3 smoke_probe.py --version` prints a non-empty version string.
- The telemetry run reaches a terminal (FULLY_DONE) state.
