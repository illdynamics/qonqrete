# Kotlin Medium: Config Migrator

## Goal
Create a Kotlin tool that migrates app config files between schema versions.

## Requirements
- Read a JSON config with a version field.
- Apply migrations step-by-step to the latest version.
- Create a backup before writing changes.
- Support `--dry-run` to print a diff-like summary.
- Include tests for each migration path.

## Acceptance Criteria
- Gradle tests pass.
- Migration is idempotent.
- Dry-run does not modify files.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
