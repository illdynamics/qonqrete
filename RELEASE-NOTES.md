# Release Notes

## [v0.4.5-alpha] - 2025-12-03
### Added
- **Sqrapyard Initialization**: On startup, Qrane now checks the `worqspace/sqrapyard` directory. If content is found, it's copied to `worqspace/qodeyard` to seed the project. If a `tasq.md` is present in `sqrapyard`, it is used as the initial task for the first cycle.

### Changed
- **Agent Output Directory**: The `construqtor` agent now writes all code output exclusively to the `worqspace/qodeyard` directory, with safeguards to prevent writing outside of this directory.
- **Instruqtor Sensitivity**: Re-implemented 10 distinct levels of granularity (0-9) for task breakdown, controlled by the `QONQ_SENSITIVITY` environment variable.
- **Context Awareness**: The `instruqtor` agent now reads all files from `qodeyard` to provide full codebase context to the planner AI.
