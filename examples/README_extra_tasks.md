# QonQrete Extra Task Pack

This pack adds 3 tests each for these common languages: Go, Java, C#, PHP, Ruby, C, C++, Kotlin, and Swift. It also adds 3 image-generation provider tests.

Recommended scoring:

- **0**: Does not run or ignores core request.
- **1**: Partial sketch; major compile/runtime issues.
- **2**: Runs, but edge cases or tests are weak.
- **3**: Solid implementation with tests and clear setup.
- **4**: Production-minded: robust errors, docs, security, idempotence, and maintainability.

Best benchmark shape:

- Use one small, one medium, and one big task per language.
- Require a clean build from scratch.
- Run visible tests plus a few hidden tests.
- Score compile success, correctness, edge cases, code quality, security posture, and README quality separately.
- For image generation, keep CI deterministic with mocks/placeholders; real-provider tests should be explicit opt-in and authorized.
