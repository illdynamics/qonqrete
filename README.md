# QonQrete - Fully Autonomous File-Based Local-First AI Coding Harness (v2.0.1)
![Release](https://img.shields.io/github/v/release/illdynamics/qonqrete)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Repo Views](https://komarev.com/ghpvc/?username=illdynamics-qonqrete&label=Repo+Views&color=blue)
[![Build VS Code Extension](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/vscode-extension.yml)
[![Build IntelliJ Plugin](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml/badge.svg)](https://github.com/illdynamics/qonqrete/actions/workflows/intellij-plugin.yml)

![QonQrete](./qonqrete.jpg)

**Current repository version:** `2.0.1`

2.0.1 — QonQrete v2 engine (current release)

> **New since v2.0.0:** QonQrete now runs on a completely new engine — the `qq` CLI. It is fully autonomous and designed to finish even huge tasks in one shot: clarify → plan → build → review, looping automatically until the build is genuinely done. No more babysitting.

QonQrete is a **local-first, file-based, deterministic AI software construction harness**. You give it a Markdown task and a destination directory; it produces a working, reviewed build. The multi-agent pipeline (Qlarifier → instruQtor → construQtor ↔ inspeQtor) plans the work into briqs, generates code, reviews it, and iterates until `FULLY_DONE` — with a rich TUI cockpit and the **briQsQope** web dashboard for live progress.

## What this repository contains

1. **QonQrete v2 core CLI** — the `qq` Python engine under `qq/`.
2. **VS Code extension** in `vscode-extension/`.
3. **IntelliJ / JetBrains plugin** in `intellij-plugin/`.
4. **briQsQope** — the read-only web kanban dashboard served by the engine.
5. **QonQrete Chat** — a local browser chat that turns prompts into QonQrete runs.

The IDE integrations are thin, friendly frontends for the same `qq` commands described below.

## Install (CLI)

The quickest way is the website one-liner — it fetches the latest QonQrete
runtime zip from the GitHub release, unpacks it, and installs everything:

```bash
curl -fsSL https://qonqrete.sh/install.sh | bash
```

Or from a fresh clone:

```bash
git clone https://github.com/illdynamics/qonqrete.git
cd qonqrete
./install.sh
```

Then run:

```bash
qq run task.md ./my-build
```

The installer creates a Python venv, installs the `qq` package, builds the
integrated Rust TUI cockpit (when `cargo` is available — optional), ensures
the system CodeSeeq CLI for the `codeseeq`/`chatgpt` providers (optional —
never vendored into the runtime), and creates the `qq` wrapper in
`~/.local/bin`.

### Run a task

```bash
# Build a task into a target directory (TUI cockpit by default)
qq run task.md ./my-build

# Headless / exec mode (no TUI)
qq run task.md ./my-build --no-tui

# Fully non-interactive: no clarifications or approvals
qq run task.md ./my-build --yolo

# Use the briQsQope web dashboard for this run
qq run task.md ./my-build --web
```

## Core commands

| Command | What it does |
|---|---|
| `qq run <task> <dest>` | Run the full clarify → plan → build → review loop |
| `qq doctor` | Check system readiness (`qq doctor -t all` runs tests) |
| `qq verify` | Run the Python acceptance checks |
| `qq cleanup --repo-root .` | Remove old run artifacts |
| `qq replay <events.jsonl>` | Print an events log for a past run |
| `qq runs sessions` | List discoverable QonQrete runs |
| `qq exec <command>` | Run an arbitrary command through the engine exec mode |
| `qq chat` | Start the local browser chat interface |
| `qq web serve` | Start the briQsQope dashboard |
| `qq models` / `qq providers` | Show models / providers |
| `qq package` | Build and validate a release zip |

## Configuration

Configuration lives in `config/qq.yaml` (with provider capabilities in `config/providers.yaml`). The IDE integrations and `qq configure`-style flows write here.

The only settings most people need are the **provider** and the **model**:

```yaml
provider: chatgpt

models:
  qlarifier:
    model: gpt-5.5
  instruqtor:
    model: gpt-5.5
  construqtor:
    model: gpt-5.5
  inspeqtor:
    model: gpt-5.5
```

The default `chatgpt` provider uses your **ChatGPT account** (Plus / Pro /
Team) through the system `codeseeq` CLI — no API key needed. When you run
QonQrete with this provider and no sign-in exists yet, it starts the login
for you on an interactive terminal:

```bash
# QonQrete runs this automatically the first time it is needed:
codeseeq login        # choose "Sign in with ChatGPT"
```

QonQrete runs the **system** `codeseeq` from your `PATH` (never a copy
vendored under `qq/codeseeq`) and reuses that `codeseeq login` session for
every agent automatically.

The login is reused wherever it lives - the project's own `.codeseeq`
(`<project>/.codeseeq`), `$CODEX_HOME` / `$CODESEEQ_HOST_CODEX_HOME`, or the
user-level `~/.codeseeq`. **Never move or `mv` codeseeq folders into a
project** (for example `mv /qq/codeseeq /qq/qonqrete/.codeseeq`): QonQrete
reuses an existing sign-in in place, and when none exists it creates one
fresh under `<project>/.codeseeq` via `codeseeq login`.

To use the DeepSeek bridge instead, switch the provider to `codeseeq` and
set `DEEPSEEK_API_KEY`.

### Local runtimes: llama.cpp (GGUF) and MLX (Apple Silicon)

For fully local, offline inference QonQrete points at an OpenAI-compatible
server that you run **separately** — the engine never loads a model itself,
it just talks to `host:port`. Two local runtimes are wired up; which one you
use depends on the model format:

| `provider`   | Model format | Server (run separately) | Default endpoint |
|--------------|--------------|-------------------------|------------------|
| `llama-cpp`  | GGUF         | `llama-server -m model.gguf --port 8888` | `http://127.0.0.1:8888/v1` |
| `mlx`        | MLX safetensors (Apple Silicon) | `mlx_lm.server --model <path-or-hf-id> --port 8080` | `http://127.0.0.1:8080/v1` |

The repo's `config/qq.yaml` defaults to `provider: llama-cpp`; switch that
line to `mlx` to use an MLX model instead. Endpoints can be pinned per
provider with the `QQ_LLAMA_CPP_ENDPOINT` / `QQ_MLX_ENDPOINT` env vars or a
`local_endpoints:` block in `config/qq.yaml`.

#### GGUF via llama.cpp (`provider: llama-cpp`)

```yaml
provider: llama-cpp
```

No model name or API key is needed — the server uses whatever GGUF model it
has loaded. The endpoint defaults to `http://127.0.0.1:8888/v1` and can be
overridden with `QQ_LLAMA_CPP_ENDPOINT` (or `local_endpoints.llama-cpp`).

**Windows + WSL2.** If `qq` runs inside WSL but `llama-server` runs as a
native Windows process, WSL2's loopback is a separate VM, so the default
`127.0.0.1:8888` gets `Connection refused`. QonQrete now auto-detects the
Windows host through the WSL NAT gateway, so pick whichever fits your setup:

1. **Run llama-server inside WSL** (simplest, recommended). `127.0.0.1:8888`
   just works, and Windows can still reach it via `localhost:8888` (WSL2
   forwards Windows localhost into WSL automatically). GPU works too via WSL
   CUDA with your normal Windows driver.
2. **Keep llama-server on Windows** and let QonQrete find it. Bind it to all
   interfaces — `llama-server -m model.gguf --host 0.0.0.0 --port 8888` —
   and allow it through Windows Firewall for the WSL virtual adapter. The
   first unreachable-loopback call falls back to the Windows-host endpoint
   automatically (`[llama-cpp] WSL: ... using Windows-host endpoint ...`).
3. **Pin the endpoint manually**:
   `QQ_LLAMA_CPP_ENDPOINT=http://<windows-host-ip>:8888/v1`
   (`QQ_WSL_HOST_IP` can seed the auto-detected IP for exotic networking).

#### MLX via mlx_lm.server (`provider: mlx`)

On Apple Silicon, MLX models (the `mlx-community` safetensors format) run
natively and fast through Apple's MLX. Load the model in its own process —
it stays up between QonQrete runs and serves any client:

```bash
mlx_lm.server --model mlx-community/<model-id> --port 8080
# or point at a local MLX weights folder:
mlx_lm.server --model ~/models/my-mlx-model --port 8080
```

Then point QonQrete at it:

```yaml
provider: mlx
```

The endpoint defaults to `http://127.0.0.1:8080/v1` and can be overridden
with `QQ_MLX_ENDPOINT` (or `local_endpoints.mlx`). No model name is sent by
default — `mlx_lm.server` serves the model it was started with (a placeholder
name would make it try to *load* a model by that name). Set a concrete
per-role model in `config/qq.yaml` only when you want the server to load a
specific MLX model. API keys are optional (`QQ_MLX_API_KEY`).

Everything else (loops, dashboard, image backend, YOLO mode, harness checks) has sensible defaults and can be tuned via CLI flags or the file.

## IDE integrations

### VS Code

1. Install **QonQrete** from the VS Code Marketplace.
2. `Ctrl+Shift+P` → **QonQrete: Provider & Model** to set provider/model.
3. Open a `.md` task file, then **QonQrete: Run Open File as Task** (or press the sidebar button).
4. Choose the destination directory and TUI/headless mode when prompted.

### IntelliJ / JetBrains

1. Install **QonQrete** from the JetBrains Marketplace.
2. Use **Settings → Tools → QonQrete** to set the destination directory and `qq` path.
3. Use **QonQrete: Provider & Model** to configure the engine.
4. Press `Ctrl+Alt+Q` or **QonQrete: Run Open File as Task**.

Both IDEs expose the same v2 controls: **Run Open Task File**, **Provider & Model**, **Doctor**, **Verify**, **Cleanup**, **List Runs**, **Replay Run**, **Exec**, and **Chat**.

## briQsQope web dashboard

`qq run` can launch a read-only kanban board that shows build groups as cards and live progress:

```bash
qq run task.md ./my-build --web
# or standalone:
qq web serve
```

It is a read-only view over the run events; QonQrete remains the controller and source of truth.

## QonQrete Chat

```bash
qq chat
```

Opens `http://127.0.0.1:1337` with a destination field and a task box. Every submitted prompt becomes a temporary Markdown task and runs through the normal `qq run <task> <destination>` pipeline (TUI + briQsQope included).

## Documentation map

- [QUICKSTART.md](./QUICKSTART.md) — shortest path to a first run
- [doc/DOCUMENTATION.md](./doc/DOCUMENTATION.md) — full technical reference
- [doc/ARCHITECTURE.md](./doc/ARCHITECTURE.md) — architecture and pipeline layout
- [doc/RELEASE-NOTES.md](./doc/RELEASE-NOTES.md) — version history
- [doc/TERMINOLOGY.md](./doc/TERMINOLOGY.md) — QonQrete vocabulary

## License

QonQrete is licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE) for full terms.
