from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DuplicateRecommendationLifecycleContext:
    already_in_bin: bool
    restore_expired: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "already_in_bin": self.already_in_bin,
            "restore_expired": self.restore_expired,
        }


@dataclass(frozen=True)
class DuplicateRecommendationKeepSummary:
    identity_status: str
    integrity_status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "identity_status": self.identity_status,
            "integrity_status": self.integrity_status,
        }


@dataclass(frozen=True)
class DuplicateRecommendationExtraSummary:
    health_class: str
    active_count: int
    healthy_count: int
    suspect_count: int
    broken_count: int
    unknown_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "health_class": self.health_class,
            "active_count": self.active_count,
            "healthy_count": self.healthy_count,
            "suspect_count": self.suspect_count,
            "broken_count": self.broken_count,
            "unknown_count": self.unknown_count,
        }


@dataclass(frozen=True)
class DuplicateRecommendation:
    state: str
    classification: str
    primary_reason_code: str
    reason_codes: tuple[str, ...]
    operator_explanation: str
    review_is_stale: bool
    integrity_is_stale: bool
    lifecycle_context: DuplicateRecommendationLifecycleContext
    keep_summary: DuplicateRecommendationKeepSummary
    extra_summary: DuplicateRecommendationExtraSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "classification": self.classification,
            "primary_reason_code": self.primary_reason_code,
            "reason_codes": list(self.reason_codes),
            "operator_explanation": self.operator_explanation,
            "review_is_stale": self.review_is_stale,
            "integrity_is_stale": self.integrity_is_stale,
            "lifecycle_context": self.lifecycle_context.to_dict(),
            "keep_summary": self.keep_summary.to_dict(),
            "extra_summary": self.extra_summary.to_dict(),
        }


@dataclass(frozen=True)
class DuplicateRecommendationFacts:
    keep_identity_known: bool
    keep_integrity_status: str | None
    extra_active_count: int
    extra_healthy_count: int
    extra_suspect_count: int
    extra_broken_count: int
    extra_unknown_count: int
    review_status: str | None
    review_is_stale: bool
    integrity_is_stale: bool
    already_in_bin: bool
    restore_expired: bool


def _normalize_keep_integrity_status(*, keep_identity_known: bool, keep_integrity_status: str | None) -> str:
    if not keep_identity_known:
        return "IDENTITY_MISSING"
    if keep_integrity_status in {"OK", "SUSPECT", "BROKEN"}:
        return keep_integrity_status
    return "UNKNOWN"


def _classify_extra_health(facts: DuplicateRecommendationFacts) -> str:
    if facts.extra_active_count <= 0:
        return "NO_ACTIVE_EXTRAS"
    if facts.extra_unknown_count > 0:
        return "EXTRAS_UNKNOWN"
    if facts.extra_healthy_count > 0 and (facts.extra_suspect_count > 0 or facts.extra_broken_count > 0):
        return "EXTRAS_MIXED_HEALTH"
    if facts.extra_healthy_count > 0 and facts.extra_suspect_count == 0 and facts.extra_broken_count == 0:
        return "EXTRAS_ALL_HEALTHY"
    if facts.extra_healthy_count == 0 and (facts.extra_suspect_count > 0 or facts.extra_broken_count > 0):
        return "EXTRAS_ALL_UNHEALTHY"
    return "EXTRAS_UNKNOWN"


def _classification_for_state(state: str) -> str:
    if state == "DO_NOT_MOVE":
        return "BLOCK"
    if state == "REVIEW_REQUIRED":
        return "WARN"
    return "INFO"


def _operator_explanation(primary_reason_code: str) -> str:
    return {
        "BIN_RESTORE_EXPIRED": "This group is already in the bin and the restore window has expired.",
        "GROUP_ALREADY_IN_BIN": "This group is already in the bin. Manage it there instead of moving it again.",
        "CANONICAL_MAPPING_MISSING": "The keep copy is not clearly identified. Resolve canonical mapping first.",
        "KEEP_COPY_UNHEALTHY": "The keep copy has playback issues. Do not move extras yet.",
        "KEEP_COPY_SUSPECT": "The keep copy is suspect. Review before moving extras.",
        "KEEP_COPY_UNKNOWN": "Keep copy health is not confirmed yet. Refresh integrity evidence first.",
        "EXTRA_COPIES_UNHEALTHY_ONLY": "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
        "SAFE_TO_MOVE_REVIEWED_DUPLICATES": "Keep copy is healthy and the group is approved for movement.",
        "MIXED_EXTRA_HEALTH": "Extra copies have mixed health. Review before moving.",
        "EXTRA_HEALTH_UNKNOWN": "Some extra copies have no usable integrity evidence yet. Review before moving.",
        "REVIEW_REQUIRED_BY_OPERATOR_STATE": "This group is not yet operator-approved for movement.",
        "REVIEW_STALE": "This group changed since it was reviewed. Review it again before moving.",
        "INTEGRITY_EVIDENCE_STALE": "Integrity evidence is incomplete or stale. Refresh it before moving.",
        "NO_ACTIVE_EXTRAS": "No active extra copies remain to move.",
    }[primary_reason_code]


