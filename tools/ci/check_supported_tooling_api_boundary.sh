#!/usr/bin/env bash
set -euo pipefail

# Guard: supported first-party tooling must not import Python service or persistence
# layers directly.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DISALLOWED_PATTERN='OperationServices|ReadServices|AdminServices|ApplyService|PlanningService|IngestService|RunService|OperatorConsoleReadService|create_db_engine|create_session_factory'

echo "[tooling-boundary-guard] Checking supported tooling for direct service/persistence imports..."
if rg -n "$DISALLOWED_PATTERN" tools -g '!tools/__init__.py' -g '!tools/ci/check_supported_tooling_api_boundary.sh' >/dev/null; then
  echo "[tooling-boundary-guard] ERROR: supported tooling imports service/persistence layers directly."
  rg -n "$DISALLOWED_PATTERN" tools -g '!tools/__init__.py' -g '!tools/ci/check_supported_tooling_api_boundary.sh'
  exit 1
fi

echo "[tooling-boundary-guard] OK: supported tooling stays on the API/client boundary."
