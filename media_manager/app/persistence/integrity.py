"""Durable integrity scan and review helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from media_manager.app.persistence.base import transactional_session
from media_manager.app.persistence.models import (
    IntegrityCheck,
    IntegrityCheckRun,
    IntegrityCheckStatus,
    IntegrityReviewDecision,
    IntegrityReviewStatus,
    IntegrityRunStatus,
    IntegrityScanMode,
    IntegritySignal,
    FileInstance,
    FileInstanceStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IntegrityScanSummary:
    run_id: str
    status: str
    scan_mode: str
    eligible_file_count: int
    scanned_count: int
    skipped_count: int
    issues_found: int
    full_rescan: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "scan_mode": self.scan_mode,
            "eligible_file_count": self.eligible_file_count,
            "scanned_count": self.scanned_count,
            "skipped_count": self.skipped_count,
            "issues_found": self.issues_found,
            "full_rescan": self.full_rescan,
        }


@dataclass(frozen=True)
class _FileSnapshot:
    absolute_path: str
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class _ScanCandidate:
    instance: FileInstance
    existing_check: IntegrityCheck | None
    current_snapshot: _FileSnapshot | None
    should_scan: bool


class IntegrityService:
    """Persist integrity facts without mutating the managed filesystem."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def scan(
        self,
        *,
        scan_mode: str,
        file_instance_ids: list[UUID] | None = None,
        operation_run_id: UUID | None = None,
        on_progress: Callable[[int, int, int], None] | None = None,
        full_rescan: bool = False,
    ) -> IntegrityScanSummary:
        normalized_mode = IntegrityScanMode(scan_mode.strip().upper())
        with transactional_session(self._session_factory) as session:
            run = IntegrityCheckRun(
                operation_run_id=operation_run_id,
                scan_mode=normalized_mode.value,
                status=IntegrityRunStatus.STARTED.value,
                paths=[],
                scanned_count=0,
                issues_found=0,
                started_at=_utcnow(),
                completed_at=None,
                error_message=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(run)
            session.flush()

            instances = self._load_instances(session, file_instance_ids=file_instance_ids)
            run.paths = [row.absolute_path for row in instances]
            return self._scan_instances(
                session,
                run=run,
                instances=instances,
                on_progress=on_progress,
                full_rescan=full_rescan,
            )

    def scan_paths(
        self,
        *,
        scan_mode: str,
        absolute_paths: list[str],
        operation_run_id: UUID | None = None,
        full_rescan: bool = False,
    ) -> IntegrityScanSummary:
        normalized_mode = IntegrityScanMode(scan_mode.strip().upper())
        normalized_paths = sorted({path.strip() for path in absolute_paths if path.strip()})
        with transactional_session(self._session_factory) as session:
            run = IntegrityCheckRun(
                operation_run_id=operation_run_id,
                scan_mode=normalized_mode.value,
                status=IntegrityRunStatus.STARTED.value,
                paths=normalized_paths,
                scanned_count=0,
                issues_found=0,
                started_at=_utcnow(),
                completed_at=None,
                error_message=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(run)
            session.flush()

            instances = self._load_instances_by_paths(session, absolute_paths=normalized_paths)
            run.paths = [row.absolute_path for row in instances]
            return self._scan_instances(
                session,
                run=run,
                instances=instances,
                full_rescan=full_rescan,
            )

    def _scan_instances(
        self,
        session: Session,
        *,
        run: IntegrityCheckRun,
        instances: list[FileInstance],
        on_progress: Callable[[int, int, int], None] | None = None,
        full_rescan: bool = False,
    ) -> IntegrityScanSummary:
        normalized_mode = IntegrityScanMode(run.scan_mode)
        eligible_file_count = len(instances)
        candidates = self._build_scan_candidates(
            session,
            instances=instances,
            requested_mode=normalized_mode,
            full_rescan=full_rescan,
        )
        scan_candidates = [candidate for candidate in candidates if candidate.should_scan]
        skipped_count = eligible_file_count - len(scan_candidates)
        issues_found = 0
        scanned_count = len(scan_candidates)
        for processed_count, candidate in enumerate(scan_candidates, start=1):
            instance = candidate.instance
            result = self._scan_path(Path(instance.absolute_path), normalized_mode)
            if result["status"] != IntegrityCheckStatus.OK.value:
                issues_found += 1
            check = session.scalar(
                select(IntegrityCheck)
                .where(IntegrityCheck.file_instance_id == instance.file_instance_id)
                .with_for_update()
            )
            now = _utcnow()
            if check is None:
                check = IntegrityCheck(
                    file_instance_id=instance.file_instance_id,
                    latest_run_id=run.id,
                    status=result["status"],
                    confidence=result["confidence"],
                    readability_ok=result["readability_ok"],
                    probe_status=result["probe_status"],
                    decode_status=result["decode_status"],
                    last_completed_scan_mode=normalized_mode.value,
                    last_scanned_absolute_path=instance.absolute_path,
                    last_scanned_size_bytes=candidate.current_snapshot.size_bytes if candidate.current_snapshot is not None else None,
                    last_scanned_mtime_ns=candidate.current_snapshot.mtime_ns if candidate.current_snapshot is not None else None,
                    last_checked_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(check)
                session.flush()
            else:
                check.latest_run_id = run.id
                check.status = result["status"]
                check.confidence = result["confidence"]
                check.readability_ok = result["readability_ok"]
                check.probe_status = result["probe_status"]
                check.decode_status = result["decode_status"]
                check.last_completed_scan_mode = normalized_mode.value
                check.last_scanned_absolute_path = instance.absolute_path
                check.last_scanned_size_bytes = candidate.current_snapshot.size_bytes if candidate.current_snapshot is not None else None
                check.last_scanned_mtime_ns = candidate.current_snapshot.mtime_ns if candidate.current_snapshot is not None else None
                check.last_checked_at = now
                check.updated_at = now
                session.flush()
                session.query(IntegritySignal).filter(IntegritySignal.check_id == check.id).delete()

            for signal in result["signals"]:
                session.add(
                    IntegritySignal(
                        check_id=check.id,
                        signal_type=signal["signal_type"],
                        severity=signal["severity"],
                        details=signal["details"],
                        created_at=now,
                    )
                )
            if (
                on_progress is not None
                and scanned_count >= 100
                and processed_count < scanned_count
                and processed_count % 100 == 0
            ):
                on_progress(processed_count, scanned_count, issues_found)

        run.scanned_count = scanned_count
        run.issues_found = issues_found
        run.status = IntegrityRunStatus.COMPLETED.value
        run.completed_at = _utcnow()
        run.updated_at = _utcnow()
        return IntegrityScanSummary(
            run_id=str(run.id),
            status=run.status,
            scan_mode=run.scan_mode,
            eligible_file_count=eligible_file_count,
            scanned_count=run.scanned_count,
            skipped_count=skipped_count,
            issues_found=run.issues_found,
            full_rescan=full_rescan,
        )

    def _build_scan_candidates(
        self,
        session: Session,
        *,
        instances: list[FileInstance],
        requested_mode: IntegrityScanMode,
        full_rescan: bool,
    ) -> list[_ScanCandidate]:
        if not instances:
            return []

        existing_checks = {
            row.file_instance_id: row
            for row in session.scalars(
                select(IntegrityCheck).where(
                    IntegrityCheck.file_instance_id.in_([instance.file_instance_id for instance in instances])
                )
            ).all()
        }

        candidates: list[_ScanCandidate] = []
        for instance in instances:
            current_snapshot = self._read_file_snapshot(Path(instance.absolute_path))
            existing_check = existing_checks.get(instance.file_instance_id)
            should_scan = full_rescan or self._needs_rescan(
                existing_check=existing_check,
                requested_mode=requested_mode,
                absolute_path=instance.absolute_path,
                current_snapshot=current_snapshot,
            )
            candidates.append(
                _ScanCandidate(
                    instance=instance,
                    existing_check=existing_check,
                    current_snapshot=current_snapshot,
                    should_scan=should_scan,
                )
            )
        return candidates

    def _needs_rescan(
        self,
        *,
        existing_check: IntegrityCheck | None,
        requested_mode: IntegrityScanMode,
        absolute_path: str,
        current_snapshot: _FileSnapshot | None,
    ) -> bool:
        if existing_check is None:
            return True
        if (
            existing_check.last_completed_scan_mode is None
            or existing_check.last_scanned_absolute_path is None
            or existing_check.last_scanned_size_bytes is None
            or existing_check.last_scanned_mtime_ns is None
        ):
            return True
        if current_snapshot is None:
            return True
        if existing_check.last_scanned_absolute_path != absolute_path:
            return True
        if existing_check.last_scanned_size_bytes != current_snapshot.size_bytes:
            return True
        if existing_check.last_scanned_mtime_ns != current_snapshot.mtime_ns:
            return True
        return not self._mode_satisfies(
            existing_mode=existing_check.last_completed_scan_mode,
            requested_mode=requested_mode,
        )

    def _mode_satisfies(self, *, existing_mode: str | None, requested_mode: IntegrityScanMode) -> bool:
        if not existing_mode:
            return False
        try:
            normalized_existing = IntegrityScanMode(existing_mode.strip().upper())
        except ValueError:
            return False
        if normalized_existing == IntegrityScanMode.DEEP:
            return True
        return normalized_existing == requested_mode

    def _read_file_snapshot(self, path: Path) -> _FileSnapshot | None:
        try:
            stat_result = path.stat()
        except (FileNotFoundError, NotADirectoryError, OSError):
            return None
        if not path.is_file() or not os.access(path, os.R_OK):
            return None
        return _FileSnapshot(
            absolute_path=str(path),
            size_bytes=int(stat_result.st_size),
            mtime_ns=int(stat_result.st_mtime_ns),
        )

    def _load_instances_by_paths(
        self,
        session: Session,
        *,
        absolute_paths: list[str],
    ) -> list[FileInstance]:
        if not absolute_paths:
            return []
        stmt = (
            select(FileInstance)
            .where(
                FileInstance.status == FileInstanceStatus.ACTIVE.value,
                FileInstance.absolute_path.in_(absolute_paths),
            )
            .order_by(FileInstance.absolute_path.asc(), FileInstance.file_instance_id.asc())
        )
        return session.scalars(stmt).all()

    def set_review_decision(
        self,
        *,
        check_id: UUID,
        decision: str,
        reviewed_by: str | None = None,
    ) -> dict[str, object]:
        normalized = IntegrityReviewStatus(decision.strip().upper())
        with transactional_session(self._session_factory) as session:
            check = session.get(IntegrityCheck, check_id)
            if check is None:
                raise ValueError(f"integrity check not found: {check_id}")
            row = session.get(IntegrityReviewDecision, check_id)
            now = _utcnow()
            if row is None:
                row = IntegrityReviewDecision(
                    check_id=check_id,
                    decision=normalized.value,
                    reviewed_by=(reviewed_by or "").strip() or None,
                    reviewed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.decision = normalized.value
                row.reviewed_by = (reviewed_by or "").strip() or None
                row.reviewed_at = now
                row.updated_at = now
            return {
                "check_id": str(check_id),
                "decision": normalized.value,
                "reviewed_by": row.reviewed_by,
                "reviewed_at": now.isoformat(),
            }

    def _load_instances(
        self,
        session: Session,
        *,
        file_instance_ids: list[UUID] | None,
    ) -> list[FileInstance]:
        # No explicit IDs means resolve the default eligible active-library scope.
        stmt = select(FileInstance).where(FileInstance.status == FileInstanceStatus.ACTIVE.value)
        if file_instance_ids:
            stmt = stmt.where(FileInstance.file_instance_id.in_(file_instance_ids))
        stmt = stmt.order_by(FileInstance.absolute_path.asc(), FileInstance.file_instance_id.asc())
        return session.scalars(stmt).all()

    def _scan_path(self, path: Path, mode: IntegrityScanMode) -> dict[str, Any]:
        signals: list[dict[str, Any]] = []
        readability_ok = path.exists() and path.is_file() and os.access(path, os.R_OK)
        probe_status = "NOT_RUN"
        decode_status = "NOT_RUN"

        if not readability_ok:
            signals.append(
                {
                    "signal_type": "readability_failed",
                    "severity": "error",
                    "details": {"path": str(path), "reason": "missing_or_unreadable"},
                }
            )
            return {
                "status": IntegrityCheckStatus.BROKEN.value,
                "confidence": 1.0,
                "readability_ok": False,
                "probe_status": "SKIPPED",
                "decode_status": "SKIPPED",
                "signals": signals,
            }

        ffprobe_path = shutil.which("ffprobe")
        if not ffprobe_path:
            signals.append(
                {
                    "signal_type": "ffprobe_unavailable",
                    "severity": "warning",
                    "details": {"path": str(path)},
                }
            )
            return {
                "status": IntegrityCheckStatus.SUSPECT.value,
                "confidence": 0.35,
                "readability_ok": True,
                "probe_status": "UNAVAILABLE",
                "decode_status": "SKIPPED",
                "signals": signals,
            }

        try:
            probe = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            signals.append(
                {
                    "signal_type": "ffprobe_timeout",
                    "severity": "warning",
                    "details": {"path": str(path)},
                }
            )
            return {
                "status": IntegrityCheckStatus.SUSPECT.value,
                "confidence": 0.7,
                "readability_ok": True,
                "probe_status": "TIMEOUT",
                "decode_status": "SKIPPED",
                "signals": signals,
            }
        if probe.returncode != 0:
            probe_status = "FAILED"
            signals.append(
                {
                    "signal_type": "ffprobe_failed",
                    "severity": "error",
                    "details": {"returncode": probe.returncode, "stderr": probe.stderr.strip()[:512]},
                }
            )
            return {
                "status": IntegrityCheckStatus.BROKEN.value,
                "confidence": 0.95,
                "readability_ok": True,
                "probe_status": probe_status,
                "decode_status": "SKIPPED",
                "signals": signals,
            }

        probe_status = "OK"
        if mode == IntegrityScanMode.DEEP:
            decode_status = "SKIPPED"
            ffmpeg_path = shutil.which("ffmpeg")
            if ffmpeg_path:
                try:
                    decode = subprocess.run(
                        [
                            ffmpeg_path,
                            "-v",
                            "error",
                            "-t",
                            "3",
                            "-i",
                            str(path),
                            "-f",
                            "null",
                            "-",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=20,
                    )
                    if decode.returncode == 0:
                        decode_status = "OK"
                    else:
                        decode_status = "FAILED"
                        signals.append(
                            {
                                "signal_type": "decode_failed",
                                "severity": "warning",
                                "details": {"returncode": decode.returncode, "stderr": decode.stderr.strip()[:512]},
                            }
                        )
                except subprocess.TimeoutExpired:
                    decode_status = "TIMEOUT"
                    signals.append(
                        {
                            "signal_type": "decode_timeout",
                            "severity": "warning",
                            "details": {"path": str(path)},
                        }
                    )

        if signals:
            return {
                "status": IntegrityCheckStatus.SUSPECT.value,
                "confidence": 0.68 if any(signal["severity"] == "warning" for signal in signals) else 0.5,
                "readability_ok": True,
                "probe_status": probe_status,
                "decode_status": decode_status,
                "signals": signals,
            }

        return {
            "status": IntegrityCheckStatus.OK.value,
            "confidence": 0.0,
            "readability_ok": True,
            "probe_status": probe_status,
            "decode_status": decode_status,
            "signals": [
                {
                    "signal_type": "integrity_ok",
                    "severity": "info",
                    "details": {"path": str(path)},
                }
            ],
        }
