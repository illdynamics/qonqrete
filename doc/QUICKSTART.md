# QonQrete Quickstart

**Version:** `v1.2.2`

This guide gets you from zero to your first Qage using the workspace deployment model in `v1.2.2`.

## Option A: IDE-first

### VS Code
1. Install the **QonQrete** extension.
2. Open a project folder.
3. Run **QonQrete: Deploy to Workspace**.
4. Run **QonQrete: Create tasq.md** and describe the task.
5. Run **QonQrete: Run Tasq**.

### IntelliJ / JetBrains
1. Install the **QonQrete** plugin.
2. Open a project.
3. Run **QonQrete: Deploy to Workspace**.
4. Run **QonQrete: Create tasq.md** and edit it.
5. Run **QonQrete: Run Tasq**.

### What gets created

```text
my-project/
  tasq.md                  ← you edit this
  .qonqrete/               ← runtime (auto-deployed, gitignored)
    qonqrete.sh
    worqspace/
    qrane/
    worqer/
    Dockerfile
    ...
```

The IDE syncs your root `tasq.md` into `.qonqrete/worqspace/tasq.md` before each run.

## Option B: CLI

### Prerequisites
- Docker or Podman
- either a cloud-provider API key **or** an external `llamacpp`-compatible HTTP endpoint

### Cloud provider example
```bash
export OPENAI_API_KEY='...'
chmod +x qonqrete.sh
./qonqrete.sh init
./qonqrete.sh run --auto --cyqles 0
```

### External llama.cpp example
Configure `worqspace/config.yaml`:

```yaml
agents:
  construqtor:
    provider: llamacpp
    model: qwen3-coder-14b
    timeout: 1800
    llamacpp:
      base_url: http://host.docker.internal:8080/v1
```

Then run:

```bash
./qonqrete.sh init
./qonqrete.sh run --auto --cyqles 0
```

`llamacpp` is an **external HTTP runtime**. It is not the same thing as `provider: local`.

## Core runtime flow

```text
Qrystallizer → InstruQtor → ConstruQtor → Qualifier → InspeQtor → Qrane
```

- **ConstruQtor** builds code only.
- **Qualifier** runs all validation and writes `quality.d/`.
- **InspeQtor** evaluates results and writes reqap markdown plus verdict JSON.
- **Qrane** stops or continues from the structured verdict.

## Auto-cycles

Use `--cyqles 0` for auto mode.

```bash
./qonqrete.sh run --auto --cyqles 0
```

Manual fixed cycles still work:

```bash
./qonqrete.sh run --cyqles 3
```

`auto_cycle_limit` in config is the hard safety cap for auto mode.

## Modes

- **`program`** — freeze execution scope to the original tasq plus canonical requirement ledger
- **`innovative`** — finish mandatory ledger work first, then keep improvements in an optional enhancement backlog

Optional enhancement briqs are labeled `Scope-Class: OPTIONAL_ENHANCEMENT` and do not extend the stop condition.

## What to inspect after a run

After a successful run, inspect these artifacts:

```text
.qonqrete/worqspace/qage_YYYYMMDD_HHMMSS/
.qonqrete/worqspace/qage_.../qrystal.d/
.qonqrete/worqspace/qage_.../qodeyard/
.qonqrete/worqspace/qage_.../quality.d/
.qonqrete/worqspace/qage_.../reqap.d/
```

Important machine-readable files:
- `quality.d/cyqleN/report.json`
- `reqap.d/cyqleN_verdict.json`
- `reqap.d/latest_verdict.json`

## Quality and completion

QonQrete cannot finish successfully if required quality checks failed.
That includes failed builds, failed tests, or failed builtin checks.

The verdict JSON is the source of truth for completion. Reqap markdown is the human-readable companion.

## Cost confirmation gate

To require confirmation after CalQulator estimates cost:

```yaml
options:
  cost_confirmation_gate: true
```
