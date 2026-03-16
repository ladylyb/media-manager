import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { MediaGrid } from "@/components/media/MediaGrid";
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getCanonical, getCanonicalTags } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { CanonicalFile, PaginatedResponse, Tag } from "@/types";
import { ArrowUpDown, ChevronLeft, ChevronRight, Images, Loader2, Search, X } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedFile, setSelectedFile] = useState<CanonicalFile | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const tagsParam = searchParams.get("tags") || "";
  const selectedTags = tagsParam.split(",").filter(Boolean);
  const sortBy = searchParams.get("sort_by") || "created_at";
  const sortOrder = searchParams.get("sort_order") || "desc";
  const page = Number(searchParams.get("page") || 1);

  const updateParams = (updates: Record<string, string | undefined>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value) next.set(key, value);
      else next.delete(key);
    });
    setSearchParams(next);
  };

  const addTag = (tag: string) => {
    if (!tag.trim() || selectedTags.includes(tag)) return;
    updateParams({ tags: [...selectedTags, tag].join(","), page: "1" });
    setTagInput("");
    setSuggestions([]);
  };

  const removeTag = (tag: string) => {
    const nextTags = selectedTags.filter((item) => item !== tag);
    updateParams({ tags: nextTags.length ? nextTags.join(",") : undefined, page: "1" });
  };

  const canonicalParams = useMemo(
    () => ({
      page,
      limit: 30,
      tags: tagsParam || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [page, sortBy, sortOrder, tagsParam],
  );

  const tagsQuery = useQuery({
    queryKey: queryKeys.canonicalTags(""),
    queryFn: async () => (await getCanonicalTags()).data,
    staleTime: queryOptions.canonicalTags.staleTime,
  });

  const galleryQuery = useQuery({
    queryKey: queryKeys.canonical(canonicalParams),
    queryFn: async () => (await getCanonical(canonicalParams)).data,
    staleTime: queryOptions.canonical.staleTime,
    placeholderData: keepPreviousData,
  });

  const data = (galleryQuery.data as PaginatedResponse<CanonicalFile> | undefined) ?? null;
  const items = data?.items ?? [];
  const videoCount = items.filter((file) => file.file_type === "video").length;
  const imageCount = items.length - videoCount;
  const allTags = (tagsQuery.data as Tag[] | undefined) ?? [];

  useEffect(() => {
    if (!tagInput) {
      setSuggestions([]);
      return;
    }

    const nextSuggestions = allTags
      .map((tag) => tag.name)
      .filter(
        (name) =>
          name.toLowerCase().includes(tagInput.toLowerCase()) &&
          !selectedTags.includes(name),
      )
      .slice(0, 8);
    setSuggestions(nextSuggestions);
  }, [allTags, selectedTags, tagInput]);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <div className="overflow-hidden rounded-[28px] border border-border/70 bg-[linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card))_35%,hsl(var(--secondary)/0.65)_100%)] shadow-sm">
        <div className="grid gap-6 px-6 py-8 lg:grid-cols-[minmax(0,1.4fr)_20rem] lg:px-8">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              <Images className="h-3.5 w-3.5" />
              Canonical media
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">Library</h1>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                Browse the current canonical media set with tag filters, sort controls, preview, and
                a dedicated detail route while staying on the existing API-backed query flow.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <MetricTile label="Visible items" value={String(items.length)} />
            <MetricTile label="Images" value={String(imageCount)} />
            <MetricTile label="Videos" value={String(videoCount)} />
          </div>
        </div>
      </div>

      {galleryQuery.error ? (
        <ErrorAlert
          message={getErrorMessage(galleryQuery.error) || "Failed to load gallery"}
        />
      ) : null}

      <div className="rounded-[28px] border border-border/70 bg-card/70 p-4 shadow-sm backdrop-blur">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-3">
            <div className="relative max-w-md">
              <Input
                value={tagInput}
                onChange={(event) => setTagInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && tagInput) {
                    event.preventDefault();
                    addTag(tagInput);
                  }
                }}
                placeholder="Filter gallery by tag"
                className="pl-9"
              />
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              {suggestions.length ? (
                <div className="absolute left-0 right-0 top-full z-10 mt-2 overflow-hidden rounded-2xl border border-border bg-popover shadow-lg">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => addTag(suggestion)}
                      className="block w-full px-4 py-2 text-left text-sm hover:bg-muted"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2">
              {selectedTags.length ? (
                selectedTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => removeTag(tag)}
                    className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                  >
                    {tag}
                    <X className="h-3 w-3" />
                  </button>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  No tags selected. Use the search box to narrow the gallery.
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 self-start lg:self-auto">
            {galleryQuery.isFetching ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
            <select
              value={sortBy}
              onChange={(event) => updateParams({ sort_by: event.target.value, page: "1" })}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="created_at">Created</option>
              <option value="tag_name">Tag</option>
              <option value="confidence_score">Confidence</option>
            </select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                updateParams({
                  sort_order: sortOrder === "asc" ? "desc" : "asc",
                  page: "1",
                })
              }
            >
              <ArrowUpDown className="mr-2 h-4 w-4" />
              {sortOrder === "asc" ? "Ascending" : "Descending"}
            </Button>
          </div>
        </div>
      </div>

      <MediaGrid
        files={items}
        loading={galleryQuery.isLoading && !data}
        emptyTitle="No media files"
        emptyDescription={
          selectedTags.length
            ? "Try adjusting your tag filters or sort order."
            : "Run an ingest to populate the gallery."
        }
        onPreview={setSelectedFile}
        getDetailHref={(file) => `/gallery/${file.id}`}
      />

      {data && data.total_pages > 1 && (
        <div className="flex flex-col gap-3 rounded-2xl border bg-card/80 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Library page {page}</p>
            <p className="text-sm text-muted-foreground">
              Showing {items.length} items on this page out of {data.total_pages} total pages.
            </p>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                updateParams({ page: String(Math.max(1, page - 1)) })
              }
              disabled={page === 1}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Prev
            </Button>
            <span className="min-w-24 text-center text-xs text-muted-foreground">
              Page {page} of {data.total_pages}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                updateParams({ page: String(Math.min(data.total_pages, page + 1)) })
              }
              disabled={page === data.total_pages}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <MediaPreviewModal file={selectedFile} onClose={() => setSelectedFile(null)} />
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/80 p-4 shadow-sm backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}
