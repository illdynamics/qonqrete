# Python Big Task — Markdown Knowledge Search Engine

## Difficulty
Big

## Goal
Build a local search tool for a folder of Markdown notes.

## What You Will Build
A Python project called `md_search` that indexes `.md` files and lets the user search through them quickly.

## Example Usage

```bash
python md_search.py index ./notes
python md_search.py search "rust async ownership"
python md_search.py search "meeting notes" --limit 5
python md_search.py rebuild ./notes
```

## Requirements

1. Recursively scan a folder for `.md` files.
2. Extract for each file:
   - path
   - title from the first Markdown heading
   - word count
   - last modified timestamp
   - plain text content

3. Build a local search index.
4. Store the index as JSON or SQLite.
5. Support keyword search.
6. Score results based on:
   - number of matching terms
   - term frequency
   - title match bonus
   - recency bonus

7. Show search results with:
   - title
   - path
   - score
   - short matching snippet

## Suggested Project Structure

```text
md_search/
├── md_search.py
├── indexer.py
├── search.py
├── storage.py
└── README.md
```

## Acceptance Criteria

- Indexing works on at least 100 Markdown files.
- Search results are sorted by relevance.
- Deleted files are removed from the index when rebuilding.
- Badly formatted Markdown files do not crash the program.
- Snippets highlight or clearly show the matching words.

## Stretch Goals

- Add fuzzy matching.
- Add tags extracted from frontmatter.
- Add SQLite full-text search.
- Add a small terminal UI.
- Add `watch` mode that re-indexes when files change.
