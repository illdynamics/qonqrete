- **Test:** Single-Provider Sweep
- **Provider:** gemini
- **Model:** gemini-2.5-pro
- **Failure:** The test failed with a `404 Not Found` error, indicating that the model name `gemini-2.5-pro` is incorrect or not available.

- **Test:** Single-Provider Sweep
- **Provider:** gemini
- **Model:** gemini-3-pro-preview
- **Failure:** The test failed with a `504 Deadline Exceeded` error. This is likely a temporary issue with the provider or the model is not yet available for general use.
- **Test:** Single-Provider Sweep
- **Provider:** gemini
- **Model:** gemini-2.5-pro
- **Failure:** The `construqtor` agent failed with a 429 quota error.

- **Test:** Single-Provider Sweep
- **Provider:** anthropic
- **Model:** claude-opus-4-5
- **Failure:** The `inspeqtor` agent failed with a "Partial" assessment, indicating that the generated code was not fully functional.

- **Test:** `init` without Docker/msb
- **Failure:** Unable to reliably simulate an environment without Docker/msb. The `PATH` manipulation tests were unsuccessful.

- **Test:** Microsandbox (`msb`) functionality
- **Failure:** The `msb` command does not support the `-t`, `--build-arg`, `--rm`, or `-it` flags used by the `qonqrete.sh` script, causing the `init` and `run` commands to fail.
