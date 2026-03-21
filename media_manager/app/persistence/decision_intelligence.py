"""Decision intelligence helpers for Phase 10.

This module is intentionally observational. It does not mutate canonical selection logic,
planned actions, or apply behavior.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import CanonicalPolicy
from media_manager.app.persistence.canonicalization import get_active_assignment
from media_manager.app.persistence.models import FileContent, FileInstance, FileInstanceStatus

DECISION_TRACE_VERSION = "phase10.v1"
DEFAULT_ARTIFACTS_DIR = Path("artifacts")


@dataclass(frozen=True)
class DecisionTrace:
    content_id: str
    canonical_instance_id: str
    candidate_instance_ids: tuple[str, ...]
    applied_policy_rules: tuple[str, ...]
    decision_reason: str
    tie_breaker_used: str
    hash_identity: str
    timestamp: str
    planner_version: str


@dataclass(frozen=True)
class SimulationDelta:
    run_id: uuid.UUID
    policy_name: str
    policy_version: str
    canonical_changes_count: int
    demotions_count: int
    merges_count: int
    impacted_content_ids: tuple[str, ...]

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "canonical_changes_count": self.canonical_changes_count,
            "demotions_count": self.demotions_count,
            "merges_count": self.merges_count,
            "impacted_content_ids": list(self.impacted_content_ids),
        }


def _policy_rules(policy_name: str, policy_version: str) -> tuple[str, ...]:
    normalized = policy_name.strip().upper()
    if normalized == "FIRST_SEEN":
        return ("pick_min_first_seen", "tie_break_file_instance_id")
    if normalized == "PREFER_ROOT":
        return ("prefer_paths_under_preferred_roots", "fallback_first_seen", "tie_break_file_instance_id")
    if normalized == "EXIF_FILENAME_FALLBACK":
        return (
            "prefer_embedded_metadata_evidence",
            "prefer_filename_date_evidence",
            "prefer_paths_under_preferred_roots",
            "tie_break_first_seen_then_file_instance_id",
        )
    if normalized == "SHORTEST_PATH":
        return ("pick_shortest_path", "tie_break_path_then_first_seen_then_file_instance_id")
    return ("policy_name_unrecognized", f"policy={policy_name}", f"version={policy_version}")


def _tie_breaker(policy_name: str) -> str:
    normalized = policy_name.strip().upper()
    if normalized in {"FIRST_SEEN", "PREFER_ROOT", "EXIF_FILENAME_FALLBACK"}:
        return "first_seen_at_then_file_instance_id"
    if normalized == "SHORTEST_PATH":
        return "absolute_path_then_first_seen_at_then_file_instance_id"
    return "assignment_assigned_at_then_assignment_id"


def _candidate_sort_key(instance: FileInstance) -> tuple[datetime, str, str]:
    return (
        instance.first_seen_at,
        instance.absolute_path,
        str(instance.file_instance_id),
    )


def _to_iso8601(dt: datetime) -> str:
    normalized = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


def _decision_trace_file(run_id: uuid.UUID, artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> Path:
    return artifacts_dir / f"decision_trace_{run_id}.json"


def _simulation_file(run_id: uuid.UUID, artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> Path:
    return artifacts_dir / f"simulation_delta_{run_id}.json"


def _latest_trace_file(artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> Path | None:
    files = sorted(
        artifacts_dir.glob("decision_trace_*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    return files[-1] if files else None


def write_decision_trace_artifact(
    *,
    run_id: uuid.UUID,
    traces: list[DecisionTrace],
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": str(run_id),
        "trace_version": DECISION_TRACE_VERSION,
        "decisions": [
            {
                "content_id": trace.content_id,
                "canonical_instance_id": trace.canonical_instance_id,
                "candidate_instance_ids": list(trace.candidate_instance_ids),
                "applied_policy_rules": list(trace.applied_policy_rules),
                "decision_reason": trace.decision_reason,
                "tie_breaker_used": trace.tie_breaker_used,
                "hash_identity": trace.hash_identity,
                "timestamp": trace.timestamp,
                "planner_version": trace.planner_version,
            }
            for trace in sorted(traces, key=lambda item: (item.content_id, item.canonical_instance_id))
        ],
    }
    path = _decision_trace_file(run_id, artifacts_dir)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return path


def write_simulation_delta_artifact(
    delta: SimulationDelta,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> Path:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = _simulation_file(delta.run_id, artifacts_dir)
    path.write_text(json.dumps(delta.to_ordered_dict(), indent=2, sort_keys=False), encoding="utf-8")
    return path


def load_latest_decision_trace(artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR) -> dict[str, Any] | None:
    path = _latest_trace_file(artifacts_dir)
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def explain_file_from_latest_trace(
    *,
    file_id: str,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> dict[str, Any] | None:
    payload = load_latest_decision_trace(artifacts_dir)
    if payload is None:
        return None

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return None

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        canonical_id = str(decision.get("canonical_instance_id", ""))
        candidates = decision.get("candidate_instance_ids")
        if not isinstance(candidates, list):
            continue
        candidate_ids = [str(item) for item in candidates]
        if file_id != canonical_id and file_id not in candidate_ids:
            continue
        return {
            "run_id": payload.get("run_id"),
            "content_id": decision.get("content_id"),
            "file_id": file_id,
            "is_canonical": file_id == canonical_id,
            "canonical_instance_id": canonical_id,
            "candidate_instance_ids": candidate_ids,
            "applied_policy_rules": decision.get("applied_policy_rules", []),
            "decision_reason": decision.get("decision_reason"),
            "tie_breaker_used": decision.get("tie_breaker_used"),
            "planner_version": decision.get("planner_version"),
            "timestamp": decision.get("timestamp"),
        }
    return None


def build_decision_traces(
    session: Session,
    canonical_instances: list[FileInstance],
    *,
    planner_version: str,
) -> list[DecisionTrace]:
    if not canonical_instances:
        return []

    content_ids = sorted({instance.content_id for instance in canonical_instances}, key=str)
    instances_by_content = _load_instances_by_content(session, content_ids)
    hash_by_content = _load_hash_by_content(session, content_ids)

    traces: list[DecisionTrace] = []
    for instance in sorted(canonical_instances, key=lambda item: (str(item.content_id), str(item.file_instance_id))):
        content_id = instance.content_id
        active_assignment = get_active_assignment(session, content_id)
        policy_name = active_assignment.policy_name if active_assignment is not None else "FIRST_SEEN"
        policy_version = active_assignment.policy_version if active_assignment is not None else "v1"
        candidates = instances_by_content.get(content_id, ())
        candidate_ids = tuple(str(candidate.file_instance_id) for candidate in candidates)
        hash_identity = hash_by_content.get(content_id, "")
        if active_assignment is not None:
            decision_timestamp = active_assignment.assigned_at
        elif candidates:
            decision_timestamp = candidates[0].first_seen_at
        else:
            decision_timestamp = datetime.now(UTC)
        traces.append(
            DecisionTrace(
                content_id=str(content_id),
                canonical_instance_id=str(instance.file_instance_id),
                candidate_instance_ids=candidate_ids,
                applied_policy_rules=_policy_rules(policy_name, policy_version),
                decision_reason=(
                    f"Latest canonical assignment selected using {policy_name} ({policy_version})"
                ),
                tie_breaker_used=_tie_breaker(policy_name),
                hash_identity=hash_identity,
                timestamp=_to_iso8601(decision_timestamp),
                planner_version=planner_version,
            )
        )
    return traces


def _load_instances_by_content(
    session: Session,
    content_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[FileInstance, ...]]:
    if not content_ids:
        return {}
    rows = session.scalars(
        select(FileInstance)
        .where(
            FileInstance.content_id.in_(content_ids),
            FileInstance.status == FileInstanceStatus.ACTIVE.value,
        )
        .order_by(
            FileInstance.content_id.asc(),
            FileInstance.first_seen_at.asc(),
            FileInstance.absolute_path.asc(),
            FileInstance.file_instance_id.asc(),
        )
    ).all()

    grouped: dict[uuid.UUID, list[FileInstance]] = {}
    for row in rows:
        grouped.setdefault(row.content_id, []).append(row)
    return {key: tuple(sorted(values, key=_candidate_sort_key)) for key, values in grouped.items()}


def _load_hash_by_content(session: Session, content_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not content_ids:
        return {}
    rows = session.execute(
        select(FileContent.content_id, FileContent.sha256_hash).where(FileContent.content_id.in_(content_ids))
    ).all()
    return {content_id: sha256_hash for content_id, sha256_hash in rows}


def simulate_policy_delta(
    session_factory: sessionmaker[Session],
    *,
    policy: CanonicalPolicy,
    context: CanonicalContext,
) -> SimulationDelta:
    run_id = uuid.uuid4()
    impacted_content_ids: list[str] = []
    canonical_changes_count = 0
    demotions_count = 0
    merges_count = 0

    with session_factory() as session:
        duplicate_content_ids = session.scalars(
            select(FileInstance.content_id)
            .where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
            .group_by(FileInstance.content_id)
            .having(func.count(FileInstance.file_instance_id) > 1)
            .order_by(FileInstance.content_id.asc())
        ).all()

        for content_id in duplicate_content_ids:
            instances = session.scalars(
                select(FileInstance)
                .where(
                    FileInstance.content_id == content_id,
                    FileInstance.status == FileInstanceStatus.ACTIVE.value,
                )
                .order_by(
                    FileInstance.first_seen_at.asc(),
                    FileInstance.absolute_path.asc(),
                    FileInstance.file_instance_id.asc(),
                )
            ).all()
            if not instances:
                continue

            current_assignment = get_active_assignment(session, content_id)
            old_id = current_assignment.canonical_instance_id if current_assignment is not None else None
            selected = policy.select(str(content_id), instances, context)
            new_id = selected.file_instance_id
            if old_id == new_id:
                continue

            canonical_changes_count += 1
            impacted_content_ids.append(str(content_id))
            if old_id is not None:
                demotions_count += 1
            if len(instances) > 2:
                merges_count += 1

    return SimulationDelta(
        run_id=run_id,
        policy_name=policy.name,
        policy_version=policy.version,
        canonical_changes_count=canonical_changes_count,
        demotions_count=demotions_count,
        merges_count=merges_count,
        impacted_content_ids=tuple(sorted(impacted_content_ids)),
    )
