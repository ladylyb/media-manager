from __future__ import annotations

import json
from pathlib import Path


def test_manual_qa_fixture_layout_is_present() -> None:
    root = Path("testdata/manual-qa/media-manager-v1")
    expected_dirs = [
        "00_README_EXPECTATIONS",
        "01_already_canonical_noop",
        "02_inbox_moves_photos",
        "03_inbox_moves_videos",
        "04_exact_duplicates",
        "05_unsupported_and_noise",
        "06_collision_targets",
        "07_unknown_date_and_mixed_metadata",
    ]

    assert root.exists()
    for relative in expected_dirs:
        assert (root / relative).is_dir(), relative


def test_manual_qa_fixture_manifest_has_expected_counts() -> None:
    manifest = json.loads(Path("testdata/manual-qa/media-manager-v1/fixture_manifest.json").read_text(encoding="utf-8"))

    scenario_counts = {
        "01_already_canonical_noop": (4, 4),
        "02_inbox_moves_photos": (7, 7),
        "03_inbox_moves_videos": (4, 4),
        "04_exact_duplicates": (6, 6),
        "05_unsupported_and_noise": (5, 0),
        "06_collision_targets": (4, 4),
        "07_unknown_date_and_mixed_metadata": (4, 4),
    }

    for scenario, (file_count, supported_count) in scenario_counts.items():
        data = manifest["scenarios"][scenario]
        assert data["file_count"] == file_count
        assert data["supported_count"] == supported_count
