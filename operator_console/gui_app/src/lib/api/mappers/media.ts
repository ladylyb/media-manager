import { mapPagination } from "@/lib/api/pagination";
import type {
  AnalyticsSummary,
  CanonicalFile,
  CanonicalFileDetail,
  DuplicateFile,
  DuplicateGroup,
  DuplicateRecommendation,
  DuplicateReclaimItem,
  HashAuditResult,
  IntegrityDashboard,
  IntegrityFileDetail,
  IntegrityIssue,
  IntegrityQuarantineItem,
  MediaFileRecord,
  PaginatedResponse,
  RetentionRecycleItem,
  Tag,
} from "@/types";

export function mapCanonicalItems(items: unknown[]): CanonicalFile[] {
  return items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      id: String(row.id ?? ""),
      filename: String(row.filename ?? ""),
      file_type: String(row.file_type ?? "image") === "video" ? "video" : "image",
      media_url: String(row.media_url ?? ""),
      poster_url: row.poster_url ? String(row.poster_url) : null,
      matched_tags: Array.isArray(row.matched_tags) ? row.matched_tags.map(String) : [],
      top_confidence_score:
        typeof row.top_confidence_score === "number" ? row.top_confidence_score : null,
      sort_tag_name: row.sort_tag_name ? String(row.sort_tag_name) : null,
    };
  });
}

export function mapCanonicalDetail(payload: Record<string, unknown>): CanonicalFileDetail {
  return {
    id: String(payload.id ?? ""),
    filename: String(payload.filename ?? ""),
    file_type: String(payload.file_type ?? "image") === "video" ? "video" : "image",
    media_url: String(payload.media_url ?? ""),
    absolute_path: String(payload.absolute_path ?? ""),
  };
}

export function mapTagItems(names: string[]): Tag[] {
  return names.map((name) => ({ name, confidence: 1.0, source: "system" }));
}

export function mapDuplicateGroups(payload: Record<string, unknown>): DuplicateGroup[] {
  const groups = Array.isArray(payload.groups) ? payload.groups : [];
  return groups.map((group) => {
    const row = group as Record<string, unknown>;
    const files = Array.isArray(row.files) ? row.files : [];
    const recommendation =
      row.duplicate_recommendation && typeof row.duplicate_recommendation === "object"
        ? (row.duplicate_recommendation as Record<string, unknown>)
        : null;
    const canonical = (row.canonical_file ?? {}) as Record<string, unknown>;
    const canonicalPath = String(canonical.absolute_path ?? "");
    const mappedFiles: DuplicateFile[] = files.map((file) => {
      const item = file as Record<string, unknown>;
      const absolutePath = String(item.absolute_path ?? "");
      return {
        file_instance_id: String(item.file_instance_id ?? ""),
        path: absolutePath,
        media_type: String(item.media_type ?? "OTHER"),
        is_image: Boolean(item.is_image),
        media_url: item.media_url ? String(item.media_url) : null,
        preview_url: item.preview_url ? String(item.preview_url) : null,
        thumbnail_url: item.thumbnail_url ? String(item.thumbnail_url) : null,
        is_canonical: absolutePath === canonicalPath,
      };
    });
    return {
      group_id: String(row.group_id ?? ""),
      hash: String(row.group_id ?? ""),
      canonical_path: String(canonical.absolute_path ?? ""),
      duplicates: mappedFiles,
      review_status: row.review_status ? String(row.review_status) as DuplicateGroup["review_status"] : null,
      reviewed_at: row.reviewed_at ? String(row.reviewed_at) : null,
      reviewed_canonical_instance_id: row.reviewed_canonical_instance_id
        ? String(row.reviewed_canonical_instance_id)
        : null,
      is_stale: Boolean(row.is_stale),
      stale_reason: row.stale_reason ? String(row.stale_reason) as DuplicateGroup["stale_reason"] : null,
      estimated_reclaim_bytes: Number(row.estimated_reclaim_bytes ?? 0),
      reclaim_status: row.reclaim_status ? String(row.reclaim_status) as DuplicateGroup["reclaim_status"] : null,
      reclaimable_file_count: Number(row.reclaimable_file_count ?? 0),
      duplicate_reclaim_actionable:
        typeof row.duplicate_reclaim_actionable === "boolean" ? row.duplicate_reclaim_actionable : undefined,
      duplicate_reclaim_unavailable_reason: row.duplicate_reclaim_unavailable_reason
        ? String(row.duplicate_reclaim_unavailable_reason) as DuplicateGroup["duplicate_reclaim_unavailable_reason"]
        : null,
      retention_expires_at: row.retention_expires_at ? String(row.retention_expires_at) : null,
      integrity_issue_count: Number(row.integrity_issue_count ?? 0),
      integrity_broken_count: Number(row.integrity_broken_count ?? 0),
      integrity_suspect_count: Number(row.integrity_suspect_count ?? 0),
      duplicate_recommendation: recommendation
        ? {
            state: String(recommendation.state ?? "REVIEW_REQUIRED") as DuplicateRecommendation["state"],
            classification: String(recommendation.classification ?? "WARN") as DuplicateRecommendation["classification"],
            primary_reason_code: String(recommendation.primary_reason_code ?? "REVIEW_REQUIRED_BY_OPERATOR_STATE") as DuplicateRecommendation["primary_reason_code"],
            reason_codes: Array.isArray(recommendation.reason_codes) ? recommendation.reason_codes.map(String) : [],
            operator_explanation: String(recommendation.operator_explanation ?? ""),
            review_is_stale: Boolean(recommendation.review_is_stale),
            integrity_is_stale: Boolean(recommendation.integrity_is_stale),
            lifecycle_context: {
              already_in_bin: Boolean(
                (recommendation.lifecycle_context as Record<string, unknown> | undefined)?.already_in_bin,
              ),
              restore_expired: Boolean(
                (recommendation.lifecycle_context as Record<string, unknown> | undefined)?.restore_expired,
              ),
            },
            keep_summary: {
              identity_status: String(
                (recommendation.keep_summary as Record<string, unknown> | undefined)?.identity_status ?? "KNOWN",
              ) as DuplicateRecommendation["keep_summary"]["identity_status"],
              integrity_status: String(
                (recommendation.keep_summary as Record<string, unknown> | undefined)?.integrity_status ?? "UNKNOWN",
              ) as DuplicateRecommendation["keep_summary"]["integrity_status"],
            },
            extra_summary: {
              health_class: String(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.health_class ?? "EXTRAS_UNKNOWN",
              ) as DuplicateRecommendation["extra_summary"]["health_class"],
              active_count: Number(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.active_count ?? 0,
              ),
              healthy_count: Number(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.healthy_count ?? 0,
              ),
              suspect_count: Number(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.suspect_count ?? 0,
              ),
              broken_count: Number(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.broken_count ?? 0,
              ),
              unknown_count: Number(
                (recommendation.extra_summary as Record<string, unknown> | undefined)?.unknown_count ?? 0,
              ),
            },
          }
        : null,
    };
  });
}

