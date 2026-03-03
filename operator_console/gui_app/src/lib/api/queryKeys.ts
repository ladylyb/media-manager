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
] as const;
