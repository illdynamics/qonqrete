# Java Medium: Log Anomaly Reporter

## Goal
Build a Java program that summarizes application logs and flags anomalies.

## Requirements
- Parse lines with timestamp, level, service, and message.
- Produce counts by level and service.
- Detect bursts of ERROR logs within a sliding 5-minute window.
- Output a text report and optional JSON report.
- Include tests for malformed log lines and time-window boundaries.

## Acceptance Criteria
- Build command and test command are documented.
- Malformed lines are counted, not fatal.
- Time-zone handling is explicit and deterministic.

## What This Test Measures
- Can QonQrete produce a complete, runnable solution rather than only a sketch?
- Can it handle edge cases and write usable tests?
- Can it explain setup and usage clearly without hiding assumptions?
