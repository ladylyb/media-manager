import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/StatusBadge";
import type { DuplicateFile } from "@/types";

import { DuplicateMediaPreview } from "@/components/duplicates/DuplicateMediaPreview";

function basename(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
}

interface DuplicateFocusCardProps {
  badge: string;
  description: string;
  emphasis?: "default" | "success" | "info";
  file: DuplicateFile;
  title?: string;
  className?: string;
  previewClassName?: string;
  previewFit?: "cover" | "contain";
  previewTestId?: string;
  titleTestId?: string;
}

export function DuplicateFocusCard({
  badge,
  description,
  emphasis = "default",
  file,
  title,
  className,
  previewClassName,
  previewFit,
  previewTestId,
  titleTestId,
}: DuplicateFocusCardProps) {
  const previewSrc = file.preview_url ?? (file.is_image ? file.media_url ?? file.thumbnail_url : null);
  const resolvedTitle = title ?? basename(file.path);

  return (
    <Card
      className={
        `${
          emphasis === "success"
            ? "overflow-hidden rounded-[28px] border-success/35 bg-success/5 shadow-sm"
            : emphasis === "info"
              ? "overflow-hidden rounded-[28px] border-primary/25 bg-primary/5 shadow-sm"
              : "overflow-hidden rounded-[28px] border-border/70 bg-background/90 shadow-sm"
        } ${className ?? ""}`
      }
    >
      <CardContent className="space-y-2.5 p-2.5">
        <DuplicateMediaPreview
          src={previewSrc}
          alt={basename(file.path)}
          isImage={file.is_image}
          mediaType={file.media_type}
          className={previewClassName ?? "aspect-[4/3]"}
          fit={previewFit}
          data-testid={previewTestId}
        />
        <div className="min-w-0 space-y-1.5">
          <StatusBadge
            label={badge}
            severity={emphasis === "success" ? "success" : emphasis === "info" ? "info" : "neutral"}
          />
          <div className="min-w-0">
            <p
              className="truncate text-base font-semibold text-foreground"
              title={resolvedTitle}
              data-testid={titleTestId}
            >
              {resolvedTitle}
            </p>
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
