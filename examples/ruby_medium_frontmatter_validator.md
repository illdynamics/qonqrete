# Ruby Medium: Frontmatter Validator

## Goal
Build a Ruby tool that validates YAML frontmatter in Markdown posts.

## Requirements
- Scan a directory recursively for Markdown files.
- Validate required fields: title, date, slug, tags.
- Check that slugs are unique and URL-safe.
- Check that dates are valid ISO dates.
- Print a clear report with file paths and line numbers where possible.

## Acceptance Criteria
- RSpec tests pass using fixture posts.
- Documents without frontmatter are reported.
- Duplicate slugs are detected across files.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
