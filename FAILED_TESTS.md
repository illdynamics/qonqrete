- **Test:** Single-Provider Sweep
- **Provider:** gemini
- **Model:** gemini-2.5-pro
- **Failure:** The `construqtor` agent failed with a 429 quota error.

- **Test:** Single-Provider Sweep
- **Provider:** anthropic
- **Model:** claude-3-5-sonnet
- **Failure:** The `instruqtor` agent failed with a 404 error, indicating that `claude-3-5-sonnet` is not a valid or accessible model name.

- **Test:** Single-Provider Sweep
- **Provider:** anthropic
- **Model:** claude-3-5-haiku
- **Failure:** The `instruqtor` agent failed with a 404 error, indicating that `claude-3-5-haiku` is not a valid or accessible model name.

- **Test:** `init` without Docker/msb
- **Failure:** Unable to reliably simulate an environment without Docker/msb. The `PATH` manipulation tests were unsuccessful.

- **Test:** Microsandbox (`msb`) functionality
- **Failure:** The `msb` command does not support the `-t`, `--build-arg`, `--rm`, or `-it` flags used by the `qonqrete.sh` script, causing the `init` and `run` commands to fail.

- **Test:** CLI Override Tests
- **Command:** `./qonqrete.sh run --auto --mode security --briq-sensitivity 0`
- **Failure:** The `construqtor` agent failed to process a briq related to "addcommentsforclarity" and exited with a non-zero status code.
