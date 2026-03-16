# QonQrete Quickstart

**Version:** `v1.1.9-stable`

This is the shortest accurate path to get the current repository running.

## Prerequisites

You need:
- Docker or Podman
- Python dependencies are handled through the container build
- at least one AI provider API key that matches your chosen config

Recommended environment variables:

```bash
export OPENAI_API_KEY='...'
export GOOGLE_API_KEY='...'      # or GEMINI_API_KEY
export ANTHROPIC_API_KEY='...'
export DEEPSEEK_API_KEY='...'
export QWEN_API_KEY='...'
```

## 1. Build the runtime image

```bash
chmod +x qonqrete.sh
./qonqrete.sh init
```

Force a runtime engine only if needed:

```bash
./qonqrete.sh init --docker
./qonqrete.sh init --podman
```

## 2. Edit the task

Edit:

```text
worqspace/tasq.md
```

Example:

```markdown
Build a small FastAPI service with CRUD endpoints, input validation, and tests.
```

## 3. Run QonQrete

### Basic run

```bash
./qonqrete.sh run
```

### Common useful variants

```bash
./qonqrete.sh run --auto
./qonqrete.sh run --user
./qonqrete.sh run -s
./qonqrete.sh run -a -n myproject
./qonqrete.sh run --mode security --briq-sensitivity 6 --cyqles 3
```

## 4. Resume an old qage

```bash
./qonqrete.sh resume
./qonqrete.sh resume -q qage_YYYYMMDD_HHMMSS
```

## 5. Clean old qages

```bash
./qonqrete.sh clean
./qonqrete.sh clean -q qage_YYYYMMDD_HHMMSS
./qonqrete.sh clean -A
```

## 6. Sqrapyard seeding

To start from an existing codebase:

1. place source material in `worqspace/sqrapyard/`
2. write a tasq that explains what to build/change
3. run with `-s`

```bash
./qonqrete.sh run -s
```

Without `-s`, sqrapyard contents are ignored.

## 7. VS Code quickstart

The repo includes a VS Code extension project in `vscode-extension/`.

### Package it

```bash
cd vscode-extension
npm install
npm run compile
npx vsce package
```

### Install locally

```bash
code --install-extension qonqrete-1.1.9.vsix
```

### What you get
- command palette actions
- sidebar panel
- run / resume / clean / init helpers
- run a Markdown file as a temporary QonQrete tasq

## 8. IntelliJ / JetBrains quickstart

The repo includes a JetBrains plugin project in `intellij-plugin/`.

### Build it

```bash
cd intellij-plugin
./gradlew buildPlugin
```

### Test it in sandbox

```bash
./gradlew runIde
```

### Install manually
Use the generated ZIP from `build/distributions/` inside your JetBrains IDE via:

```text
Settings → Plugins → Install Plugin from Disk
```

## 9. Recommended first-run sanity checks

After a successful run, verify these exist:

```text
worqspace/qage_YYYYMMDD_HHMMSS/
worqspace/qage_.../qodeyard/
worqspace/qage_.../exeq.d/
worqspace/qage_.../reqap.d/
```

If you saved a qonstruction, also check:

```text
worqspace/qonstructions/
```

## 10. Important honesty notes

- The repo currently works as a **repo-local QonQrete project**.
- The IDE integrations do not yet implement a fully centralized engine bootstrap flow.
- `TUI`, `MSB`, and `wonqrete` are still non-core / experimental paths.
- The committed config file may not represent the best defaults for your exact use case; tune `mode`, `briq_sensitivity`, and `auto_cycle_limit` for the task at hand.
