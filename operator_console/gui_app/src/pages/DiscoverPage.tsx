import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { getCanonical, getCanonicalTags } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { CanonicalFile, Tag, PaginatedResponse } from "@/types/api";
import { Search, X, ImageIcon, ArrowUpDown, Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function DiscoverPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tagInput, setTagInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const tagsParam = searchParams.get("tags") || "";
  const selectedTags = tagsParam.split(",").filter(Boolean);
  const sortBy = searchParams.get("sort_by") || "created_at";
  const sortOrder = searchParams.get("sort_order") || "desc";
  const page = Number(searchParams.get("page") || 1);

  const updateParams = (updates: Record<string, string | undefined>) => {
    const newParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([k, v]) => {
      if (v) newParams.set(k, v);
      else newParams.delete(k);
    });
    setSearchParams(newParams);
  };

  const addTag = (tag: string) => {
    if (!selectedTags.includes(tag)) {
      updateParams({ tags: [...selectedTags, tag].join(","), page: "1" });
    }
    setTagInput("");
    setSuggestions([]);
  };

  const removeTag = (tag: string) => {
    const next = selectedTags.filter(t => t !== tag);
    updateParams({ tags: next.length ? next.join(",") : undefined, page: "1" });
  };

  const canonicalParams = useMemo(
    () => ({
      page,
      limit: 24,
      tags: tagsParam,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [page, tagsParam, sortBy, sortOrder],
  );

  const tagsQuery = useQuery({
    queryKey: queryKeys.canonicalTags(""),
    queryFn: async () => (await getCanonicalTags()).data,
    staleTime: queryOptions.canonicalTags.staleTime,
  });

  const canonicalQuery = useQuery({
    queryKey: queryKeys.canonical(canonicalParams),
    queryFn: async () => (await getCanonical(canonicalParams)).data,
    staleTime: queryOptions.canonical.staleTime,
    placeholderData: keepPreviousData,
  });

  const allTags = (tagsQuery.data as Tag[] | undefined) ?? [];
  const data = (canonicalQuery.data as PaginatedResponse<CanonicalFile> | undefined) ?? null;

  useEffect(() => {
    if (tagInput.length > 0) {
      const filtered = allTags
        .map(t => t.name)
        .filter(
          n => n.toLowerCase().includes(tagInput.toLowerCase()) && !selectedTags.includes(n),
        )
        .slice(0, 8);
      setSuggestions(filtered);
    } else {
      setSuggestions([]);
    }
  }, [tagInput, allTags, selectedTags]);

  const error =
    getErrorMessage(canonicalQuery.error) || getErrorMessage(tagsQuery.error);

  const isInitialLoading = canonicalQuery.isLoading && !data;

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Discover</h1>
        <p className="text-sm text-muted-foreground mt-1">Browse and filter canonical media by tags</p>
      </div>

      {error && <ErrorAlert message={error} />}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <input
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && tagInput) addTag(tagInput);
            }}
            placeholder="Filter by tag…"
            className="rounded-md border bg-background px-3 py-2 text-sm pl-8 w-64"
          />
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          {suggestions.length > 0 && (
            <div className="absolute top-full mt-1 w-full rounded-md border bg-card shadow-lg z-10 max-h-48 overflow-auto">
              {suggestions.map(s => (
                <button
                  key={s}
                  onClick={() => addTag(s)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-muted"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
        {selectedTags.map(tag => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 rounded-md bg-primary/10 text-primary px-2 py-1 text-xs font-medium"
          >
            {tag}
            <button onClick={() => removeTag(tag)}>
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {canonicalQuery.isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          <select
            value={sortBy}
            onChange={e => updateParams({ sort_by: e.target.value, page: "1" })}
            className="rounded-md border bg-background px-2 py-1.5 text-xs"
          >
            <option value="created_at">Created</option>
            <option value="tag_name">Tag</option>
            <option value="confidence_score">Confidence</option>
          </select>
          <button
            onClick={() =>
              updateParams({
                sort_order: sortOrder === "asc" ? "desc" : "asc",
                page: "1",
              })
            }
            className="p-1.5 rounded border hover:bg-muted"
          >
            <ArrowUpDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {isInitialLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card overflow-hidden">
              <Skeleton className="aspect-square w-full" />
              <div className="p-2 space-y-1">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-12" />
              </div>
            </div>
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<ImageIcon className="h-10 w-10" />}
          title="No media found"
          description="Try adjusting your tag filters"
        />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {data.items.map(file => (
            <div
              key={file.id}
              className="rounded-lg border bg-card overflow-hidden hover:border-primary/30 transition-colors group cursor-pointer"
            >
              <div className="aspect-square bg-muted flex items-center justify-center overflow-hidden">
                {file.media_url ? (
                  <img
                    src={file.media_url}
                    alt={file.filename}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                  />
                ) : (
                  <ImageIcon className="h-8 w-8 text-muted-foreground" />
                )}
              </div>
              <div className="p-2">
                <p className="text-xs font-mono truncate text-muted-foreground">{file.filename}</p>
                {file.matched_tags?.[0] && (
                  <StatusBadge
                    label={`${file.matched_tags[0]} ${((file.top_confidence_score ?? 0) * 100).toFixed(0)}%`}
                    severity="info"
                    className="mt-1"
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => updateParams({ page: String(Math.max(1, page - 1)) })}
            disabled={page === 1}
            className="px-3 py-1 text-sm rounded border disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-xs text-muted-foreground">
            Page {page} of {data.total_pages}
          </span>
          <button
            onClick={() =>
              updateParams({ page: String(Math.min(data.total_pages, page + 1)) })
            }
            disabled={page === data.total_pages}
            className="px-3 py-1 text-sm rounded border disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
