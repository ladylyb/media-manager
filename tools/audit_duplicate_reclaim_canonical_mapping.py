#!/usr/bin/env python3
"""Audit duplicate reclaim canonical-mapping gaps for historical data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from media_manager.app.persistence.base import create_db_engine, create_session_factory
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    DuplicateReclaimRecord,
    FileContent,
    FileInstance,
    FileInstanceStatus,
)


@dataclass(frozen=True)
class AuditRow:
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
            "Audit duplicate groups where CanonicalAssignment exists but "
            "FileContent.canonical_file_instance_id is still missing."
        )
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of sample rows to include for each category set (default: 10).",
    )
    return parser.parse_args()


def _sample(rows: list[AuditRow], limit: int) -> list[dict[str, object]]:
    return [row.to_dict() for row in sorted(rows, key=lambda row: str(row.content_id))[: max(limit, 0)]]


def main() -> int:
    args = _parse_args()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        assignments = session.execute(
            select(
                CanonicalAssignment.content_id,
                CanonicalAssignment.canonical_instance_id,
                CanonicalAssignment.assigned_at,
                CanonicalAssignment.assignment_id,
            ).order_by(
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

        file_content_rows = {
            row.content_id: row.canonical_file_instance_id
            for row in session.scalars(select(FileContent)).all()
        }
        all_instances = {}
        active_instances_by_content: dict[UUID, list[FileInstance]] = {}
        for file_instance in session.scalars(select(FileInstance)).all():
            all_instances[file_instance.file_instance_id] = file_instance
            if file_instance.status == FileInstanceStatus.ACTIVE.value:
                active_instances_by_content.setdefault(file_instance.content_id, []).append(file_instance)

        reclaim_status_by_content = {
            row.content_id: row.reclaim_status
            for row in session.scalars(select(DuplicateReclaimRecord)).all()
        }

    rows: list[AuditRow] = []
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
            AuditRow(
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

    category_breakdown = Counter(row.category for row in rows)
    reclaim_status_breakdown = Counter((row.reclaim_status or "NONE") for row in rows)
    auto_backfillable = [row for row in rows if row.auto_backfillable]
    manual_review = [row for row in rows if not row.auto_backfillable]

    payload = {
        "total_mismatch_groups": len(rows),
        "category_breakdown": dict(category_breakdown),
        "reclaim_status_breakdown": dict(reclaim_status_breakdown),
        "auto_backfillable_count": len(auto_backfillable),
        "needs_manual_review_count": len(manual_review),
        "auto_backfillable_sample": _sample(auto_backfillable, args.sample_limit),
        "needs_manual_sample": _sample(manual_review, args.sample_limit),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
