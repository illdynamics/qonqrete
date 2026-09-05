# PHP Medium: Markdown Link Auditor

## Goal
Build a PHP tool that audits Markdown links in a project.

## Requirements
- Recursively scan `.md` files.
- Check local file references and optionally HTTP links with `--check-remote`.
- Cache remote checks during a run to avoid duplicate requests.
- Ignore fenced code blocks.
- Output a sorted report with file and line numbers.

## Acceptance Criteria
- PHPUnit tests pass.
- Broken local links are detected reliably.
- Remote checking has sane timeout handling and does not crash on DNS errors.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
