# Shell Script Medium Task — Dotfile Auditor

## Difficulty
Medium

## Goal
Build a shell script that audits important dotfiles and reports useful system configuration details.

## What You Will Build
A script called `dotfile_audit.sh` that scans the user's home directory for common shell/dev config files.

## Files to Check

At minimum, check for:

- `~/.zshrc`
- `~/.bashrc`
- `~/.profile`
- `~/.gitconfig`
- `~/.ssh/config`
- `~/.vimrc`
- `~/.config/starship.toml`

## Requirements

For each file, report:

- whether it exists
- file size
- last modified date
- permissions
- whether it contains suspicious world-writable permissions

Also report:

- current shell
- operating system
- hostname
- current user
- git username/email if configured

## Example Usage

```bash
./dotfile_audit.sh
./dotfile_audit.sh --markdown report.md
```

## Acceptance Criteria

- The script does not crash if files are missing.
- Permission checks are readable and correct.
- Output is nicely aligned in terminal mode.
- Markdown mode writes a valid `.md` report.
- The script avoids unsafe unquoted variables.

## Stretch Goals

- Add JSON output.
- Add detection for duplicate PATH entries.
- Add a check for private SSH keys with unsafe permissions.
- Add a summary score like `OK`, `WARN`, or `RISKY`.
