from __future__ import annotations

import pytest

from media_manager.app.persistence.tag_normalization import normalize_tag_list, normalize_tag_name


def test_normalize_tag_name_trims_lowercases_and_collapses_spaces() -> None:
    assert normalize_tag_name("  SUMMER    Trip  ") == "summer trip"


def test_normalize_tag_name_nfkc_normalizes_unicode_forms() -> None:
    assert normalize_tag_name("Ｆｏｏ　Ｂａｒ") == "foo bar"


def test_normalize_tag_name_punctuation_removal_toggle() -> None:
    assert normalize_tag_name("city-life!") == "city-life!"
    assert normalize_tag_name("city-life!", remove_punctuation=True) == "citylife"


def test_normalize_tag_name_punctuation_removal_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIA_MANAGER_TAG_NORMALIZATION_REMOVE_PUNCTUATION", "true")
    assert normalize_tag_name("road-trip?!") == "roadtrip"


def test_normalize_tag_name_rejects_empty_or_whitespace_only() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        normalize_tag_name("   ")


def test_normalize_tag_list_is_sorted_unique_and_deterministic() -> None:
    tags = ["  Travel ", "travel", "Ｆｏｏ", "foo", "road   trip"]
    assert normalize_tag_list(tags) == ["foo", "road trip", "travel"]
