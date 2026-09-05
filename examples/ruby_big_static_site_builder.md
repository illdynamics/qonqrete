# Ruby Big: Static Site Builder

## Goal
Create a tiny static site generator in Ruby.

## Requirements
- Read Markdown files with YAML frontmatter.
- Generate HTML pages using ERB templates.
- Build index pages, tag pages, and RSS feed.
- Copy static assets and clean stale output files.
- Include tests for rendering, routing, tags, and incremental rebuild behavior.

## Acceptance Criteria
- `bundle exec rspec` passes.
- A sample site builds with one command.
- Generated links are relative and valid.

## Stretch Goals
- Add a watch mode that rebuilds changed files.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
