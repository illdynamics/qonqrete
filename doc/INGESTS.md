# `qq ingest` — what it is for

`qq ingest` manages QonQrete's ingest-side bookkeeping for externally submitted runs.

It is **not** the normal task runner. A normal local build is started with:

```bash
qq run <task-file> <destination-directory>
```

Ingest is used when another system (for example the QonQrete runs/ingest API or a
transport such as `qq-trans`) submits work to QonQrete. The ingest layer keeps
idempotency records so the same request is not accidentally executed twice and
keeps a dead-letter log for requests that could not be processed.

## Commands

### `qq ingest status`

Shows the ingest idempotency records and their status. Use `--source` to filter
by submitting source and `--control-root` to inspect a specific control root.

### `qq ingest purge-stale`

Removes old idempotency records. The default age is `24h`; examples include:

```bash
qq ingest purge-stale --older-than 7d
qq ingest purge-stale --older-than 3600s --source qq-trans
```

### `qq ingest dead-letter list`

Lists requests that were moved to the dead-letter store because they could not
be processed.

### `qq ingest retry <idempotency-key>`

Removes a matching dead-letter record so the originating system can submit it
again (the command itself does not invent a new task payload).

## Why this exists

The separation is intentional:

- **`qq run`** = execute a task locally.
- **`qq ingest`** = operational bookkeeping around externally submitted tasks.
- **`qq runs`** = inspect/select/clean up known QonQrete run sessions.
- **`qq web`** = operate the briQsQope dashboard.

The ingest records live under the configured control root and are independent
of CodeSeeq's temporary `.codeseeq` working directories.
