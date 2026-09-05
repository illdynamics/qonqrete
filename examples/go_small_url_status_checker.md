# Go Small: URL Status Checker CLI

## Goal
Build a small Go CLI that checks whether one or more URLs are reachable.

## Requirements
- Accept URLs as positional arguments and print one line per URL: URL, HTTP status code, response time, and ok/fail.
- Use context timeouts so a dead endpoint cannot hang forever.
- Return a non-zero exit code if any URL fails, times out, or returns a 5xx response.
- Include unit tests using httptest for 200, 404, 500, and timeout cases.

## Acceptance Criteria
- `go test ./...` passes.
- Running with no arguments prints usage and exits non-zero.
- Network errors are shown cleanly without panics.

## Constraints
- Use only the Go standard library.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
