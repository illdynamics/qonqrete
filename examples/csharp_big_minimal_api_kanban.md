# C# Big: Minimal API Kanban

## Goal
Build an ASP.NET Core Minimal API for a personal Kanban board.

## Requirements
- Implement boards, columns, cards, labels, due dates, and card movement.
- Persist to SQLite via EF Core or a clearly documented alternative.
- Add validation and consistent error responses.
- Provide OpenAPI/Swagger support.
- Include integration tests for CRUD and moving cards between columns.

## Acceptance Criteria
- `dotnet test` passes.
- API can be started locally with one command.
- Card ordering remains stable after moves and deletes.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
