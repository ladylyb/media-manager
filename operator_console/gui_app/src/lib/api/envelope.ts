import type { ApiEnvelope } from "@/types";

export function withData<T>(envelope: ApiEnvelope<unknown>, data: T): ApiEnvelope<T> {
  return { ...envelope, data };
}
