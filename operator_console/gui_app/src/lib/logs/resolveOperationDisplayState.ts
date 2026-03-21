import type {
  LogPhase,
  LogStatus,
  ProgressOperationKind,
  ProgressOperationStatus,
} from "@/types/logs";

interface ResolveOperationDisplayStateInput {
  operationKind?: ProgressOperationKind;
  operationStatus?: ProgressOperationStatus;
  parsedPhase: LogPhase;
  parsedStatus: LogStatus;
  progressPercent: number | null;
}

export function resolveOperationDisplayState({
  operationKind,
  operationStatus,
  parsedPhase,
  parsedStatus,
  progressPercent,
}: ResolveOperationDisplayStateInput): {
  kind: ProgressOperationKind;
  status: ProgressOperationStatus;
} {
  const kind = operationKind ?? parsedPhase ?? null;
  const passiveStatus =
    parsedStatus === "error"
      ? "error"
      : parsedStatus === "running"
        ? "running"
        : kind !== null && progressPercent !== null && progressPercent >= 100
          ? "completed"
          : "idle";

  if (!operationStatus) {
    return { kind, status: passiveStatus };
  }

  if (operationStatus === "running" && progressPercent !== null && progressPercent >= 100) {
    return { kind, status: "finalizing" };
  }

  return { kind, status: operationStatus };
}
