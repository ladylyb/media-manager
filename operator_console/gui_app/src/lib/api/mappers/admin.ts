import type { OperationResult } from "@/types";

interface MapOperationResultOptions {
  fallbackOperation?: string;
}

function humanizeOperationLabel(operation: string): string {
  return operation
    .toLowerCase()
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

export function mapOperationResult(
  payload: Record<string, unknown>,
  options?: MapOperationResultOptions,
): OperationResult {
  const operation = String(payload.operation ?? options?.fallbackOperation ?? "UNKNOWN");
  const mode = String(payload.mode ?? "EXECUTION");
  const details = payload as Record<string, unknown>;
  const status = String(payload.status ?? "COMPLETED");
  const operationLabel = humanizeOperationLabel(operation);
  let summary = `${operationLabel} completed.`;
  if (mode === "VALIDATION_ONLY") {
    summary = `${operationLabel} validation completed (no writes).`;
  } else if (mode === "DRY_RUN") {
    summary = `${operationLabel} dry-run completed.`;
  } else if (mode === "APPLY") {
    summary = `${operationLabel} apply completed.`;
  } else if (status === "FAILED") {
    summary = `${operationLabel} failed.`;
  }
  return {
    operation,
    success: status !== "FAILED",
    summary,
    details,
    duration_ms: typeof payload.duration_ms === "number" ? payload.duration_ms : 0,
  };
}
