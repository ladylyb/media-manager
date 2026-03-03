from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from sqlalchemy import select, text

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.factory import build_canonical_policy
from media_manager.app.core import perf_cli
from media_manager.app.core.errors import MediaManagerError
from media_manager.app.persistence.apply import ApplyService
from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.canonicalization import RecomputeMode, recompute_canonical_assignments
from media_manager.app.persistence.decision_intelligence import (
    explain_file_from_latest_trace,
    load_latest_decision_trace,
    simulate_policy_delta,
    write_simulation_delta_artifact,
)
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.legacy_import import LegacyImportService
from media_manager.app.persistence.materialized_reads import (
    benchmark_planner_lookup,
    fetch_canonical_metadata,
    refresh_materialized_view,
)
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.persistence.operator_run_trigger import OperatorRunTriggerService, RunTriggerCommand
from media_manager.app.persistence.policy_settings import PolicySettingsService, UpdatePolicySettingsCommand
from media_manager.app.persistence.models import MediaFileStatus, PlannedAction
from media_manager.app.persistence.models import TagSource
from media_manager.app.observability import generate_metrics_text, start_metrics_http_server_if_enabled
from media_manager.app.persistence.planner import PlanningService
from media_manager.app.persistence.runs import RunService
from media_manager.app.persistence.tag_enrichment import (
    EnrichmentScope,
    TagEnrichmentCommand,
    run_tag_enrichment,
)
from media_manager.app.service_layer import (
    OperationServices,
    ReadServices,
    ServiceCache,
    WORKFLOW_VERSION as SERVICE_WORKFLOW_VERSION,
    schema_version as service_schema_version,
)

WORKFLOW_VERSION = SERVICE_WORKFLOW_VERSION


def _path_sort_key(path: Path) -> str:
    return path.resolve(strict=False).as_posix()


def _collect_input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return sorted(files, key=_path_sort_key)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _schema_version(session_factory) -> str:
    return service_schema_version(session_factory)


def _build_service_adapters():
    """Create per-command service-layer adapters with isolated session scope."""
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    cache = ServiceCache()
    return session_factory, ReadServices(session_factory=session_factory, cache=cache), OperationServices(session_factory=session_factory, cache=cache)


def _json_payload(
    *,
    session_factory,
    ok: bool,
    data: dict[str, object] | None = None,
    errors: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "ok": ok,
        "workflow_version": WORKFLOW_VERSION,
        "schema_version": _schema_version(session_factory),
        "generated_at": _iso_now(),
        "data": data or {},
        "errors": errors or [],
    }


def _print_json_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_plan_output(run_id: uuid.UUID, planned_actions: list[PlannedAction], summary) -> None:
    grouped: dict[str, list[PlannedAction]] = {"MOVE": [], "MARK_DUPLICATE": [], "NOOP": []}
    for action in planned_actions:
        if action.action_type in {"MOVE", "RENAME"}:
            grouped["MOVE"].append(action)
        elif action.action_type in {"MARK_DUPLICATE", "COLLISION_RESOLVED"}:
            grouped["MARK_DUPLICATE"].append(action)
        elif action.action_type in {"NOOP", "SKIP"}:
            grouped["NOOP"].append(action)

    section_order = [("MOVE", "MOVE"), ("MARK_DUPLICATE", "DUPLICATE"), ("NOOP", "NOOP")]
    first_section = True
    for action_type, label in section_order:
        entries = grouped[action_type]
        if not entries:
            continue
        if not first_section:
            print()
        first_section = False
        print(label)
        for action in entries:
            print(f"  {action.source_path}")
            if action.action_type not in {"NOOP", "SKIP"} and action.target_path:
                print(f"    → {action.target_path}")

    print()
    print("----------------------------------------")
    print("Summary")
    print(f"  Files scanned: {summary.scanned_count}")
    print(f"  Moves: {summary.move_actions}")
    print(f"  Duplicates: {summary.duplicate_actions}")
    print(f"  No-op: {summary.noop_actions}")
    print(f"  Skipped: {summary.skipped_count}")
    print("----------------------------------------")
    print(f"Run ID: {run_id}")


def _render_apply_output(run_id: uuid.UUID, planned_actions: list[PlannedAction], summary) -> None:
    grouped: dict[str, list[PlannedAction]] = {"MOVE": [], "MARK_DUPLICATE": [], "NOOP": []}
    for action in planned_actions:
        if action.action_type in {"MOVE", "RENAME"}:
            grouped["MOVE"].append(action)
        elif action.action_type in {"MARK_DUPLICATE", "COLLISION_RESOLVED"}:
            grouped["MARK_DUPLICATE"].append(action)
        elif action.action_type in {"NOOP", "SKIP"}:
            grouped["NOOP"].append(action)

    section_order = [("MOVE", "MOVE"), ("MARK_DUPLICATE", "DUPLICATE"), ("NOOP", "NOOP")]
    first_section = True
    for action_type, label in section_order:
        entries = grouped[action_type]
        if not entries:
            continue
        if not first_section:
            print()
        first_section = False
        print(label)
        for action in entries:
            print(f"  {action.source_path}")
            if action.action_type not in {"NOOP", "SKIP"} and action.target_path:
                print(f"    → {action.target_path}")

    print()
    print("----------------------------------------")
    print("Summary")
    print(f"  Files applied: {summary.applied_count}")
    print(f"  Moves: {summary.moves_count}")
    print(f"  Duplicates: {summary.duplicates_count}")
    print(f"  No-op: {summary.noop_count}")
    print(f"  Skipped: {summary.skipped_count}")
    print(f"  Errors: {summary.errors_count}")
    print("----------------------------------------")
    print(f"Run ID: {run_id}")


def _render_ingest_output(summary) -> None:
    print("----------------------------------------")
    print("Ingest Summary")
    print(f"  Files scanned: {summary.files_scanned}")
    print(f"  New contents: {summary.new_contents}")
    print(f"  New instances: {summary.new_instances}")
    print(f"  Duplicates detected: {summary.duplicates_detected}")
    print(f"  Metadata extracted: {summary.metadata_extracted}")
    print(f"  Duration (s): {summary.duration_s:.3f}")
    print("----------------------------------------")


def _render_ingest_validation_output(report, *, as_json: bool) -> None:
    payload = report.to_dict()
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    scan = payload["scan"]
    delta = payload["delta"]
    print("----------------------------------------")
    print("Ingest Validation (Dry Run)")
    print(f"  Root path: {payload['root_path']}")
    print(f"  Files scanned: {scan['files_scanned']}")
    print(f"  Files missing during scan: {scan['files_missing_during_scan']}")
    print("  Delta:")
    print(f"    Would insert: {delta['would_insert']}")
    print(f"    Would update: {delta['would_update']}")
    print(f"    Would mark deleted: {delta['would_mark_deleted']}")
    print(f"    Hash mismatches observed: {delta['hash_mismatch_observed']}")
    print(f"    Reappearances after deleted: {delta['would_reappear_after_delete']}")
    warnings = payload.get("warnings") or []
    if warnings:
        print("  Warnings:")
        for warning in warnings:
            print(f"    - {warning}")
    print("----------------------------------------")


