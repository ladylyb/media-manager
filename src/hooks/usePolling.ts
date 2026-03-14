import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

/**
 * usePolling — useQuery with automatic refetch interval.
 * Default interval: 10000ms.
 */
export function usePolling<T>(
  queryKey: string[],
  queryFn: () => Promise<T>,
  intervalMs = 10_000,
  options?: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn" | "refetchInterval">
) {
  return useQuery<T, Error>({
    queryKey,
    queryFn,
    refetchInterval: intervalMs,
    ...options,
  });
}
