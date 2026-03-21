import { useQuery } from "@tanstack/react-query";
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
        void logsQuery.refetch();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [logsQuery]);

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
