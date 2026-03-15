import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import type { CanonicalFile } from "@/types/api";
import { ImageIcon, Video } from "lucide-react";

interface MediaCardProps {
  file: CanonicalFile;
  onClick?: () => void;
}

function primaryTagLabel(file: CanonicalFile): string | null {
  const tag = file.sort_tag_name ?? file.matched_tags[0];
  if (!tag) return null;
  const score = file.top_confidence_score == null ? null : `${Math.round(file.top_confidence_score * 100)}%`;
  return score ? `${tag} ${score}` : tag;
}

export function MediaCard({ file, onClick }: MediaCardProps) {
  const isVideo = file.file_type === "video";
  const tagLabel = primaryTagLabel(file);

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group overflow-hidden rounded-2xl border border-border/80 bg-card text-left shadow-sm transition-all",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      )}
    >
      <div className="relative aspect-[4/5] overflow-hidden bg-gradient-to-br from-muted via-muted to-secondary/60">
        {file.media_url ? (
          <img
            src={file.media_url}
            alt={file.filename}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            {isVideo ? (
              <Video className="h-10 w-10 text-muted-foreground" />
            ) : (
              <ImageIcon className="h-10 w-10 text-muted-foreground" />
            )}
          </div>
        )}

        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3">
          <span className="rounded-full border border-black/10 bg-background/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/80 backdrop-blur">
            {isVideo ? "Video" : "Image"}
          </span>
          {tagLabel ? (
            <StatusBadge
              label={tagLabel}
              severity="info"
              className="max-w-[11rem] truncate border-white/20 bg-info/85 text-white"
            />
          ) : null}
        </div>

        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/65 via-black/15 to-transparent" />
      </div>

      <div className="space-y-2 p-3">
        <p className="truncate text-sm font-semibold text-foreground">{file.filename}</p>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            {file.id.slice(0, 8)}
          </span>
          {file.matched_tags.length > 1 ? (
            <span className="text-xs text-muted-foreground">+{file.matched_tags.length - 1} tags</span>
          ) : null}
        </div>
      </div>
    </button>
  );
}
