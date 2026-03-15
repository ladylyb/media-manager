import type { OperationResult } from "@/types";

export function mapOperationResult(payload: Record<string, unknown>): OperationResult {
  const operation = String(payload.operation ?? "UNKNOWN");
  const mode = String(payload.mode ?? "EXECUTION");
  const details = payload as Record<string, unknown>;
  let summary = `${operation} completed.`;
  if (mode === "VALIDATION_ONLY") {
    summary = `${operation} validation completed (no writes).`;
  } else if (mode === "DRY_RUN") {
    summary = `${operation} dry-run completed.`;
  } else if (mode === "APPLY") {
    summary = `${operation} apply completed.`;
  }
  return {
    operation,
    success: true,
    summary,
    details,
    duration_ms: 0,
  };
}
