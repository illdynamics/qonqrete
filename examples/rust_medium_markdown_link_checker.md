# Rust Medium Task — Markdown Link Checker

## Difficulty
Medium

## Goal
Build a local Markdown link checker.

## What You Will Build
A Rust binary called `mdlinkcheck` that scans Markdown files and reports broken local links.

## Example Usage

```bash
cargo run -- ./docs
cargo run -- ./README.md
```

## Requirements

1. Accept either a Markdown file or a directory.
2. If given a directory, recursively scan `.md` files.
3. Detect Markdown links:

```markdown
[title](./some-file.md)
[section](./guide.md#install)
![image](./img/logo.png)
```

4. Validate local file links:
   - target file exists
   - image file exists
   - anchor links are checked when possible

5. Ignore external links by default:
   - `https://...`
   - `http://...`
   - `mailto:...`

6. Print a report:
   - total Markdown files scanned
   - total links found
   - broken links
   - file and line number for each issue

## Suggested Crates

- `clap`
- `walkdir`
- `regex`

## Acceptance Criteria

- Relative paths are resolved from the Markdown file's directory.
- Broken links include line numbers.
- External links are skipped unless a future flag enables them.
- The program exits with code `1` if broken links are found.
- The program exits with code `0` if all links are valid.

## Stretch Goals

- Add `--check-external`.
- Add support for GitHub-style heading anchors.
- Add JSON output.
- Add a GitHub Actions example.
