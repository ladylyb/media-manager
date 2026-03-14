from __future__ import annotations

import logging
import os

from media_manager.app.core.config import load_environment

_CONFIGURED = False


class _StructuredDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "-"
        if not hasattr(record, "phase"):
            record.phase = "-"
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
        if not hasattr(record, "sequence_no"):
            record.sequence_no = "-"
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
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "run_id=%(run_id)s phase=%(phase)s action_type=%(action_type)s "
            "filename=%(filename)s file_hash=%(file_hash)s action=%(action)s "
            "codes_extracted=%(codes_extracted)s "
            "scanned=%(scanned)s supported=%(supported)s skipped=%(skipped)s "
            "moves=%(moves)s duplicates=%(duplicates)s noop=%(noop)s "
            "applied=%(applied)s errors=%(errors)s "
            "duration_s=%(duration_s)s files_count=%(files_count)s batch_size=%(batch_size)s "
            "cache_hits=%(cache_hits)s cache_misses=%(cache_misses)s "
            "content_id=%(content_id)s canonical_instance_id=%(canonical_instance_id)s "
            "policy_name=%(policy_name)s policy_version=%(policy_version)s "
            "recompute_mode=%(recompute_mode)s sequence_no=%(sequence_no)s %(message)s"
        ),
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addFilter(_StructuredDefaultsFilter())
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s "
        "run_id=%(run_id)s phase=%(phase)s action_type=%(action_type)s "
        "filename=%(filename)s file_hash=%(file_hash)s action=%(action)s "
        "codes_extracted=%(codes_extracted)s "
        "scanned=%(scanned)s supported=%(supported)s skipped=%(skipped)s "
        "moves=%(moves)s duplicates=%(duplicates)s noop=%(noop)s "
        "applied=%(applied)s errors=%(errors)s "
        "duration_s=%(duration_s)s files_count=%(files_count)s batch_size=%(batch_size)s "
        "cache_hits=%(cache_hits)s cache_misses=%(cache_misses)s "
        "content_id=%(content_id)s canonical_instance_id=%(canonical_instance_id)s "
        "policy_name=%(policy_name)s policy_version=%(policy_version)s "
        "recompute_mode=%(recompute_mode)s sequence_no=%(sequence_no)s %(message)s",
        defaults={
            "run_id": "-",
            "phase": "-",
            "action_type": "-",
            "filename": "-",
            "file_hash": "-",
            "action": "-",
            "codes_extracted": "-",
            "scanned": "-",
            "supported": "-",
            "skipped": "-",
            "moves": "-",
            "duplicates": "-",
            "noop": "-",
            "applied": "-",
            "errors": "-",
            "duration_s": "-",
            "files_count": "-",
            "batch_size": "-",
            "cache_hits": "-",
            "cache_misses": "-",
            "content_id": "-",
            "canonical_instance_id": "-",
            "policy_name": "-",
            "policy_version": "-",
            "recompute_mode": "-",
            "sequence_no": "-",
        },
    )
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
