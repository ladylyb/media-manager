export type LogPhase = "ingest" | "plan" | null;

export type LogStatus = "idle" | "running" | "error";

export interface ParsedLogState {
  phase: LogPhase;
  processedCount: number | null;
  totalCount: number | null;
  progressPercent: number | null;
  throughputFps: number | null;
  lines: string[];
  status: LogStatus;
}
