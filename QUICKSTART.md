# QonQrete Quickstart (v2.0.1)

The fastest path from a fresh clone to a finished build.

## 1. Install

```bash
git clone https://github.com/illdynamics/qonqrete.git
cd qonqrete
./qq-install.sh
```

This creates the venv, installs the `qq` package, builds the integrated Rust TUI when `cargo` is present, installs CodeSeeq, and creates the `qq` wrapper in `~/.local/bin`.

## 2. Run a task

```bash
qq run task.md ./my-build
```

- `task.md` — any Markdown file describing what to build.
- `./my-build` — the destination directory QonQrete builds into.

The default run opens the **TUI cockpit**. Add `--no-tui` for plain headless output, or `--yolo` for a fully non-interactive run.

## 3. Useful commands

```bash
qq doctor                 # check readiness
qq verify                 # run acceptance checks
qq cleanup --repo-root .  # remove old run artifacts
qq runs sessions          # list past runs
qq replay .qq/runs/<id>/events.jsonl
qq exec <command>         # run a command through the engine
qq chat                   # local browser chat → QonQrete runs
qq web serve              # briQsQope live dashboard
```

## 4. Configure provider & model

Edit `config/qq.yaml`:

```yaml
provider: codeseeq

models:
  qlarifier:
    model: deepseek-v4-flash-thinking
    reasoning: high
  instruqtor:
    model: deepseek-v4-flash-thinking
    reasoning: high
  construqtor:
    model: deepseek-v4-flash
    reasoning: low
  inspeqtor:
    model: deepseek-v4-flash-thinking
    reasoning: max
```

Provider capabilities live in `config/providers.yaml`. `qq models` and `qq providers` show what is available.

## 5. Use an IDE

- **VS Code:** install the QonQrete extension, set **Provider & Model**, open a `.md` task file, and run **QonQrete: Run Open File as Task**.
- **IntelliJ:** install the QonQrete plugin, use **Settings → Tools → QonQrete** to set the destination directory, configure **Provider & Model**, then press `Ctrl+Alt+Q`.

Both IDEs also expose Doctor, Verify, Cleanup, List Runs, Replay Run, Exec, and Chat.

## 6. Where things land

- Configuration: `config/qq.yaml` + `config/providers.yaml`
- Run artifacts: `<destination>/.qq/runs/<run-id>/`
- Events log: `<run-id>/events.jsonl`
- Web dashboard: briQsQope (read-only kanban over the active run)

---

*QonQrete v2.0.1 — one-shot fully autonomous builds, TUI cockpit, briQsQope dashboard, and IDE parity.*
