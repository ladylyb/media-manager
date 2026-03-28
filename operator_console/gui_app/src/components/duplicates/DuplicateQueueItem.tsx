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
  onSelect: () => void;
}

export function DuplicateQueueItem({
  index,
  active,
  group,
  markLabel,
  onSelect,
}: DuplicateQueueItemProps) {
  const duplicateCount = group.duplicates.filter((file) => !file.is_canonical).length;
  const label = basename(group.canonical_path);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-[18px] border px-3 py-2 text-left transition-all",
        active
          ? "border-primary/35 bg-primary/8 shadow-sm ring-1 ring-primary/10"
          : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/40",
      )}
    >
      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {String(index + 1).padStart(2, "0")}
          </span>
          {active ? <span className="text-[11px] text-primary">Current</span> : null}
        </div>
        <p
          className="truncate text-sm font-semibold text-foreground"
          title={label}
          data-testid="review-queue-item-title"
        >
          {label}
        </p>
        <p className="truncate text-xs text-muted-foreground" title={group.canonical_path}>
          {truncateMiddle(group.canonical_path, 40)}
        </p>
        <p className="text-[11px] text-muted-foreground">
          {markLabel} • {duplicateCount === 1 ? "1 extra copy" : `${duplicateCount} extra copies`}
        </p>
        <div data-testid="review-queue-no-thumbnails" className="hidden" />
      </div>
    </button>
  );
}
