import { mapPagination } from "@/lib/api/pagination";
import type {
  AnalyticsSummary,
  CanonicalFile,
  CanonicalFileDetail,
  DuplicateFile,
  DuplicateGroup,
  HashAuditResult,
  MediaFileRecord,
  PaginatedResponse,
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
        thumbnail_url: item.thumbnail_url ? String(item.thumbnail_url) : null,
        is_canonical: absolutePath === canonicalPath,
      };
    });
    return {
      group_id: String(row.group_id ?? ""),
      hash: String(row.group_id ?? ""),
      canonical_path: String(canonical.absolute_path ?? ""),
      duplicates: mappedFiles,
    };
  });
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
