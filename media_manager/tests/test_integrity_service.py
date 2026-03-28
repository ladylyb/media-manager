from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from media_manager.app.persistence.integrity import IntegrityService
from media_manager.app.persistence.models import (
    FileContent,
    FileInstance,
    FileInstanceStatus,
    IntegrityCheck,
    IntegrityScanMode,
    IntegritySignal,
)


def _add_content(session, *, content_id: UUID, sha256_hash: str, at: datetime) -> None:
    session.add(FileContent(content_id=content_id, sha256_hash=sha256_hash, first_seen_at=at))


def _add_instance(
    session,
    *,
    file_instance_id: UUID,
    content_id: UUID,
    absolute_path: str,
    at: datetime,
) -> None:
    session.add(
        FileInstance(
            file_instance_id=file_instance_id,
            content_id=content_id,
            absolute_path=absolute_path,
            filesystem_id="fs-1",
            first_seen_at=at,
            last_seen_at=at,
            status=FileInstanceStatus.ACTIVE.value,
        )
    )


def _ok_result(signal_type: str = "integrity_ok") -> dict[str, object]:
    return {
        "status": "OK",
        "confidence": 0.0,
        "readability_ok": True,
        "probe_status": "OK",
        "decode_status": "NOT_RUN",
        "signals": [
            {
                "signal_type": signal_type,
                "severity": "info",
                "details": {"signal_type": signal_type},
            }
        ],
    }


def _install_scan_stub(service: IntegrityService, *, signal_type: str, calls: list[tuple[str, str]], monkeypatch) -> None:
    def _fake_scan_path(path: Path, mode: IntegrityScanMode) -> dict[str, object]:
        calls.append((str(path), mode.value))
        return _ok_result(signal_type)

    monkeypatch.setattr(service, "_scan_path", _fake_scan_path)


def test_unchanged_fast_scan_is_skipped_and_preserves_existing_snapshot(session_factory, tmp_path: Path, monkeypatch) -> None:
    service = IntegrityService(session_factory)
    now = datetime(2026, 3, 28, 12, 0, tzinfo=UTC)
    content_id = uuid4()
    file_instance_id = uuid4()
    media_path = tmp_path / "clip-fast.mp4"
    media_path.write_bytes(b"fast-scan")

    with session_factory.begin() as session:
        _add_content(session, content_id=content_id, sha256_hash="a" * 64, at=now)
        _add_instance(session, file_instance_id=file_instance_id, content_id=content_id, absolute_path=str(media_path), at=now)

    first_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="first_integrity_ok", calls=first_calls, monkeypatch=monkeypatch)
    first_summary = service.scan(scan_mode="FAST")
    assert first_summary.scanned_count == 1
    assert first_summary.skipped_count == 0
    assert first_calls == [(str(media_path), "FAST")]

    with session_factory() as session:
        first_check = session.scalar(select(IntegrityCheck).where(IntegrityCheck.file_instance_id == file_instance_id))
        assert first_check is not None
        first_signal_ids = [
            signal.id
            for signal in session.scalars(
                select(IntegritySignal).where(IntegritySignal.check_id == first_check.id).order_by(IntegritySignal.id.asc())
            ).all()
        ]
        first_last_checked_at = first_check.last_checked_at
        first_latest_run_id = first_check.latest_run_id

    second_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="second_integrity_ok", calls=second_calls, monkeypatch=monkeypatch)
    second_summary = service.scan(scan_mode="FAST")

    assert second_summary.eligible_file_count == 1
    assert second_summary.scanned_count == 0
    assert second_summary.skipped_count == 1
    assert second_summary.issues_found == 0
    assert second_calls == []

    with session_factory() as session:
        second_check = session.scalar(select(IntegrityCheck).where(IntegrityCheck.file_instance_id == file_instance_id))
        assert second_check is not None
        second_signals = session.scalars(
            select(IntegritySignal).where(IntegritySignal.check_id == second_check.id).order_by(IntegritySignal.id.asc())
        ).all()

    assert second_check.latest_run_id == first_latest_run_id
    assert second_check.last_checked_at == first_last_checked_at
    assert second_check.last_completed_scan_mode == "FAST"
    assert [signal.id for signal in second_signals] == first_signal_ids
    assert [signal.signal_type for signal in second_signals] == ["first_integrity_ok"]


def test_prior_deep_scan_satisfies_fast_on_unchanged_file(session_factory, tmp_path: Path, monkeypatch) -> None:
    service = IntegrityService(session_factory)
    now = datetime(2026, 3, 28, 12, 30, tzinfo=UTC)
    content_id = uuid4()
    file_instance_id = uuid4()
    media_path = tmp_path / "clip-deep.mov"
    media_path.write_bytes(b"deep-scan")

    with session_factory.begin() as session:
        _add_content(session, content_id=content_id, sha256_hash="b" * 64, at=now)
        _add_instance(session, file_instance_id=file_instance_id, content_id=content_id, absolute_path=str(media_path), at=now)

    initial_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="deep_integrity_ok", calls=initial_calls, monkeypatch=monkeypatch)
    first_summary = service.scan(scan_mode="DEEP")

    assert first_summary.scanned_count == 1
    assert initial_calls == [(str(media_path), "DEEP")]

    second_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="fast_integrity_ok", calls=second_calls, monkeypatch=monkeypatch)
    second_summary = service.scan(scan_mode="FAST")

    assert second_summary.scanned_count == 0
    assert second_summary.skipped_count == 1
    assert second_calls == []


