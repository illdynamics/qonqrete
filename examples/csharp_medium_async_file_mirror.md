# C# Medium: Async File Mirror

## Goal
Create a .NET tool that mirrors files from one directory to another.

## Requirements
- Copy new and changed files asynchronously.
- Preserve relative paths and timestamps.
- Support `--dry-run`, `--delete-extra`, and `--exclude` glob patterns.
- Print a summary of copied, skipped, deleted, and failed files.
- Include tests using temporary directories.

## Acceptance Criteria
- `dotnet test` passes.
- Dry-run never mutates the destination.
- Re-running the mirror is idempotent.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
