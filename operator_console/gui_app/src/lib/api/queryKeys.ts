export interface CanonicalQueryParams {
  page?: number;
  limit?: number;
  tags?: string;
  sort_by?: string;
  sort_order?: string;
}

export const queryKeys = {
  status: ["status"] as const,
  dashboardSummary: ["dashboard-summary"] as const,
  latestMetrics: ["latest-metrics"] as const,
  runsRoot: ["runs"] as const,
  runs: (limit = 200) => ["runs", { limit }] as const,
  canonicalRoot: ["canonical"] as const,
  canonical: (params: CanonicalQueryParams) => ["canonical", params] as const,
  canonicalTagsRoot: ["canonical-tags"] as const,
  canonicalTags: (q = "") => ["canonical-tags", { q }] as const,
  duplicates: ["duplicates"] as const,
  policy: ["policy"] as const,
  analytics: ["analytics"] as const,
  adminObservabilitySummary: ["admin", "observability", "summary"] as const,
  adminObservabilityRuns: (params?: { limit?: number; operation_type?: string; status?: string }) =>
    ["admin", "observability", "runs", params ?? {}] as const,
  adminObservabilityFailures: (limit = 25) => ["admin", "observability", "failures", { limit }] as const,
  adminObservabilitySeries: (hours = 24) => ["admin", "observability", "series", { hours }] as const,
  benchmarkRunsRoot: ["admin", "benchmarks"] as const,
  benchmarkRuns: (limit = 50) => ["admin", "benchmarks", { limit }] as const,
  benchmarkRun: (operationRunId: string) => ["admin", "benchmark", operationRunId] as const,
  ledgerByHash: (hashPrefix: string, page = 1, limit = 30) =>
    ["ledger", "by-hash", { hashPrefix, page, limit }] as const,
  ledgerHistory: (path: string, page = 1, limit = 30) => ["ledger", "history", { path, page, limit }] as const,
  ledgerByStatus: (status: string, page = 1, limit = 30) =>
    ["ledger", "by-status", { status, page, limit }] as const,
  ledgerReappearances: (path: string, page = 1, limit = 30) =>
    ["ledger", "reappearances", { path, page, limit }] as const,
};

export const allReadQueryRoots = [
  queryKeys.status,
  queryKeys.dashboardSummary,
  queryKeys.latestMetrics,
  queryKeys.runsRoot,
  queryKeys.canonicalRoot,
  queryKeys.canonicalTagsRoot,
  queryKeys.duplicates,
  queryKeys.policy,
  queryKeys.analytics,
  queryKeys.adminObservabilitySummary,
  queryKeys.benchmarkRunsRoot,
] as const;
