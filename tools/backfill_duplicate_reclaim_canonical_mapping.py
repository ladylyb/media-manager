#!/usr/bin/env python3
"""Backfill planner-side canonical mappings for historical duplicate reclaim data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from media_manager.app.persistence.base import create_db_engine, create_session_factory, transactional_session
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    DuplicateReclaimRecord,
    FileContent,
    FileInstance,
    FileInstanceStatus,
)


@dataclass(frozen=True)
class CandidateRow:
    content_id: UUID
    latest_assignment_canonical_instance_id: UUID | None
    active_file_count: int
    assignment_count: int
    latest_assignment_tie_count: int
    reclaim_status: str | None
    category: str
    auto_backfillable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "content_id": str(self.content_id),
            "latest_assignment_canonical_instance_id": (
                str(self.latest_assignment_canonical_instance_id)
                if self.latest_assignment_canonical_instance_id is not None
                else None
            ),
            "active_file_count": self.active_file_count,
            "assignment_count": self.assignment_count,
            "latest_assignment_tie_count": self.latest_assignment_tie_count,
            "reclaim_status": self.reclaim_status,
            "category": self.category,
            "auto_backfillable": self.auto_backfillable,
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill FileContent.canonical_file_instance_id from the latest "
            "CanonicalAssignment for historical duplicate-reclaim groups only."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the backfill. Without this flag the command is dry-run only.",
    )
    parser.add_argument(
        "--content-id",
        action="append",
        default=[],
        help="Limit the backfill to one or more specific content_ids.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of auto-backfillable rows to process.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of sample rows to include in the report (default: 10).",
    )
    return parser.parse_args()


def _collect_candidates(content_ids: set[UUID] | None = None) -> list[CandidateRow]:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        assignment_stmt = select(
            CanonicalAssignment.content_id,
            CanonicalAssignment.canonical_instance_id,
            CanonicalAssignment.assigned_at,
            CanonicalAssignment.assignment_id,
        )
        if content_ids:
            assignment_stmt = assignment_stmt.where(CanonicalAssignment.content_id.in_(content_ids))
        assignments = session.execute(
            assignment_stmt.order_by(
                CanonicalAssignment.content_id.asc(),
                CanonicalAssignment.assigned_at.desc(),
                CanonicalAssignment.assignment_id.desc(),
            )
        ).all()

        latest_by_content: dict[UUID, dict[str, object]] = {}
        assignment_count: Counter[UUID] = Counter()
        assigned_at_counter: Counter[tuple[UUID, object]] = Counter()
        for content_id, canonical_instance_id, assigned_at, assignment_id in assignments:
            assignment_count[content_id] += 1
            assigned_at_counter[(content_id, assigned_at)] += 1
            if content_id not in latest_by_content:
                latest_by_content[content_id] = {
                    "canonical_instance_id": canonical_instance_id,
                    "assigned_at": assigned_at,
                    "assignment_id": assignment_id,
                }

        latest_assignment_ties: Counter[UUID] = Counter()
        for (content_id, assigned_at), count in assigned_at_counter.items():
            latest = latest_by_content.get(content_id)
            if latest is not None and latest["assigned_at"] == assigned_at and count > 1:
                latest_assignment_ties[content_id] = count

        file_content_stmt = select(FileContent)
        if content_ids:
            file_content_stmt = file_content_stmt.where(FileContent.content_id.in_(content_ids))
        file_content_rows = {
            row.content_id: row.canonical_file_instance_id
            for row in session.scalars(file_content_stmt).all()
        }

        file_instance_stmt = select(FileInstance)
        if content_ids:
            file_instance_stmt = file_instance_stmt.where(FileInstance.content_id.in_(content_ids))
        all_instances = {}
        active_instances_by_content: dict[UUID, list[FileInstance]] = {}
        for file_instance in session.scalars(file_instance_stmt).all():
            all_instances[file_instance.file_instance_id] = file_instance
            if file_instance.status == FileInstanceStatus.ACTIVE.value:
                active_instances_by_content.setdefault(file_instance.content_id, []).append(file_instance)

        reclaim_stmt = select(DuplicateReclaimRecord)
        if content_ids:
            reclaim_stmt = reclaim_stmt.where(DuplicateReclaimRecord.content_id.in_(content_ids))
        reclaim_status_by_content = {
            row.content_id: row.reclaim_status
            for row in session.scalars(reclaim_stmt).all()
        }

    rows: list[CandidateRow] = []
    for content_id, latest in latest_by_content.items():
        active_instances = active_instances_by_content.get(content_id, [])
        if len(active_instances) <= 1:
            continue
        if file_content_rows.get(content_id) is not None:
            continue

        canonical_instance_id = latest["canonical_instance_id"]
        canonical_instance = all_instances.get(canonical_instance_id)
        if canonical_instance is None:
            category = "latest_assignment_instance_missing"
            auto_backfillable = False
        elif canonical_instance.content_id != content_id:
            category = "latest_assignment_points_to_other_content"
            auto_backfillable = False
        elif canonical_instance.status != FileInstanceStatus.ACTIVE.value:
            category = "latest_assignment_instance_inactive"
            auto_backfillable = False
        else:
            category = "latest_assignment_active_same_content"
            auto_backfillable = True

        rows.append(
            CandidateRow(
                content_id=content_id,
                latest_assignment_canonical_instance_id=canonical_instance_id,
                active_file_count=len(active_instances),
                assignment_count=assignment_count[content_id],
                latest_assignment_tie_count=latest_assignment_ties.get(content_id, 0),
                reclaim_status=reclaim_status_by_content.get(content_id),
                category=category,
                auto_backfillable=auto_backfillable,
            )
        )
    return rows


def _sample(rows: list[CandidateRow], limit: int) -> list[dict[str, object]]:
    return [row.to_dict() for row in sorted(rows, key=lambda row: str(row.content_id))[: max(limit, 0)]]


def _apply_backfill(rows: list[CandidateRow], limit: int | None) -> tuple[int, list[str]]:
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    candidates = [row for row in rows if row.auto_backfillable]
    if limit is not None:
        candidates = candidates[: max(limit, 0)]

    updated_content_ids: list[str] = []
    for row in candidates:
        assert row.latest_assignment_canonical_instance_id is not None
        with transactional_session(session_factory) as session:
            file_content = session.get(FileContent, row.content_id)
            if file_content is None:
                continue
            if file_content.canonical_file_instance_id is not None:
                continue

            latest_assignment = session.execute(
                select(CanonicalAssignment)
                .where(CanonicalAssignment.content_id == row.content_id)
                .order_by(CanonicalAssignment.assigned_at.desc(), CanonicalAssignment.assignment_id.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest_assignment is None:
                continue

            canonical_instance = session.get(FileInstance, latest_assignment.canonical_instance_id)
            if canonical_instance is None:
                continue
            if canonical_instance.content_id != row.content_id:
                continue
            if canonical_instance.status != FileInstanceStatus.ACTIVE.value:
                continue

            file_content.canonical_file_instance_id = latest_assignment.canonical_instance_id
            updated_content_ids.append(str(row.content_id))

    return len(updated_content_ids), updated_content_ids


def main() -> int:
    args = _parse_args()
    content_ids = {UUID(raw) for raw in args.content_id} if args.content_id else None

    rows = _collect_candidates(content_ids)
    auto_backfillable = [row for row in rows if row.auto_backfillable]
    manual_review = [row for row in rows if not row.auto_backfillable]
    category_breakdown = Counter(row.category for row in rows)
    reclaim_status_breakdown = Counter((row.reclaim_status or "NONE") for row in rows)

    updated_count = 0
    updated_content_ids: list[str] = []
    if args.apply:
        updated_count, updated_content_ids = _apply_backfill(rows, args.limit)

    payload = {
        "mode": "apply" if args.apply else "dry_run",
        "requested_content_ids": [str(content_id) for content_id in sorted(content_ids, key=str)] if content_ids else [],
        "limit": args.limit,
        "total_mismatch_groups": len(rows),
        "category_breakdown": dict(category_breakdown),
        "reclaim_status_breakdown": dict(reclaim_status_breakdown),
        "auto_backfillable_count": len(auto_backfillable),
        "needs_manual_review_count": len(manual_review),
        "auto_backfillable_sample": _sample(auto_backfillable, args.sample_limit),
        "needs_manual_sample": _sample(manual_review, args.sample_limit),
        "updated_count": updated_count,
        "updated_content_ids_sample": updated_content_ids[: max(args.sample_limit, 0)],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
