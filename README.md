# Qq — QonQrete v2 Spine

Deterministic local-first multi-agent coding harness.

```
Qlarifier → instruQtor → (construQtor ↔ inspeQtor)
    ↑ ask_human            ↓            ↓
    └─── clarification ───┘    harness  ─┘
```

Qq is the rebuilt base architecture for the devops-team agent loop.
It runs a deterministic orchestration engine (Qontroller) that cycles
through Qlarifier (clarification), instruQtor (plan splitting), construQtor
(implementation), harness (shell checks), and inspeQtor (review) until
inspeQtor returns the exact token `FULLY_DONE`.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with mock adapter (zero API calls, zero CodeSeeq required)
python3 -m qq run examples/example_task.md --repo-root /tmp/myapp --dry-run --max-cycles 10

# Run all acceptance checks
python3 -m compileall -q qq tests
python3 -m unittest discover -s tests -v
pytest -q                                    # optional, if pytest is available
python3 -m qq providers --json
python3 -m qq package
python3 -m qq package --check
bash scripts/verify.sh                       # runs all of the above
```

## Running with CodeSeeq (optional)

CodeSeeq is an open-source launcher for the Codex CLI wired to DeepSeek V4 models.
See https://github.com/illdynamics/codeseeq for installation.

```bash
# Set your API key
export DEEPSEEK_API_KEY=sk-...

# Install codeseeq from the repo above, then:
python3 -m qq run task.md --repo-root . --provider codeseeq
```

**Important:** Live CodeSeeq integration was not executed in this environment.
The CodeSeeq adapter is covered by command-construction/unit tests only.
Provide your own CodeSeeq binary and API key to use the real adapter.



## Streaming live CodeSeeq output

Qq can stream agent stdout/stderr live to the terminal while still writing
artifacts. Quiet mode is the default — no agent output is shown unless
`--stream-agent-output` is passed.

When `--stream-agent-output` is enabled, Qq prints agent stdout/stderr chunks
as they arrive. It must not wait for the agent process to finish before showing
output. The streaming path uses `subprocess.Popen` with threaded concurrent
readers for stdout and stderr, emitting each line/chunk immediately to the
terminal and writing it to artifact files.

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--stream-agent-output` | off | Stream agent stdout/stderr live |
| `--stream-mode prefixed\|raw` | prefixed | Prefix mode (`[role stdout]`) or raw |
| `--stream-stderr` / `--no-stream-stderr` | on (when streaming) | Whether to stream stderr |
| `--show-prompts` | off | Print prompt file paths during streaming |
| `--stream-indicator stream\|spinner\|none` | stream | What to show after role prefix |
| `--stream-transport pipe\|pty` | pipe | Subprocess transport mode (pty for heavy-buffering CLIs) |
| `--event-log-agent-output` | *optional* | Log per-line output to events.jsonl |

### Dry-run

```bash
python3 -m qq run examples/example_task.md \
  --repo-root "$(mktemp -d)" \
  --dry-run \
  --max-cycles 10 \
  --stream-agent-output

# With spinner indicator (braille_snake)
python3 -m qq run examples/example_task.md \
  --repo-root "$(mktemp -d)" \
  --dry-run \
  --max-cycles 10 \
  --stream-agent-output \
  --stream-indicator spinner
```

Dry-run streaming emits simulated output:
```
[Qlarifier stdout] clarified task ready
[instruQtor stdout] created 2 briQs across 1 build group
[construQtor stdout] mock build cycle 1 wrote files
[inspeQtor stdout] NOT_DONE: one issue found
```

With spinner indicator, the terminal shows a `braille_snake` animation:
```
[Qlarifier] ⠁ clarified task ready
[instruQtor] ⠁ created 2 briQs across 1 build group
[construQtor] ⠁ mock build cycle 1 wrote files
[inspeQtor] ⠁ NOT_DONE: one issue found
```

The spinner indicator is terminal display only:
- Default indicator is `stream` (shows literal `stdout`/`stderr`).
- `spinner` shows a `braille_snake` frame sequence: `⠁⠃⠇⡇⣇⣧⣷⣿⡿⠿⠟⠛⠙⠉`.
- `none` shows only the role prefix.
- Artifacts (`stdout.txt`/`stderr.txt`) and event metadata still use `stdout`/`stderr`.
- `stdin` is not an output stream and is never rendered as agent output.
- Spinner state is per `(role, stream_name, call_id)` — concurrent streams don't share counters.
- Raw mode ignores the spinner indicator.



### Sticky terminal status line

Qq supports a sticky terminal status bar that displays live agent/session metadata
at the top or bottom of the terminal while streaming output scrolls normally.

#### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--stream-status-line off\|bottom\|top` | off | Enable sticky status line |
| `--stream-line-prefix auto\|agent\|stream\|none` | auto | Control body line prefix behavior |

#### Exact sticky status line format

```
╭─[ꝖꝖ]─❯❯❯<agent-name> <spinner> M=<model-code> C=<cycle> · T=<time> · A=<time> · B=<number> · P≈<score>% [✓0|↯N]─╮
```

#### Field reference

| Field | Meaning |
|-------|---------|
| `ꝖꝖ` | Qq logo |
| `❯❯❯` | QonQrete flow arrows |
| `<agent-name>` | Active agent: Qlarifier, instruQtor, construQtor, or inspeQtor |
| `<spinner>` | Current braille_snake spinner frame (`⠁⠃⠇⡇⣇⣧⣷⣿⡿⠿⠟⠛⠙⠉`) |
| `M=<code>` | Model code: F, FT, P, PT, or ? |
| `C=<n>` | Current cycle number |
| `T=<time>` | Total QonQrete run time (MM:SS or H:MM:SS) |
| `A=<time>` | Current active agent runtime |
| `B=<n>` | Streamed chunk count for active agent call |
| `P≈<score>%` | Latest InspeQtor score as estimated completion percentage |
| `[✓0]` | Last exit status: success (green checkmark) |
| `[↯N]` | Last exit status: failure with exit code N (red lightning) |

#### Model codes

```
F  = deepseek-v4-flash
FT = deepseek-v4-flash-thinking (thinking mode on)
P  = deepseek-v4-pro
PT = deepseek-v4-pro-thinking (thinking mode on)
?  = unknown/custom model
```

#### Examples

```bash
# Sticky status line at top
python3 -m qq run examples/example_task.md   --repo-root "$(mktemp -d)"   --dry-run   --max-cycles 10   --stream-agent-output   --stream-indicator spinner   --stream-status-line top

# Sticky status line at bottom
python3 -m qq run examples/example_task.md   --repo-root "$(mktemp -d)"   --dry-run   --max-cycles 10   --stream-agent-output   --stream-indicator spinner   --stream-status-line bottom

# Explicit stream prefix override
python3 -m qq run examples/example_task.md   --repo-root "$(mktemp -d)"   --dry-run   --stream-agent-output   --stream-status-line bottom   --stream-line-prefix stream
```

#### Behavior

- **TTY-only**: Sticky ANSI codes are emitted only in interactive terminals.
  Non-TTY output (pipes, CI, redirects) degrades to clean line streaming automatically.
- **Clean body**: When sticky line is active, stream body output defaults to clean text
  (no agent prefix like `[construQtor]`). Prefixes can be restored with
  `--stream-line-prefix agent` or `--stream-line-prefix stream`.
- **Raw mode incompatible**: `--stream-mode raw` + `--stream-status-line` exits with
  a clear error — sticky line uses terminal control sequences incompatible with raw mode.
- **Agent switching**: The sticky line switches agent name, model code, spinner, and
  resets chunk count/chunk timer whenever the active agent changes.
- **InspeQtor score**: `P≈<score>%` updates after each InspeQtor review. Pre-reviews
  show `P≈0%`.
- **Score validation**: `FULLY_DONE` requires score >= 95. Score 100 with
  non-empty issues is rejected as inconsistent. Missing/invalid score triggers retry.
- **Spinner animation**: Spinner advances on every stream chunk, with idle animation
  at ~6 fps during quiet agent runtime (without increasing chunk count B).

### PTY transport mode

If a provider CLI buffers output heavily when stdout is a pipe (some CLIs only
stream properly when attached to a TTY), use the PTY transport mode:

```bash
python3 -m qq run task.md \
  --repo-root /path/to/repo \
  --provider codeseeq \
  --stream-agent-output \
  --stream-transport pty
```

- Default: `pipe` (uses `subprocess.Popen(stdout=PIPE, stderr=PIPE)`).
- `pty`: attaches child stdout/stderr to a pseudo-terminal for unbuffered streaming.
- PTY mode is terminal UX only; artifacts are still written normally.
- PTY mode does not corrupt JSON parsing.
- If PTY is unsupported on the platform, a clear error is printed.

### Production

```bash
python3 -m qq run task.md \
  --repo-root /path/to/repo \
  --provider codeseeq \
  --runtime-mode host \
  --bridge-mode process \
  --stream-agent-output \
  --check "pytest -q"
```

Production streaming shows live CodeSeeq stdout/stderr with `[role stream]`
prefixes while writing the same output (non-redacted) to artifact files under
`.qq/runs/<id>/agents/`.

