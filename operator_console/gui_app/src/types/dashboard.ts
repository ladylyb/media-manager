export interface SystemStatus {
  workflow_version: string;
  schema_version: string;
  active_phase?: string;
  available_features?: string[];
}

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
