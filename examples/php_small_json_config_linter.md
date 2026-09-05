# PHP Small: JSON Config Linter

## Goal
Write a PHP CLI linter for JSON config files.

## Requirements
- Accept one or more JSON file paths.
- Validate JSON syntax and required keys from a small schema file.
- Print filename, line/column when possible, and error reason.
- Exit non-zero if any file is invalid.

## Acceptance Criteria
- Composer scripts include `test` and `lint`.
- Unit tests cover valid JSON, invalid JSON, missing keys, and wrong value types.
- The tool handles unreadable files gracefully.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
