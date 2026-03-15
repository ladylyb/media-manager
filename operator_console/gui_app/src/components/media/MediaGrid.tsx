import { EmptyState } from "@/components/EmptyState";
import { MediaCard } from "@/components/media/MediaCard";
import { Skeleton } from "@/components/ui/skeleton";
import type { CanonicalFile } from "@/types";
import { ImageIcon } from "lucide-react";

interface MediaGridProps {
  files: CanonicalFile[];
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onPreview?: (file: CanonicalFile) => void;
  getDetailHref?: (file: CanonicalFile) => string;
}

export function MediaGrid({
  files,
  loading = false,
  emptyTitle = "No media found",
  emptyDescription = "Run an ingest to populate the gallery",
  onPreview,
  getDetailHref,
}: MediaGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 10 }).map((_, index) => (
          <div key={index} className="overflow-hidden rounded-2xl border bg-card shadow-sm">
            <Skeleton className="aspect-[4/5] w-full" />
            <div className="space-y-2 p-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!files.length) {
    return (
      <EmptyState
        icon={<ImageIcon className="h-10 w-10" />}
        title={emptyTitle}
        description={emptyDescription}
        className="rounded-2xl border border-dashed bg-card/50"
      />
    );
  }

  return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {files.map((file) => (
        <MediaCard
          key={file.id}
          file={file}
          onPreview={() => onPreview?.(file)}
          detailHref={getDetailHref?.(file)}
        />
      ))}
    </div>
  );
}
