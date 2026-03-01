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

printf 'photo-a-bytes\n' > "${TEST_ROOT}/inbox/IMG_A.jpg"
printf 'photo-a-bytes\n' > "${TEST_ROOT}/inbox/IMG_A_copy.jpg"
printf 'photo-b-bytes\n' > "${TEST_ROOT}/inbox/IMG_B.jpg"
printf 'clip-c-bytes\n' > "${TEST_ROOT}/nested/VID_C.mp4"

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
media-manager ingest "${TEST_ROOT}" | tee "${LOG_DIR}/ingest.out"

echo
echo "=== Step 2: plan (strict metadata) ==="
media-manager plan "${TEST_ROOT}" --strict-metadata | tee "${LOG_DIR}/plan.out"

plan_run_id="$(
python - "${LOG_DIR}/plan.out" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"Run ID:\s*([0-9a-fA-F-]{36})", text)
if not match:
    raise SystemExit("Unable to parse run id from plan output")
print(match.group(1))
PY
)"
echo "Plan run id: ${plan_run_id}"

echo
echo "=== Step 3: apply (collision-mode rename) ==="
media-manager apply "${plan_run_id}" --collision-mode rename | tee "${LOG_DIR}/apply.out"

echo
echo "=== Step 4: canonical recompute (FIRST_SEEN dry-run) ==="
media-manager canonical recompute --policy FIRST_SEEN --dry-run | tee "${LOG_DIR}/canonical.out"

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
import re
import sys
from pathlib import Path

ingest_out = Path(sys.argv[1]).read_text(encoding="utf-8")
plan_out = Path(sys.argv[2]).read_text(encoding="utf-8")
apply_out = Path(sys.argv[3]).read_text(encoding="utf-8")
canonical_out = Path(sys.argv[4]).read_text(encoding="utf-8")
summary_path = Path(sys.argv[5])
before_count = int(sys.argv[6])
after_count = int(sys.argv[7])

def m(pattern: str, text: str, default: str = "0") -> str:
    found = re.search(pattern, text, re.MULTILINE)
    return found.group(1).strip() if found else default

ingest = {
    "files_scanned": int(m(r"Files scanned:\s+(\d+)", ingest_out)),
    "new_contents": int(m(r"New contents:\s+(\d+)", ingest_out)),
    "new_instances": int(m(r"New instances:\s+(\d+)", ingest_out)),
    "duplicates_detected": int(m(r"Duplicates detected:\s+(\d+)", ingest_out)),
    "metadata_extracted": int(m(r"Metadata extracted:\s+(\d+)", ingest_out)),
    "duration_s": float(m(r"Duration \(s\):\s+([0-9]+\.[0-9]+)", ingest_out, "0.0")),
}

plan = {
    "run_id": m(r"Run ID:\s+([0-9a-fA-F-]{36})", plan_out, ""),
    "files_scanned": int(m(r"Files scanned:\s+(\d+)", plan_out)),
    "moves": int(m(r"Moves:\s+(\d+)", plan_out)),
    "duplicates": int(m(r"Duplicates:\s+(\d+)", plan_out)),
    "noop": int(m(r"No-op:\s+(\d+)", plan_out)),
    "skipped": int(m(r"Skipped:\s+(\d+)", plan_out)),
}

apply = {
    "run_id": m(r"Run ID:\s+([0-9a-fA-F-]{36})", apply_out, ""),
    "files_applied": int(m(r"Files applied:\s+(\d+)", apply_out)),
    "moves": int(m(r"Moves:\s+(\d+)", apply_out)),
    "duplicates": int(m(r"Duplicates:\s+(\d+)", apply_out)),
    "noop": int(m(r"No-op:\s+(\d+)", apply_out)),
    "skipped": int(m(r"Skipped:\s+(\d+)", apply_out)),
    "errors": int(m(r"Errors:\s+(\d+)", apply_out)),
}

canonical = {
    "run_id": m(r"Run ID:\s+([0-9a-fA-F-]{36})", canonical_out, ""),
    "status": m(r"Status:\s+([A-Z_]+)", canonical_out, ""),
    "duplicate_contents_scanned": int(m(r"Duplicate contents scanned:\s+(\d+)", canonical_out)),
    "assignments_changed": int(m(r"Assignments changed:\s+(\d+)", canonical_out)),
    "assignments_applied": int(m(r"Assignments applied:\s+(\d+)", canonical_out)),
    "failed_contents": int(m(r"Failed contents:\s+(\d+)", canonical_out)),
    "mode": "DRY_RUN",
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
