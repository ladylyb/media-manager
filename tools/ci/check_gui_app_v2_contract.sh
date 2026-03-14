#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible wrapper around the canonical gui_app API-client guard.
# Keep this filename while CI references are migrating.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

NEW_GUARD="tools/ci/check_gui_app_api_client_contract.sh"

if [[ ! -f "$NEW_GUARD" ]]; then
  echo "[api-contract-guard] ERROR: missing delegated guard: $NEW_GUARD"
  exit 1
fi

bash "$NEW_GUARD"
