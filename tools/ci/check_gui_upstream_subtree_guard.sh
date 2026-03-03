#!/usr/bin/env bash
set -euo pipefail

# Guard: prevent manual edits to operator_console/gui_upstream.
# Allowed updates must come from git subtree operations, which leave
# commit metadata lines like:
#   git-subtree-dir: operator_console/gui_upstream

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BASE_REF="${GITHUB_BASE_REF:-}"
DIFF_RANGE=""

if [[ -n "$BASE_REF" ]]; then
  git fetch --no-tags --depth=200 origin "$BASE_REF"
  DIFF_RANGE="origin/${BASE_REF}...HEAD"
elif [[ -n "${GITHUB_EVENT_BEFORE:-}" && "${GITHUB_EVENT_BEFORE}" != "0000000000000000000000000000000000000000" ]]; then
  DIFF_RANGE="${GITHUB_EVENT_BEFORE}...HEAD"
else
  DIFF_RANGE="HEAD~1...HEAD"
fi

echo "[subtree-guard] Using diff range: ${DIFF_RANGE}"
CHANGED="$(git diff --name-only "$DIFF_RANGE" -- operator_console/gui_upstream || true)"

if [[ -z "$CHANGED" ]]; then
  echo "[subtree-guard] OK: no gui_upstream changes detected."
  exit 0
fi

echo "[subtree-guard] gui_upstream changes detected:"
echo "$CHANGED"

if git log --format=%B "$DIFF_RANGE" | rg -q 'git-subtree-dir:\s*operator_console/gui_upstream'; then
  echo "[subtree-guard] OK: subtree metadata found in commit history for this range."
  exit 0
fi

echo "[subtree-guard] ERROR: gui_upstream was modified without subtree metadata."
echo "[subtree-guard] Use subtree pull/add commands, not manual edits:"
echo "  git fetch lovable-gui"
echo "  git subtree pull --prefix operator_console/gui_upstream lovable-gui main"
exit 1
