# Release Notes

## [v0.4.6-alpha] - 2025-12-02
### Added
- **Claude Provider**: Added support for `claude-code` via the `claude` CLI. Configure `provider: claude` in `config.yaml`.
- **API Key Handling**: `qonqrete.sh` now supports `ANTHROPIC_API_KEY` and relaxes the strict startup check.

## [v0.4.5-alpha] - 2025-12-02
### Fixed
- **ConstruQtor File Writing**: Fixed critical issue where `construQtor` would not write generated code to disk.
- **ConstruQtor Context**: Fixed issue where `construQtor` was not receiving `qodeyard` context.
- **Code Extraction**: Implemented robust markdown parsing to extract code blocks with filename comments.

## [v0.4.4-alpha] - 2025-12-02
### Changed
- **InstruQtor Sensitivity**: Implemented 10 distinct levels of granularity (0-9) for task breakdown.
- **Context Awareness**: InstruQtor now reads all files from `qodeyard` to provide full codebase context to the planner.

## [v0.4.3-alpha] - 2025-12-02
### Added
- **Init Seeding**: `qonqrete.sh init` now copies contents from `sqrapyard` to `qodeyard` if available, enabling warm starts with existing code.
