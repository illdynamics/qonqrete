# Go Medium: Markdown Asset Checker

## Goal
Create a tool that scans Markdown files and validates local image/link references.

## Requirements
- Recursively scan a directory for `.md` files.
- Find Markdown links/images and report missing local files with line numbers.
- Ignore http, https, mailto, anchor-only, and code-block links.
- Run checks concurrently with a bounded worker pool.
- Output either human-readable text or JSON via `--json`.

## Acceptance Criteria
- `go test ./...` passes with fixture directories.
- The checker detects missing files inside nested directories.
- The JSON output is valid and deterministic.

## Stretch Goals
- Add `--fix-case` to suggest case-sensitive path fixes on case-insensitive systems.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
