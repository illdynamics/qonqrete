# Go Big: Local Persistent Job Queue

## Goal
Implement a local job queue service with an HTTP API and durable storage.

## Requirements
- Expose endpoints to create jobs, list jobs, read one job, mark a job complete, and retry failed jobs.
- Persist queue state to disk using JSONL or SQLite.
- Use goroutines safely: no data races under `go test -race`.
- Add priority ordering and delayed jobs.
- Provide a tiny CLI client for enqueue/list/complete.

## Acceptance Criteria
- `go test ./...` and `go test -race ./...` pass.
- Jobs survive service restart.
- Concurrent job creation does not corrupt state.
- API responses have useful HTTP status codes and error bodies.

## Constraints
- Standard library preferred; SQLite dependency allowed only if documented.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
