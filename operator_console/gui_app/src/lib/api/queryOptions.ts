export const queryOptions = {
  status: {
    staleTime: 0,
  },
  latestMetrics: {
    staleTime: 20_000,
  },
  dashboardSummary: {
    staleTime: 45_000,
  },
  runs: {
    staleTime: 45_000,
  },
  duplicates: {
    staleTime: 90_000,
  },
  analytics: {
    staleTime: 90_000,
  },
  canonical: {
    staleTime: 90_000,
  },
  policy: {
    staleTime: 5 * 60_000,
  },
  canonicalTags: {
    staleTime: 5 * 60_000,
  },
} as const;
