# C Big: TCP Echo Server

## Goal
Implement a concurrent TCP echo server in C.

## Requirements
- Accept multiple clients concurrently using select, poll, or threads.
- Support graceful shutdown on SIGINT/SIGTERM.
- Add configurable port and max clients.
- Log connections and disconnections.
- Provide integration tests or a test script using netcat/Python.

## Acceptance Criteria
- Builds with strict compiler warnings enabled.
- No obvious leaks under Valgrind/ASan.
- Server handles abrupt client disconnects without crashing.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
