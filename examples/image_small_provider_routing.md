# Image Small: Provider Routing Smoke Test

## Goal
Test whether QonQrete can route an image-generation request through a provider abstraction without hardcoding one vendor.

## Requirements
- Implement or validate an image provider interface with at least `codeseeq`, `openai_compatible`, and `venice` provider names.
- Use mocked providers in unit tests; do not make real network calls in unit tests.
- Given a prompt, route to the configured primary provider and return a generated PNG path plus metadata.
- Record provider name, prompt hash, dimensions, and created timestamp in metadata.
- Fail fast when no authorized provider is configured.

## Acceptance Criteria
- Unit tests prove `codeseeq` is selected when configured as primary.
- The generated artifact path and metadata are returned consistently.
- No API keys, tokens, prompts, or raw credentials are logged.

## Constraints
- Do not rely on private, hidden, scraped, or unauthenticated upstream endpoints. Use mocks or an explicitly authorized provider.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
