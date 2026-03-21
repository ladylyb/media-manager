import { Clock3, ListTodo } from "lucide-react";

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
    <div className="rounded-[28px] border border-border/70 bg-card/95 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label="Review Progress" severity="info" />
            <StatusBadge label={`${reviewedCount} reviewed`} severity="neutral" />
            <StatusBadge label={`${remaining} remaining`} severity="caution" />
          </div>
          <div>
            <p className="text-xl font-semibold tracking-tight text-foreground">
              {total > 0 ? `Group ${currentIndex + 1} of ${total}` : "No duplicate groups"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Work down the queue quickly, keep place, and only open full technical details when you need them.
            </p>
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl border border-border/70 bg-background/80 px-4 py-3">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <ListTodo className="h-3.5 w-3.5" />
              Completion
            </div>
            <p className="mt-2 text-lg font-semibold text-foreground">{percent}%</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-background/80 px-4 py-3">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Clock3 className="h-3.5 w-3.5" />
              Remaining
            </div>
            <p className="mt-2 text-lg font-semibold text-foreground">{remaining} groups</p>
          </div>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Reviewed</span>
          <span>{reviewedCount} / {total}</span>
        </div>
        <Progress value={percent} className="h-2.5 bg-muted/70" />
      </div>
    </div>
  );
}
