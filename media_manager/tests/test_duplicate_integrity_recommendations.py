from __future__ import annotations

from media_manager.app.persistence.duplicate_integrity_recommendations import (
    DuplicateRecommendationFacts,
    derive_duplicate_recommendation,
)


def _facts(**overrides: object) -> DuplicateRecommendationFacts:
    base = DuplicateRecommendationFacts(
        keep_identity_known=True,
        keep_integrity_status="OK",
        extra_active_count=2,
        extra_healthy_count=2,
        extra_suspect_count=0,
        extra_broken_count=0,
        extra_unknown_count=0,
        review_status="looks_right",
        review_is_stale=False,
        integrity_is_stale=False,
        already_in_bin=False,
        restore_expired=False,
    )
    return DuplicateRecommendationFacts(**{**base.__dict__, **overrides})


def test_recommendation_precedence_restore_expired_beats_already_in_bin() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(already_in_bin=True, restore_expired=True, keep_identity_known=False, keep_integrity_status="BROKEN")
    )

    assert recommendation.state == "EXPIRED_IN_BIN"
    assert recommendation.primary_reason_code == "BIN_RESTORE_EXPIRED"


def test_recommendation_precedence_already_in_bin_beats_do_not_move() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(already_in_bin=True, keep_identity_known=False, keep_integrity_status="BROKEN")
    )

    assert recommendation.state == "ALREADY_IN_BIN"
    assert recommendation.primary_reason_code == "GROUP_ALREADY_IN_BIN"


def test_recommendation_precedence_do_not_move_beats_review_required() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(keep_integrity_status="BROKEN", review_is_stale=True, review_status="needs_review")
    )

    assert recommendation.state == "DO_NOT_MOVE"
    assert recommendation.primary_reason_code == "KEEP_COPY_UNHEALTHY"


def test_recommendation_precedence_review_required_beats_safe_to_move() -> None:
    recommendation = derive_duplicate_recommendation(_facts(review_is_stale=True))

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.primary_reason_code == "REVIEW_STALE"


def test_healthy_keep_and_unhealthy_extras_recommend_safe_to_move() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(extra_healthy_count=0, extra_suspect_count=1, extra_broken_count=1)
    )

    assert recommendation.state == "SAFE_TO_MOVE_EXTRAS"
    assert recommendation.primary_reason_code == "EXTRA_COPIES_UNHEALTHY_ONLY"
    assert recommendation.reason_codes == ("EXTRA_COPIES_UNHEALTHY_ONLY",)


def test_unhealthy_keep_and_healthy_extras_recommend_do_not_move() -> None:
    recommendation = derive_duplicate_recommendation(_facts(keep_integrity_status="BROKEN"))

    assert recommendation.state == "DO_NOT_MOVE"
    assert recommendation.reason_codes == ("KEEP_COPY_UNHEALTHY",)


def test_keep_unknown_recommends_review_required() -> None:
    recommendation = derive_duplicate_recommendation(_facts(keep_integrity_status=None))

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.reason_codes == ("KEEP_COPY_UNKNOWN",)


def test_missing_canonical_mapping_recommends_do_not_move() -> None:
    recommendation = derive_duplicate_recommendation(_facts(keep_identity_known=False, keep_integrity_status=None))

    assert recommendation.state == "DO_NOT_MOVE"
    assert recommendation.reason_codes == ("CANONICAL_MAPPING_MISSING",)


def test_mixed_extras_recommend_review_required() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(extra_healthy_count=1, extra_suspect_count=0, extra_broken_count=1)
    )

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.reason_codes == ("MIXED_EXTRA_HEALTH",)


def test_stale_review_recommends_review_required() -> None:
    recommendation = derive_duplicate_recommendation(_facts(review_is_stale=True))

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.reason_codes == ("REVIEW_STALE",)


def test_stale_integrity_evidence_recommends_review_required() -> None:
    recommendation = derive_duplicate_recommendation(_facts(integrity_is_stale=True))

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.reason_codes == ("INTEGRITY_EVIDENCE_STALE",)


def test_no_active_extras_recommends_do_not_move() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(
            extra_active_count=0,
            extra_healthy_count=0,
            extra_suspect_count=0,
            extra_broken_count=0,
            extra_unknown_count=0,
        )
    )

    assert recommendation.state == "DO_NOT_MOVE"
    assert recommendation.reason_codes == ("NO_ACTIVE_EXTRAS",)


def test_already_in_bin_recommends_already_in_bin() -> None:
    recommendation = derive_duplicate_recommendation(_facts(already_in_bin=True))

    assert recommendation.state == "ALREADY_IN_BIN"
    assert recommendation.reason_codes == ("GROUP_ALREADY_IN_BIN",)


def test_restore_expired_recommends_expired_in_bin() -> None:
    recommendation = derive_duplicate_recommendation(_facts(already_in_bin=True, restore_expired=True))

    assert recommendation.state == "EXPIRED_IN_BIN"
    assert recommendation.reason_codes == ("BIN_RESTORE_EXPIRED",)


def test_reason_codes_are_stable_and_primary_reason_is_deterministic() -> None:
    recommendation = derive_duplicate_recommendation(
        _facts(
            review_status="needs_review",
            review_is_stale=True,
            keep_integrity_status="SUSPECT",
            extra_healthy_count=1,
            extra_broken_count=1,
            integrity_is_stale=True,
        )
    )

    assert recommendation.state == "REVIEW_REQUIRED"
    assert recommendation.primary_reason_code == "REVIEW_REQUIRED_BY_OPERATOR_STATE"
    assert recommendation.reason_codes == (
        "REVIEW_REQUIRED_BY_OPERATOR_STATE",
        "REVIEW_STALE",
        "KEEP_COPY_SUSPECT",
        "MIXED_EXTRA_HEALTH",
        "INTEGRITY_EVIDENCE_STALE",
    )
