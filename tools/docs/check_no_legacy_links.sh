#!/usr/bin/env bash
set -euo pipefail

# Guard: keep legacy docs out of published MkDocs navigation and links.
#
# Usage:
#   bash tools/docs/check_no_legacy_links.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[docs-guard] Checking mkdocs navigation for legacy/archive entries..."
if rg -n '^\s*-\s*Archive\s*:' mkdocs.yml >/dev/null; then
  echo "[docs-guard] ERROR: 'Archive' nav section is not allowed in mkdocs.yml"
  exit 1
fi

if rg -n 'archive/(index|project-history|legacy-implementation|retention-policy)\.md' mkdocs.yml >/dev/null; then
  echo "[docs-guard] ERROR: legacy archive pages must not appear in mkdocs.yml nav"
  exit 1
fi

echo "[docs-guard] Checking published docs for forbidden legacy links..."
FORBIDDEN_LINK_PATTERN='\[[^]]+\]\([^)]*(archive/legacy/docs|documentation/archive|archive/index\.md|archive/project-history\.md|archive/legacy-implementation\.md|archive/retention-policy\.md)[^)]*\)'
if rg -n "$FORBIDDEN_LINK_PATTERN" documentation >/dev/null; then
  echo "[docs-guard] ERROR: found forbidden legacy link targets in documentation/"
  rg -n "$FORBIDDEN_LINK_PATTERN" documentation
  exit 1
fi

TARGET_BRANCH="${GITHUB_BASE_REF:-$(git rev-parse --abbrev-ref HEAD)}"
if [[ "$TARGET_BRANCH" == "develop" ]] && find documentation/project -type f -name '*.md' 2>/dev/null | rg -q .; then
  echo "[docs-guard] ERROR: documentation/project/** must not exist on develop-targeted changes"
  find documentation/project -type f -name '*.md' 2>/dev/null
  exit 1
fi

echo "[docs-guard] OK: no legacy/archive nav entries or published links found."
