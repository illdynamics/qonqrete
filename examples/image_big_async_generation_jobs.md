# Image Big: Async Image Generation Jobs

## Goal
Build an asynchronous image-generation job system to test queueing, fallback, retries, and artifact storage.

## Requirements
- Implement job creation with prompt, size, style options, and provider preference.
- Expose job statuses: queued, running, succeeded, failed, canceled.
- Use a worker that calls the provider abstraction and stores images plus metadata.
- Add retry policy with exponential backoff and provider fallback.
- Include a test mode that uses deterministic generated placeholder images so CI is free and stable.
- Add an optional real-provider integration test gated by environment variables.

## Acceptance Criteria
- Unit and integration tests pass without external network access.
- Job state survives process restart if persistence is enabled.
- Canceled jobs do not keep generating.
- Provider fallback decisions are visible in sanitized job events.

## Constraints
- Do not use or test bypasses around authentication, billing, or private upstream access. Verify capability through mocks or authorized integrations.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
