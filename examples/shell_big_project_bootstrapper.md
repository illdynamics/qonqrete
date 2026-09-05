# Shell Script Big Task — Project Bootstrapper

## Difficulty
Big

## Goal
Build a shell-based project bootstrapper that creates clean starter project layouts.

## What You Will Build
A script called `bootstrap_project.sh` that can generate project folders for different project types.

## Supported Project Types

Support at least:

- `python-cli`
- `node-ts`
- `rust-cli`
- `static-site`

## Example Usage

```bash
./bootstrap_project.sh python-cli my-tool
./bootstrap_project.sh node-ts dashboard-api
./bootstrap_project.sh rust-cli qscanner
./bootstrap_project.sh static-site landing-page
```

## Requirements

1. Validate arguments:
   - project type
   - project name

2. Refuse to overwrite an existing directory unless `--force` is passed.
3. Create sensible folder structures for each project type.
4. Generate starter files:
   - `README.md`
   - `.gitignore`
   - basic source file
   - optional config file

5. Initialize git unless `--no-git` is passed.
6. Print next steps after creation.

## Suggested Structures

### python-cli

```text
my-tool/
├── README.md
├── .gitignore
├── pyproject.toml
└── src/
    └── my_tool/
        └── __init__.py
```

### node-ts

```text
dashboard-api/
├── README.md
├── package.json
├── tsconfig.json
└── src/
    └── index.ts
```

### rust-cli

```text
qscanner/
├── README.md
├── Cargo.toml
└── src/
    └── main.rs
```

### static-site

```text
landing-page/
├── README.md
├── index.html
├── styles.css
└── script.js
```

## Acceptance Criteria

- Invalid project type shows available types.
- Existing directories are protected.
- Generated files contain the project name.
- Git init works when available.
- Script works from any current directory.
- Shellcheck reports no major quoting issues.

## Stretch Goals

- Add template files in a `templates/` directory.
- Add interactive mode.
- Add license selection.
- Add `--open` to open the project in `$EDITOR` or VS Code.
