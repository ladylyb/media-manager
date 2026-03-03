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
  details?: Record<string, unknown>;
}

// Status
export interface SystemStatus {
  workflow_version: string;
  schema_version: string;
  active_phase?: string;
  available_features?: string[];
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
  ingest_time_ms: number;
  plan_time_ms: number;
  apply_time_ms: number;
  db_time_ms: number;
  cache_hit_rate: number;
  last_regression_status: "PASS" | "FAIL" | "UNKNOWN";
}

// Runs
export interface Run {
  run_id: string;
  timestamp: string;
  files_processed: number;
  duplicates_found: number;
  runtime_ms: number;
  regression_status: "PASS" | "FAIL" | "UNKNOWN";
  details?: Record<string, unknown>;
}

// Canonical / Gallery
export interface CanonicalFile {
  id: string;
  filename: string;
  file_type: "image" | "video";
  media_url: string;
  matched_tags: string[];
  top_confidence_score: number | null;
  sort_tag_name?: string | null;
}

export interface Tag {
  name: string;
  confidence: number;
  source: string;
}

// Duplicates
export interface DuplicateGroup {
  group_id: string;
  hash: string;
  canonical_path: string;
  duplicates: DuplicateFile[];
}

export interface DuplicateFile {
  path: string;
  size_bytes: number;
  created_at: string;
  is_canonical: boolean;
}

// Ledger / Media File
export interface MediaFileRecord {
  id: string;
  current_path: string;
  discovered_path: string;
  status: string;
  hash_sha256: string;
  discovered_at: string | null;
  ingested_at: string | null;
  deleted_at: string | null;
  size_bytes: number;
}

export interface AnalyticsSummary {
  total_records: number;
  by_status: Record<string, number>;
  avg_file_size: number;
  trend_data?: TrendPoint[];
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface HashAuditResult {
  hash: string;
  path: string;
  status: string;
  audit_note: string;
}

// Policy
export interface Policy {
  selected_policy: string;
  preferred_roots: string[];
  recanonicalization_enabled: boolean;
  tie_breaker_preview?: string;
  version: number;
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
  record_counts?: Record<string, number>;
  warnings?: string[];
  message?: string;
  dry_run?: boolean;
}

export interface DbResetResult {
  success: boolean;
  affected_tables: string[];
  message: string;
  dry_run: boolean;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
