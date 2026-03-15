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