def _render_canonical_recompute_output(summary) -> None:
    print("----------------------------------------")
    print("Canonical Recompute Summary")
    print(f"  Run ID: {summary.run_id}")
    print(f"  Status: {summary.status}")
    print(f"  Duplicate contents scanned: {summary.scanned_count}")
    print(f"  Assignments changed: {summary.changed_count}")
    print(f"  Assignments applied: {summary.applied_count}")
    print(f"  Failed contents: {summary.failed_count}")
    if summary.changed_content_ids:
        print("  Changed content IDs:")
        for content_id in summary.changed_content_ids:
            print(f"    {content_id}")
    if summary.failed_content_ids:
        print("  Failed content IDs:")
        for content_id in summary.failed_content_ids:
            print(f"    {content_id}")
    print("----------------------------------------")


def _render_policy_simulation_output(delta, artifact_path: Path) -> None:
    print("----------------------------------------")
    print("Policy Simulation Summary")
    print(f"  Run ID: {delta.run_id}")
    print(f"  Policy: {delta.policy_name} ({delta.policy_version})")
    print(f"  Canonical Changes: {delta.canonical_changes_count}")
    print(f"  Merges: {delta.merges_count}")
    print(f"  Demotions: {delta.demotions_count}")
    print(f"  Impacted Content IDs: {len(delta.impacted_content_ids)}")
    print(f"  Artifact: {artifact_path}")
    print("----------------------------------------")


def _render_file_explanation(payload: dict[str, object]) -> None:
    print("----------------------------------------")
    print("File Decision Explanation")
    print(f"  Run ID: {payload.get('run_id')}")
    print(f"  Content ID: {payload.get('content_id')}")
    print(f"  File ID: {payload.get('file_id')}")
    print(f"  Is Canonical: {payload.get('is_canonical')}")
    print(f"  Canonical Instance: {payload.get('canonical_instance_id')}")
    print(f"  Decision Reason: {payload.get('decision_reason')}")
    print(f"  Tie Breaker: {payload.get('tie_breaker_used')}")
    print("  Rules:")
    for rule in payload.get("applied_policy_rules", []):
        print(f"    - {rule}")
    print("  Candidates:")
    canonical_id = str(payload.get("canonical_instance_id"))
    file_id = str(payload.get("file_id"))
    for candidate in payload.get("candidate_instance_ids", []):
        marker = ""
        if str(candidate) == canonical_id:
            marker = " (canonical)"
        if str(candidate) == file_id and marker:
            marker += " [queried]"
        elif str(candidate) == file_id:
            marker = " [queried]"
        print(f"    - {candidate}{marker}")
    print("----------------------------------------")


def _render_legacy_import_output(summary) -> None:
    print("----------------------------------------")
    print("Legacy Import Summary")
    print(f"  Import run ID: {summary.import_run_id}")
    print(f"  State: {summary.state}")
    if summary.raw_counts:
        print("  Raw row counts:")
        for table_name in sorted(summary.raw_counts):
            print(f"    {table_name}: {summary.raw_counts[table_name]}")
    print(f"  Verification failures: {len(summary.verification_failures)}")
    print("----------------------------------------")


def _render_mv_refresh_output(summary) -> None:
    print("----------------------------------------")
    print("Materialized View Refresh Summary")
    print("  View: mv_canonical_metadata")
    print(f"  Mode: {'CONCURRENTLY' if summary.concurrently else 'STANDARD'}")
    print(f"  Scheduled flag: {summary.scheduled}")
    if summary.schedule_label:
        print(f"  Schedule label: {summary.schedule_label}")
    print("----------------------------------------")


def _render_planner_benchmark_output(summary) -> None:
    print("----------------------------------------")
    print("Planner Benchmark")
    print(f"Base mean: {summary.base_mean_ms:.3f} ms")
    print(f"MV mean: {summary.mv_mean_ms:.3f} ms")
    print(f"StdDev: {summary.stddev_ms:.3f} ms")
    print(f"Improvement: {summary.improvement_pct:.2f}%")
    print("----------------------------------------")


def _extract_metric_lines_for_run_id(run_id: str) -> list[str]:
    metric_names = (
        "canonical_read_cache_hits_total",
        "canonical_read_cache_misses_total",
        "canonical_read_cache_hit_ratio_percent",
    )
    payload = generate_metrics_text().decode("utf-8", errors="ignore")
    lines: list[str] = []
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        if not any(line.startswith(metric_name) for metric_name in metric_names):
            continue
        if f'run_id="{run_id}"' not in line:
            continue
        lines.append(line)
    return sorted(lines)


def _render_observability_quick_check_output(
    *,
    run_id: str,
    sample_size: int,
    base_rows: int,
    mv_rows: int,
    metric_lines: list[str],
    complete: bool,
) -> None:
    print("----------------------------------------")
    print("Observability Quick Check")
    print(f"  Run ID: {run_id}")
    print(f"  Sample size: {sample_size}")
    print(f"  Base rows read: {base_rows}")
    print(f"  MV rows read: {mv_rows}")
    print(f"  Metrics complete: {complete}")
    print("----------------------------------------")
    print("Matching metric lines:")
    for line in metric_lines:
        print(f"  {line}")
    print("----------------------------------------")


def _render_tag_enrichment_output(summary) -> None:
    def _value(name: str):
        if isinstance(summary, dict):
            return summary.get(name)
        return getattr(summary, name)

    print("----------------------------------------")
    print("Tag Enrichment Summary")
    print(f"  Run ID: {_value('run_id')}")
    print(f"  Scope: {_value('scope')}")
    print(f"  Status: {_value('status')}")
    print(f"  Items processed: {_value('number_of_items_processed')}")
    print(f"  Failed items: {_value('failed_items')}")
    avg = _value("average_confidence")
    print(f"  Average confidence: {avg if avg is not None else 'n/a'}")
    print(f"  Duration (ms): {_value('duration_ms')}")
    timestamp = _value("timestamp")
    if hasattr(timestamp, "isoformat"):
        timestamp = timestamp.isoformat()
    print(f"  Timestamp: {timestamp}")
    print("----------------------------------------")


def _render_hash_audit_output(payload: dict[str, object]) -> None:
    print("----------------------------------------")


