import type { PaginatedResponse } from "@/types";

export function mapPagination<T>(payload: Record<string, unknown>, items: T[]): PaginatedResponse<T> {
  const total = Number(payload.total_count ?? 0);
  const limit = Number(payload.limit ?? 30);
  return {
    items,
    total,
    page: Number(payload.page ?? 1),
    page_size: limit,
    total_pages: Number(payload.total_pages ?? 0),
  };
}
