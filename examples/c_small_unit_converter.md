# C Small: Unit Converter

## Goal
Write a C CLI that converts common units.

## Requirements
- Support length, weight, and temperature conversions.
- Accept commands like `convert 10 km mi`.
- Print useful errors for unknown units and invalid numbers.
- Include a Makefile and tests.

## Acceptance Criteria
- `make test` passes.
- Floating-point output is rounded consistently.
- Invalid input never segfaults.

## Constraints
- Use only the C standard library.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
