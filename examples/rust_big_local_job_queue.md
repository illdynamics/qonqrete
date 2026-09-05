# Rust Big Task — Local Job Queue Server

## Difficulty
Big

## Goal
Build a local job queue server that accepts jobs, stores them, and lets workers process them.

## What You Will Build
A Rust project called `qjobs` with a small TCP or HTTP API.

## Core Concept

Clients can submit jobs. Workers can claim jobs. Jobs move through states:

```text
queued -> running -> done
queued -> running -> failed
```

## Required Job Fields

Each job should have:

- id
- name
- payload
- status
- created_at
- updated_at
- attempts
- last_error

## Required Commands or Endpoints

Implement these actions:

```text
SUBMIT <name> <payload>
CLAIM
DONE <job_id>
FAIL <job_id> <error>
STATUS <job_id>
LIST
```

You may implement this as:

- a plain TCP text protocol, or
- a small HTTP API

## Requirements

1. Multiple clients can connect.
2. Shared job state is safe across threads or tasks.
3. Jobs are claimed one at a time.
4. Failed jobs can be retried up to 3 times.
5. Completed jobs are not claimed again.
6. All changes are logged.
7. The protocol is documented in `README.md`.

## Suggested Implementation Options

### Standard Library Route

Use:

- `std::net::TcpListener`
- `std::thread`
- `Arc<Mutex<_>>`
- `HashMap` or `VecDeque`

### Async Route

Use:

- `tokio`
- `axum` or `warp`
- `serde`
- `uuid`

## Acceptance Criteria

- Two workers cannot claim the same job at the same time.
- A failed job is retried until the retry limit.
- Invalid commands return useful errors.
- The server keeps running after client disconnects.
- The code is split into modules:
  - protocol/API
  - job store
  - worker logic
  - main server startup

## Stretch Goals

- Persist jobs to a JSON file or SQLite.
- Add priorities.
- Add delayed jobs.
- Add a small CLI client.
- Add integration tests with multiple simulated workers.