export function mapIntegrityDashboard(payload: Record<string, unknown>): IntegrityDashboard {
  return {
    total_files_scanned: Number(payload.total_files_scanned ?? 0),
    playback_issues: Number(payload.playback_issues ?? 0),
    quarantined: Number(payload.quarantined ?? 0),
    last_scan_at: payload.last_scan_at ? String(payload.last_scan_at) : null,
    broken_count: Number(payload.broken_count ?? 0),
    suspect_count: Number(payload.suspect_count ?? 0),
    ignored_count: Number(payload.ignored_count ?? 0),
    marked_ok_count: Number(payload.marked_ok_count ?? 0),
    high_confidence_unresolved_count: Number(payload.high_confidence_unresolved_count ?? 0),
  };
}

export function mapIntegrityIssuePage(payload: Record<string, unknown>): PaginatedResponse<IntegrityIssue> {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const mapped = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      check_id: String(row.check_id ?? ""),
      file_instance_id: String(row.file_instance_id ?? ""),
      absolute_path: String(row.absolute_path ?? ""),
      status: String(row.status ?? "SUSPECT") as IntegrityIssue["status"],
      confidence: Number(row.confidence ?? 0),
      probe_status: row.probe_status ? String(row.probe_status) : null,
      decode_status: row.decode_status ? String(row.decode_status) : null,
      reviewed_decision: row.reviewed_decision ? String(row.reviewed_decision) as IntegrityIssue["reviewed_decision"] : null,
      reviewed_at: row.reviewed_at ? String(row.reviewed_at) : null,
      signal_types: Array.isArray(row.signal_types) ? row.signal_types.map(String) : [],
    };
  });
  return mapPagination(payload, mapped);
}

export function mapIntegrityFileDetail(payload: Record<string, unknown>): IntegrityFileDetail {
  return {
    check_id: String(payload.check_id ?? ""),
    file_instance_id: String(payload.file_instance_id ?? ""),
    absolute_path: String(payload.absolute_path ?? ""),
    status: String(payload.status ?? "SUSPECT") as IntegrityFileDetail["status"],
    confidence: Number(payload.confidence ?? 0),
    probe_status: payload.probe_status ? String(payload.probe_status) : null,
    decode_status: payload.decode_status ? String(payload.decode_status) : null,
    reviewed_decision: payload.reviewed_decision ? String(payload.reviewed_decision) as IntegrityFileDetail["reviewed_decision"] : null,
    reviewed_at: payload.reviewed_at ? String(payload.reviewed_at) : null,
    signal_types: Array.isArray(payload.signal_types) ? payload.signal_types.map(String) : [],
    signals: Array.isArray(payload.signals)
      ? payload.signals.map((item) => {
          const row = item as Record<string, unknown>;
          return {
            signal_type: String(row.signal_type ?? ""),
            severity: String(row.severity ?? ""),
            details: (row.details ?? {}) as Record<string, unknown>,
            created_at: String(row.created_at ?? ""),
          };
        })
      : [],
  };
}

