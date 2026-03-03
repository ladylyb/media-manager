import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-lg border bg-card p-4 space-y-3", className)}>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-20" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 4, className }: { rows?: number; cols?: number; className?: string }) {
  return (
    <div className={cn("rounded-lg border bg-card overflow-hidden", className)}>
      <div className="border-b bg-muted/50 px-4 py-3 flex gap-8">
        {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-3 w-20" />)}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="border-b last:border-0 px-4 py-3 flex gap-8">
          {Array.from({ length: cols }).map((_, j) => <Skeleton key={j} className="h-4 w-24" />)}
        </div>
      ))}
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
      <TableSkeleton />
    </div>
  );
}
