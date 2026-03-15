import type { LatestMetrics } from "@/types/dashboard";
import type { Run } from "@/types/runs";

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
