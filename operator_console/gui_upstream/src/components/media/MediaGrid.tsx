import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import { MediaCard } from "@/components/media/MediaCard";
import type { CanonicalFile } from "@/types/media";
import { ImageIcon } from "lucide-react";

interface MediaGridProps {
  files: CanonicalFile[];
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onSelect?: (file: CanonicalFile) => void;
}

export function MediaGrid({ files, loading, emptyTitle, emptyDescription, onSelect }: MediaGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {Array.from({ length: 18 }).map((_, i) => (
          <div key={i} className="rounded-lg border bg-card overflow-hidden">
            <Skeleton className="aspect-square w-full" />
            <div className="p-2 space-y-1">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-12" />
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
        title={emptyTitle || "No media found"}
        description={emptyDescription || "Run an ingest to populate the gallery"}
      />
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
      {files.map((file) => (
        <MediaCard key={file.hash} file={file} onClick={() => onSelect?.(file)} />
      ))}
    </div>
  );
}
