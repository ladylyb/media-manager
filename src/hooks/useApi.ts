import { useQuery, useMutation, type UseQueryOptions, type UseMutationOptions } from "@tanstack/react-query";

/**
 * Thin wrapper around useQuery for API calls.
 * All API functions already return parsed data (envelope unwrapped).
 */
export function useApi<T>(
  queryKey: string[],
  queryFn: () => Promise<T>,
  options?: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">
) {
  return useQuery<T, Error>({
    queryKey,
    queryFn,
    ...options,
  });
}

/**
 * Thin wrapper around useMutation for API calls.
 */
export function useApiMutation<TData, TVariables = void>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: Omit<UseMutationOptions<TData, Error, TVariables>, "mutationFn">
) {
  return useMutation<TData, Error, TVariables>({
    mutationFn,
    ...options,
  });
}
