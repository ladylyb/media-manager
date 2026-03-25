import { apiGet, apiPost } from "@/lib/api/client";
import { withData } from "@/lib/api/envelope";
import {
  mapAnalyticsSummary,
  mapCanonicalDetail,
  mapCanonicalItems,
  mapDuplicateGroups,
  mapDuplicateReclaimItems,
  mapHashAuditRows,
  mapIntegrityDashboard,
  mapIntegrityFileDetail,
  mapIntegrityIssuePage,
  mapIntegrityQuarantineItems,
  mapLedgerRows,
  mapTagItems,
} from "@/lib/api/mappers/media";
import { mapPagination } from "@/lib/api/pagination";

export const getCanonical = async (params?: {
  page?: number;
  limit?: number;
  tags?: string;
  sort_by?: string;
  sort_order?: string;
}) => {
  const envelope = await apiGet<Record<string, unknown>>(
    "/canonical",
    params as Record<string, string | number>,
  );
  const payload = (envelope.data ?? {}) as Record<string, unknown>;
  const items = Array.isArray(payload.items) ? payload.items : [];
  return withData(envelope, mapPagination(payload, mapCanonicalItems(items)));
};

export const getCanonicalDetail = async (fileId: string) => {
  const envelope = await apiGet<Record<string, unknown>>(`/gallery/${fileId}`);
  return withData(envelope, mapCanonicalDetail((envelope.data ?? {}) as Record<string, unknown>));
};

export const getCanonicalTags = async (q?: string) => {
  const envelope = await apiGet<{ items: string[] }>("/canonical/tags", { q, limit: 25 });
  const names = Array.isArray(envelope.data.items) ? envelope.data.items : [];
  return withData(envelope, mapTagItems(names));
};

export const getDuplicates = async () => {
  const envelope = await apiGet<Record<string, unknown>>("/duplicates");
  return withData(envelope, mapDuplicateGroups(envelope.data));
};

export const setDuplicateReview = async (payload: {
  content_id: string;
  review_status: "looks_right" | "needs_review" | "not_sure";
  reviewed_canonical_instance_id: string;
  reviewed_by?: string;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/duplicates/review", payload);
  return withData(envelope, envelope.data);
};

export const setDuplicateReclaim = async (payload: {
  content_id: string;
  reclaim_status: "UNREVIEWED" | "REVIEWED_SAFE_TO_RECLAIM";
  reviewed_by?: string;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/duplicates/reclaim", payload);
  return withData(envelope, envelope.data);
};

export const executeDuplicateReclaim = async (payload?: {
  content_ids?: string[];
  retention_days?: number;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/duplicates/reclaim/execute", {
    content_ids: payload?.content_ids ?? [],
    retention_days: payload?.retention_days ?? 14,
  });
  return withData(envelope, envelope.data);
};

export const getDuplicateReclaimItems = async (params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/duplicates/reclaim/items", {
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapDuplicateReclaimItems(envelope.data));
};

export const restoreDuplicateReclaim = async (payload?: { file_instance_ids?: string[] }) => {
  const envelope = await apiPost<Record<string, unknown>>("/duplicates/reclaim/restore", {
    file_instance_ids: payload?.file_instance_ids ?? [],
  });
  return withData(envelope, envelope.data);
};

export const getIntegrityDashboard = async () => {
  const envelope = await apiGet<Record<string, unknown>>("/integrity/dashboard");
  return withData(envelope, mapIntegrityDashboard(envelope.data));
};

export const getIntegrityIssues = async (params?: {
  status?: string;
  min_confidence?: number;
  page?: number;
  limit?: number;
}) => {
  const envelope = await apiGet<Record<string, unknown>>(
    "/integrity/issues",
    params as Record<string, string | number>,
  );
  return withData(envelope, mapIntegrityIssuePage(envelope.data));
};

export const getIntegrityFile = async (checkId: string) => {
  const envelope = await apiGet<Record<string, unknown>>(`/integrity/file/${checkId}`);
  return withData(envelope, mapIntegrityFileDetail(envelope.data));
};

export const startIntegrityScan = async (payload?: {
  mode?: "FAST" | "DEEP";
  file_instance_ids?: string[];
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/integrity/scan", {
    mode: payload?.mode ?? "FAST",
    file_instance_ids: payload?.file_instance_ids ?? [],
  });
  return withData(envelope, envelope.data);
};

export const setIntegrityReview = async (payload: {
  check_id: string;
  decision: "MARK_OK" | "IGNORE";
  reviewed_by?: string;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/integrity/review", payload);
  return withData(envelope, envelope.data);
};

export const getIntegrityQuarantineItems = async (params?: { page?: number; limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>("/integrity/quarantine/items", {
    page: params?.page ?? 1,
    limit: params?.limit ?? 30,
  });
  return withData(envelope, mapIntegrityQuarantineItems(envelope.data));
};

export const quarantineIntegrityFile = async (payload: { check_id: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/integrity/quarantine", payload);
  return withData(envelope, envelope.data);
};

export const restoreIntegrityFile = async (payload: { file_instance_id: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/integrity/restore", payload);
  return withData(envelope, envelope.data);
};

export const reportIntegrityPlaybackFailure = async (payload: { file_instance_id: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/integrity/playback-failure", payload);
  return withData(envelope, envelope.data);
};

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
  return withData(envelope, mapAnalyticsSummary(envelope.data));
};

export const getHashAudit = async (params: { sample_limit?: number; root_path?: string }) => {
  const envelope = await apiGet<Record<string, unknown>>(
    "/admin/hash-audit",
    params as Record<string, string | number>,
  );
  return withData(envelope, mapHashAuditRows(envelope.data));
};

export const getDryRunAudit = () => apiGet<Record<string, unknown>>("/media-file/dry-run-audit");
