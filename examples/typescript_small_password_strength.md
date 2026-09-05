# TypeScript Small Task — Password Strength Checker

## Difficulty
Small

## Goal
Build a TypeScript function and CLI that scores password strength.

## What You Will Build
A small TypeScript project called `password-strength`.

## Example Usage

```bash
npm run check -- "correct horse battery staple"
npm run check -- "P@ssw0rd123!"
```

## Requirements

Create a function:

```ts
type StrengthResult = {
  score: number;
  label: "weak" | "okay" | "strong" | "very strong";
  warnings: string[];
};

function checkPasswordStrength(password: string): StrengthResult;
```

Score based on:

- length
- uppercase letters
- lowercase letters
- numbers
- symbols
- repeated characters
- common bad passwords like `password`, `admin`, `qwerty`, `letmein`

## Acceptance Criteria

- Empty password returns score `0`.
- Common bad passwords are always weak.
- Very short passwords are weak.
- Long mixed-character passwords score higher.
- CLI prints score, label, and warnings.
- Code compiles with `tsc`.

## Suggested Project Structure

```text
password-strength/
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts
    └── cli.ts
```

## Stretch Goals

- Add tests with Vitest.
- Add JSON output.
- Add estimated crack-time text.
