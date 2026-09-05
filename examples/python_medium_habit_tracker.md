# Python Medium Task — Local Habit Tracker

## Difficulty
Medium

## Goal
Build a CLI habit tracker that stores progress locally.

## What You Will Build
A Python app called `habit_tracker.py` that lets a user create habits, mark them complete, and view streaks.

## Commands

```bash
python habit_tracker.py add "Drink water"
python habit_tracker.py done "Drink water"
python habit_tracker.py list
python habit_tracker.py stats
python habit_tracker.py remove "Drink water"
```

## Requirements

1. Store data in a local JSON file called `habits.json`.
2. Each habit should contain:
   - name
   - creation date
   - list of completion dates
   - archived status

3. `add` creates a new habit.
4. `done` marks a habit complete for today.
5. `list` shows active habits and whether they are done today.
6. `stats` shows:
   - total completions
   - current streak
   - longest streak
   - completion percentage for the last 30 days

7. `remove` should archive the habit instead of deleting it permanently.

## Acceptance Criteria

- Running the app with no JSON file creates one automatically.
- Completing the same habit twice on the same day does not duplicate the entry.
- Date handling works across month boundaries.
- Output is readable in a terminal.
- The code is split into clear functions.

## Stretch Goals

- Add colored output.
- Add weekly summaries.
- Add CSV export.
- Add unit tests for streak calculations.