### Behavior

- **Quiet mode** (default): Only high-level Qq status lines are printed.
- **Streaming mode**: Agent subprocess stdout/stderr is printed live in real time.
- **Artifacts**: All output is still written to `stdout.txt` and `stderr.txt` in the artifact directories — streaming never replaces artifact writing.
- **Redaction**: Terminal output is redacted (secrets like API keys are masked). Artifact files preserve the original raw output for debugging.
- **Prompts**: Not printed unless `--show-prompts` is enabled (and then only the file path, not the full content).

## Commands

```text
qq run task.md --repo-root .
    Run the full clarify → plan → build → review loop

qq run task.md --repo-root . --dry-run
    Run with the mock adapter — zero API calls, no CodeSeeq required

qq run task.md --repo-root . --check "pytest -q"
    Add harness check commands (repeatable)

qq run task.md --repo-root . --max-cycles 25 --briq-sensitivity 5
    Tune the repair loop ceiling and decomposition granularity

qq run task.md --repo-root . --provider codeseeq
    Use the real CodeSeeq provider (requires API key)

qq run task.md --repo-root . --review-on-harness-failure
    Run InspeQtor even when harness checks fail

qq replay .qq/runs/<run-id>/events.jsonl
    Print an events.jsonl run log

qq doctor
    Check system readiness (git, CodeSeeq binary, API keys, config)

qq doctor --offline
    Check only local/offline readiness (warns on missing API keys)

qq providers
    List available providers and their capabilities

qq cleanup --repo-root . --older-than 7d
    Remove old Qq run artifacts

qq package
    Build a clean release zip

qq package --check
    Validate the source tree is package-clean

qq package --check-archive dist/qonqrete-qq-v2.0.0.zip
    Validate a release archive

qq package --final
    Build and print the final artifact path prominently

qq package --check-upload-tree
    Stricter tree check (also fails on .git/ and dist/*.zip)

qq package --check-uploaded-zip <path>
    Validate an uploaded zip archive
```

## CodeSeeq Image Fallback

Qq can use CodeSeeq's upstream Codex/OpenAI image services without requiring
a direct OpenAI API key. This is the recommended path for generating images
through CodeSeeq skills like `imagegen`.

### Setup

```bash
export CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES=true
export CODESEEQ_RUNTIME_MODE=host
```

This enables:
- CodeSeeq to use upstream Codex/OpenAI services where supported
- Host runtime (required for image generation skills)
- No local OpenAI API key needed
- Variables are propagated to CodeSeeq and all skills

### Image Smoke Test

```bash
# Mocked test (no network, no upstream services)
python3 -m qq image-smoke-test

# Real upstream image test (requires codeseeq + imagegen skill)
CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES=true \
CODESEEQ_RUNTIME_MODE=host \
QQ_RUN_IMAGE_SMOKE_TEST=1 \
python3 -m qq image-smoke-test
```

The smoke test generates an image of QonQrete the cybersquid and saves:
- `.qq/image-tests/qonqrete_cybersquid.png` — the image
- `.qq/image-tests/qonqrete_cybersquid.meta.json` — metadata

### Environment Propagation

The `build_codeseeq_env()` helper ensures consistent env propagation:
- `CODESEEQ_ALLOW_UPSTREAM_CODEX_SERVICES` (default: `true`)
- `CODESEEQ_RUNTIME_MODE` (default: `host`)

User-set values are preserved; only missing keys get defaults.
If upstream services are disabled, image commands fail with a clear message.

## Testing

Both test runners are supported:

```bash
# unittest (required by acceptance criteria)
python3 -m unittest discover -s tests -v

# pytest (optional, if installed)
pytest -q

# Run specific test classes for streaming:
python3 -m pytest tests/test_streaming.py -q -v

# Full verification (all acceptance checks)
python3 -m qq.verify
bash scripts/verify.sh
```

## Architecture

```
qq/
├── __init__.py, __main__.py, cli.py   # Entry points
├── qontroller.py                       # Orchestration loop
├── agents/
│   ├── qlarifier.py     # Clarification
│   ├── instruqtor.py    # Plan splitting
│   ├── construqtor.py   # Implementation
│   ├── inspeqtor.py     # Review
│   └── _jsonio.py       # JSON I/O + streaming bridge
├── adapters/
│   ├── base.py          # AgentAdapter interface
│   ├── parameters.py    # CodeSeeq (Codex CLI) adapter
│   ├── mock.py          # Mock adapter for offline/dry-run
│   └── stubs.py         # Future provider stubs
├── models.py             # Data classes (Task, BriQ, Plan, etc.)
├── config.py             # YAML configuration + provider loading
├── streaming.py          # Live stdout/stderr rendering
├── eventlog.py           # JSONL event logging
├── process.py            # Subprocess management
├── verify.py             # Python-based verification runner
├── package.py            # Release packaging (pure Python)
├── workspaces.py         # Git worktree management
└── harness/              # Shell-based quality gates
```

