export interface Run {
  run_id: string;
  timestamp: string;
  files_processed: number;
  duplicates_found: number;
  runtime_ms: number;
  regression: "PASS" | "FAIL" | "UNKNOWN";
  details?: Record<string, unknown>;
}
