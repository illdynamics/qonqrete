# Java Small: CSV Sanity Checker

## Goal
Write a Java CLI that validates simple CSV files and reports bad rows.

## Requirements
- Accept a file path and expected column count.
- Handle quoted fields, escaped quotes, commas inside quotes, and blank lines.
- Print row numbers for malformed rows.
- Exit non-zero on validation failure.

## Acceptance Criteria
- Builds with Maven or Gradle.
- Includes unit tests for quoted commas, bad quotes, blank rows, and wrong column counts.
- Handles large files line-by-line rather than loading the whole file.

## Constraints
- No external CSV parser libraries; implement the parser.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
