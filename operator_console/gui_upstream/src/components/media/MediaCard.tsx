import { StatusBadge } from "@/components/StatusBadge";
import type { CanonicalFile } from "@/types/media";
import { ImageIcon, Video } from "lucide-react";

interface MediaCardProps {
  file: CanonicalFile;
  onClick?: () => void;
}

export function MediaCard({ file, onClick }: MediaCardProps) {
  const isVideo = file.mime_type?.startsWith("video/");

  return (
    <button
      onClick={onClick}
      className="rounded-lg border bg-card overflow-hidden hover:border-primary/30 transition-colors group text-left"
    >
      <div className="aspect-square bg-muted flex items-center justify-center overflow-hidden relative">
        {file.thumbnail_url ? (
          <img
            src={file.thumbnail_url}
            alt={file.path}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
          />
        ) : isVideo ? (
          <Video className="h-8 w-8 text-muted-foreground" />
        ) : (
          <ImageIcon className="h-8 w-8 text-muted-foreground" />
        )}
        {isVideo && (
          <span className="absolute top-2 right-2 bg-card/80 backdrop-blur rounded px-1.5 py-0.5 text-[10px] font-semibold">
            VIDEO
          </span>
        )}
      </div>
      <div className="p-2">
        <p className="text-xs font-mono truncate text-muted-foreground">
          {file.path.split("/").pop()}
        </p>
        {file.tags?.[0] && (
          <StatusBadge
            label={`${file.tags[0].name} ${(file.tags[0].confidence * 100).toFixed(0)}%`}
            severity="info"
            className="mt-1"
          />
        )}
      </div>
    </button>
  );
}
