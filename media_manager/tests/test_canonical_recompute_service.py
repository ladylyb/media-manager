from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import (
    CanonicalPolicy,
    ExifFilenameFallbackPolicy,
    FirstSeenPolicy,
    ShortestPathPolicy,
)
from media_manager.app.core.errors import CanonicalPolicyException
from media_manager.app.persistence.canonicalization import (
    RecomputeMode,
    append_assignment,
    get_active_assignment,
    recompute_canonical_assignments,
)
from media_manager.app.persistence.ingest import IngestService
from media_manager.app.persistence.models import (
    CanonicalAssignment,
    CanonicalRecomputeItem,
    CanonicalRecomputeRun,
    FileContent,
    FileInstance,
)


def _write_file(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_recompute_dry_run_is_append_only_for_assignments(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "one.jpg", b"same")
    second = _write_file(tmp_path / "copy" / "two.jpg", b"same")
    ingest.ingest_paths([first, second])

    with session_factory() as session:
        before = len(session.scalars(select(CanonicalAssignment)).all())

    summary = recompute_canonical_assignments(
        session_factory,
        policy=ShortestPathPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.DRY_RUN,
    )
    assert summary.scanned_count == 1
    assert summary.changed_count >= 0

    with session_factory() as session:
        after = len(session.scalars(select(CanonicalAssignment)).all())
        assert after == before
        runs = session.scalars(select(CanonicalRecomputeRun)).all()
        items = session.scalars(select(CanonicalRecomputeItem)).all()
        assert len(runs) == 1
        assert len(items) == 1


def test_recompute_apply_inserts_only_changed_rows(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "aaa" / "first.jpg", b"same")
    second = _write_file(tmp_path / "a.jpg", b"same")
    ingest.ingest_paths([first, second])

    with session_factory() as session:
        content_id = session.scalar(select(FileContent.content_id))
        assert content_id is not None
        before_count = len(session.scalars(select(CanonicalAssignment)).all())

    summary = recompute_canonical_assignments(
        session_factory,
        policy=ShortestPathPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.APPLY,
    )
    assert summary.changed_count == 1
    assert summary.applied_count == 1

    with session_factory() as session:
        rows = session.scalars(select(CanonicalAssignment).order_by(CanonicalAssignment.assigned_at.asc())).all()
        assert len(rows) == before_count + 1


def test_recompute_dry_run_is_deterministic(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "alpha.jpg", b"same")
    second = _write_file(tmp_path / "beta" / "beta.jpg", b"same")
    ingest.ingest_paths([first, second])

    one = recompute_canonical_assignments(
        session_factory,
        policy=ShortestPathPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.DRY_RUN,
    )
    two = recompute_canonical_assignments(
        session_factory,
        policy=ShortestPathPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.DRY_RUN,
    )
    assert one.scanned_count == two.scanned_count
    assert one.changed_count == two.changed_count
    assert one.failed_count == two.failed_count


def test_recompute_exif_filename_fallback_prefers_filename_candidate_over_filesystem_only(
    tmp_path: Path, session_factory
) -> None:
    ingest = IngestService(session_factory)
    first = _write_file(tmp_path / "copy.jpg", b"same")
    second = _write_file(tmp_path / "IMG_20240214_235959.jpg", b"same")
    ingest.ingest_paths([first, second])

    with session_factory.begin() as session:
        content_id = session.scalar(select(FileContent.content_id))
        assert content_id is not None
        instances = session.scalars(
            select(FileInstance).where(FileInstance.content_id == content_id).order_by(FileInstance.absolute_path.asc())
        ).all()
        by_name = {Path(instance.absolute_path).name: instance for instance in instances}
        append_assignment(
            session,
            content_id=content_id,
            canonical_instance_id=by_name["copy.jpg"].file_instance_id,
            policy_name=FirstSeenPolicy.name,
            policy_version=FirstSeenPolicy.version,
        )

    summary = recompute_canonical_assignments(
        session_factory,
        policy=ExifFilenameFallbackPolicy(),
        context=CanonicalContext(),
        mode=RecomputeMode.APPLY,
    )

    assert summary.changed_count == 1
    with session_factory() as session:
        content_id = session.scalar(select(FileContent.content_id))
        assert content_id is not None
        active = get_active_assignment(session, content_id)
        assert active is not None
        selected = session.get(FileInstance, active.canonical_instance_id)
        assert selected is not None
        assert Path(selected.absolute_path).name == "IMG_20240214_235959.jpg"


class _FailingPolicy:
    name = "FAIL"
    version = "v1"

    def select(self, content_id: str, instances: list[FileInstance], context: CanonicalContext) -> FileInstance:
        del content_id, instances, context
        raise CanonicalPolicyException("forced failure")


def test_recompute_records_item_failures_and_continues(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    ingest.ingest_paths(
        [
            _write_file(tmp_path / "one.jpg", b"dup-one"),
            _write_file(tmp_path / "copy" / "one_copy.jpg", b"dup-one"),
        ]
    )

    summary = recompute_canonical_assignments(
        session_factory,
        policy=_FailingPolicy(),  # type: ignore[arg-type]
        context=CanonicalContext(),
        mode=RecomputeMode.DRY_RUN,
    )
    assert summary.failed_count == 1
    assert summary.status == "COMPLETED_WITH_ERRORS"


def test_get_active_assignment_uses_latest_timestamp_and_id(tmp_path: Path, session_factory) -> None:
    ingest = IngestService(session_factory)
    root = tmp_path / "tmp-recompute-active"
    first = _write_file(root / "x.jpg", b"x")
    second = _write_file(root / "copy" / "x.jpg", b"x")
    ingest.ingest_paths([first, second])
    with session_factory.begin() as session:
        content_id = session.scalar(select(FileContent.content_id))
        assert content_id is not None
        instances = session.scalars(
            select(FileInstance).where(FileInstance.content_id == content_id).order_by(FileInstance.absolute_path.asc())
        ).all()
        assert len(instances) == 2
        append_assignment(
            session,
            content_id=content_id,
            canonical_instance_id=instances[0].file_instance_id,
            policy_name=FirstSeenPolicy.name,
            policy_version=FirstSeenPolicy.version,
        )
        append_assignment(
            session,
            content_id=content_id,
            canonical_instance_id=instances[1].file_instance_id,
            policy_name=FirstSeenPolicy.name,
            policy_version=FirstSeenPolicy.version,
        )

    with session_factory() as session:
        active = get_active_assignment(session, content_id)
        assert active is not None
        assert active.canonical_instance_id == instances[1].file_instance_id