## Verifier

The Python verifier (`qq.verify`) runs all acceptance checks with Python
subprocess management instead of fragile shell-process timeout logic.

```bash
# Run all checks (fail-fast: stops on first failure)
python3 -m qq.verify

# Run all checks, continue after failures
python3 -m qq.verify --continue-on-failure

# Dev tree mode (skip package + archive steps)
python3 -m qq.verify --skip-pytest --timeout-scale 0.5

# Via shell wrapper
bash scripts/verify.sh --skip-pytest --timeout-scale 0.5
```

### Verification steps

| # | Check | Default timeout |
|---|-------|----------------|
| 1 | `python3 -m compileall -q qq tests` | 180s |
| 2 | `python3 -m unittest discover -s tests -v` | 600s |
| 3 | `python3 -m pytest -q -s` | 180s |
| 4 | `python3 -m qq providers --json` | 30s |
| 5 | `python3 -m qq doctor --offline` | 30s |
| 6 | `python3 -m qq run ... --dry-run` | 90s |
| 7 | `python3 -m qq run ... --stream-agent-output` | 90s |
| 8 | `python3 -m qq package --check` | 60s |
| 9 | `python3 -m qq package --final` | 120s |
| 10 | `python3 -m qq package --check-archive` | 30s |
| 11 | `python3 -m qq package --check-uploaded-zip` | 30s |
| 12 | Orphan-process audit | n/a |

## Verification with Python-extracted releases

When the release zip is extracted with Python's `zipfile.extractall()`,
`scripts/verify.sh` becomes non-executable on disk (Python's default
extraction does not restore POSIX permissions). This is expected:

```bash
# Works fine — Bash only needs read permission
bash scripts/verify.sh --skip-pytest --skip-package-steps --timeout-scale 0.5

# Does NOT require chmod
python3 -m qq.verify --skip-pytest --skip-package-steps --timeout-scale 0.5
```

The executable bit is validated at archive level (`ZipInfo.external_attr`),
not at extracted file level, so Python-extracted release trees pass
verification without manual `chmod +x`.

## Package archive validation

`python3 -m qq package --check-archive` validates:
- Exactly one top-level directory
- No banned entries (.git/, __MACOSX/, .DS_Store, pycache, .pyc, etc.)
- `scripts/verify.sh` has executable bits in `ZipInfo.external_attr` (mode 0755)
- No nested .zip files
- No .qq/runs, .qq/worktrees

## Version history

2.0.0 — 2026-06-30
    Major version bump to QonQrete v2.0.0. Full repo cleanup, consolidated
    documentation, and final hardened release. Clean sweep of all temporary
    files, pycache, and legacy artifacts. Production-ready multi-agent
    coding harness with streaming, sticky status line, PTY transport,
    CodeSeeq upstream image fallback, and comprehensive verification suite.

0.2.27 — 2026-06-29
    Lightened frame/chrome grey (ANSI 254) for status bar; hardened three-part
    float layout (left/center/right) with explicit padding to terminal width
    and ljust fallback; all decorative line-art, brackets, and separator dots
    use consistent lighter grey.

0.2.22 — 2026-06-28
    CodeSeeq upstream image-generation fallback integration; image smoke-test
    command; build_codeseeq_env() env propagation helper; inspeQtor display
    changes: NOT_DONE in red, FULLY_DONE to FULLY_DONE in green;
    comprehensive env propagation and image tests.

0.2.20 — 2026-06-28
    Sticky terminal status line with live agent/session metadata; InspeQtor
    score integration; exact formatter with braille_snake spinner; TTY-only
    activation; clean body output; model code derivation; CLI flags for
    --stream-status-line and --stream-line-prefix; comprehensive UI tests.
    Fix verify.sh executable-bit test; fail-fast verifier; live streaming;
    archive-level permissions validation; PTY transport mode.
    Fix verify.sh executable-bit test; fail-fast verifier; live streaming;
    archive-level permissions validation; PTY transport mode.

0.2.18 — 2026-06-28
    Verified verifier; braille_snake spinner; archive hygiene hardening.

0.2.17
    Original qonqrete-qq-v0.2.17.zip (archived) release.

## License

MIT