def derive_duplicate_recommendation(facts: DuplicateRecommendationFacts) -> DuplicateRecommendation:
    keep_integrity_status = _normalize_keep_integrity_status(
        keep_identity_known=facts.keep_identity_known,
        keep_integrity_status=facts.keep_integrity_status,
    )
    extra_health_class = _classify_extra_health(facts)

    lifecycle_context = DuplicateRecommendationLifecycleContext(
        already_in_bin=facts.already_in_bin,
        restore_expired=facts.restore_expired,
    )
    keep_summary = DuplicateRecommendationKeepSummary(
        identity_status="KNOWN" if facts.keep_identity_known else "MISSING",
        integrity_status=keep_integrity_status,
    )
    extra_summary = DuplicateRecommendationExtraSummary(
        health_class=extra_health_class,
        active_count=facts.extra_active_count,
        healthy_count=facts.extra_healthy_count,
        suspect_count=facts.extra_suspect_count,
        broken_count=facts.extra_broken_count,
        unknown_count=facts.extra_unknown_count,
    )

    if facts.restore_expired:
        reason_codes = ("BIN_RESTORE_EXPIRED",)
        state = "EXPIRED_IN_BIN"
    elif facts.already_in_bin:
        reason_codes = ("GROUP_ALREADY_IN_BIN",)
        state = "ALREADY_IN_BIN"
    elif not facts.keep_identity_known:
        reason_codes = ("CANONICAL_MAPPING_MISSING",)
        state = "DO_NOT_MOVE"
    elif keep_integrity_status == "BROKEN":
        reason_codes = ("KEEP_COPY_UNHEALTHY",)
        state = "DO_NOT_MOVE"
    elif extra_health_class == "NO_ACTIVE_EXTRAS":
        reason_codes = ("NO_ACTIVE_EXTRAS",)
        state = "DO_NOT_MOVE"
    else:
        review_reason_codes: list[str] = []
        if facts.review_status != "looks_right":
            review_reason_codes.append("REVIEW_REQUIRED_BY_OPERATOR_STATE")
        if facts.review_is_stale:
            review_reason_codes.append("REVIEW_STALE")
        if keep_integrity_status == "SUSPECT":
            review_reason_codes.append("KEEP_COPY_SUSPECT")
        if keep_integrity_status == "UNKNOWN":
            review_reason_codes.append("KEEP_COPY_UNKNOWN")
        if extra_health_class == "EXTRAS_MIXED_HEALTH":
            review_reason_codes.append("MIXED_EXTRA_HEALTH")
        if extra_health_class == "EXTRAS_UNKNOWN":
            review_reason_codes.append("EXTRA_HEALTH_UNKNOWN")
        if facts.integrity_is_stale:
            review_reason_codes.append("INTEGRITY_EVIDENCE_STALE")

        if review_reason_codes:
            reason_codes = tuple(dict.fromkeys(review_reason_codes))
            state = "REVIEW_REQUIRED"
        else:
            safe_reason_codes: list[str] = []
            if extra_health_class == "EXTRAS_ALL_UNHEALTHY":
                safe_reason_codes.append("EXTRA_COPIES_UNHEALTHY_ONLY")
            reason_codes = tuple(safe_reason_codes or ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"])
            state = "SAFE_TO_MOVE_EXTRAS"

    primary_reason_code = reason_codes[0]
    return DuplicateRecommendation(
        state=state,
        classification=_classification_for_state(state),
        primary_reason_code=primary_reason_code,
        reason_codes=reason_codes,
        operator_explanation=_operator_explanation(primary_reason_code),
        review_is_stale=facts.review_is_stale,
        integrity_is_stale=facts.integrity_is_stale,
        lifecycle_context=lifecycle_context,
        keep_summary=keep_summary,
        extra_summary=extra_summary,
    )
