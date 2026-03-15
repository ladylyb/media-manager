import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { MediaGrid } from "@/components/media/MediaGrid";
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal";
import { Button } from "@/components/ui/button";
import { getCanonical } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { CanonicalFile, PaginatedResponse } from "@/types/api";
import { ChevronLeft, ChevronRight, Images } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedFile, setSelectedFile] = useState<CanonicalFile | null>(null);
  const page = Number(searchParams.get("page") || 1);

  const canonicalParams = useMemo(
    () => ({
      page,
      limit: 30,
    }),
    [page],
  );

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
              <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                Gallery
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                Browse the current canonical media set with the existing API-backed query flow. This
                refresh is visual only, so paging, selection, and preview behavior stay on the local
                runtime contract.
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

      {galleryQuery.error && (
        <ErrorAlert
          message={getErrorMessage(galleryQuery.error) || "Failed to load gallery"}
        />
      )}

      <MediaGrid
        files={items}
        loading={galleryQuery.isLoading && !data}
        emptyTitle="No media files"
        emptyDescription="Run an ingest to populate the gallery."
        onSelect={setSelectedFile}
      />

      {data && data.total_pages > 1 && (
        <div className="flex flex-col gap-3 rounded-2xl border bg-card/80 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Gallery page {page}</p>
            <p className="text-sm text-muted-foreground">
              Showing {items.length} items on this page out of {data.total_pages} total pages.
            </p>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <Button
              type="button"
              variant="outline"
              size="sm"
            onClick={() => setSearchParams({ page: String(Math.max(1, page - 1)) })}
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
              setSearchParams({ page: String(Math.min(data.total_pages, page + 1)) })
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
