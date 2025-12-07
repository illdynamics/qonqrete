# Failed Tests Report

The following tests failed or could not be executed successfully in the current environment:

## Microsandbox (msb)
- [ ] **Init with msb**: `Run ./qonqrete.sh init --msb`. Failed because `msb` is not installed or configured in the test environment.
- [ ] **Run with msb**: `Run a full task cycle using ./qonqrete.sh run --msb`. Failed because `msb` is not installed.
- [ ] **Default Detection**: `Set microsandbox: true in pipeline_config.yaml and run without the --msb flag`. Failed/Skipped due to missing `msb`.

## TUI Mode
- [ ] **Interactive TUI**: Full interactive TUI tests (scrolling, keypresses) could not be verified in the non-interactive test environment.
