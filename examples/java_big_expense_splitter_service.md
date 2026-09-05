# Java Big: Expense Splitter Service

## Goal
Create a small Java service for splitting group expenses.

## Requirements
- Implement endpoints or CLI commands for users, groups, expenses, balances, and settlement suggestions.
- Persist data to SQLite, H2, or a local JSON file.
- Use decimal-safe money handling, not floating point.
- Include validation for negative amounts, unknown users, and duplicate names.
- Provide integration tests covering the full split workflow.

## Acceptance Criteria
- Project builds from a clean checkout.
- Balances reconcile to zero after settlement suggestions.
- Service/CLI has clear error messages and examples.

## Stretch Goals
- Add CSV import/export for expenses.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
