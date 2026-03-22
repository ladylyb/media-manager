import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import type { CanonicalFile } from "@/types";
import { ArrowUpRight, Eye, ImageIcon, Video } from "lucide-react";
import { Link } from "react-router-dom";

interface MediaCardProps {
  file: CanonicalFile;
  onPreview?: () => void;
  detailHref?: string;
  density?: "large" | "medium" | "small" | "compact";
}

function primaryTagLabel(file: CanonicalFile): string | null {
  const tag = file.sort_tag_name ?? file.matched_tags[0];
  if (!tag) return null;
  const score = file.top_confidence_score == null ? null : `${Math.round(file.top_confidence_score * 100)}%`;
  return score ? `${tag} ${score}` : tag;
}

export function MediaCard({ file, onPreview, detailHref, density = "medium" }: MediaCardProps) {
  const isVideo = file.file_type === "video";
  const tagLabel = primaryTagLabel(file);
  const preferredPoster = isVideo ? file.poster_url ?? null : file.media_url;
  const [imageSrc, setImageSrc] = useState(preferredPoster);
  const compactActions = density === "small" || density === "compact";
  const hideSupplementaryMeta = density === "compact";
  const hideTagChip = density === "compact";

  useEffect(() => {
    setImageSrc(preferredPoster);
  }, [preferredPoster]);

  return (
    <div
      className={cn(
        "group overflow-hidden rounded-2xl border border-border/80 bg-card text-left shadow-sm transition-all",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10",
      )}
    >
      <button
        type="button"
        onClick={onPreview}
        className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <div className="relative aspect-[4/5] overflow-hidden bg-gradient-to-br from-muted via-muted to-secondary/60">
          {imageSrc ? (
            <img
              src={imageSrc}
              alt={file.filename}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
              onError={() => setImageSrc(null)}
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-gradient-to-br from-slate-900/10 via-transparent to-slate-950/10">
              {isVideo ? (
                <>
                  <div className="rounded-full border border-border/70 bg-background/85 p-3 shadow-sm">
                    <Video className="h-10 w-10 text-muted-foreground" />
                  </div>
                  <p className="px-4 text-center text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    Video preview unavailable
                  </p>
                </>
              ) : (
                <ImageIcon className="h-10 w-10 text-muted-foreground" />
              )}
            </div>
          )}

          <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3">
            <span className="rounded-full border border-black/10 bg-background/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/80 backdrop-blur">
              {isVideo ? "Video" : "Image"}
            </span>
            {tagLabel && !hideTagChip ? (
              <StatusBadge
                label={tagLabel}
                severity="info"
                className="max-w-[11rem] truncate border-white/20 bg-info/85 text-white"
              />
            ) : null}
          </div>

          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/65 via-black/15 to-transparent" />
        </div>
      </button>

      <div className={cn("space-y-2 p-3", density === "compact" && "space-y-1.5 p-2.5")}>
        <p className={cn("truncate text-sm font-semibold text-foreground", density === "compact" && "text-xs")}>
          {file.filename}
        </p>
        <div className="flex items-center justify-between gap-3">
          <span className={cn("text-[11px] uppercase tracking-[0.18em] text-muted-foreground", density === "compact" && "text-[10px]")}>
            {file.id.slice(0, 8)}
          </span>
          {file.matched_tags.length > 1 && !hideSupplementaryMeta ? (
            <span className="text-xs text-muted-foreground">+{file.matched_tags.length - 1} tags</span>
          ) : null}
        </div>
        {compactActions ? (
          <div className="flex items-center justify-end gap-2 pt-1">
            {density === "small" ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={onPreview}
                aria-label={`Quick preview ${file.filename}`}
                title="Quick preview"
              >
                <Eye className="h-4 w-4" />
              </Button>
            ) : null}
            {detailHref ? (
              <Button
                asChild
                type="button"
                variant={density === "compact" ? "outline" : "default"}
                size="icon"
                className="h-8 w-8 shrink-0"
              >
                <Link to={detailHref} aria-label={`View details for ${file.filename}`} title="View details">
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="grid gap-2 pt-1 sm:grid-cols-2">
            <Button type="button" variant="outline" size="sm" className="w-full min-w-0" onClick={onPreview}>
              Quick preview
            </Button>
            {detailHref ? (
              <Button asChild type="button" size="sm" className="w-full min-w-0">
                <Link to={detailHref}>View details</Link>
              </Button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