export function mapIntegrityQuarantineItems(payload: Record<string, unknown>): PaginatedResponse<IntegrityQuarantineItem> {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const mapped = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      file_instance_id: String(row.file_instance_id ?? ""),
      check_id: String(row.check_id ?? ""),
      original_path: String(row.original_path ?? ""),
      quarantine_path: String(row.quarantine_path ?? ""),
      quarantine_status: String(row.quarantine_status ?? "PENDING") as IntegrityQuarantineItem["quarantine_status"],
      quarantined_at: row.quarantined_at ? String(row.quarantined_at) : null,
      restored_at: row.restored_at ? String(row.restored_at) : null,
    };
  });
  return mapPagination(payload, mapped);
}

export function mapDuplicateReclaimItems(payload: Record<string, unknown>): PaginatedResponse<DuplicateReclaimItem> {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const mapped = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      file_instance_id: String(row.file_instance_id ?? ""),
      content_id: String(row.content_id ?? ""),
      original_path: String(row.original_path ?? ""),
      archive_path: String(row.archive_path ?? ""),
      item_status: String(row.item_status ?? "PENDING") as DuplicateReclaimItem["item_status"],
      reclaimed_at: row.reclaimed_at ? String(row.reclaimed_at) : null,
      expires_at: row.expires_at ? String(row.expires_at) : null,
      restored_at: row.restored_at ? String(row.restored_at) : null,
    };
  });
  return mapPagination(payload, mapped);
}

export function mapRetentionRecycleItems(payload: Record<string, unknown>): PaginatedResponse<RetentionRecycleItem> {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const mapped = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      workflow: String(row.workflow ?? "duplicate_reclaim") as RetentionRecycleItem["workflow"],
      file_instance_id: String(row.file_instance_id ?? ""),
      source_path: String(row.source_path ?? ""),
      recycle_path: row.recycle_path ? String(row.recycle_path) : null,
      current_status: String(row.current_status ?? ""),
      retention_expires_at: row.retention_expires_at ? String(row.retention_expires_at) : null,
      recycled_at: row.recycled_at ? String(row.recycled_at) : null,
      purge_after_at: row.purge_after_at ? String(row.purge_after_at) : null,
      purged_at: row.purged_at ? String(row.purged_at) : null,
      ready_for_recycle: Boolean(row.ready_for_recycle),
      ready_for_purge: Boolean(row.ready_for_purge),
      days_remaining: typeof row.days_remaining === "number" ? row.days_remaining : null,
    };
  });
  return mapPagination(payload, mapped);
}

export function mapLedgerRows(payload: Record<string, unknown>): PaginatedResponse<MediaFileRecord> {
  const items = Array.isArray(payload.items) ? payload.items : [];
  const mapped = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      id: String(row.id ?? ""),
      current_path: String(row.current_path ?? ""),
      discovered_path: String(row.discovered_path ?? ""),
      status: String(row.status ?? ""),
      hash_sha256: String(row.hash_sha256 ?? ""),
      discovered_at: row.discovered_at ? String(row.discovered_at) : null,
      ingested_at: row.ingested_at ? String(row.ingested_at) : null,
      deleted_at: row.deleted_at ? String(row.deleted_at) : null,
      size_bytes: Number(row.size_bytes ?? 0),
    };
  });
  return mapPagination(payload, mapped);
}

export function mapAnalyticsSummary(payload: Record<string, unknown>): AnalyticsSummary {
  const totals = (payload.totals ?? {}) as Record<string, unknown>;
  const byStatus = (payload.by_status ?? {}) as Record<string, number>;
  return {
    total_records: Number(totals.files_tracked ?? 0),
    by_status: byStatus,
    avg_file_size: 0,
    trend_data: [],
  };
}

export function mapHashAuditRows(payload: Record<string, unknown>): HashAuditResult[] {
  const missing = Array.isArray(payload.sample_missing_hash_paths) ? payload.sample_missing_hash_paths : [];
  const mismatches = Array.isArray(payload.sample_mismatch_paths) ? payload.sample_mismatch_paths : [];
  return [
    ...missing.map((path) => ({
      hash: "MISSING",
      path: String(path),
      status: "MISSING_HASH",
      audit_note: "Missing hash value",
    })),
    ...mismatches.map((path) => ({
      hash: "MISMATCH",
      path: String(path),
      status: "MISMATCH",
      audit_note: "Hash mismatch observed",
    })),
  ];
}
