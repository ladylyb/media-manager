from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.core.errors import CanonicalPolicyException
from media_manager.app.persistence.models import FileInstance


class CanonicalPolicy(Protocol):
    name: str
    version: str

    def select(
        self,
        content_id: str,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance: ...


def _uuid_key(value: uuid.UUID) -> str:
    return str(value)


def _first_seen_key(instance: FileInstance) -> tuple[object, str]:
    return (instance.first_seen_at, _uuid_key(instance.file_instance_id))


def _deterministic_first_seen(instances: list[FileInstance]) -> FileInstance:
    if not instances:
        raise CanonicalPolicyException("Cannot select canonical instance from an empty candidate list.")
    return min(instances, key=_first_seen_key)


def _is_under_roots(absolute_path: str, roots: tuple[Path, ...]) -> bool:
    if not roots:
        return False
    candidate = Path(absolute_path).resolve(strict=False)
    for root in roots:
        normalized_root = root.resolve(strict=False)
        try:
            candidate.relative_to(normalized_root)
            return True
        except ValueError:
            continue
    return False


class FirstSeenPolicy:
    name = "FIRST_SEEN"
    version = "v1"

    def select(
        self,
        content_id: str,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance:
        del content_id, context
        return _deterministic_first_seen(instances)


class PreferRootPolicy:
    name = "PREFER_ROOT"
    version = "v1"

    def select(
        self,
        content_id: str,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance:
        del content_id
        if not instances:
            raise CanonicalPolicyException("Cannot select canonical instance from an empty candidate list.")
        root_matches = [
            instance
            for instance in instances
            if _is_under_roots(instance.absolute_path, context.preferred_roots)
        ]
        if root_matches:
            return _deterministic_first_seen(root_matches)
        return _deterministic_first_seen(instances)


class ShortestPathPolicy:
    name = "SHORTEST_PATH"
    version = "v1"

    def select(
        self,
        content_id: str,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance:
        del content_id, context
        if not instances:
            raise CanonicalPolicyException("Cannot select canonical instance from an empty candidate list.")
        return min(
            instances,
            key=lambda instance: (
                len(instance.absolute_path),
                instance.absolute_path,
                instance.first_seen_at,
                _uuid_key(instance.file_instance_id),
            ),
        )


class ExifFilenameFallbackPolicy:
    name = "EXIF_FILENAME_FALLBACK"
    version = "v1"

    def select(
        self,
        content_id: str,
        instances: list[FileInstance],
        context: CanonicalContext,
    ) -> FileInstance:
        del content_id
        if not instances:
            raise CanonicalPolicyException("Cannot select canonical instance from an empty candidate list.")

        def evidence_rank(instance: FileInstance) -> int:
            if context.taken_dt_source == "metadata":
                return 0
            if _uuid_key(instance.file_instance_id) in context.filename_evidence_instance_ids:
                return 1
            return 2

        return min(
            instances,
            key=lambda instance: (
                evidence_rank(instance),
                0 if _is_under_roots(instance.absolute_path, context.preferred_roots) else 1,
                instance.first_seen_at,
                _uuid_key(instance.file_instance_id),
            ),
        )

