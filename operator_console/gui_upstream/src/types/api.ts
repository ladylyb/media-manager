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

// Runs
export interface Run {
  run_id: string;
  timestamp: string;
  files_processed: number;
  duplicates_found: number;
  runtime_ms: number;
  regression: "PASS" | "FAIL" | "UNKNOWN";
  details?: Record<string, unknown>;
}

// Canonical / Gallery
export interface CanonicalFile {
  hash: string;
  path: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  tags?: Tag[];
  thumbnail_url?: string;
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
  hash: string;
  path: string;
  status: string;
  first_seen: string;
  last_seen: string;
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
