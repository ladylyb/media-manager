import { apiGet, apiPost } from "./client";
import type {
  ApiEnvelope,
  AnalyticsSummary,
  CanonicalFile,
  DbResetPreview,
  DbResetResult,
  DuplicateFile,
  DuplicateGroup,
  HashAuditResult,
  LatestMetrics,
  MediaFileRecord,
  OperationResult,
  PaginatedResponse,
  Policy,
  Run,
  SystemStatus,
  Tag,
} from "@/types/api";

function withData<T>(envelope: ApiEnvelope<unknown>, data: T): ApiEnvelope<T> {
  return { ...envelope, data };
}

function mapPagination<T>(payload: Record<string, unknown>, items: T[]): PaginatedResponse<T> {
  const total = Number(payload.total_count ?? 0);
  const limit = Number(payload.limit ?? 30);
  return {
    items,
    total,
    page: Number(payload.page ?? 1),
    page_size: limit,
    total_pages: Number(payload.total_pages ?? 0),
  };
}

function mapOperationResult(payload: Record<string, unknown>): OperationResult {
  const operation = String(payload.operation ?? "UNKNOWN");
  const mode = String(payload.mode ?? "EXECUTION");
  const details = payload as Record<string, unknown>;
  let summary = `${operation} completed.`;
  if (mode === "VALIDATION_ONLY") {
    summary = `${operation} validation completed (no writes).`;
  } else if (mode === "DRY_RUN") {
    summary = `${operation} dry-run completed.`;
  } else if (mode === "APPLY") {
    summary = `${operation} apply completed.`;
  }
  return {
    operation,
    success: true,
    summary,
    details,
    duration_ms: 0,
  };
}

function mapCanonicalItems(items: unknown[]): CanonicalFile[] {
  return items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      id: String(row.id ?? ""),
      filename: String(row.filename ?? ""),
      file_type: String(row.file_type ?? "image") === "video" ? "video" : "image",
      media_url: String(row.media_url ?? ""),
      matched_tags: Array.isArray(row.matched_tags) ? row.matched_tags.map(String) : [],
      top_confidence_score:
        typeof row.top_confidence_score === "number" ? row.top_confidence_score : null,
      sort_tag_name: row.sort_tag_name ? String(row.sort_tag_name) : null,
    };
  });
}

function mapDuplicateGroups(payload: Record<string, unknown>): DuplicateGroup[] {
  const groups = Array.isArray(payload.groups) ? payload.groups : [];
  return groups.map((group) => {
    const row = group as Record<string, unknown>;
    const files = Array.isArray(row.files) ? row.files : [];
    const canonical = (row.canonical_file ?? {}) as Record<string, unknown>;
    const mappedFiles: DuplicateFile[] = files.map((file) => {
      const item = file as Record<string, unknown>;
      const absolutePath = String(item.absolute_path ?? "");
      const canonicalPath = String(canonical.absolute_path ?? "");
      return {
        path: absolutePath,
        size_bytes: Number(item.size_bytes ?? 0),
        created_at: String(item.created_at ?? ""),
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

function mapLedgerRows(payload: Record<string, unknown>): PaginatedResponse<MediaFileRecord> {
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

// System
export const getStatus = () => apiGet<SystemStatus>("/status");

// Dashboard
export const getDashboardSummary = () => apiGet<Record<string, number>>("/dashboard-summary");
export const getLatestMetrics = () => apiGet<LatestMetrics>("/latest-metrics");

// Runs
export const getRuns = async (params?: { limit?: number }) => {
  const envelope = await apiGet<unknown[]>("/runs", params as Record<string, string | number>);
  const items = Array.isArray(envelope.data) ? envelope.data : [];
  const mapped: Run[] = items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      run_id: String(row.run_id ?? ""),
      timestamp: String(row.timestamp ?? ""),
      files_processed: Number(row.files_processed ?? 0),
      duplicates_found: Number(row.duplicates_found ?? 0),
      runtime_ms: Number(row.runtime_ms ?? 0),
      regression_status:
        String(row.regression_status ?? "UNKNOWN").toUpperCase() === "PASS"
          ? "PASS"
          : String(row.regression_status ?? "UNKNOWN").toUpperCase() === "FAIL"
            ? "FAIL"
            : "UNKNOWN",
    };
  });
  const paged = mapPagination({ total_count: mapped.length, page: 1, limit: mapped.length, total_pages: 1 }, mapped);
  return withData(envelope, paged);
};

// Canonical / Gallery
export const getCanonical = async (params?: {
  page?: number;
  limit?: number;
  tags?: string;
  sort_by?: string;
  sort_order?: string;
}) => {
  const envelope = await apiGet<Record<string, unknown>>("/canonical", params as Record<string, string | number>);
  const payload = (envelope.data ?? {}) as Record<string, unknown>;
  const items = Array.isArray(payload.items) ? payload.items : [];
  return withData(envelope, mapPagination(payload, mapCanonicalItems(items)));
};

export const getCanonicalTags = async (q?: string) => {
  const envelope = await apiGet<{ items: string[] }>("/canonical/tags", { q, limit: 25 });
  const tags = Array.isArray(envelope.data.items)
    ? envelope.data.items.map((name) => ({ name, confidence: 1.0, source: "system" }))
    : [];
  return withData(envelope, tags as Tag[]);
};

// Duplicates
export const getDuplicates = async () => {
  const envelope = await apiGet<Record<string, unknown>>("/duplicates");
  return withData(envelope, mapDuplicateGroups(envelope.data));
};

// Ledger / Media File
export const getMediaByHash = async (hashPrefix: string, params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/media-file/by-hash", {
    hash_prefix: hashPrefix,
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapLedgerRows(envelope.data).items);
};

export const getMediaHistory = async (path: string, params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/media-file/history", {
    path,
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapLedgerRows(envelope.data).items);
};

export const getMediaByStatus = async (status: string, params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/media-file/by-status", {
    status,
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapLedgerRows(envelope.data));
};

export const getReappearances = async (path: string, params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/media-file/reappearances", {
    path,
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapLedgerRows(envelope.data));
};

