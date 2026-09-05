# Swift Big: Local Notes Sync

## Goal
Create a Swift command-line app that syncs notes between two local folders.

## Requirements
- Model notes as Markdown files with metadata.
- Detect creates, updates, deletes, and conflicts.
- Use content hashes and modified times.
- Provide `plan`, `apply`, and `resolve-conflict` commands.
- Include tests for conflict scenarios and idempotent sync.

## Acceptance Criteria
- `swift test` passes.
- Plan mode never writes files.
- Conflicts are preserved safely rather than overwritten.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