def _http_call_json(
    *,
    method: str,
    api_base: str,
    path: str,
    timeout: int,
    query: dict[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    normalized_api = (api_base or "").strip().rstrip("/")
    if not normalized_api:
        raise ValueError("--api must not be empty when --transport http is used.")
    if timeout <= 0:
        raise ValueError("--timeout must be > 0.")
    url = f"{normalized_api}{path}"
    if query:
        url = f"{url}?{urllib_parse.urlencode(query)}"
    payload_bytes: bytes | None = None
    headers = {"Accept": "application/json"}
    if body is not None:
        payload_bytes = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib_request.Request(url, data=payload_bytes, headers=headers, method=method.upper())
    with urllib_request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("HTTP response payload must be a JSON object.")
        return int(response.status), data
    print("Ledger Hash Audit")
    print(f"  Total files: {payload.get('total_files', 0)}")
    print(f"  Missing hash: {payload.get('missing_hash', 0)}")
    print(f"  Hash mismatches: {payload.get('hash_mismatches', 0)}")
    print(f"  Deleted rows skipped: {payload.get('deleted_rows_skipped', 0)}")
    missing_samples = payload.get("sample_missing_hash_paths") or []
    mismatch_samples = payload.get("sample_mismatch_paths") or []
    if missing_samples:
        print("  Sample missing-hash paths:")
        for value in missing_samples:
            print(f"    - {value}")
    if mismatch_samples:
        print("  Sample mismatch paths:")
        for value in mismatch_samples:
            print(f"    - {value}")
    print("----------------------------------------")


def _tag_enrich_command(
    *,
    run_all: bool,
    canonical_id: str | None,
    batch_size: int,
    source: str,
    transport: str,
    api_base: str,
    timeout: int,
    as_json: bool = False,
) -> int:
    if run_all == (canonical_id is not None):
        print("Specify exactly one of --all or --canonical-id.", file=sys.stderr)
        return 2
    if batch_size <= 0:
        print("--batch-size must be > 0.", file=sys.stderr)
        return 2
    try:
        source_value = TagSource(source).value
    except Exception:
        print(f"Invalid --source value: {source}", file=sys.stderr)
        return 2

    target_id: uuid.UUID | None = None
    if canonical_id is not None:
        try:
            target_id = uuid.UUID(canonical_id)
        except ValueError:
            print(f"Invalid --canonical-id UUID: {canonical_id}", file=sys.stderr)
            return 2

    if transport == "http":
        payload: dict[str, object] = {"all": run_all, "batch_size": batch_size, "source": source_value}
        if canonical_id is not None:
            payload["canonical_id"] = canonical_id
        try:
            status_code, response_payload = _http_call_json(
                method="POST",
                api_base=api_base,
                path="/api/v2/tag-enrichment",
                timeout=timeout,
                body=payload,
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            _render_tag_enrichment_output((response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else response_payload)  # type: ignore[arg-type]
        return 0 if status_code == 200 else 1

    session_factory, _, operations = _build_service_adapters()
    try:
        summary = operations.tag_enrichment(
            run_all=run_all,
            canonical_id=str(target_id) if target_id is not None else None,
            batch_size=batch_size,
            source=source_value,
        )
    except MediaManagerError as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "TAG_ENRICH_ERROR", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "TAG_ENRICH_ERROR", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={"result": summary},
            )
        )
    else:
        _render_tag_enrichment_output(summary)
    return 0


def _health_check_command(
    *,
    audit_hashes: bool,
    root: str | None,
    api: str,
    timeout: int,
    sample_limit: int,
) -> int:
    if not audit_hashes:
        print("Specify --audit-hashes for health-check command.", file=sys.stderr)
        return 2
    normalized_api = (api or "").strip().rstrip("/")
    if not normalized_api:
        print("--api must not be empty.", file=sys.stderr)
        return 2
    if timeout <= 0:
        print("--timeout must be > 0.", file=sys.stderr)
        return 2
    if sample_limit < 1 or sample_limit > 200:
        print("--sample-limit must be within [1, 200].", file=sys.stderr)
        return 2

    query: dict[str, str] = {"sample_limit": str(sample_limit)}
    if root is not None and root.strip():
        query["root_path"] = root.strip()
    endpoint = f"{normalized_api}/api/v1/ledger/hash-audit?{urllib_parse.urlencode(query)}"
    request = urllib_request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                print(f"Health-check API returned status {response.status}.", file=sys.stderr)
                return 2
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError) as exc:
        print(f"Health-check API request failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unable to parse health-check response: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("Health-check API returned invalid payload shape.", file=sys.stderr)
        return 2
    _render_hash_audit_output(payload)

    missing_hash = int(payload.get("missing_hash") or 0)
    hash_mismatches = int(payload.get("hash_mismatches") or 0)
    if missing_hash > 0 or hash_mismatches > 0:
        return 1
    return 0


def _status_command(*, as_json: bool, transport: str, api_base: str, timeout: int) -> int:
    if transport == "http":
        try:
            _, payload = _http_call_json(
                method="GET",
                api_base=api_base,
                path="/api/v2/status",
                timeout=timeout,
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            print("Status")
            print(f"  Active phase: {data.get('active_phase', '--')}")
        return 0 if payload.get("ok") else 1

    session_factory, read_service, _ = _build_service_adapters()
    try:
        data = read_service.status()
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "STATUS_READ_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if as_json:
        payload = _json_payload(
            session_factory=session_factory,
            ok=True,
            data=data,
        )
        _print_json_payload(payload)
        return 0
    print("Status")
    print(f"  Active phase: {data.get('active_phase', 'phase13')}")
    phase_status = data.get("phase_status")
    summary = (
        phase_status[0].get("details", {}).get("dashboard_summary", {})
        if isinstance(phase_status, list) and phase_status
        else {}
    )
    print(f"  Total files: {summary.get('total_files', 0)}")
    return 0


def _operator_read_command(
    *,
    resource: str,
    as_json: bool,
    limit: int,
    page: int,
    tags: str | None,
    sort_by: str,
    sort_order: str | None,
    source: str | None,
    min_confidence: float | None,
    q: str | None,
    hash_prefix: str | None,
    path: str | None,
    status: str | None,
    root_path: str | None,
    sample_limit: int,
    start: str | None,
    end: str | None,
    transport: str,
    api_base: str,
    timeout: int,
) -> int:
    if transport == "http":
        try:
            if resource == "dashboard-summary":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/dashboard-summary", timeout=timeout)
            elif resource == "latest-metrics":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/latest-metrics", timeout=timeout)
            elif resource == "runs":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/runs", timeout=timeout, query={"limit": str(limit)})
            elif resource == "duplicates":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/duplicates", timeout=timeout)
            elif resource == "canonical":
                query = {"page": str(page), "limit": str(limit), "sort_by": sort_by}
                if sort_order:
                    query["sort_order"] = sort_order
                if tags:
                    query["tags"] = tags
                if source:
                    query["source"] = source
                if min_confidence is not None:
                    query["min_confidence"] = str(min_confidence)
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/canonical", timeout=timeout, query=query)
            elif resource == "canonical-tags":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/canonical/tags", timeout=timeout, query={"q": q or "", "limit": str(limit)})
            elif resource == "media-file-by-hash":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/by-hash", timeout=timeout, query={"hash_prefix": hash_prefix or "", "page": str(page), "limit": str(limit)})
            elif resource == "media-file-history":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/history", timeout=timeout, query={"path": path or "", "page": str(page), "limit": str(limit)})
            elif resource == "media-file-by-status":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/by-status", timeout=timeout, query={"status": status or "", "page": str(page), "limit": str(limit)})
            elif resource == "media-file-reappearances":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/reappearances", timeout=timeout, query={"path": path or "", "page": str(page), "limit": str(limit)})
            elif resource == "media-file-analytics":
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/analytics", timeout=timeout)
            elif resource == "ledger-hash-audit":
                query = {"sample_limit": str(sample_limit)}
                if root_path:
                    query["root_path"] = root_path
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/ledger/hash-audit", timeout=timeout, query=query)
            elif resource == "media-file-dry-run-audit":
                query = {"limit": str(limit)}
                if start:
                    query["start"] = start
                if end:
                    query["end"] = end
                _, response_payload = _http_call_json(method="GET", api_base=api_base, path="/api/v2/media-file/dry-run-audit", timeout=timeout, query=query)
            else:
                raise ValueError(f"Unsupported resource: {resource}")
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            result = (response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else {}
            print(json.dumps({"resource": resource, "result": result}, indent=2, sort_keys=True))
        return 0 if response_payload.get("ok") else 1

    session_factory, read_service, _ = _build_service_adapters()
    try:
        if resource == "dashboard-summary":
            result: object = read_service.dashboard_summary()
        elif resource == "latest-metrics":
            result = read_service.latest_metrics()
        elif resource == "runs":
            result = read_service.runs(limit=limit)
        elif resource == "duplicates":
            result = read_service.duplicates()
        elif resource == "canonical":
            tags_tuple = tuple(part.strip() for part in (tags or "").split(",") if part.strip())
            result = read_service.canonical(
                page=max(1, page),
                limit=min(100, max(1, limit)),
                tags=tags_tuple,
                sort_by=sort_by.strip().lower(),
                sort_order=sort_order.strip().lower() if sort_order else None,
                source=source.strip().lower() if source else None,
                min_confidence=min_confidence,
            )
        elif resource == "canonical-tags":
            result = read_service.canonical_tags(q=q, limit=limit)
        elif resource == "media-file-by-hash":
            result = read_service.media_file_by_hash(
                hash_prefix=(hash_prefix or "").strip(),
                page=max(1, page),
                limit=min(100, max(1, limit)),
            )
        elif resource == "media-file-history":
            result = read_service.media_file_history(
                path=(path or "").strip(),
                page=max(1, page),
                limit=min(100, max(1, limit)),
            )
        elif resource == "media-file-by-status":
            result = read_service.media_file_by_status(
                status=(status or "").strip(),
                page=max(1, page),
                limit=min(100, max(1, limit)),
            )
        elif resource == "media-file-reappearances":
            result = read_service.media_file_reappearances(
                path=(path or "").strip(),
                page=max(1, page),
                limit=min(100, max(1, limit)),
            )
        elif resource == "media-file-analytics":
            result = read_service.media_file_analytics()
        elif resource == "ledger-hash-audit":
            result = read_service.ledger_hash_audit(
                root_path=(root_path.strip() if root_path else None),
                sample_limit=sample_limit,
            )
        elif resource == "media-file-dry-run-audit":
            result = read_service.media_file_dry_run_audit(
                start=start,
                end=end,
                limit=limit,
            )
        else:
            raise ValueError(f"Unsupported resource: {resource}")
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "OPERATOR_READ_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={"resource": resource, "result": result},
            )
        )
    else:
        print(json.dumps({"resource": resource, "result": result}, indent=2, sort_keys=True))
    return 0


def _operator_run_command(
    *,
    folder_path: str,
    policy_name: str,
    dry_run: bool,
    as_json: bool,
    transport: str,
    api_base: str,
    timeout: int,
) -> int:
    if transport == "http":
        try:
            _, response_payload = _http_call_json(
                method="POST",
                api_base=api_base,
                path="/api/v2/run",
                timeout=timeout,
                body={"folder_path": folder_path, "policy_name": policy_name, "dry_run": dry_run},
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            result = (response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else {}
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if response_payload.get("ok") else 1

    session_factory, _, operations = _build_service_adapters()
    try:
        result = operations.run(folder_path=folder_path, policy_name=policy_name, dry_run=dry_run)
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "RUN_TRIGGER_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if as_json:
        _print_json_payload(
            _json_payload(session_factory=session_factory, ok=True, data={"result": result})
        )
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _policy_get_command(*, as_json: bool, transport: str, api_base: str, timeout: int) -> int:
    if transport == "http":
        try:
            _, response_payload = _http_call_json(
                method="GET",
                api_base=api_base,
                path="/api/v2/policy",
                timeout=timeout,
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            result = (response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else {}
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if response_payload.get("ok") else 1

    session_factory, _, operations = _build_service_adapters()
    try:
        result = operations.policy_get()
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "POLICY_GET_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if as_json:
        _print_json_payload(_json_payload(session_factory=session_factory, ok=True, data={"result": result}))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _policy_set_command(
    *,
    selected_policy: str,
    preferred_roots: list[str],
    recanonicalization_enabled: bool,
    version: int,
    as_json: bool,
    transport: str,
    api_base: str,
    timeout: int,
) -> int:
    if transport == "http":
        try:
            _, response_payload = _http_call_json(
                method="POST",
                api_base=api_base,
                path="/api/v2/policy",
                timeout=timeout,
                body={
                    "selected_policy": selected_policy,
                    "preferred_roots": preferred_roots,
                    "recanonicalization_enabled": recanonicalization_enabled,
                    "version": version,
                },
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            result = (response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else {}
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if response_payload.get("ok") else 1

    session_factory, _, operations = _build_service_adapters()
    try:
        result = operations.policy_set(
            selected_policy=selected_policy,
            preferred_roots=tuple(preferred_roots),
            recanonicalization_enabled=recanonicalization_enabled,
            version=version,
        )
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "POLICY_SET_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if as_json:
        _print_json_payload(_json_payload(session_factory=session_factory, ok=True, data={"result": result}))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _observability_quick_check_command(*, run_id: str | None, sample_size: int, as_json: bool = False) -> int:
    normalized_sample_size = max(int(sample_size), 1)
    normalized_run_id = str(run_id).strip() if run_id is not None else ""
    if not normalized_run_id:
        normalized_run_id = f"obs-quickcheck-{uuid.uuid4()}"

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            base_rows = fetch_canonical_metadata(
                session,
                use_mv=False,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            # Trigger one hit per source so all cache metric families are visible.
            fetch_canonical_metadata(
                session,
                use_mv=False,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            fetch_canonical_metadata(
                session,
                use_mv=True,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
            mv_rows = fetch_canonical_metadata(
                session,
                use_mv=True,
                sample_size=normalized_sample_size,
                use_cache=True,
                metrics_run_id=normalized_run_id,
            )
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "OBSERVABILITY_QUICK_CHECK_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    metric_lines = _extract_metric_lines_for_run_id(normalized_run_id)
    expected_tokens = tuple(
        f'{metric_name}{{run_id="{normalized_run_id}",source="{source}"'
        for metric_name in (
            "canonical_read_cache_hits_total",
            "canonical_read_cache_misses_total",
            "canonical_read_cache_hit_ratio_percent",
        )
        for source in ("base", "mv")
    )
    complete = all(any(token in line for line in metric_lines) for token in expected_tokens)
    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=bool(complete),
                data={
                    "result": {
                        "run_id": normalized_run_id,
                        "sample_size": normalized_sample_size,
                        "base_rows": len(base_rows),
                        "mv_rows": len(mv_rows),
                        "metric_lines": metric_lines,
                        "complete": bool(complete),
                    }
                },
                errors=[] if complete else [{"code": "METRIC_LINES_INCOMPLETE", "message": "Missing expected canonical cache metric lines for this run_id."}],
            )
        )
    else:
        _render_observability_quick_check_output(
            run_id=normalized_run_id,
            sample_size=normalized_sample_size,
            base_rows=len(base_rows),
            mv_rows=len(mv_rows),
            metric_lines=metric_lines,
            complete=complete,
        )
        if not complete:
            print("Missing expected canonical cache metric lines for this run_id.", file=sys.stderr)
            return 1
    if not complete:
        return 1
    return 0


def _legacy_import_command(
    *,
    sqlite_path: str,
    pg_url: str | None,
    raw_schema: str,
    normalized_schema: str,
    import_run_id: str | None,
    source_db_name: str | None,
) -> int:
    path = Path(sqlite_path)
    if not path.exists():
        print(f"SQLite path does not exist: {path}", file=sys.stderr)
        return 2

    parsed_run_id: uuid.UUID | None = None
    if import_run_id:
        try:
            parsed_run_id = uuid.UUID(import_run_id)
        except ValueError:
            print(f"Invalid import_run_id: {import_run_id}", file=sys.stderr)
            return 2

    engine = create_db_engine(pg_url)
    service = LegacyImportService(engine, raw_schema=raw_schema, normalized_schema=normalized_schema)
    try:
        summary = service.import_sqlite(
            path,
            import_run_id=parsed_run_id,
            source_db_name=source_db_name,
        )
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    _render_legacy_import_output(summary)
    return 0


def _refresh_mv_command(
    *,
    concurrently: bool,
    scheduled: bool,
    schedule_label: str | None,
    as_json: bool = False,
) -> int:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        # Advisory-only scheduling mode in this phase:
        # no background scheduler/trigger is created here.
        summary = refresh_materialized_view(
            engine,
            concurrently=concurrently,
            scheduled=scheduled,
            schedule_label=schedule_label,
        )
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "REFRESH_MV_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={"result": summary.__dict__},
            )
        )
    else:
        _render_mv_refresh_output(summary)
    return 0


def _planner_benchmark_command(
    *,
    sample_size: int,
    repeats: int,
    use_cache: bool,
    seed: int,
    as_json: bool = False,
) -> int:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    try:
        summary = benchmark_planner_lookup(
            session_factory,
            sample_size=sample_size,
            repeats=repeats,
            use_cache=use_cache,
            seed=seed,
        )
    except Exception as exc:
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=False,
                    errors=[{"code": "PLANNER_BENCHMARK_FAILED", "message": str(exc)}],
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={"result": summary.__dict__},
            )
        )
    else:
        _render_planner_benchmark_output(summary)
    return 0


def _explain_file_command(file_id: str, *, as_json: bool = False) -> int:
    latest = load_latest_decision_trace()
    if latest is None:
        if as_json:
            _print_json_payload(
                {
                    "ok": False,
                    "workflow_version": WORKFLOW_VERSION,
                    "schema_version": "unknown",
                    "generated_at": _iso_now(),
                    "data": {},
                    "errors": [{"code": "DECISION_TRACE_MISSING", "message": "No decision trace artifact available."}],
                }
            )
        else:
            print("No decision trace artifact available.", file=sys.stderr)
        return 1
    payload = explain_file_from_latest_trace(file_id=file_id)
    if payload is None:
        if as_json:
            _print_json_payload(
                {
                    "ok": False,
                    "workflow_version": WORKFLOW_VERSION,
                    "schema_version": "unknown",
                    "generated_at": _iso_now(),
                    "data": {},
                    "errors": [{"code": "FILE_NOT_FOUND", "message": f"File not found: {file_id}"}],
                }
            )
        else:
            print(f"File not found in latest decision trace: {file_id}", file=sys.stderr)
        return 1
    if as_json:
        _print_json_payload(
            {
                "ok": True,
                "workflow_version": WORKFLOW_VERSION,
                "schema_version": "unknown",
                "generated_at": _iso_now(),
                "data": {"result": payload},
                "errors": [],
            }
        )
    else:
        _render_file_explanation(payload)
    return 0


def _plan_command(
    path_arg: str,
    *,
    strict_metadata: bool = False,
    simulate_policy: bool = False,
    policy_name: str | None = None,
    preferred_roots: list[str] | None = None,
    as_json: bool = False,
) -> int:
    path = Path(path_arg)
    if not path.exists():
        print(f"Path does not exist: {path}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    if simulate_policy:
        selected_policy = policy_name or "FIRST_SEEN"
        try:
            policy = build_canonical_policy(selected_policy)
        except MediaManagerError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        context = CanonicalContext(preferred_roots=tuple(Path(root) for root in (preferred_roots or [])))
        try:
            delta = simulate_policy_delta(
                session_factory,
                policy=policy,
                context=context,
            )
        except MediaManagerError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        artifact_path = write_simulation_delta_artifact(delta)
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=True,
                    data={
                        "result": {
                            "delta": delta.to_dict(),
                            "artifact_path": str(artifact_path),
                        }
                    },
                )
            )
        else:
            _render_policy_simulation_output(delta, artifact_path)
        return 0

    run_service = RunService(session_factory)
    ingest_service = IngestService(session_factory)
    planner = PlanningService(session_factory)

    ingest_files = _collect_input_files(path)
    ingest_service.ingest_paths(ingest_files)

    run = run_service.create_run()
    summary = planner.plan_run(
        run.id,
        ingest_files,
        ingest_if_needed=False,
        strict_missing_metadata=strict_metadata,
    )

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run.id)
            .order_by(PlannedAction.action_type.asc(), PlannedAction.source_path.asc(), PlannedAction.target_path.asc())
        ).all()

    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={
                    "result": {
                        "run_id": str(run.id),
                        "summary": {
                            "scanned_count": summary.scanned_count,
                            "supported_count": summary.supported_count,
                            "skipped_count": summary.skipped_count,
                            "move_actions": summary.move_actions,
                            "noop_actions": summary.noop_actions,
                            "duplicate_actions": summary.duplicate_actions,
                        },
                    }
                },
            )
        )
    else:
        _render_plan_output(run.id, planned_actions, summary)
    return 0


