"""SQLAlchemy models for deterministic run lifecycle and failure logging."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    SKIP = "SKIP"
    RENAME = "RENAME"
    COLLISION_RESOLVED = "COLLISION_RESOLVED"


class FileInstanceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


class CanonicalRecomputeMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    APPLY = "APPLY"


class CanonicalRecomputeStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"


class CanonicalRecomputeItemResult(StrEnum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"


class TagSource(StrEnum):
    AI = "ai"
    MANUAL = "manual"
    IMPORT = "import"
    SYSTEM = "system"


class TagEnrichmentScope(StrEnum):
    ALL = "ALL"
    SINGLE = "SINGLE"


class TagEnrichmentStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class TagEnrichmentItemResult(StrEnum):
    UNCHANGED = "UNCHANGED"
    UPDATED = "UPDATED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


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
    apply_audit_runs: Mapped[list[ApplyAuditRun]] = relationship(
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
    """Legacy table retained for one transition release."""

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
    """Legacy table retained for one transition release."""

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


Index("idx_files_hash", File.hash)
Index("idx_files_original_file_id", File.original_file_id)


class FileContent(Base):
    __tablename__ = "file_contents"

    content_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sha256_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    canonical_file_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_instances.file_instance_id", ondelete="SET NULL"),
        nullable=True,
    )

    instances: Mapped[list[FileInstance]] = relationship(
        back_populates="content",
        cascade="save-update, merge",
        passive_deletes=True,
        foreign_keys="FileInstance.content_id",
    )
    canonical_instance: Mapped[FileInstance | None] = relationship(
        "FileInstance",
        foreign_keys=[canonical_file_instance_id],
    )
    metadata_rows: Mapped[list[MediaMetadata]] = relationship(
        back_populates="content",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    canonical_assignments: Mapped[list[CanonicalAssignment]] = relationship(
        back_populates="content",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    canonical_tags: Mapped[list[CanonicalTag]] = relationship(
        back_populates="canonical",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    tag_enrichment_items: Mapped[list[TagEnrichmentItem]] = relationship(
        back_populates="canonical",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_file_contents_sha256_hash", FileContent.sha256_hash)
Index("idx_file_contents_canonical_instance", FileContent.canonical_file_instance_id)


class FileInstance(Base):
    __tablename__ = "file_instances"

    file_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="CASCADE"),
        nullable=False,
    )
    absolute_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    filesystem_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default=FileInstanceStatus.ACTIVE.value)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    content: Mapped[FileContent] = relationship(back_populates="instances", foreign_keys=[content_id])
    planned_actions: Mapped[list[PlannedAction]] = relationship(
        back_populates="file_instance",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    canonical_assignments: Mapped[list[CanonicalAssignment]] = relationship(
        back_populates="canonical_instance",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_file_instances_content_id", FileInstance.content_id)
Index("idx_file_instances_absolute_path", FileInstance.absolute_path)
Index("idx_file_instances_status", FileInstance.status)


class CanonicalAssignment(Base):
    __tablename__ = "canonical_assignments"

    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_instances.file_instance_id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    content: Mapped[FileContent] = relationship(back_populates="canonical_assignments")
    canonical_instance: Mapped[FileInstance] = relationship(back_populates="canonical_assignments")


Index("idx_canonical_assignments_content_id", CanonicalAssignment.content_id)
Index("idx_canonical_assignments_instance_id", CanonicalAssignment.canonical_instance_id)
Index(
    "idx_canonical_assignments_latest",
    CanonicalAssignment.content_id,
    CanonicalAssignment.assigned_at.desc(),
    CanonicalAssignment.assignment_id.desc(),
)


class CanonicalRecomputeRun(Base):
    __tablename__ = "canonical_recompute_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[CanonicalRecomputeItem]] = relationship(
        back_populates="run",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_canonical_recompute_runs_started_at", CanonicalRecomputeRun.started_at)


class CanonicalRecomputeItem(Base):
    __tablename__ = "canonical_recompute_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_recompute_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="CASCADE"),
        nullable=False,
    )
    old_canonical_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    new_canonical_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    result: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    run: Mapped[CanonicalRecomputeRun] = relationship(back_populates="items")


Index("idx_canonical_recompute_items_run_id", CanonicalRecomputeItem.run_id)
Index("idx_canonical_recompute_items_content_id", CanonicalRecomputeItem.content_id)
Index("uq_canonical_recompute_items_run_sequence", CanonicalRecomputeItem.run_id, CanonicalRecomputeItem.sequence_no, unique=True)


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
        ForeignKey("file_instances.file_instance_id", ondelete="RESTRICT"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    run: Mapped[Run] = relationship(back_populates="planned_actions")
    file_instance: Mapped[FileInstance] = relationship(back_populates="planned_actions")
    apply_audit_items: Mapped[list[ApplyAuditItem]] = relationship(
        back_populates="planned_action",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_planned_actions_run_id", PlannedAction.run_id)
Index("idx_planned_actions_file_id", PlannedAction.file_id)
Index("idx_planned_actions_action_type", PlannedAction.action_type)


class ApplyAuditRun(Base):
    __tablename__ = "apply_audit_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    applied_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    skipped_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    collision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship(back_populates="apply_audit_runs")
    items: Mapped[list[ApplyAuditItem]] = relationship(
        back_populates="audit_run",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_apply_audit_runs_run_id", ApplyAuditRun.run_id)


class ApplyAuditItem(Base):
    __tablename__ = "apply_audit_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apply_audit_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    planned_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("planned_actions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    audit_run: Mapped[ApplyAuditRun] = relationship(back_populates="items")
    planned_action: Mapped[PlannedAction] = relationship(back_populates="apply_audit_items")


Index("idx_apply_audit_items_run_id", ApplyAuditItem.run_id)
Index("idx_apply_audit_items_planned_action_id", ApplyAuditItem.planned_action_id)


class MetadataCode(Base):
    __tablename__ = "metadata_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_type: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    metadata_rows: Mapped[list[MediaMetadata]] = relationship(
        back_populates="code",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class MediaMetadata(Base):
    __tablename__ = "media_metadata"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="RESTRICT"),
        nullable=False,
    )
    code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metadata_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decode_value: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    content: Mapped[FileContent] = relationship(back_populates="metadata_rows")
    code: Mapped[MetadataCode] = relationship(back_populates="metadata_rows")


Index("idx_media_metadata_content_id", MediaMetadata.content_id)
Index("idx_media_metadata_code_id", MediaMetadata.code_id)
Index("uq_media_metadata_content_code", MediaMetadata.content_id, MediaMetadata.code_id, unique=True)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_tags_normalized_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_tags_name_nonempty"),
        CheckConstraint("length(trim(normalized_name)) > 0", name="ck_tags_normalized_name_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    canonical_links: Mapped[list[CanonicalTag]] = relationship(
        back_populates="tag",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class CanonicalTag(Base):
    __tablename__ = "canonical_tags"
    __table_args__ = (
        UniqueConstraint("canonical_id", "tag_id", "source", name="uq_canonical_tags_canonical_tag_source"),
        CheckConstraint(
            "source IN ('ai','manual','import','system')",
            name="ck_canonical_tags_source",
        ),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_canonical_tags_confidence_range",
        ),
        CheckConstraint("enrichment_version > 0", name="ck_canonical_tags_enrichment_version_positive"),
    )

    canonical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    enrichment_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    canonical: Mapped[FileContent] = relationship(back_populates="canonical_tags")
    tag: Mapped[Tag] = relationship(back_populates="canonical_links")


Index("idx_canonical_tags_canonical_id", CanonicalTag.canonical_id)
Index("idx_canonical_tags_tag_id", CanonicalTag.tag_id)


class TagEnrichmentRun(Base):
    __tablename__ = "tag_enrichment_runs"
    __table_args__ = (
        CheckConstraint("scope IN ('ALL','SINGLE')", name="ck_tag_enrichment_runs_scope"),
        CheckConstraint(
            "source IN ('ai','manual','import','system')",
            name="ck_tag_enrichment_runs_source",
        ),
        CheckConstraint("batch_size > 0", name="ck_tag_enrichment_runs_batch_size_positive"),
        CheckConstraint(
            "status IN ('STARTED','COMPLETED','COMPLETED_WITH_ERRORS','FAILED')",
            name="ck_tag_enrichment_runs_status",
        ),
        CheckConstraint(
            "number_of_items_processed >= 0",
            name="ck_tag_enrichment_runs_items_processed_nonnegative",
        ),
        CheckConstraint("failed_items >= 0", name="ck_tag_enrichment_runs_failed_items_nonnegative"),
        CheckConstraint("duration_ms >= 0", name="ck_tag_enrichment_runs_duration_ms_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    target_canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    number_of_items_processed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    average_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    failed_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[TagEnrichmentItem]] = relationship(
        back_populates="run",
        cascade="save-update, merge",
        passive_deletes=True,
    )


Index("idx_tag_enrichment_runs_started_at", TagEnrichmentRun.started_at)
Index("idx_tag_enrichment_runs_status", TagEnrichmentRun.status)


class TagEnrichmentItem(Base):
    __tablename__ = "tag_enrichment_items"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_tag_enrichment_items_run_sequence"),
        UniqueConstraint("run_id", "canonical_id", name="uq_tag_enrichment_items_run_canonical"),
        CheckConstraint(
            "result IN ('UNCHANGED','UPDATED','FAILED','SKIPPED')",
            name="ck_tag_enrichment_items_result",
        ),
        CheckConstraint(
            "tags_emitted_count >= 0",
            name="ck_tag_enrichment_items_tags_emitted_count_nonnegative",
        ),
        CheckConstraint("duration_ms >= 0", name="ck_tag_enrichment_items_duration_ms_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tag_enrichment_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_contents.content_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    tags_emitted_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    average_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[TagEnrichmentRun] = relationship(back_populates="items")
    canonical: Mapped[FileContent] = relationship(back_populates="tag_enrichment_items")


Index("idx_tag_enrichment_items_run_id", TagEnrichmentItem.run_id)
Index("idx_tag_enrichment_items_canonical_id", TagEnrichmentItem.canonical_id)


class OperatorPolicySetting(Base):
    __tablename__ = "operator_policy_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    selected_policy: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_roots_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default=text("'[]'"))
    recanonicalization_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
