export type LogPhase = "ingest" | "plan" | "apply" | "canonical" | "integrity" | "tag" | null;

export type LogStatus = "idle" | "running" | "error";

export type ProgressOperationKind = "ingest" | "plan" | "apply" | "canonical" | "integrity" | "tag" | null;

export type ProgressOperationStatus = "idle" | "running" | "finalizing" | "completed" | "error";

export interface ParsedLogState {
  phase: LogPhase;
  stage: string | null;
  processedCount: number | null;
  totalCount: number | null;
  progressPercent: number | null;
  throughputFps: number | null;
  lines: string[];
  status: LogStatus;
}
