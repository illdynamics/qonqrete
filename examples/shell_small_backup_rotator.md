# Shell Script Small Task — Backup Rotator

## Difficulty
Small

## Goal
Build a shell script that creates timestamped backups of a folder and keeps only the newest backups.

## What You Will Build
A POSIX-ish shell script called `backup_rotator.sh`.

## Example Usage

```bash
./backup_rotator.sh ./notes ./backups 5
```

This should back up `./notes` into `./backups` and keep only the newest 5 backup archives.

## Requirements

1. Accept three arguments:
   - source directory
   - destination directory
   - number of backups to keep

2. Validate that the source directory exists.
3. Create the destination directory if it does not exist.
4. Create a `.tar.gz` archive with a timestamped filename.

Example:

```text
notes-2026-06-28-153012.tar.gz
```

5. Delete older backups beyond the keep count.
6. Print clear status messages.

## Acceptance Criteria

- Missing arguments show a usage message.
- Invalid source directory exits with a non-zero status.
- Backup archive is created successfully.
- Old backups are removed correctly.
- Paths with spaces are handled safely.

## Stretch Goals

- Add `--dry-run`.
- Add checksum generation with `sha256sum` or `shasum`.
- Add a log file.
