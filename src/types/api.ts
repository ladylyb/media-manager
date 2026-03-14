// API Envelope
export interface ApiEnvelope<T = unknown> {
  ok: boolean;
  workflow_version: string;
  schema_version: string;
  generated_at: string;
  data: T;
  errors: ApiError[];
}

export interface ApiError {
  code?: string;
  message: string;
  detail?: string;
}

// Re-export domain types for convenience
export type { Run } from "./runs";
export type {
  CanonicalFile, Tag, DuplicateGroup, DuplicateFile,
  MediaFileRecord, AnalyticsSummary, TrendPoint, HashAuditResult,
} from "./media";

// Status
export interface SystemStatus {
  workflow_version: string;
  schema_version: string;
  uptime_seconds: number;
  database_connected: boolean;
}

// Dashboard
export interface DashboardSummary {
  total_files: number;
  total_images: number;
  total_videos: number;
  duplicate_groups: number;
  canonical_files: number;
  total_runs: number;
}

export interface LatestMetrics {
  ingest_ms: number;
  plan_ms: number;
  apply_ms: number;
  db_ms: number;
  cache_hit_rate: number;
  regression_status: "PASS" | "FAIL" | "UNKNOWN";
}

// Policy
export interface Policy {
  selected_policy: string;
  preferred_roots: string[];
  recanonicalize: boolean;
  tie_breaker_preview?: string;
  version: string;
}

// Operations
export interface OperationResult {
  operation: string;
  success: boolean;
  summary: string;
  details: Record<string, unknown>;
  duration_ms: number;
}

// Admin
export interface DbResetPreview {
  affected_tables: string[];
  record_counts: Record<string, number>;
  warnings: string[];
}

export interface DbResetResult {
  success: boolean;
  tables_cleared: string[];
  message: string;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
