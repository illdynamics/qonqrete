# QonQrete Live Proof Task

## Goal

Demonstrate one real, bounded, end-to-end QonQrete run on a small but non-trivial repository task that exercises clarification, planning, build, validation, realization, inspection, manifest generation, and bounded-stop behavior.

## Task

Add a tiny self-contained demo capability to QonQrete's repo-native bridge surfaces:

1. Add a new CLI/help-visible example or status message that makes the task-file-first flow more obvious to a first-time user.
2. Ensure the message does not reintroduce `sqrapyard` as the main path and does not require a fixed `tasq.md` ritual.
3. Keep the change small, bounded, and safe.
4. Preserve current bridge architecture and compatibility behavior.
5. Update any directly related help text or high-signal user-facing surface only if needed for consistency.

## Constraints

- Do not start phases 06/07/08 work.
- Do not redesign orchestration.
- Do not broaden scope into large README rewrites.
- Do not remove compatibility behavior unless directly needed for this small task.
- Keep the change suitable for a proof run: small, visible, and easy to validate.

## Completion Criteria

- The repository contains one small, clear improvement to the task-file-first demo path.
- The run produces manifest and audit artifacts.
- The run follows bounded-stop clarified-pass behavior by default.
- Any changed user-facing text remains consistent with the post-05 bridge direction.
- The final report states clearly what happened in the live run.

## Why this task

This task is intentionally small enough to keep the proof run stable, while still being real enough to exercise QonQrete's migrated bridge behavior end-to-end.
