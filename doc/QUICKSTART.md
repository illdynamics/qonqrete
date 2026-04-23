# QonQrete Quickstart

**Version:** `v1.4.0`

This is the shortest accurate path to get QonQrete running.

## Option A: IDE-First (Recommended)

### VS Code

1. Install the **QonQrete** extension from the VS Code Marketplace
2. Open any project folder
3. Run **"QonQrete: Deploy to Workspace"** from the Command Palette (`Ctrl+Shift+P`)
4. Run **"QonQrete: Create Task File"** — edit the starter `tasq.md` to describe your build task
5. Run **"QonQrete: Run Tasq"** — runs the default task file directly; auto-init handles the container image build on first run

### IntelliJ / JetBrains

1. Install the **QonQrete** plugin from the JetBrains Marketplace
2. Open any project
3. Run **"QonQrete: Deploy to Workspace"** from the action search (`Ctrl+Shift+A`)
4. Run **"QonQrete: Create Task File"** — edit the starter `tasq.md`
5. Run **"QonQrete: Run Tasq"** (`Ctrl+Alt+Q`) — runs the default task file directly, auto-init on first run

### What happens

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

The IDE uses your chosen task file directly. `tasq.md` remains the default starter file, and you never need to touch the hidden runtime directory.

## Option B: CLI (Power Users)

### Prerequisites

- Docker or Podman
- At least one AI provider API key

```bash
export OPENAI_API_KEY='...'
export GOOGLE_API_KEY='...'      # or GEMINI_API_KEY
export ANTHROPIC_API_KEY='...'
export DEEPSEEK_API_KEY='...'
export QWEN_API_KEY='...'
```

### 1. Build the runtime image

```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

### 2. Edit the task

```text
tasq.md
```

### 3. Run QonQrete

```bash
./qonqrete.sh tasq.md
./qonqrete.sh run -f tasq.md
./qonqrete.sh run --auto
./qonqrete.sh run --auto --mode security --briq-sensitivity 6 --cyqles 3
./qonqrete.sh run -a -n myproject
./qonqrete.sh run -N -n local_only_output
./qonqrete.sh status
./qonqrete.sh audit
```

`-N` / `--no-sync` keeps run output in Qage/Qonstruction paths and skips the final repo-root sync-back step.

### 4. Resume / Clean

```bash
./qonqrete.sh resume
./qonqrete.sh clean
./qonqrete.sh clean -A
```

## IDE Commands Reference

Both VS Code and IntelliJ support the same commands:

| Command | What it does |
|---------|-------------|
| Deploy to Workspace | Install runtime into `.qonqrete/` |
| Create Task File | Create starter `tasq.md` at project root |
| Configure Run | Set sensitivity, cycles, mode, engine |
| Run Tasq | Run the default task file directly with auto-init when needed |
| Run as QonQrete Tasq | Run any markdown file directly as task input |
| Resume Run | Continue from a previous qage |
| Clean Qages | Delete old qage directories |

## Recommended first-run sanity checks

After a successful run, verify these exist:

```text
.qonqrete/worqspace/qage_YYYYMMDD_HHMMSS/
.qonqrete/worqspace/qage_.../run-manifest.v1.json
.qonqrete/worqspace/qage_.../task/task-spec.v1.json
.qonqrete/worqspace/qage_.../validation/validation-bundle.v1.json
.qonqrete/worqspace/qage_.../realization/realization-bundle.v1.json
.qonqrete/worqspace/qage_.../verdict/inspection-verdict.v1.json
.qonqrete/worqspace/qage_.../qodeyard/
.qonqrete/worqspace/qage_.../build/attempts/
```

## Cost Confirmation Gate

To require confirmation before running after cost estimation:

```yaml
# In worqspace/config.yaml
options:
  cost_confirmation_gate: true
```

The GateQeeper will prompt you to confirm after CalQulator shows the cost estimate.

## Validation Reality

Deterministic validation in the current bridge is strongest for Python. Other stacks still run through the workflow, but deterministic compile/test depth is not yet equivalent.
