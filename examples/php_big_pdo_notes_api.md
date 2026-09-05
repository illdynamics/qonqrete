# PHP Big: PDO Notes API

## Goal
Create a plain PHP notes API backed by SQLite.

## Requirements
- Implement endpoints for creating, listing, updating, deleting, tagging, and searching notes.
- Use PDO prepared statements everywhere.
- Add a migration/init script.
- Include tests for SQL injection attempts, empty notes, tag filtering, and search.
- Provide a small README with curl examples.

## Acceptance Criteria
- Tests run through Composer.
- Database schema is created automatically for local development.
- All user input is validated and escaped in responses.

## Constraints
- Do not use a full framework unless the README justifies it.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
