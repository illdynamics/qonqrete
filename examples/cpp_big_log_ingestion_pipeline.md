# C++ Big: Log Ingestion Pipeline

## Goal
Create a C++ log ingestion pipeline with parsing, aggregation, and query mode.

## Requirements
- Read large log files efficiently.
- Parse timestamp, level, service, trace ID, and message.
- Aggregate counts by service/level and top trace IDs.
- Support query filters by time range, service, level, and text substring.
- Write tests plus sample fixture logs.

## Acceptance Criteria
- Build and tests are one-command documented.
- Large inputs do not require loading the entire file into memory.
- Invalid lines are reported and skipped, not fatal.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
