# Image Medium: Fallback Contract Test

## Goal
Test image-generation fallback behavior when the primary provider fails.

## Requirements
- Create a provider chain such as `codeseeq -> openai_compatible -> venice`.
- Mock timeout, 429, 500, invalid response, and success responses.
- Fallback only for retryable failures; do not fallback on policy/safety denials or invalid credentials unless explicitly configured.
- Persist a failure trace with sanitized error categories.
- Expose a CLI command like `generate-image --prompt "..." --size 1024x1024`.

## Acceptance Criteria
- Tests show fallback happens after retryable provider failure.
- Tests show fallback does not happen after safety/policy denial.
- CLI returns a useful error when every authorized provider fails.
- Secrets are redacted in logs and test snapshots.

## Constraints
- Integration tests requiring real upstream access must be opt-in and skipped unless valid credentials/config are present.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
