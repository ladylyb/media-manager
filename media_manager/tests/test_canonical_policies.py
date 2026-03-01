from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from media_manager.app.canonical.context import CanonicalContext
from media_manager.app.canonical.policies import FirstSeenPolicy, PreferRootPolicy, ShortestPathPolicy
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


def test_policies_raise_for_empty_candidate_list() -> None:
    context = CanonicalContext()
    with pytest.raises(CanonicalPolicyException):
        FirstSeenPolicy().select("x", [], context)
    with pytest.raises(CanonicalPolicyException):
        PreferRootPolicy().select("x", [], context)
    with pytest.raises(CanonicalPolicyException):
        ShortestPathPolicy().select("x", [], context)

