import { StatusBadge } from "@/components/StatusBadge";
import { Progress } from "@/components/ui/progress";

interface DuplicateReviewProgressProps {
  currentIndex: number;
  total: number;
  reviewedCount: number;
}

export function DuplicateReviewProgress({
  currentIndex,
  total,
  reviewedCount,
}: DuplicateReviewProgressProps) {
  const remaining = Math.max(total - reviewedCount, 0);
  const percent = total > 0 ? Math.round((reviewedCount / total) * 100) : 0;

  return (
    <div className="rounded-[24px] border border-border/70 bg-card/95 p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label={`${currentIndex + 1} of ${total}`} severity="info" />
          <StatusBadge label={`${reviewedCount} reviewed`} severity="neutral" />
          <StatusBadge label={`${remaining} left`} severity="caution" />
        </div>
        <p className="text-xs font-medium text-muted-foreground">{percent}% complete</p>
      </div>
      <Progress value={percent} className="mt-3 h-1.5 bg-muted/70" />
    </div>
  );
}
