#!/usr/bin/env bash
set -euo pipefail

# Guard: gui_app is the supported API-only runtime client, while gui_upstream is
# reference-only subtree content. Prevent coupling between the two layers and
# prevent legacy API-path assumptions from leaking back into gui_app.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

GUI_APP_ROOT="operator_console/gui_app/src"

if [[ ! -d "$GUI_APP_ROOT" ]]; then
  echo "[gui-sync-boundary] ERROR: missing gui_app source root: $GUI_APP_ROOT"
  exit 1
fi

echo "[gui-sync-boundary] Checking for gui_upstream imports inside gui_app..."
UPSTREAM_IMPORT_PATTERN='gui_upstream'
if rg -n "$UPSTREAM_IMPORT_PATTERN" "$GUI_APP_ROOT" >/dev/null; then
  echo "[gui-sync-boundary] ERROR: gui_app must not import or reference gui_upstream."
  rg -n "$UPSTREAM_IMPORT_PATTERN" "$GUI_APP_ROOT"
  exit 1
fi

echo "[gui-sync-boundary] Checking for legacy API base assumptions inside gui_app..."
LEGACY_API_PATTERN='/api/v1|/api/v2'
if rg -n "$LEGACY_API_PATTERN" "$GUI_APP_ROOT" >/dev/null; then
  echo "[gui-sync-boundary] ERROR: gui_app must target canonical /api/* routes only."
  rg -n "$LEGACY_API_PATTERN" "$GUI_APP_ROOT"
  exit 1
fi

echo "[gui-sync-boundary] OK: gui_app stays isolated from gui_upstream and legacy API paths."
