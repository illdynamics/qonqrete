# Ruby Small: Word Frequency CLI

## Goal
Write a Ruby CLI that counts word frequencies in text files.

## Requirements
- Accept one or more files or stdin.
- Normalize case and punctuation while preserving apostrophes inside words.
- Print the top N words via `--top N`.
- Exit cleanly on missing or unreadable files.

## Acceptance Criteria
- RSpec tests cover stdin, multiple files, punctuation, and top-N ordering.
- Output order is deterministic for ties.
- Large files are streamed.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
