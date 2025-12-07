- **Test:** Single-Provider Sweep
- **Provider:** gemini
- **Model:** gemini-2.5-pro
- **Failure:** The `construqtor` agent failed with a 429 quota error.

- **Test:** `init` without Docker/msb
- **Failure:** Unable to reliably simulate an environment without Docker/msb. The `PATH` manipulation tests were unsuccessful.

- **Test:** Microsandbox (`msb`) functionality
- **Failure:** The `msb` command does not support the `-t`, `--build-arg`, `--rm`, or `-it` flags used by the `qonqrete.sh` script, causing the `init` and `run` commands to fail.