def _apply_command(run_id_arg: str, *, collision_mode: str = "rename", as_json: bool = False) -> int:
    try:
        run_id = uuid.UUID(run_id_arg)
    except ValueError:
        print(f"Invalid run_id: {run_id_arg}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    apply_service = ApplyService(session_factory)

    try:
        summary = apply_service.apply_run(run_id, collision_mode=collision_mode)  # type: ignore[arg-type]
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    with session_factory() as session:
        planned_actions = session.scalars(
            select(PlannedAction)
            .where(PlannedAction.run_id == run_id)
            .order_by(
                PlannedAction.action_type.asc(),
                PlannedAction.source_path.asc(),
                PlannedAction.target_path.asc(),
                PlannedAction.id.asc(),
            )
        ).all()

    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={
                    "result": {
                        "run_id": str(run_id),
                        "summary": {
                            "applied_count": summary.applied_count,
                            "moves_count": summary.moves_count,
                            "duplicates_count": summary.duplicates_count,
                            "noop_count": summary.noop_count,
                            "skipped_count": summary.skipped_count,
                            "errors_count": summary.errors_count,
                        },
                    }
                },
            )
        )
    else:
        _render_apply_output(run_id, planned_actions, summary)
    return 0


def _ingest_command(
    path_arg: str,
    *,
    dry_run: bool,
    as_json: bool,
    transport: str,
    api_base: str,
    timeout: int,
) -> int:
    path = Path(path_arg)
    if transport == "http":
        if not dry_run:
            print("HTTP transport supports only ingest --dry-run.", file=sys.stderr)
            return 2
        try:
            _, response_payload = _http_call_json(
                method="POST",
                api_base=api_base,
                path="/api/v2/media-file/validate",
                timeout=timeout,
                body={"folder_path": str(path), "policy_name": None},
            )
        except Exception as exc:
            print(f"HTTP transport failed: {exc}", file=sys.stderr)
            return 2
        if as_json:
            print(json.dumps(response_payload, indent=2, sort_keys=True))
        else:
            result = (response_payload.get("data") or {}).get("result") if isinstance(response_payload.get("data"), dict) else {}
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if response_payload.get("ok") else 1

    if not path.exists():
        print(f"Path does not exist: {path}", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    ingest_service = IngestService(session_factory)
    if dry_run:
        report = ingest_service.validate_path(path)
        if as_json:
            _print_json_payload(
                _json_payload(
                    session_factory=session_factory,
                    ok=True,
                    data={"result": report.to_dict()},
                )
            )
        else:
            _render_ingest_validation_output(report, as_json=False)
        return 0

    summary = ingest_service.ingest_path(path)
    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={
                    "result": {
                        "files_scanned": summary.files_scanned,
                        "new_contents": summary.new_contents,
                        "new_instances": summary.new_instances,
                        "duplicates_detected": summary.duplicates_detected,
                        "metadata_extracted": summary.metadata_extracted,
                        "duration_s": summary.duration_s,
                    }
                },
            )
        )
    else:
        _render_ingest_output(summary)
    return 0


