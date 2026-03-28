import type { QueryClient } from "@tanstack/react-query";
import { allReadQueryRoots, queryKeys } from "@/lib/api/queryKeys";

export type OperationInvalidationTarget =
  | "ingest"
  | "plan"
  | "apply"
  | "canonicalRecompute"
  | "integrityScan"
  | "tagEnrichment";

export async function invalidateReadsAfterOperation(
  queryClient: QueryClient,
  _operation: OperationInvalidationTarget,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.home }),
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboardSummary }),
    queryClient.invalidateQueries({ queryKey: queryKeys.latestMetrics }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runsRoot }),
    queryClient.invalidateQueries({ queryKey: queryKeys.duplicates }),
    queryClient.invalidateQueries({ queryKey: queryKeys.integrityDashboard }),
    queryClient.invalidateQueries({ queryKey: ["integrity", "issues"] }),
    queryClient.invalidateQueries({ queryKey: queryKeys.canonicalRoot }),
    queryClient.invalidateQueries({ queryKey: queryKeys.analytics }),
  ]);
}

export async function invalidateReadsAfterPolicyUpdate(queryClient: QueryClient) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.policy }),
    queryClient.invalidateQueries({ queryKey: queryKeys.canonicalRoot }),
    queryClient.invalidateQueries({ queryKey: queryKeys.duplicates }),
  ]);
}

export async function invalidateAllReadsAfterDbReset(queryClient: QueryClient) {
  await Promise.all(
    allReadQueryRoots.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
  );
}
