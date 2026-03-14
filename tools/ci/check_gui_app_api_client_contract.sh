#!/usr/bin/env bash
set -euo pipefail

# Guard: enforce gui_app as an API-only client integration layer.
# Scope intentionally limited to operator_console/gui_app.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ADAPTER_FILE="operator_console/gui_app/src/lib/api/endpoints.ts"
CLIENT_FILE="operator_console/gui_app/src/lib/api/client.ts"

if [[ ! -f "$ADAPTER_FILE" ]]; then
  echo "[api-client-guard] ERROR: missing adapter file: $ADAPTER_FILE"
  exit 1
fi

echo "[api-client-guard] Checking disallowed request keys..."
DISALLOWED_PATTERN='\b(root_path|challenge)\s*:'
if rg -n "$DISALLOWED_PATTERN" "$ADAPTER_FILE" >/dev/null; then
  echo "[api-client-guard] ERROR: found non-canonical request key(s) in adapter:"
  rg -n "$DISALLOWED_PATTERN" "$ADAPTER_FILE"
  echo "[api-client-guard] Use canonical keys such as folder_path and challenge_word."
  exit 1
fi

echo "[api-client-guard] Checking required canonical request keys..."
for key in folder_path hash_prefix challenge_word; do
  if ! rg -n "\\b${key}\\b" "$ADAPTER_FILE" >/dev/null; then
    echo "[api-client-guard] ERROR: expected canonical key missing in adapter: ${key}"
    exit 1
  fi
done

echo "[api-client-guard] Checking for direct HTTP calls outside client..."
DIRECT_HTTP_PATTERN='fetch\s*\(|axios|XMLHttpRequest'
if rg -n "$DIRECT_HTTP_PATTERN" operator_console/gui_app/src --glob "!${CLIENT_FILE}" >/dev/null; then
  echo "[api-client-guard] ERROR: direct HTTP call found outside client.ts."
  rg -n "$DIRECT_HTTP_PATTERN" operator_console/gui_app/src --glob "!${CLIENT_FILE}"
  exit 1
fi

echo "[api-client-guard] OK: gui_app is using the shared API client only."
