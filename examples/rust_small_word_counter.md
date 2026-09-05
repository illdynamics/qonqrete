# Rust Small Task — Word Counter CLI

## Difficulty
Small

## Goal
Build a command-line word counter in Rust.

## What You Will Build
A Rust binary called `wordcount` that reads a text file and prints useful text statistics.

## Example Usage

```bash
cargo run -- ./sample.txt
```

## Requirements

Print:

- number of lines
- number of words
- number of characters
- number of bytes
- top 10 most common words

## Rules

- Treat words case-insensitively.
- Strip basic punctuation from words.
- Ignore empty words.
- Sort common words by count descending, then alphabetically.

## Output Example

```text
Lines: 42
Words: 389
Characters: 2140
Bytes: 2218

Top words:
1. the — 28
2. and — 19
3. rust — 12
```

## Acceptance Criteria

- Missing files show a clean error.
- UTF-8 text is handled correctly.
- The program does not panic on an empty file.
- The logic is split into functions instead of living entirely in `main`.

## Stretch Goals

- Add `--top N`.
- Add `--json`.
- Add support for reading from stdin.
