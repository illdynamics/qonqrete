# QonQrete Quickstart

**Version:** `v1.2.0-stable`

This is the shortest accurate path to get QonQrete running.

## Option A: IDE-First (Recommended)

### VS Code

1. Install the **QonQrete** extension from the VS Code Marketplace
2. Open any project folder
3. Run **"QonQrete: Deploy to Workspace"** from the Command Palette (`Ctrl+Shift+P`)
4. Run **"QonQrete: Create tasq.md"** — edit the file to describe your build task
5. Run **"QonQrete: Run Tasq"** — auto-init handles the container image build on first run

### IntelliJ / JetBrains

1. Install the **QonQrete** plugin from the JetBrains Marketplace
2. Open any project
3. Run **"QonQrete: Deploy to Workspace"** from the action search (`Ctrl+Shift+A`)
4. Run **"QonQrete: Create tasq.md"** — edit the file
5. Run **"QonQrete: Run Tasq"** (`Ctrl+Alt+Q`) — auto-init on first run

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

The IDE syncs your root `tasq.md` into `.qonqrete/worqspace/tasq.md` before each run. You never need to touch the hidden directory.

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
worqspace/tasq.md
```

### 3. Run QonQrete

```bash
./qonqrete.sh run
./qonqrete.sh run --auto
./qonqrete.sh run --auto --mode security --briq-sensitivity 6 --cyqles 3
./qonqrete.sh run -a -n myproject
```

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
| Create tasq.md | Create starter template at project root |
| Configure Run | Set sensitivity, cycles, mode, engine |
| Run Tasq | Sync tasq → auto-init → execute |
| Run as QonQrete Tasq | Run any markdown as a temp tasq |
| Resume Run | Continue from a previous qage |
| Clean Qages | Delete old qage directories |

## Recommended first-run sanity checks

After a successful run, verify these exist:

```text
.qonqrete/worqspace/qage_YYYYMMDD_HHMMSS/
.qonqrete/worqspace/qage_.../qodeyard/
.qonqrete/worqspace/qage_.../exeq.d/
.qonqrete/worqspace/qage_.../reqap.d/
```
