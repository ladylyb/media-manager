export interface CanonicalQueryParams {
  page?: number;
  limit?: number;
  tags?: string;
  sort_by?: string;
  sort_order?: string;
}

export const queryKeys = {
  status: ["status"] as const,
  home: ["home"] as const,
  dashboardSummary: ["dashboard-summary"] as const,
  latestMetrics: ["latest-metrics"] as const,
  liveLogs: (limit = 100) => ["live-logs", { limit }] as const,
  runsRoot: ["runs"] as const,
  runs: (limit = 200) => ["runs", { limit }] as const,
  canonicalRoot: ["canonical"] as const,
  canonical: (params: CanonicalQueryParams) => ["canonical", params] as const,
  canonicalDetail: (fileId: string) => ["canonical", "detail", fileId] as const,
  canonicalTagsRoot: ["canonical-tags"] as const,
  canonicalTags: (q = "") => ["canonical-tags", { q }] as const,
  duplicates: ["duplicates"] as const,
  integrityDashboard: ["integrity", "dashboard"] as const,
  integrityIssues: (params?: { status?: string; min_confidence?: number; page?: number; limit?: number }) =>
    ["integrity", "issues", params ?? {}] as const,
  integrityFile: (checkId: string) => ["integrity", "file", checkId] as const,
  integrityQuarantine: (page = 1, limit = 30) => ["integrity", "quarantine", { page, limit }] as const,
  duplicateBinItemsRoot: ["duplicates", "reclaim-items"] as const,
  duplicateBinItems: (page = 1, limit = 30) => ["duplicates", "reclaim-items", { page, limit }] as const,
  duplicateBinPolicy: ["duplicates", "bin-policy"] as const,
  retentionRecycleItems: (page = 1, limit = 30) => ["retention", "recycle", { page, limit }] as const,
  policy: ["policy"] as const,
  analytics: ["analytics"] as const,
  directoryPickerCapability: ["directory-picker", "capability"] as const,
  directoryPickerListing: (path: string) => ["directory-picker", "listing", { path }] as const,
  adminObservabilitySummary: ["admin", "observability", "summary"] as const,
  adminObservabilityRuns: (params?: { limit?: number; operation_type?: string; status?: string }) =>
    ["admin", "observability", "runs", params ?? {}] as const,
  adminObservabilityFailures: (limit = 25) => ["admin", "observability", "failures", { limit }] as const,
  adminObservabilitySeries: (hours = 24) => ["admin", "observability", "series", { hours }] as const,
  adminOperationRunReconcile: ["admin", "operation-runs", "reconcile-stale"] as const,
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
  queryKeys.home,
  queryKeys.dashboardSummary,
  queryKeys.latestMetrics,
  queryKeys.runsRoot,
  queryKeys.canonicalRoot,
  queryKeys.canonicalTagsRoot,
  queryKeys.duplicates,
  queryKeys.integrityDashboard,
  queryKeys.policy,
  queryKeys.analytics,
  queryKeys.adminObservabilitySummary,
  queryKeys.benchmarkRunsRoot,
] as const;
