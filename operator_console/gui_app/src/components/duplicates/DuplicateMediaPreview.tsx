import { useEffect, useState } from "react";
import { FileIcon, ImageIcon, Video } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";

interface DuplicateMediaPreviewProps {
  src?: string | null;
  alt: string;
  isImage: boolean;
  mediaType: string;
  className?: string;
  fit?: "cover" | "contain";
}

export function DuplicateMediaPreview({
  src,
  alt,
  isImage,
  mediaType,
  className,
  fit = "cover",
}: DuplicateMediaPreviewProps) {
  const [imageSrc, setImageSrc] = useState(src ?? null);
  const isVideo = !isImage && ["vid", "video"].includes(mediaType.toLowerCase());

  useEffect(() => {
    setImageSrc(src ?? null);
  }, [src]);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[24px] border border-border/70 bg-[linear-gradient(135deg,hsl(var(--muted))_0%,hsl(var(--secondary)/0.4)_100%)]",
        className,
      )}
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={alt}
          className={cn("h-full w-full", fit === "contain" ? "object-contain" : "object-cover")}
          onError={() => setImageSrc(null)}
        />
      ) : (
        <div className="flex h-full min-h-36 items-center justify-center">
          {isImage ? (
            <ImageIcon className="h-10 w-10 text-muted-foreground" />
          ) : isVideo ? (
            <Video className="h-10 w-10 text-muted-foreground" />
          ) : (
            <FileIcon className="h-10 w-10 text-muted-foreground" />
          )}
        </div>
      )}
      <div className="absolute left-3 top-3">
        <StatusBadge
          label={isImage ? "Image" : isVideo ? "Video" : "File"}
          severity="neutral"
          className="border-white/30 bg-background/85 text-foreground"
        />
      </div>
    </div>
  );
}