def test_prior_fast_scan_is_rescanned_for_deep_mode(session_factory, tmp_path: Path, monkeypatch) -> None:
    service = IntegrityService(session_factory)
    now = datetime(2026, 3, 28, 13, 0, tzinfo=UTC)
    content_id = uuid4()
    file_instance_id = uuid4()
    media_path = tmp_path / "clip-upgrade.mkv"
    media_path.write_bytes(b"upgrade")

    with session_factory.begin() as session:
        _add_content(session, content_id=content_id, sha256_hash="c" * 64, at=now)
        _add_instance(session, file_instance_id=file_instance_id, content_id=content_id, absolute_path=str(media_path), at=now)

    first_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="fast_integrity_ok", calls=first_calls, monkeypatch=monkeypatch)
    service.scan(scan_mode="FAST")

    with session_factory() as session:
        first_check = session.scalar(select(IntegrityCheck).where(IntegrityCheck.file_instance_id == file_instance_id))
        assert first_check is not None
        first_latest_run_id = first_check.latest_run_id

    second_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="deep_integrity_ok", calls=second_calls, monkeypatch=monkeypatch)
    second_summary = service.scan(scan_mode="DEEP")

    assert second_summary.scanned_count == 1
    assert second_summary.skipped_count == 0
    assert second_calls == [(str(media_path), "DEEP")]

    with session_factory() as session:
        second_check = session.scalar(select(IntegrityCheck).where(IntegrityCheck.file_instance_id == file_instance_id))
        assert second_check is not None

    assert second_check.latest_run_id != first_latest_run_id
    assert second_check.last_completed_scan_mode == "DEEP"


def test_changed_file_is_rescanned_even_when_mode_is_unchanged(session_factory, tmp_path: Path, monkeypatch) -> None:
    service = IntegrityService(session_factory)
    now = datetime(2026, 3, 28, 13, 30, tzinfo=UTC)
    content_id = uuid4()
    file_instance_id = uuid4()
    media_path = tmp_path / "clip-changed.mp4"
    media_path.write_bytes(b"before")

    with session_factory.begin() as session:
        _add_content(session, content_id=content_id, sha256_hash="d" * 64, at=now)
        _add_instance(session, file_instance_id=file_instance_id, content_id=content_id, absolute_path=str(media_path), at=now)

    first_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="first_integrity_ok", calls=first_calls, monkeypatch=monkeypatch)
    service.scan(scan_mode="FAST")

    stat_before = media_path.stat()
    media_path.write_bytes(b"after and larger")
    next_mtime = stat_before.st_mtime_ns + 1_000_000_000
    os_times = (next_mtime, next_mtime)
    media_path.touch()
    os.utime(media_path, ns=os_times)

    second_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="second_integrity_ok", calls=second_calls, monkeypatch=monkeypatch)
    second_summary = service.scan(scan_mode="FAST")

    assert second_summary.scanned_count == 1
    assert second_summary.skipped_count == 0
    assert second_calls == [(str(media_path), "FAST")]


def test_full_rescan_bypasses_skip_logic_for_all_eligible_files(session_factory, tmp_path: Path, monkeypatch) -> None:
    service = IntegrityService(session_factory)
    now = datetime(2026, 3, 28, 14, 0, tzinfo=UTC)
    first_path = tmp_path / "full-one.mp4"
    second_path = tmp_path / "full-two.mp4"
    first_path.write_bytes(b"one")
    second_path.write_bytes(b"two")
    first_content = uuid4()
    second_content = uuid4()
    first_instance = uuid4()
    second_instance = uuid4()

    with session_factory.begin() as session:
        _add_content(session, content_id=first_content, sha256_hash="e" * 64, at=now)
        _add_content(session, content_id=second_content, sha256_hash="f" * 64, at=now + timedelta(seconds=1))
        _add_instance(session, file_instance_id=first_instance, content_id=first_content, absolute_path=str(first_path), at=now)
        _add_instance(
            session,
            file_instance_id=second_instance,
            content_id=second_content,
            absolute_path=str(second_path),
            at=now + timedelta(seconds=1),
        )

    initial_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="initial_integrity_ok", calls=initial_calls, monkeypatch=monkeypatch)
    initial_summary = service.scan(scan_mode="FAST")
    assert initial_summary.scanned_count == 2

    full_rescan_calls: list[tuple[str, str]] = []
    _install_scan_stub(service, signal_type="full_rescan_ok", calls=full_rescan_calls, monkeypatch=monkeypatch)
    full_rescan_summary = service.scan(scan_mode="FAST", full_rescan=True)

    assert full_rescan_summary.eligible_file_count == 2
    assert full_rescan_summary.scanned_count == 2
    assert full_rescan_summary.skipped_count == 0
    assert full_rescan_summary.full_rescan is True
    assert sorted(full_rescan_calls) == sorted([(str(first_path), "FAST"), (str(second_path), "FAST")])
