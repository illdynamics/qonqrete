#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${ALLOW_DIRTY_RELEASE:-}" ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
      echo "FATAL: Dirty tree detected. Commit changes or set ALLOW_DIRTY_RELEASE=1." >&2
      exit 1
    fi
  fi
fi

VERSION=$(cat VERSION | tr -d '[:space:]')
if [ -z "$VERSION" ]; then
  echo "FATAL: VERSION file is empty" >&2
  exit 1
fi

STAGING="qonqrete-v${VERSION}"
rm -rf "$STAGING"
mkdir -p "$STAGING"
trap 'rm -rf "$STAGING"' EXIT

cp -r \
  qonqrete.sh \
  VERSION \
  Dockerfile \
  requirements.txt \
  requirements-optional-tree-sitter.txt \
  package.json \
  LICENSE \
  COPYRIGHT \
  README.md \
  qonqrete.jpg \
  .env.example \
  qrane \
  worqer \
  worqspace \
  doc \
  tests \
  "$STAGING/"

# Remove Phase 2 and dev files from staging before zipping
rm -f "$STAGING/worqer/smoqetester/adapters/playwright_browser.py" 2>/dev/null || true
rm -f "$STAGING/tests/test_browser_validation_benchmarks.py" 2>/dev/null || true
rm -rf "$STAGING/benchmarks/recipe_planner/" 2>/dev/null || true
rm -f "$STAGING/masterwonqprompt.md" 2>/dev/null || true
rm -rf "$STAGING/.codeseeq/" 2>/dev/null || true
rm -rf "$STAGING/sqrapyard/" 2>/dev/null || true
find "$STAGING" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$STAGING" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

# Zip exclusions based on CI + additional junks
VERSIONED_ZIP="qonqrete-v${VERSION}.zip"
OUTPUT_ZIP="${OUTPUT_ZIP:-generated.zip}"
rm -f "$VERSIONED_ZIP" "$OUTPUT_ZIP"

zip -r "$VERSIONED_ZIP" "$STAGING/" \
  -x "*/.DS_Store" "*/._*" \
     "*/__MACOSX/*" "*/__MACOSX/" \
     "*/__pycache__/*" "*/__pycache__/" \
     "*.pyc" "*/.pytest_cache/*" "*/.pytest_cache/" \
     "*/.ruff_cache/*" "*/.ruff_cache/" \
     "*/.mypy_cache/*" "*/.mypy_cache/" \
     "*/.gradle/*" "*/.gradle/" \
     "*/node_modules/*" "*/node_modules/" \
     "*/.git/*" "*/.git/" \
     "*/.venv/*" "*/.venv/" \
     "*/.test_venv/*" "*/.test_venv/" \
     "*/.validation-env-cache/*" "*/.validation-env-cache/" \
     "*/qages/*" "*/qages/" \
     "*/audit/*" "*/audit/" \
     "*/qonstructions/*" "*/qonstructions/" \
     "*/struqture/*" "*/struqture/" \
     "*/vscode-extension/out/*" "*/vscode-extension/out/"

if [[ "$OUTPUT_ZIP" != "$VERSIONED_ZIP" ]]; then
  cp "$VERSIONED_ZIP" "$OUTPUT_ZIP"
fi

ls -lh "$VERSIONED_ZIP"
sha256sum "$VERSIONED_ZIP" > "qonqrete-v${VERSION}-SHA256.txt"
