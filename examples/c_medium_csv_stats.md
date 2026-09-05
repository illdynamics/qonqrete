# C Medium: CSV Stats

## Goal
Build a C program that computes statistics for numeric CSV columns.

## Requirements
- Parse CSV with quoted fields and configurable delimiter.
- Compute count, min, max, mean, and standard deviation for selected columns.
- Stream input line-by-line.
- Report malformed rows without crashing.
- Include memory-safety-focused tests.

## Acceptance Criteria
- `make test` passes.
- Runs cleanly under AddressSanitizer or Valgrind.
- Handles empty files and non-numeric cells sensibly.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