export const getAnalytics = async () => {
  const envelope = await apiGet<Record<string, unknown>>("/media-file/analytics");
  const payload = envelope.data;
  const totals = (payload.totals ?? {}) as Record<string, unknown>;
  const byStatus = (payload.by_status ?? {}) as Record<string, number>;
  const mapped: AnalyticsSummary = {
    total_records: Number(totals.files_tracked ?? 0),
    by_status: byStatus,
    avg_file_size: 0,
    trend_data: [],
  };
  return withData(envelope, mapped);
};

export const getHashAudit = async (params: { sample_limit?: number; root_path?: string }) => {
  const envelope = await apiGet<Record<string, unknown>>("/ledger/hash-audit", params as Record<string, string | number>);
  const payload = envelope.data;
  const missing = Array.isArray(payload.sample_missing_hash_paths) ? payload.sample_missing_hash_paths : [];
  const mismatches = Array.isArray(payload.sample_mismatch_paths) ? payload.sample_mismatch_paths : [];
  const rows: HashAuditResult[] = [
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
  return withData(envelope, rows);
};

export const getDryRunAudit = () => apiGet<Record<string, unknown>>("/media-file/dry-run-audit");

// Policy
export const getPolicy = async () => apiGet<Policy>("/policy");

export const updatePolicy = async (policy: Partial<Policy>) => {
  const current = await getPolicy();
  const payload = {
    selected_policy: policy.selected_policy ?? current.data.selected_policy,
    preferred_roots: policy.preferred_roots ?? current.data.preferred_roots,
    recanonicalization_enabled:
      policy.recanonicalization_enabled ?? current.data.recanonicalization_enabled,
    version: Number(policy.version ?? current.data.version),
  };
  return apiPost<Policy>("/policy", payload);
};

// Operations
export const runIngest = async (params: { folder_path?: string; dry_run?: boolean }) => {
  const envelope = await apiPost<Record<string, unknown>>("/ingest", {
    folder_path: params.folder_path ?? "",
    dry_run: Boolean(params.dry_run),
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runPlan = async (params?: { folder_path?: string; strict_metadata?: boolean }) => {
  const envelope = await apiPost<Record<string, unknown>>("/plan", {
    folder_path: params?.folder_path ?? "",
    strict_metadata: Boolean(params?.strict_metadata),
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runApply = async (params?: { run_id?: string; collision_mode?: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/apply", {
    run_id: params?.run_id ?? "",
    collision_mode: params?.collision_mode ?? "rename",
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runCanonicalRecompute = async (params?: {
  policy_name?: string;
  dry_run?: boolean;
  preferred_roots?: string[];
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/canonical/recompute", {
    policy_name: params?.policy_name ?? "FIRST_SEEN",
    dry_run: params?.dry_run ?? true,
    preferred_roots: params?.preferred_roots ?? [],
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runOperatorRun = async (params?: {
  folder_path?: string;
  policy_name?: string;
  dry_run?: boolean;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/operator-run", {
    folder_path: params?.folder_path ?? "",
    policy_name: params?.policy_name ?? "FIRST_SEEN",
    dry_run: params?.dry_run ?? true,
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runTagEnrichment = async (params?: {
  all?: boolean;
  canonical_id?: string | null;
  batch_size?: number;
  source?: string;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/tag-enrichment", {
    all: params?.all ?? true,
    canonical_id: params?.canonical_id ?? null,
    batch_size: params?.batch_size ?? 100,
    source: params?.source ?? "system",
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

// Admin
export const adminDbReset = async (params: { dry_run: boolean; challenge_word?: string }) => {
  return apiPost<DbResetPreview | DbResetResult>("/admin/db-reset", {
    dry_run: params.dry_run,
    challenge_word: params.challenge_word,
  });
};
