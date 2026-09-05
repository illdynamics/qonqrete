# C# Small: Password Policy Tool

## Goal
Build a .NET CLI that evaluates password strength against a configurable policy.

## Requirements
- Accept passwords from stdin or a file.
- Support policy options: min length, uppercase, lowercase, digits, symbols, and banned substrings.
- Return structured results with pass/fail and reasons.
- Include tests for empty passwords, Unicode, and banned substring matching.

## Acceptance Criteria
- `dotnet test` passes.
- No password is written to logs by default.
- CLI exits non-zero if any checked password fails.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
