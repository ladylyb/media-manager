import { Copy } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";
import type { DuplicateGroup } from "@/types";

function basename(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
}

function truncateMiddle(value: string, maxLength = 44): string {
  if (value.length <= maxLength) return value;
  const keep = Math.floor((maxLength - 3) / 2);
  return `${value.slice(0, keep)}...${value.slice(-keep)}`;
}

interface DuplicateQueueItemProps {
  index: number;
  active: boolean;
  group: DuplicateGroup;
  markLabel: string;
  markSeverity: "success" | "destructive" | "caution";
  onSelect: () => void;
}

export function DuplicateQueueItem({
  index,
  active,
  group,
  markLabel,
  markSeverity,
  onSelect,
}: DuplicateQueueItemProps) {
  const previewFiles = group.duplicates.filter((file) => file.thumbnail_url).slice(0, 3);
  const duplicateCount = group.duplicates.filter((file) => !file.is_canonical).length;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-[22px] border px-3 py-2.5 text-left transition-all",
        active
          ? "border-primary/35 bg-primary/8 shadow-sm ring-1 ring-primary/10"
          : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/40",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex min-h-11 min-w-[4.5rem] items-center">
          {previewFiles.length ? (
            previewFiles.map((file, index) => (
              <div
                key={file.file_instance_id || `${file.path}-${index}`}
                className={cn(
                  "h-11 w-11 overflow-hidden rounded-2xl border border-background bg-muted shadow-sm",
                  index > 0 && "-ml-3",
                )}
              >
                <img src={file.thumbnail_url ?? ""} alt={basename(file.path)} className="h-full w-full object-cover" />
              </div>
            ))
          ) : (
            <div className="flex h-12 w-20 items-center justify-center rounded-2xl border border-dashed border-border/80 bg-muted/30">
              <Copy className="h-4 w-4 text-muted-foreground" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {String(index + 1).padStart(2, "0")}
            </span>
            {active ? <StatusBadge label="Now" severity="info" /> : null}
            <StatusBadge label={markLabel} severity={markSeverity} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
            <StatusBadge label={`${group.duplicates.length} files`} severity="neutral" />
          </div>
          <p className="text-xs text-muted-foreground">
            {duplicateCount === 1 ? "1 matching copy" : `${duplicateCount} matching copies`}
          </p>
          <p className="truncate text-[11px] text-muted-foreground/80">{truncateMiddle(group.canonical_path, 32)}</p>
        </div>
      </div>
    </button>
  );
}
