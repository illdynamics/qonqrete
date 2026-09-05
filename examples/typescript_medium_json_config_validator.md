# TypeScript Medium Task — JSON Config Validator

## Difficulty
Medium

## Goal
Build a TypeScript CLI that validates app configuration files.

## What You Will Build
A project called `config-guardian` that reads a JSON config file and validates it against a schema.

## Example Config

```json
{
  "appName": "qonqrete-api",
  "port": 8080,
  "environment": "development",
  "features": {
    "auth": true,
    "metrics": false
  },
  "allowedOrigins": ["http://localhost:3000"]
}
```

## Requirements

Validate:

- `appName` is a non-empty string
- `port` is a number between 1 and 65535
- `environment` is one of:
  - `development`
  - `staging`
  - `production`
- `features.auth` is boolean
- `features.metrics` is boolean
- `allowedOrigins` is an array of valid-looking URLs

## Example Usage

```bash
npm run validate -- ./config.json
npm run validate -- ./config.json --pretty
```

## Output

For valid config:

```text
✓ config is valid
```

For invalid config:

```text
✗ config is invalid
- port must be between 1 and 65535
- environment must be development, staging, or production
```

## Acceptance Criteria

- Invalid JSON is handled cleanly.
- Multiple validation errors are shown together.
- The validator returns a typed result object.
- The CLI exits with code `0` for valid config.
- The CLI exits with code `1` for invalid config.
- No `any` unless there is a strong reason.

## Suggested Project Structure

```text
config-guardian/
├── package.json
├── tsconfig.json
└── src/
    ├── cli.ts
    ├── validator.ts
    └── types.ts
```

## Stretch Goals

- Add schema loading from a separate file.
- Add JSON output.
- Add environment-specific rules.
- Add tests for every invalid field.
