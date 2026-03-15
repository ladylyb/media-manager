import type { FailureEventItem, ObservabilityFailures, Run } from "@/types";

function mapRunStatus(status: unknown): Run["status"] {
  const normalized = String(status ?? "STARTED").toUpperCase();
  if (normalized === "COMPLETED") return "COMPLETED";
  if (normalized === "FAILED") return "FAILED";
  return "STARTED";
}

export function mapRunItem(item: unknown): Run {
  const row = item as Record<string, unknown>;
  return {
    operation_run_id: String(row.operation_run_id ?? ""),
    operation_type: String(row.operation_type ?? ""),
    status: mapRunStatus(row.status),
    started_at: String(row.started_at ?? ""),
    completed_at: row.completed_at ? String(row.completed_at) : null,
    duration_ms: row.duration_ms == null ? null : Number(row.duration_ms),
    linked_run_id: row.linked_run_id ? String(row.linked_run_id) : null,
    context: (row.context as Record<string, unknown>) ?? {},
    error_message: row.error_message ? String(row.error_message) : null,
  };
}

export function mapFailureEventItems(items: unknown[]): FailureEventItem[] {
  return items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      id: String(row.id ?? ""),
      run_id: String(row.run_id ?? ""),
      phase: String(row.phase ?? ""),
      error_code: String(row.error_code ?? ""),
      error_message: String(row.error_message ?? ""),
      created_at: String(row.created_at ?? ""),
    };
  });
}

export function mapFailedRunItems(items: unknown[]): Run[] {
  return items.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      operation_run_id: String(row.operation_run_id ?? ""),
      operation_type: String(row.operation_type ?? ""),
      status: "FAILED",
      started_at: String(row.started_at ?? ""),
      completed_at: row.completed_at ? String(row.completed_at) : null,
      duration_ms: null,
      linked_run_id: row.linked_run_id ? String(row.linked_run_id) : null,
      context: (row.context as Record<string, unknown>) ?? {},
      error_message: row.error_message ? String(row.error_message) : null,
    };
  });
}

export function mapObservabilityFailures(payload: Record<string, unknown>): ObservabilityFailures {
  const failureEvents = Array.isArray(payload.failure_events)
    ? mapFailureEventItems(payload.failure_events)
    : [];
  const failedOperationRuns = Array.isArray(payload.failed_operation_runs)
    ? mapFailedRunItems(payload.failed_operation_runs)
    : [];
  return {
    failure_events: failureEvents,
    failed_operation_runs: failedOperationRuns,
  };
}
