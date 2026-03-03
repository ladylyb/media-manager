"""Read/query façade for Operator Console and CLI adapters."""

from __future__ import annotations

from dataclasses import dataclass

from media_manager.app.persistence.models import MediaFileStatus, TagSource
from media_manager.app.persistence.operator_console import OperatorConsoleReadService
from media_manager.app.service_layer.cache import ServiceCache
from media_manager.app.service_layer.versioning import compute_phase_metadata


@dataclass
class ReadServices:
    """Shared read/query service entrypoint with short-lived caching."""

    session_factory: object
    cache: ServiceCache

    def __post_init__(self) -> None:
        self._read_service = OperatorConsoleReadService(self.session_factory)

    def status(self) -> dict[str, object]:
        cached = self.cache.get("status")
        if isinstance(cached, dict):
            return dict(cached)
        summary = self._read_service.get_dashboard_summary().to_dict()
        phase = compute_phase_metadata(self.session_factory)
        payload = {
            **phase.to_dict(),
            "available_features": [
                "run",
                "policy",
                "tag_enrichment",
                "dashboard_summary",
                "runs",
                "latest_metrics",
                "canonical",
                "duplicates",
                "ledger",
            ],
            "phase_status": [
                {
                    "phase": phase.active_phase,
                    "status": "ACTIVE",
                    "last_run_id": None,
                    "updated_at": None,
                    "details": {"dashboard_summary": summary},
                }
            ],
        }
        self.cache.set("status", payload, ttl_s=5)
        return dict(payload)

    def dashboard_summary(self) -> dict[str, object]:
        cached = self.cache.get("dashboard_summary")
        if isinstance(cached, dict):
            return dict(cached)
        payload = self._read_service.get_dashboard_summary().to_dict()
        self.cache.set("dashboard_summary", payload, ttl_s=2)
        return payload

    def latest_metrics(self) -> dict[str, object]:
        cached = self.cache.get("latest_metrics")
        if isinstance(cached, dict):
            return dict(cached)
        payload = self._read_service.get_latest_metrics().to_dict()
        self.cache.set("latest_metrics", payload, ttl_s=2)
        return payload

    def runs(self, *, limit: int) -> list[dict[str, object]]:
        return [item.to_dict() for item in self._read_service.get_run_history(limit=limit)]

    def duplicates(self) -> dict[str, object]:
        return {"groups": [group.to_dict() for group in self._read_service.get_duplicate_groups()]}

    def canonical(
        self,
        *,
        page: int,
        limit: int,
        tags: tuple[str, ...],
        sort_by: str,
        sort_order: str | None,
        source: str | None,
        min_confidence: float | None,
    ) -> dict[str, object]:
        source_value = TagSource(source.strip().lower()) if source else None
        return self._read_service.get_canonical_gallery(
            page=page,
            limit=limit,
            tags=tags,
            sort_by=sort_by,
            sort_order=sort_order,
            source=source_value,
            min_confidence=min_confidence,
        ).to_dict()

    def canonical_tags(self, *, q: str | None, limit: int) -> dict[str, object]:
        return {"items": list(self._read_service.get_tag_suggestions(q=q, limit=limit))}

    def media_file_by_hash(self, *, hash_prefix: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_by_hash_page(hash_prefix=hash_prefix, page=page, limit=limit).to_dict()

    def media_file_history(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_history_page(path=path, page=page, limit=limit).to_dict()

    def media_file_by_status(self, *, status: str, page: int, limit: int) -> dict[str, object]:
        status_value = MediaFileStatus(status.strip().upper())
        return self._read_service.get_media_file_by_status_page(status=status_value, page=page, limit=limit).to_dict()

    def media_file_reappearances(self, *, path: str, page: int, limit: int) -> dict[str, object]:
        return self._read_service.get_media_file_reappearances_page(path=path, page=page, limit=limit).to_dict()

    def media_file_analytics(self) -> dict[str, object]:
        return self._read_service.get_media_file_analytics().to_dict()

    def ledger_hash_audit(self, *, root_path: str | None, sample_limit: int) -> dict[str, object]:
        return self._read_service.get_ledger_hash_audit(root_path=root_path, sample_limit=sample_limit).to_dict()

    def media_file_dry_run_audit(self, *, start: str | None, end: str | None, limit: int) -> dict[str, object]:
        return self._read_service.get_dry_run_side_effect_audit(start=start, end=end, limit=limit).to_dict()
