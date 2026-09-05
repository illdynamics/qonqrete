# C++ Medium: Thread-Safe LRU Cache

## Goal
Implement a reusable thread-safe LRU cache library.

## Requirements
- Generic key/value support via templates.
- Configurable capacity and optional TTL.
- Thread-safe get/put/erase operations.
- Unit tests for eviction order, updates, TTL expiry, and concurrent access.
- Include a small benchmark or stress test.

## Acceptance Criteria
- Builds with CMake.
- Tests pass under ThreadSanitizer where available.
- API is simple enough to use in a short example.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
