from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import (
    ExifFilenameFallbackPolicy,
    FirstSeenPolicy,
    PreferRootPolicy,
    ShortestPathPolicy,
)
from media_manager.app.core.errors import CanonicalPolicyException
from media_manager.app.persistence.models import FileInstance, FileInstanceStatus


def _instance(path: str, *, seen_second: int) -> FileInstance:
    return FileInstance(
        file_instance_id=uuid.uuid4(),
        content_id=uuid.uuid4(),
        absolute_path=path,
        filesystem_id=None,
        first_seen_at=datetime(2024, 1, 1, 0, 0, seen_second, tzinfo=timezone.utc),
        last_seen_at=datetime(2024, 1, 1, 0, 0, seen_second, tzinfo=timezone.utc),
        status=FileInstanceStatus.ACTIVE.value,
        ingestion_run_id=None,
    )


def test_first_seen_policy_is_deterministic_with_shuffled_input() -> None:
    policy = FirstSeenPolicy()
    a = _instance("C:/dataset/a.jpg", seen_second=2)
    b = _instance("C:/dataset/b.jpg", seen_second=1)
    c = _instance("C:/dataset/c.jpg", seen_second=3)
    context = CanonicalContext()

    selected_1 = policy.select("content-1", [a, b, c], context)
    selected_2 = policy.select("content-1", [c, a, b], context)
    assert selected_1.file_instance_id == b.file_instance_id
    assert selected_2.file_instance_id == b.file_instance_id


def test_prefer_root_policy_prefers_matching_root_and_falls_back() -> None:
    policy = PreferRootPolicy()
    under_root = _instance("C:/archive/media/match.jpg", seen_second=5)
    outside_root_early = _instance("C:/other/early.jpg", seen_second=1)
    context = CanonicalContext(preferred_roots=(Path("C:/archive"),))

    selected = policy.select("content-2", [outside_root_early, under_root], context)
    assert selected.file_instance_id == under_root.file_instance_id

    fallback = policy.select("content-2", [outside_root_early], CanonicalContext(preferred_roots=(Path("C:/x"),)))
    assert fallback.file_instance_id == outside_root_early.file_instance_id


def test_shortest_path_policy_uses_deterministic_sort_key() -> None:
    policy = ShortestPathPolicy()
    long_path = _instance("C:/dataset/deeper/path/image.jpg", seen_second=1)
    short_path = _instance("C:/d.jpg", seen_second=5)

    selected = policy.select("content-3", [long_path, short_path], CanonicalContext())
    assert selected.file_instance_id == short_path.file_instance_id


def test_exif_filename_fallback_prefers_embedded_metadata_first() -> None:
    policy = ExifFilenameFallbackPolicy()
    a = _instance("C:/archive/no-date.jpg", seen_second=2)
    b = _instance("C:/archive/IMG_20240214.jpg", seen_second=1)

    selected = policy.select(
        "content-4",
        [a, b],
        CanonicalContext(taken_dt_source="metadata", filename_evidence_instance_ids=frozenset({str(b.file_instance_id)})),
    )

    assert selected.file_instance_id == b.file_instance_id


def test_exif_filename_fallback_prefers_filename_over_filesystem_only() -> None:
    policy = ExifFilenameFallbackPolicy()
    filename_candidate = _instance("C:/archive/IMG_20240214.jpg", seen_second=3)
    fs_only_candidate = _instance("C:/archive/copy.jpg", seen_second=1)

    selected = policy.select(
        "content-5",
        [fs_only_candidate, filename_candidate],
        CanonicalContext(
            taken_dt_source="filesystem",
            filename_evidence_instance_ids=frozenset({str(filename_candidate.file_instance_id)}),
        ),
    )

    assert selected.file_instance_id == filename_candidate.file_instance_id


def test_exif_filename_fallback_applies_preferred_root_after_evidence_quality() -> None:
    policy = ExifFilenameFallbackPolicy()
    filename_candidate = _instance("C:/other/IMG_20240214.jpg", seen_second=5)
    preferred_root_fs_only = _instance("C:/archive/copy.jpg", seen_second=1)

    selected = policy.select(
        "content-6",
        [preferred_root_fs_only, filename_candidate],
        CanonicalContext(
            preferred_roots=(Path("C:/archive"),),
            taken_dt_source="filesystem",
            filename_evidence_instance_ids=frozenset({str(filename_candidate.file_instance_id)}),
        ),
    )

    assert selected.file_instance_id == filename_candidate.file_instance_id


def test_exif_filename_fallback_is_deterministic_with_shuffled_input() -> None:
    policy = ExifFilenameFallbackPolicy()
    a = _instance("C:/archive/a.jpg", seen_second=3)
    b = _instance("C:/archive/b.jpg", seen_second=1)
    c = _instance("C:/archive/IMG_20240214.jpg", seen_second=2)
    context = CanonicalContext(
        taken_dt_source="filesystem",
        filename_evidence_instance_ids=frozenset({str(c.file_instance_id)}),
    )

    selected_1 = policy.select("content-7", [a, b, c], context)
    selected_2 = policy.select("content-7", [c, a, b], context)
    assert selected_1.file_instance_id == c.file_instance_id
    assert selected_2.file_instance_id == c.file_instance_id


def test_policies_raise_for_empty_candidate_list() -> None:
    context = CanonicalContext()
    with pytest.raises(CanonicalPolicyException):
        FirstSeenPolicy().select("x", [], context)
    with pytest.raises(CanonicalPolicyException):
        PreferRootPolicy().select("x", [], context)
    with pytest.raises(CanonicalPolicyException):
        ShortestPathPolicy().select("x", [], context)
    with pytest.raises(CanonicalPolicyException):
        ExifFilenameFallbackPolicy().select("x", [], context)

