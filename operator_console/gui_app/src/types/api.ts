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
  operation_run_id: string;
  operation_type: string;
  status: "STARTED" | "COMPLETED" | "FAILED";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  linked_run_id?: string | null;
  context?: Record<string, unknown>;
  error_message?: string | null;
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

export interface CanonicalFileDetail {
  id: string;
  filename: string;
  file_type: "image" | "video";
  media_url: string;
  absolute_path: string;
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

export interface ObservabilitySummary {
  metrics_enabled: boolean;
  prometheus_url?: string | null;
  grafana_url?: string | null;
  generated_at: string;
  window_hours: number;
  recent_failure_count: number;
  recent_runs_by_status: Record<string, number>;
  recent_runs_by_type: Record<string, number>;
  last_success_by_type: Record<string, string | null>;
  latest_metrics: LatestMetrics;
}

export interface FailureEventItem {
  id: string;
  run_id: string;
  phase: string;
  error_code: string;
  error_message: string;
  created_at: string;
}

export interface ObservabilityFailures {
  failure_events: FailureEventItem[];
  failed_operation_runs: Run[];
}

export interface SeriesPoint {
  timestamp: string;
  value: number;
}

export interface ObservabilityMetricsSeries {
  hours: number;
  series: {
    operation_volume: SeriesPoint[];
    failure_volume: SeriesPoint[];
    latency_ms_avg: SeriesPoint[];
  };
}

export interface BenchmarkRun {
  benchmark_run_id: string;
  operation_run_id: string;
  benchmark_type: "METADATA" | "DISCOVERY" | string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCEL_REQUESTED" | "CANCELLED" | string;
  parameters: Record<string, unknown>;
  report_payload?: Record<string, unknown> | null;
  summary_payload?: Record<string, unknown> | null;
  cleanup_status?: string | null;
  cleanup_error?: string | null;
  error_message?: string | null;
  queued_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  cancel_requested_at?: string | null;
}

export interface BenchmarkQueueResult {
  queued: boolean;
  operation_run_id: string;
  benchmark: BenchmarkRun;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
