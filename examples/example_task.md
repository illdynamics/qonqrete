# Example Task — Qq End-to-End Demo

A small, self-contained example task used to exercise the Qq harness
(dry-run and streaming) without any external API calls.

## Difficulty

Small

## Goal

Build a minimal Python command-line tool that reports the version and
capabilities of the Qq harness it is being asked to build against.

## What You Will Build

A single Python script named `qq_demo.py` at the repo root that:

1. Prints `Qq demo ready` to stdout.
2. Accepts a `--version` flag and prints the harness version.
3. Exits 0 on success and exits non-zero on malformed arguments,
   printing a helpful error to stderr.

## Requirements

- Use only the Python standard library.
- The script must be executable via `python3 qq_demo.py`.
- Include a short `--help` message listing the available flags.
- Do not create any files outside the current repository root.

## Example Usage

```bash
python3 qq_demo.py            # -> "Qq demo ready"
python3 qq_demo.py --version  # -> prints a version string
```

## Acceptance Criteria

- `python3 qq_demo.py` prints `Qq demo ready` and exits 0.
- `python3 qq_demo.py --version` prints a non-empty version string and exits 0.
- An unrecognized flag prints an error to stderr and exits non-zero.
- The script is self-contained (no external dependencies).

## Stretch Goals

- Add a `--self-check` flag that validates the reported capabilities end-to-end.
- Add a small `pytest` test file covering the CLI behavior.
