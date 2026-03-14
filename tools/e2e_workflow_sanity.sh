#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C
export TZ=UTC

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="/tmp/test_media"
LOG_DIR="/tmp/media_manager_e2e_logs"

mkdir -p "${LOG_DIR}"
rm -rf "${TEST_ROOT}"
mkdir -p "${TEST_ROOT}/inbox" "${TEST_ROOT}/nested"

if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.venv/bin/activate"
fi

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set. Populate ${PROJECT_ROOT}/.env or export it before running." >&2
  exit 2
fi

export MEDIA_REQUIRED_CODES="OWNER,CONTEXT,TAKEN_DT"
export PYTHONPATH="${PROJECT_ROOT}"
export MEDIA_MANAGER_API_HOST="127.0.0.1"
export MEDIA_MANAGER_API_PORT="8010"
API_BASE="http://${MEDIA_MANAGER_API_HOST}:${MEDIA_MANAGER_API_PORT}"

server_pid=""

cleanup() {
  if [[ -n "${server_pid}" ]] && kill -0 "${server_pid}" 2>/dev/null; then
    kill "${server_pid}" 2>/dev/null || true
    wait "${server_pid}" 2>/dev/null || true
  fi
}

trap cleanup EXIT

printf 'photo-a-bytes\n' > "${TEST_ROOT}/inbox/IMG_A.jpg"
printf 'photo-a-bytes\n' > "${TEST_ROOT}/inbox/IMG_A_copy.jpg"
printf 'photo-b-bytes\n' > "${TEST_ROOT}/inbox/IMG_B.jpg"
printf 'clip-c-bytes\n' > "${TEST_ROOT}/nested/VID_C.mp4"

media-manager-api > "${LOG_DIR}/api.out" 2>&1 &
server_pid=$!

for _ in $(seq 1 30); do
  if curl -fsS "${API_BASE}/api/status" > /dev/null; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${API_BASE}/api/status" > /dev/null; then
  echo "API server did not become ready at ${API_BASE}" >&2
  exit 2
fi

echo "=== Test dataset (deterministic order) ==="
find "${TEST_ROOT}" -type f | sort
echo

canonical_assignments_before_dry_run="$(
python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"], future=True)
with engine.connect() as conn:
    value = conn.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one()
print(int(value))
PY
)"

echo "=== Step 1: ingest ==="
curl -fsS -X POST "${API_BASE}/api/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"folder_path\":\"${TEST_ROOT}\",\"dry_run\":false}" | tee "${LOG_DIR}/ingest.out"

echo
echo "=== Step 2: plan (strict metadata) ==="
curl -fsS -X POST "${API_BASE}/api/plan" \
  -H 'Content-Type: application/json' \
  -d "{\"folder_path\":\"${TEST_ROOT}\",\"strict_metadata\":true}" | tee "${LOG_DIR}/plan.out"

plan_run_id="$(
python - "${LOG_DIR}/plan.out" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
run_id = payload.get("data", {}).get("result", {}).get("run_id")
if not run_id:
    raise SystemExit("Unable to parse run id from plan response")
print(run_id)
PY
)"
echo "Plan run id: ${plan_run_id}"

echo
echo "=== Step 3: apply (collision-mode rename) ==="
curl -fsS -X POST "${API_BASE}/api/apply" \
  -H 'Content-Type: application/json' \
  -d "{\"run_id\":\"${plan_run_id}\",\"collision_mode\":\"rename\"}" | tee "${LOG_DIR}/apply.out"

echo
echo "=== Step 4: canonical recompute (FIRST_SEEN dry-run) ==="
curl -fsS -X POST "${API_BASE}/api/canonical/recompute" \
  -H 'Content-Type: application/json' \
  -d '{"policy_name":"FIRST_SEEN","dry_run":true,"preferred_roots":[]}' | tee "${LOG_DIR}/canonical.out"

canonical_assignments_after_dry_run="$(
python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"], future=True)
with engine.connect() as conn:
    value = conn.execute(text("SELECT COUNT(*) FROM canonical_assignments")).scalar_one()
print(int(value))
PY
)"

python - "${LOG_DIR}/ingest.out" "${LOG_DIR}/plan.out" "${LOG_DIR}/apply.out" "${LOG_DIR}/canonical.out" \
  "${LOG_DIR}/summary.json" "${canonical_assignments_before_dry_run}" "${canonical_assignments_after_dry_run}" <<'PY'
import json
import sys
from pathlib import Path

ingest_payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
plan_payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
apply_payload = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
canonical_payload = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
summary_path = Path(sys.argv[5])
before_count = int(sys.argv[6])
after_count = int(sys.argv[7])

ingest_result = ingest_payload["data"]["result"]
plan_result = plan_payload["data"]["result"]
apply_result = apply_payload["data"]["result"]
canonical_result = canonical_payload["data"]["result"]
ingest_summary = ingest_result["summary"]
plan_summary = plan_result["summary"]
apply_summary = apply_result["summary"]
canonical_summary = canonical_result["summary"]

ingest = dict(ingest_summary)
plan = {
    "run_id": plan_result["run_id"],
    "files_scanned": int(plan_summary["scanned_count"]),
    "moves": int(plan_summary["move_actions"]),
    "duplicates": int(plan_summary["duplicate_actions"]),
    "noop": int(plan_summary["noop_actions"]),
    "skipped": int(plan_summary["skipped_count"]),
}

apply = {
    "run_id": apply_result["run_id"],
    "files_applied": int(apply_summary["applied_count"]),
    "moves": int(apply_summary["moves_count"]),
    "duplicates": int(apply_summary["duplicates_count"]),
    "noop": int(apply_summary["noop_count"]),
    "skipped": int(apply_summary["skipped_count"]),
    "errors": int(apply_summary["errors_count"]),
}

canonical = {
    "run_id": canonical_summary["run_id"],
    "status": canonical_summary["status"],
    "duplicate_contents_scanned": int(canonical_summary["scanned_count"]),
    "assignments_changed": int(canonical_summary["changed_count"]),
    "assignments_applied": int(canonical_summary["applied_count"]),
    "failed_contents": int(canonical_summary["failed_count"]),
    "mode": canonical_result["mode"],
}

dry_run_validation = {
    "canonical_assignments_before": before_count,
    "canonical_assignments_after": after_count,
    "no_new_canonical_assignments": before_count == after_count,
    "dry_run_assignments_applied_zero": canonical["assignments_applied"] == 0,
}

summary = {
    "ingest": ingest,
    "plan": plan,
    "apply": apply,
    "canonical_recompute_dry_run": canonical,
    "dry_run_validation": dry_run_validation,
}

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))

if not dry_run_validation["no_new_canonical_assignments"]:
    raise SystemExit("Validation failed: dry-run changed canonical_assignments row count")
if not dry_run_validation["dry_run_assignments_applied_zero"]:
    raise SystemExit("Validation failed: dry-run reported non-zero assignments_applied")
PY

echo
echo "=== Final report ==="
cat "${LOG_DIR}/summary.json"
echo
echo "Artifacts:"
echo "  ingest output:    ${LOG_DIR}/ingest.out"
echo "  plan output:      ${LOG_DIR}/plan.out"
echo "  apply output:     ${LOG_DIR}/apply.out"
echo "  canonical output: ${LOG_DIR}/canonical.out"
echo "  summary json:     ${LOG_DIR}/summary.json"
