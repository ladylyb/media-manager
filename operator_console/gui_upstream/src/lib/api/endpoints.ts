import { apiGet, apiPost } from "./client";
import type {
  SystemStatus, DashboardSummary, LatestMetrics, Run,
  CanonicalFile, Tag, DuplicateGroup, MediaFileRecord,
  AnalyticsSummary, HashAuditResult, Policy, OperationResult,
  DbResetPreview, DbResetResult, PaginatedResponse
} from "@/types/api";

// System
export const getStatus = () => apiGet<SystemStatus>("/status");

// Dashboard
export const getDashboardSummary = () => apiGet<DashboardSummary>("/dashboard-summary");
export const getLatestMetrics = () => apiGet<LatestMetrics>("/latest-metrics");

// Runs
export const getRuns = (params?: { page?: number; page_size?: number; sort?: string; order?: string }) =>
  apiGet<PaginatedResponse<Run>>("/runs", params as Record<string, string | number>);

// Canonical / Gallery
export const getCanonical = (params?: { page?: number; page_size?: number }) =>
  apiGet<PaginatedResponse<CanonicalFile>>("/canonical", params as Record<string, string | number>);

export const getCanonicalTags = () => apiGet<Tag[]>("/canonical/tags");

// Duplicates
export const getDuplicates = () => apiGet<DuplicateGroup[]>("/duplicates");

// Ledger / Media File
export const getMediaByHash = (hash: string) => apiGet<MediaFileRecord>("/media-file/by-hash", { hash });
export const getMediaHistory = (path: string) => apiGet<MediaFileRecord[]>("/media-file/history", { path });
export const getMediaByStatus = (status: string, params?: { page?: number; page_size?: number }) =>
  apiGet<PaginatedResponse<MediaFileRecord>>("/media-file/by-status", { status, ...params } as Record<string, string | number>);
export const getReappearances = (params?: { page?: number; page_size?: number }) =>
  apiGet<PaginatedResponse<MediaFileRecord>>("/media-file/reappearances", params as Record<string, string | number>);
export const getAnalytics = () => apiGet<AnalyticsSummary>("/media-file/analytics");
export const getHashAudit = (params: { sample_limit?: number; root_path?: string }) =>
  apiGet<HashAuditResult[]>("/admin/hash-audit", params as Record<string, string | number>);
export const getDryRunAudit = () => apiGet<Record<string, unknown>>("/media-file/dry-run-audit");

// Policy
export const getPolicy = () => apiGet<Policy>("/policy");
export const updatePolicy = (policy: Partial<Policy>) => apiPost<Policy>("/policy", policy);

// Operations
export const runIngest = (params: { root_path?: string; dry_run?: boolean }) =>
  apiPost<OperationResult>("/ingest", params);
export const runPlan = (params?: Record<string, unknown>) =>
  apiPost<OperationResult>("/plan", params);
export const runApply = (params?: Record<string, unknown>) =>
  apiPost<OperationResult>("/apply", params);
export const runCanonicalRecompute = () =>
  apiPost<OperationResult>("/canonical/recompute");
export const runOperatorRun = (params?: Record<string, unknown>) =>
  apiPost<OperationResult>("/operator-run", params);
export const runTagEnrichment = (params?: Record<string, unknown>) =>
  apiPost<OperationResult>("/tag-enrichment", params);

// Admin
export const adminDbReset = (params: { dry_run: boolean; challenge?: string }) =>
  apiPost<DbResetPreview | DbResetResult>("/admin/db-reset", params);
