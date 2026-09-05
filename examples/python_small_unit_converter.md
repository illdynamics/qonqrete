# Python Small Task — Terminal Unit Converter

## Difficulty
Small

## Goal
Build a simple command-line unit converter.

## What You Will Build
A Python script called `unit_converter.py` that converts values between common units.

## Requirements

Support at least these conversions:

- Celsius ↔ Fahrenheit
- Kilometers ↔ Miles
- Kilograms ↔ Pounds
- Liters ↔ Gallons

The script should accept:

- value
- source unit
- target unit

Example:

```bash
python unit_converter.py 10 km miles
python unit_converter.py 25 c f
python unit_converter.py 80 kg lb
```

## Output Example

```text
10 km = 6.21 miles
```

## Acceptance Criteria

- Invalid units show a helpful error.
- Non-numeric values do not crash the program.
- Output is rounded to 2 decimal places.
- Conversion logic is separated into functions.
- The script has a `--help` message.

## Stretch Goals

- Add meters, centimeters, inches, and feet.
- Add a small test suite with `pytest`.
- Add an interactive mode where the user can keep converting until they type `quit`.
