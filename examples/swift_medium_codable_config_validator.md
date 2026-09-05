# Swift Medium: Codable Config Validator

## Goal
Build a Swift tool that validates JSON app configuration files.

## Requirements
- Define typed Codable models for config sections.
- Validate semantic rules beyond JSON syntax.
- Print all detected errors, not just the first one.
- Support `--pretty` to print normalized JSON.
- Include tests using fixture configs.

## Acceptance Criteria
- `swift test` passes.
- Unknown fields are either rejected or documented.
- Errors point to the relevant config keys where possible.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
