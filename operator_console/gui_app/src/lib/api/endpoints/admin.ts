import { apiGet, apiPost } from "@/lib/api/client";
import { withData } from "@/lib/api/envelope";
import { mapObservabilityFailures, mapRunItem } from "@/lib/api/mappers/runs";
import type {
  BenchmarkQueueResult,
  BenchmarkRun,
  DbResetPreview,
  DbResetResult,
  ObservabilityMetricsSeries,
  ObservabilitySummary,
} from "@/types";

export const adminDbReset = async (params: { dry_run: boolean; challenge_word?: string }) => {
  return apiPost<DbResetPreview | DbResetResult>("/admin/db-reset", {
    dry_run: params.dry_run,
    challenge_word: params.challenge_word,
  });
};

export const getAdminObservabilitySummary = async () =>
  apiGet<ObservabilitySummary>("/admin/observability/summary");

export const getAdminObservabilityOperationRuns = async (params?: {
  limit?: number;
  operation_type?: string;
  status?: string;
}) => {
  const envelope = await apiGet<unknown[]>(
    "/admin/observability/operation-runs",
    params as Record<string, string | number>,
  );
  const items = Array.isArray(envelope.data) ? envelope.data : [];
  return withData(envelope, items.map(mapRunItem));
};

export const getAdminObservabilityFailures = async (params?: { limit?: number }) => {
  const envelope = await apiGet<Record<string, unknown>>(
    "/admin/observability/failures",
    params as Record<string, string | number>,
  );
  return withData(envelope, mapObservabilityFailures(envelope.data));
};

export const getAdminObservabilityMetricsSeries = async (params?: { hours?: number }) =>
  apiGet<ObservabilityMetricsSeries>(
    "/admin/observability/metrics-series",
    params as Record<string, string | number>,
  );

export const queueMetadataBenchmark = async (params: {
  items: number;
  batch_size: number;
  challenge_word: string;
}) => apiPost<BenchmarkQueueResult>("/admin/benchmarks/metadata", params);

export const queueDiscoveryBenchmark = async (params: { items: number; challenge_word: string }) =>
  apiPost<BenchmarkQueueResult>("/admin/benchmarks/discovery", params);

export const getBenchmarkRuns = async (params?: { limit?: number }) =>
  apiGet<BenchmarkRun[]>("/admin/benchmarks/runs", params as Record<string, string | number>);

export const getBenchmarkRun = async (operationRunId: string) =>
  apiGet<BenchmarkRun>(`/admin/benchmarks/runs/${operationRunId}`);

export const cancelBenchmarkRun = async (operationRunId: string) =>
  apiPost<BenchmarkRun>(`/admin/benchmarks/runs/${operationRunId}/cancel`);
