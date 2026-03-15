export interface OperationResult {
  operation: string;
  success: boolean;
  summary: string;
  details: Record<string, unknown>;
  duration_ms: number;
}
