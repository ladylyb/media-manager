import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchLogs } from "@/lib/api/endpoints/system";
import { queryKeys } from "@/lib/api/queryKeys";
import { mergeLogLines, parseProgressLogs } from "@/lib/logs/parseProgressLogs";
import { queryOptions } from "@/lib/api/queryOptions";

function documentIsVisible() {
  return typeof document === "undefined" || document.visibilityState === "visible";
}

export function useLiveLogs(limit = 100) {
  const [lines, setLines] = useState<string[]>([]);
  const queryClient = useQueryClient();

  const logsQuery = useQuery({
    queryKey: queryKeys.liveLogs(limit),
    queryFn: async () => fetchLogs(limit),
    staleTime: queryOptions.liveLogs.staleTime,
    refetchInterval: () => (documentIsVisible() ? 1_000 : false),
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    if (!logsQuery.data) return;
    setLines((currentLines) => mergeLogLines(currentLines, logsQuery.data, limit));
  }, [logsQuery.data, limit]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (documentIsVisible()) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.liveLogs(limit) });
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [limit, queryClient]);

  const parsed = useMemo(
    () => parseProgressLogs(lines),
    [lines],
  );

  return {
    parsed,
    lines,
    error: logsQuery.error instanceof Error ? logsQuery.error.message : null,
  };
}
