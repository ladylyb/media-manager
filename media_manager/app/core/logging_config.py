from __future__ import annotations

import logging
import os

from media_manager.app.core.config import load_environment

_CONFIGURED = False

_STRUCTURED_FIELDS = (
    "run_id",
    "phase",
    "stage",
    "status",
    "action_type",
    "action",
    "from",
    "to",
    "processed_count",
    "total_count",
    "progress_percent",
    "elapsed_seconds",
    "throughput_fps",
    "duration_s",
    "duration_ms",
    "files_count",
    "batch_size",
    "scanned",
    "supported",
    "skipped",
    "moves",
    "duplicates",
    "noop",
    "applied",
    "errors",
    "cache_hits",
    "cache_misses",
    "content_id",
    "canonical_instance_id",
    "policy_name",
    "policy_version",
    "recompute_mode",
    "scope",
    "source",
    "sequence_no",
    "summary",
    "path",
    "trace_entries",
    "batch_offset",
    "batch_count",
    "failed_items",
    "planned_action_id",
    "file_instance_id",
    "collision_mode",
    "filename",
    "file_hash",
    "codes_extracted",
)


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        timestamp = self.formatTime(record, self.datefmt)
        structured_parts: list[str] = []
        for field in _STRUCTURED_FIELDS:
            value = record.__dict__.get(field)
            if value in (None, "", "-"):
                continue
            structured_parts.append(f"{field}={value}")

        base = [timestamp, record.levelname, record.name]
        if structured_parts:
            base.extend(structured_parts)
        base.append(record.message)
        message = " ".join(base)

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                message = f"{message}\n{record.exc_text}"
        return message


class _StructuredDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "-"
        if not hasattr(record, "phase"):
            record.phase = "-"
        if not hasattr(record, "stage"):
            record.stage = "-"
        if not hasattr(record, "status"):
            record.status = "-"
        if not hasattr(record, "action_type"):
            record.action_type = "-"
        if not hasattr(record, "filename"):
            record.filename = "-"
        if not hasattr(record, "action"):
            record.action = "-"
        if not hasattr(record, "file_hash"):
            record.file_hash = "-"
        if not hasattr(record, "codes_extracted"):
            record.codes_extracted = "-"
        if not hasattr(record, "scanned"):
            record.scanned = "-"
        if not hasattr(record, "supported"):
            record.supported = "-"
        if not hasattr(record, "skipped"):
            record.skipped = "-"
        if not hasattr(record, "moves"):
            record.moves = "-"
        if not hasattr(record, "duplicates"):
            record.duplicates = "-"
        if not hasattr(record, "noop"):
            record.noop = "-"
        if not hasattr(record, "errors"):
            record.errors = "-"
        if not hasattr(record, "applied"):
            record.applied = "-"
        if not hasattr(record, "duration_s"):
            record.duration_s = "-"
        if not hasattr(record, "files_count"):
            record.files_count = "-"
        if not hasattr(record, "batch_size"):
            record.batch_size = "-"
        if not hasattr(record, "cache_hits"):
            record.cache_hits = "-"
        if not hasattr(record, "cache_misses"):
            record.cache_misses = "-"
        if not hasattr(record, "content_id"):
            record.content_id = "-"
        if not hasattr(record, "canonical_instance_id"):
            record.canonical_instance_id = "-"
        if not hasattr(record, "policy_name"):
            record.policy_name = "-"
        if not hasattr(record, "policy_version"):
            record.policy_version = "-"
        if not hasattr(record, "recompute_mode"):
            record.recompute_mode = "-"
        if not hasattr(record, "scope"):
            record.scope = "-"
        if not hasattr(record, "source"):
            record.source = "-"
        if not hasattr(record, "sequence_no"):
            record.sequence_no = "-"
        if not hasattr(record, "from"):
            record.__dict__["from"] = "-"
        if not hasattr(record, "to"):
            record.to = "-"
        if not hasattr(record, "processed_count"):
            record.processed_count = "-"
        if not hasattr(record, "total_count"):
            record.total_count = "-"
        if not hasattr(record, "progress_percent"):
            record.progress_percent = "-"
        if not hasattr(record, "elapsed_seconds"):
            record.elapsed_seconds = "-"
        if not hasattr(record, "throughput_fps"):
            record.throughput_fps = "-"
        if not hasattr(record, "duration_ms"):
            record.duration_ms = "-"
        if not hasattr(record, "summary"):
            record.summary = "-"
        if not hasattr(record, "path"):
            record.path = "-"
        if not hasattr(record, "trace_entries"):
            record.trace_entries = "-"
        if not hasattr(record, "batch_offset"):
            record.batch_offset = "-"
        if not hasattr(record, "batch_count"):
            record.batch_count = "-"
        if not hasattr(record, "failed_items"):
            record.failed_items = "-"
        if not hasattr(record, "planned_action_id"):
            record.planned_action_id = "-"
        if not hasattr(record, "file_instance_id"):
            record.file_instance_id = "-"
        if not hasattr(record, "collision_mode"):
            record.collision_mode = "-"
        return True


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    load_environment()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(message)s",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addFilter(_StructuredDefaultsFilter())
    formatter = _StructuredFormatter()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
