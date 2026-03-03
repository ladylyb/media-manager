#!/usr/bin/env bash
set -euo pipefail

# Guard: keep documentation nav-driven with a tight orphan allowlist.
#
# Usage:
#   bash tools/docs/check_orphan_docs.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "[docs-orphans] Checking for orphan markdown files under documentation/..."

ALL_DOCS="$(mktemp)"
NAV_DOCS="$(mktemp)"
ALLOWED_ORPHANS="$(mktemp)"
trap 'rm -f "$ALL_DOCS" "$NAV_DOCS" "$ALLOWED_ORPHANS"' EXIT

find documentation -type f -name '*.md' -printf '%P\n' | sort -u >"$ALL_DOCS"
rg -o '[A-Za-z0-9_./-]+\.md' mkdocs.yml | sort -u >"$NAV_DOCS"

cat <<'EOF' | sort -u >"$ALLOWED_ORPHANS"
AGENT_CHECKLIST.md
LOCAL_INSTRUCTIONS.md
README.md
architecture/adr/TEMPLATE.md
EOF

ORPHANS="$(comm -23 "$ALL_DOCS" <(cat "$NAV_DOCS" "$ALLOWED_ORPHANS" | sort -u))"
if [[ -n "$ORPHANS" ]]; then
  echo "[docs-orphans] ERROR: found non-allowed orphan docs:"
  printf '%s\n' "$ORPHANS"
  exit 1
fi

echo "[docs-orphans] OK: orphan docs match allowlist."
