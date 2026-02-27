"""SQLAlchemy models for deterministic run lifecycle and failure logging."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStateDB(StrEnum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    APPLYING = "APPLYING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class FailurePhase(StrEnum):
    PLANNING = "planning"
    APPLY = "apply"


class PlannedActionType(StrEnum):
    MOVE = "MOVE"
    NOOP = "NOOP"
    MARK_DUPLICATE = "MARK_DUPLICATE"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state: Mapped[RunStateDB] = mapped_column(
        Enum(RunStateDB, name="run_state", native_enum=True),
        nullable=False,
        default=RunStateDB.CREATED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    failure_events: Mapped[list[FailureEvent]] = relationship(
        back_populates="run",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    planned_actions: Mapped[list[PlannedAction]] = relationship(
        back_populates="run",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index(
    "uq_runs_single_applying",
    Run.state,
    unique=True,
    postgresql_where=text("state = 'APPLYING'"),
)


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    phase: Mapped[FailurePhase] = mapped_column(
        Enum(
            FailurePhase,
            name="failure_phase",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    run: Mapped[Run] = relationship(back_populates="failure_events")


class ContentObject(Base):
    __tablename__ = "content_objects"

    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    files: Mapped[list[File]] = relationship(
        back_populates="content_object",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    hash: Mapped[str] = mapped_column(
        Text,
        ForeignKey("content_objects.hash", ondelete="RESTRICT"),
        nullable=False,
    )
    is_duplicate: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    original_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    content_object: Mapped[ContentObject] = relationship(back_populates="files")
    original_file: Mapped[File | None] = relationship(
        "File",
        remote_side="File.id",
        foreign_keys=[original_file_id],
    )
    planned_actions: Mapped[list[PlannedAction]] = relationship(
        back_populates="file",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_files_hash", File.hash)
Index("idx_files_original_file_id", File.original_file_id)


class PlannedAction(Base):
    __tablename__ = "planned_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    run: Mapped[Run] = relationship(back_populates="planned_actions")
    file: Mapped[File] = relationship(back_populates="planned_actions")


Index("idx_planned_actions_run_id", PlannedAction.run_id)
Index("idx_planned_actions_file_id", PlannedAction.file_id)
Index("idx_planned_actions_action_type", PlannedAction.action_type)
