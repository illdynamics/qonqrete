#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "${ROOT_DIR}/.qonqrete/qonqrete.sh" run -f "${ROOT_DIR}/.qonqrete/worqspace/tasq.md" --auto
