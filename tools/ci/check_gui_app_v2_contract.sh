#!/usr/bin/env bash
set -euo pipefail

# Guard: enforce canonical /api/v2 adapter keys in gui_app API layer.
# Scope intentionally limited to integration adapter file.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ADAPTER_FILE="operator_console/gui_app/src/lib/api/endpoints.ts"

if [[ ! -f "$ADAPTER_FILE" ]]; then
  echo "[v2-contract-guard] ERROR: missing adapter file: $ADAPTER_FILE"
  exit 1
fi

echo "[v2-contract-guard] Checking disallowed request keys..."
DISALLOWED_PATTERN='\b(root_path|challenge)\s*:'
if rg -n "$DISALLOWED_PATTERN" "$ADAPTER_FILE" >/dev/null; then
  echo "[v2-contract-guard] ERROR: found non-canonical request key(s) in adapter:"
  rg -n "$DISALLOWED_PATTERN" "$ADAPTER_FILE"
  echo "[v2-contract-guard] Use canonical keys: folder_path, limit, hash_prefix, challenge_word."
  exit 1
fi

echo "[v2-contract-guard] Checking required canonical request keys..."
for key in folder_path limit hash_prefix challenge_word; do
  if ! rg -n "\\b${key}\\b" "$ADAPTER_FILE" >/dev/null; then
    echo "[v2-contract-guard] ERROR: expected canonical key missing in adapter: ${key}"
    exit 1
  fi
done

echo "[v2-contract-guard] Checking for direct /api/v2 fetches outside client..."
if rg -n '/api/v2' operator_console/gui_app/src --glob '!operator_console/gui_app/src/lib/api/client.ts' >/dev/null; then
  echo "[v2-contract-guard] ERROR: direct /api/v2 usage found outside client.ts."
  rg -n '/api/v2' operator_console/gui_app/src --glob '!operator_console/gui_app/src/lib/api/client.ts'
  exit 1
fi

echo "[v2-contract-guard] OK: gui_app v2 adapter contract checks passed."
