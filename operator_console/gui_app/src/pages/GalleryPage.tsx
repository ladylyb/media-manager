import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { MediaGrid } from "@/components/media/MediaGrid";
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from "@/components/ui/pagination";
import { Slider } from "@/components/ui/slider";
import { getCanonical, getCanonicalTags } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { CanonicalFile, PaginatedResponse, Tag } from "@/types";
import { ArrowUpDown, Grid2X2, Images, LayoutGrid, Loader2, Search, X } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

const DENSITY_PRESETS = [
  {
    key: "large",
    label: "Large",
    limit: 12,
    gridClassName: "grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4",
  },
  {
    key: "medium",
    label: "Medium",
    limit: 20,
    gridClassName: "grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5",
  },
  {
    key: "small",
    label: "Small",
    limit: 30,
    gridClassName: "grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6",
  },
  {
    key: "compact",
    label: "Compact",
    limit: 42,
    gridClassName: "grid grid-cols-3 gap-4 md:grid-cols-5 xl:grid-cols-7",
  },
] as const;

type DensityKey = (typeof DENSITY_PRESETS)[number]["key"];

function getDensityPreset(densityParam: string | null) {
  return DENSITY_PRESETS.find((preset) => preset.key === densityParam) ?? DENSITY_PRESETS[1];
}

function getVisiblePages(currentPage: number, totalPages: number): Array<number | "ellipsis"> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages: Array<number | "ellipsis"> = [1];
  if (currentPage > 3) pages.push("ellipsis");

  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);
  for (let page = start; page <= end; page += 1) pages.push(page);

  if (currentPage < totalPages - 2) pages.push("ellipsis");
  pages.push(totalPages);
  return pages;
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
  const page = Math.max(1, Number(searchParams.get("page") || 1));
  const densityPreset = getDensityPreset(searchParams.get("density"));
  const densityIndex = DENSITY_PRESETS.findIndex((preset) => preset.key === densityPreset.key);

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
      limit: densityPreset.limit,
      tags: tagsParam || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [densityPreset.limit, page, sortBy, sortOrder, tagsParam],
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
  const allTags = (tagsQuery.data as Tag[] | undefined) ?? [];
  const totalCount = data?.total_count ?? 0;
  const totalPages = Math.max(data?.total_pages ?? 1, 1);
  const visiblePages = useMemo(() => getVisiblePages(page, totalPages), [page, totalPages]);

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
      <TopSurfaceHeader
        badge="Library"
        title="Browse your media without leaving the flow."
        description="Use filters, sorting, preview, and the detail view to quickly find the photo or video you need. This page should feel more like a calm library shelf than a dashboard."
        icon={Images}
        density="compact"
        className="rounded-[28px]"
      >
        <div className="flex flex-wrap gap-3">
          <div className="rounded-2xl border border-border/70 bg-background/85 px-4 py-3 text-sm text-muted-foreground shadow-sm">
            {selectedTags.length
              ? `${selectedTags.length} tag filter${selectedTags.length === 1 ? "" : "s"} applied`
              : "No filters applied yet"}
          </div>
          <div className="rounded-2xl border border-border/70 bg-background/85 px-4 py-3 text-sm text-muted-foreground shadow-sm">
            Sorted by {sortBy.replace("_", " ")} in {sortOrder === "asc" ? "ascending" : "descending"} order
          </div>
          <div className="rounded-2xl border border-border/70 bg-background/85 px-4 py-3 text-sm text-muted-foreground shadow-sm">
            {galleryQuery.isLoading && !data
              ? "Loading gallery..."
              : `${totalCount} item${totalCount === 1 ? "" : "s"} · Page ${page} of ${totalPages}`}
          </div>
        </div>
      </TopSurfaceHeader>

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

          <div className="flex flex-wrap items-center gap-3 self-start lg:self-auto">
            {galleryQuery.isFetching ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
            <div className="flex items-center gap-2">
              <Grid2X2 className="h-4 w-4 text-muted-foreground" />
              <Slider
                value={[densityIndex]}
                onValueChange={([value]) => {
                  const nextPreset = DENSITY_PRESETS[value as number];
                  if (!nextPreset) return;
                  updateParams({
                    density: nextPreset.key === "medium" ? undefined : nextPreset.key,
                    page: undefined,
                  });
                }}
                min={0}
                max={DENSITY_PRESETS.length - 1}
                step={1}
                className="w-24"
              />
              <LayoutGrid className="h-4 w-4 text-muted-foreground" />
              <span className="min-w-14 text-right text-sm text-muted-foreground">
                {densityPreset.label}
              </span>
            </div>
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
        gridClassName={densityPreset.gridClassName}
        skeletonCount={densityPreset.limit}
        emptyTitle="No media files"
        emptyDescription={
          selectedTags.length
            ? "Try adjusting your tag filters or sort order."
            : "Run an ingest to populate the gallery."
        }
        onPreview={setSelectedFile}
        getDetailHref={(file) => `/gallery/${file.id}`}
      />

      {data && totalPages > 1 && (
        <Pagination className="justify-center">
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (page === 1) return;
                  updateParams({ page: page - 1 <= 1 ? undefined : String(page - 1) });
                }}
                className={page === 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
            {visiblePages.map((pageNumber, index) =>
              pageNumber === "ellipsis" ? (
                <PaginationItem key={`ellipsis-${index}`}>
                  <PaginationEllipsis />
                </PaginationItem>
              ) : (
                <PaginationItem key={pageNumber}>
                  <PaginationLink
                    href="#"
                    isActive={pageNumber === page}
                    onClick={(event) => {
                      event.preventDefault();
                      updateParams({ page: pageNumber === 1 ? undefined : String(pageNumber) });
                    }}
                    className="cursor-pointer"
                  >
                    {pageNumber}
                  </PaginationLink>
                </PaginationItem>
              ),
            )}
            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  if (page >= totalPages) return;
                  updateParams({ page: String(page + 1) });
                }}
                className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}

      <MediaPreviewModal file={selectedFile} onClose={() => setSelectedFile(null)} />
    </div>
  );
}