def _canonical_recompute_command(
    *,
    policy_name: str,
    dry_run: bool,
    apply: bool,
    preferred_roots: list[str],
    as_json: bool = False,
) -> int:
    if dry_run and apply:
        print("Specify only one of --dry-run or --apply.", file=sys.stderr)
        return 2

    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    mode = RecomputeMode.APPLY if apply else RecomputeMode.DRY_RUN
    try:
        policy = build_canonical_policy(policy_name)
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    context = CanonicalContext(preferred_roots=tuple(Path(root) for root in preferred_roots))
    try:
        summary = recompute_canonical_assignments(
            session_factory,
            policy=policy,
            context=context,
            mode=mode,
        )
    except MediaManagerError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if as_json:
        _print_json_payload(
            _json_payload(
                session_factory=session_factory,
                ok=True,
                data={
                    "result": {
                        "run_id": str(summary.run_id),
                        "status": summary.status,
                        "scanned_count": summary.scanned_count,
                        "changed_count": summary.changed_count,
                        "applied_count": summary.applied_count,
                        "failed_count": summary.failed_count,
                        "changed_content_ids": [str(item) for item in summary.changed_content_ids],
                        "failed_content_ids": [str(item) for item in summary.failed_content_ids],
                    }
                },
            )
        )
    else:
        _render_canonical_recompute_output(summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the media-manager CLI parser."""
    parser = argparse.ArgumentParser(prog="media-manager")
    parser.add_argument(
        "--transport",
        choices=["local", "http"],
        default="local",
        help="Execution transport for supported commands (default: local).",
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="Base API URL used when --transport=http.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout seconds when --transport=http.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Create a deterministic plan for file organization.")
    plan_parser.add_argument("path", help="File or directory path to plan.")
    plan_parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="Raise on missing required metadata codes during planning.",
    )
    plan_parser.add_argument(
        "--simulate-policy",
        action="store_true",
        help="Run policy simulation only (no planner/apply mutation).",
    )
    plan_parser.add_argument(
        "--policy",
        help="Canonical policy name for simulation mode (e.g. FIRST_SEEN, PREFER_ROOT, SHORTEST_PATH).",
    )
    plan_parser.add_argument(
        "--preferred-root",
        action="append",
        default=[],
        help="Preferred root path for PREFER_ROOT simulation policy. Can be provided multiple times.",
    )
    plan_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    ingest_parser = subparsers.add_parser("ingest", help="Ingest files into logical content/instance tables.")
    ingest_parser.add_argument("path", help="File or directory path to ingest.")
    ingest_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read-only validate mode. Computes ingest delta without DB writes.",
    )
    ingest_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON envelope.",
    )
    apply_parser = subparsers.add_parser("apply", help="Apply an existing planned run.")
    apply_parser.add_argument("run_id", help="Run identifier to apply.")
    apply_parser.add_argument(
        "--collision-mode",
        choices=["rename", "skip", "fail"],
        default="rename",
        help="Collision behavior when target path already exists.",
    )
    apply_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    canonical_parser = subparsers.add_parser("canonical", help="Canonicalization commands.")
    canonical_subparsers = canonical_parser.add_subparsers(dest="canonical_command", required=True)
    canonical_recompute = canonical_subparsers.add_parser(
        "recompute",
        help="Deterministically recompute canonical assignments for duplicate contents.",
    )
    canonical_recompute.add_argument("--policy", required=True, help="Canonical policy name.")
    canonical_recompute.add_argument("--dry-run", action="store_true", help="Compute diff without appending assignments.")
    canonical_recompute.add_argument("--apply", action="store_true", help="Append changed canonical assignments.")
    canonical_recompute.add_argument(
        "--preferred-root",
        action="append",
        default=[],
        help="Preferred root path for PREFER_ROOT policy. Can be provided multiple times.",
    )
    canonical_recompute.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    perf_run_parser = subparsers.add_parser(
        "perf-run",
        help="Run ingest/plan/apply perf workflow and emit performance artifact JSON.",
    )
    perf_run_parser.add_argument("--dataset", required=True, help="Dataset path to process.")
    perf_run_parser.add_argument("--env-class", required=True, help="Environment class label (e.g., ci/local).")
    perf_run_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label for perf metadata context.")
    perf_run_parser.add_argument("--dry-run", action="store_true", help="Run ingest+plan only (skip apply).")
    perf_run_parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="Raise on missing required metadata codes during planning.",
    )

    perf_compare_parser = subparsers.add_parser(
        "perf-compare",
        help="Compare current perf artifact against baseline.",
    )
    perf_compare_parser.add_argument("--dataset", required=True, help="Dataset id key for baseline lookup.")
    perf_compare_parser.add_argument("--env-class", required=True, help="Environment class label.")
    perf_compare_parser.add_argument("--artifact", help="Optional current artifact path.")
    perf_compare_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label passthrough.")
    perf_compare_parser.add_argument("--dry-run", action="store_true", help="No-op flag for workflow parity.")

    perf_refresh_parser = subparsers.add_parser(
        "perf-refresh-baseline",
        help="Store current perf artifact as baseline for dataset/env.",
    )
    perf_refresh_parser.add_argument("--dataset", required=True, help="Dataset id key.")
    perf_refresh_parser.add_argument("--env-class", required=True, help="Environment class label.")
    perf_refresh_parser.add_argument("--artifact", help="Optional current artifact path.")
    perf_refresh_parser.add_argument("--policy", default="FIRST_SEEN", help="Policy label passthrough.")
    perf_refresh_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate baseline write contract without persisting.",
    )
    legacy_import_parser = subparsers.add_parser(
        "legacy-import",
        help="One-off import of legacy SQLite DB into legacy_raw and legacy_3nf schemas.",
    )
    legacy_import_parser.add_argument("--sqlite-path", required=True, help="Path to legacy SQLite database file.")
    legacy_import_parser.add_argument("--pg-url", help="Optional PostgreSQL URL override. Defaults to DATABASE_URL.")
    legacy_import_parser.add_argument("--raw-schema", default="legacy_raw", help="Raw mirror schema name.")
    legacy_import_parser.add_argument(
        "--normalized-schema",
        default="legacy_3nf",
        help="Normalized legacy schema name.",
    )
    legacy_import_parser.add_argument("--import-run-id", help="Optional stable import run UUID for resume/idempotency.")
    legacy_import_parser.add_argument("--source-db-name", help="Optional source database label.")
    explain_file_parser = subparsers.add_parser(
        "explain-file",
        help="Explain canonical decision for a file instance from latest decision trace artifact.",
    )
    explain_file_parser.add_argument("file_id", help="File instance UUID.")
    explain_file_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    refresh_mv_parser = subparsers.add_parser(
        "refresh-mv",
        help="Refresh optional mv_canonical_metadata materialized view.",
    )
    refresh_mv_parser.add_argument(
        "--concurrently",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use REFRESH MATERIALIZED VIEW CONCURRENTLY (default: true).",
    )
    refresh_mv_parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Advisory schedule mode only (still performs one refresh in this phase).",
    )
    refresh_mv_parser.add_argument("--schedule-label", help="Optional schedule strategy label for logs/output.")
    refresh_mv_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    planner_benchmark_parser = subparsers.add_parser(
        "planner-benchmark",
        help="Compare canonical metadata lookup cost between base tables and MV.",
    )
    planner_benchmark_parser.add_argument("--sample-size", type=int, default=1000, help="Max canonical rows to query.")
    planner_benchmark_parser.add_argument("--repeats", type=int, default=5, help="Benchmark repeat count.")
    planner_benchmark_parser.add_argument("--seed", type=int, default=42, help="Deterministic benchmark seed.")
    planner_benchmark_parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable optional in-memory canonical read cache for MV lookup.",
    )
    planner_benchmark_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")
    observability_quick_check_parser = subparsers.add_parser(
        "observability-quick-check",
        help="Run one base+MV canonical metadata read and print matching Prometheus lines.",
    )
    observability_quick_check_parser.add_argument(
        "--run-id",
        help="Optional explicit run_id label for filtering emitted metric lines.",
    )
    observability_quick_check_parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="Maximum canonical metadata rows to read per source.",
    )
    observability_quick_check_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON envelope.",
    )
    tag_enrich_parser = subparsers.add_parser(
        "tag-enrich",
        help="Manually run deterministic tag enrichment for canonical items.",
    )
    tag_enrich_parser.add_argument(
        "--all",
        action="store_true",
        help="Enrich all current canonical content ids.",
    )
    tag_enrich_parser.add_argument(
        "--canonical-id",
        help="Single canonical content id (file_contents.content_id) to enrich.",
    )
    tag_enrich_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Deterministic batch size for enrichment processing.",
    )
    tag_enrich_parser.add_argument(
        "--source",
        choices=[member.value for member in TagSource],
        default=TagSource.SYSTEM.value,
        help="Tag source label for enrichment writes.",
    )
    tag_enrich_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    status_parser = subparsers.add_parser("status", help="Read current operator status metadata.")
    status_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    operator_parser = subparsers.add_parser("operator", help="Read operator-console resources.")
    operator_parser.add_argument(
        "resource",
        choices=[
            "dashboard-summary",
            "latest-metrics",
            "runs",
            "duplicates",
            "canonical",
            "canonical-tags",
            "media-file-by-hash",
            "media-file-history",
            "media-file-by-status",
            "media-file-reappearances",
            "media-file-analytics",
            "ledger-hash-audit",
            "media-file-dry-run-audit",
        ],
        help="Read resource name.",
    )
    operator_parser.add_argument("--limit", type=int, default=50, help="Row limit for list resources.")
    operator_parser.add_argument("--page", type=int, default=1, help="Page number for paginated resources.")
    operator_parser.add_argument("--tags", help="Comma-separated tag filter.")
    operator_parser.add_argument("--sort-by", default="created_at", help="Sort field for canonical resource.")
    operator_parser.add_argument("--sort-order", help="Sort order for canonical resource.")
    operator_parser.add_argument("--source", help="Source filter for canonical resource.")
    operator_parser.add_argument("--min-confidence", type=float, help="Minimum confidence filter for canonical resource.")
    operator_parser.add_argument("--q", help="Query string for suggestion resources.")
    operator_parser.add_argument("--hash-prefix", help="Hash prefix for media-file-by-hash resource.")
    operator_parser.add_argument("--path", help="Path for history/reappearance resources.")
    operator_parser.add_argument("--status", help="Status for media-file-by-status resource.")
    operator_parser.add_argument("--root-path", help="Root path scope for hash-audit resource.")
    operator_parser.add_argument("--sample-limit", type=int, default=20, help="Sample limit for hash-audit resource.")
    operator_parser.add_argument("--start", help="Start ISO timestamp for dry-run-audit resource.")
    operator_parser.add_argument("--end", help="End ISO timestamp for dry-run-audit resource.")
    operator_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    operator_run_parser = subparsers.add_parser("operator-run", help="Trigger an operator run workflow.")
    operator_run_parser.add_argument("--folder-path", required=True, help="Root folder path to process.")
    operator_run_parser.add_argument("--policy-name", required=True, help="Canonical policy to use for run.")
    operator_run_parser.add_argument("--dry-run", action="store_true", help="Run read-only validation mode.")
    operator_run_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    policy_get_parser = subparsers.add_parser("policy-get", help="Read current operator policy settings.")
    policy_get_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    policy_set_parser = subparsers.add_parser("policy-set", help="Update operator policy settings.")
    policy_set_parser.add_argument("--selected-policy", required=True, help="Policy name to persist.")
    policy_set_parser.add_argument(
        "--preferred-root",
        action="append",
        default=[],
        help="Preferred root path for PREFER_ROOT policy. Can be provided multiple times.",
    )
    policy_set_parser.add_argument(
        "--recanonicalization-enabled",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Persist recanonicalization preference.",
    )
    policy_set_parser.add_argument("--version", type=int, required=True, help="Optimistic concurrency version.")
    policy_set_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON envelope.")

    health_check_parser = subparsers.add_parser(
        "health-check",
        help="Run read-only health checks against operator-console REST endpoints.",
    )
    health_check_parser.add_argument(
        "--audit-hashes",
        action="store_true",
        help="Run ledger hash audit check.",
    )
    health_check_parser.add_argument(
        "--root",
        help="Optional root path scope filter for ledger hash audit.",
    )
    health_check_parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="Operator Console base URL.",
    )
    health_check_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    health_check_parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="Sample path cap for the audit response.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    # Optional, non-blocking metrics endpoint for CLI-driven deployments.
    try:
        start_metrics_http_server_if_enabled()
    except Exception:
        # Observability must not block CLI command execution.
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return _plan_command(
            args.path,
            strict_metadata=args.strict_metadata,
            simulate_policy=args.simulate_policy,
            policy_name=args.policy,
            preferred_roots=args.preferred_root,
            as_json=args.json,
        )
    if args.command == "ingest":
        return _ingest_command(
            args.path,
            dry_run=args.dry_run,
            as_json=args.json,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "apply":
        return _apply_command(args.run_id, collision_mode=args.collision_mode, as_json=args.json)
    if args.command == "canonical" and args.canonical_command == "recompute":
        return _canonical_recompute_command(
            policy_name=args.policy,
            dry_run=args.dry_run,
            apply=args.apply,
            preferred_roots=args.preferred_root,
            as_json=args.json,
        )
    if args.command == "perf-run":
        return perf_cli.run_perf_run(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            strict_metadata=args.strict_metadata,
            argv=argv or sys.argv[1:],
        )
    if args.command == "perf-compare":
        return perf_cli.run_perf_compare(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            artifact=args.artifact,
        )
    if args.command == "perf-refresh-baseline":
        return perf_cli.run_perf_refresh_baseline(
            dataset=args.dataset,
            env_class=args.env_class,
            policy=args.policy,
            dry_run=args.dry_run,
            artifact=args.artifact,
        )
    if args.command == "legacy-import":
        return _legacy_import_command(
            sqlite_path=args.sqlite_path,
            pg_url=args.pg_url,
            raw_schema=args.raw_schema,
            normalized_schema=args.normalized_schema,
            import_run_id=args.import_run_id,
            source_db_name=args.source_db_name,
        )
    if args.command == "explain-file":
        return _explain_file_command(args.file_id, as_json=args.json)
    if args.command == "refresh-mv":
        return _refresh_mv_command(
            concurrently=args.concurrently,
            scheduled=args.scheduled,
            schedule_label=args.schedule_label,
            as_json=args.json,
        )
    if args.command == "planner-benchmark":
        return _planner_benchmark_command(
            sample_size=args.sample_size,
            repeats=args.repeats,
            use_cache=args.use_cache,
            seed=args.seed,
            as_json=args.json,
        )
    if args.command == "observability-quick-check":
        return _observability_quick_check_command(
            run_id=args.run_id,
            sample_size=args.sample_size,
            as_json=args.json,
        )
    if args.command == "tag-enrich":
        return _tag_enrich_command(
            run_all=args.all,
            canonical_id=args.canonical_id,
            batch_size=args.batch_size,
            source=args.source,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
            as_json=args.json,
        )
    if args.command == "status":
        return _status_command(
            as_json=args.json,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "operator":
        return _operator_read_command(
            resource=args.resource,
            as_json=args.json,
            limit=args.limit,
            page=args.page,
            tags=args.tags,
            sort_by=args.sort_by,
            sort_order=args.sort_order,
            source=args.source,
            min_confidence=args.min_confidence,
            q=args.q,
            hash_prefix=args.hash_prefix,
            path=args.path,
            status=args.status,
            root_path=args.root_path,
            sample_limit=args.sample_limit,
            start=args.start,
            end=args.end,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "operator-run":
        return _operator_run_command(
            folder_path=args.folder_path,
            policy_name=args.policy_name,
            dry_run=args.dry_run,
            as_json=args.json,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "policy-get":
        return _policy_get_command(
            as_json=args.json,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "policy-set":
        return _policy_set_command(
            selected_policy=args.selected_policy,
            preferred_roots=args.preferred_root,
            recanonicalization_enabled=args.recanonicalization_enabled,
            version=args.version,
            as_json=args.json,
            transport=args.transport,
            api_base=args.api,
            timeout=args.timeout,
        )
    if args.command == "health-check":
        return _health_check_command(
            audit_hashes=args.audit_hashes,
            root=args.root,
            api=args.api,
            timeout=args.timeout,
            sample_limit=args.sample_limit,
        )

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
