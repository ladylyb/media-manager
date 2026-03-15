import { apiGet } from "@/lib/api/client";
import { withData } from "@/lib/api/envelope";
import { mapPagination } from "@/lib/api/pagination";
import { mapRunItem } from "@/lib/api/mappers/runs";

export const getRuns = async (params?: { limit?: number }) => {
  const envelope = await apiGet<unknown[]>("/runs", params as Record<string, string | number>);
  const items = Array.isArray(envelope.data) ? envelope.data : [];
  const mapped = items.map(mapRunItem);
  const paged = mapPagination(
    { total_count: mapped.length, page: 1, limit: mapped.length, total_pages: 1 },
    mapped,
  );
  return withData(envelope, paged);
};
