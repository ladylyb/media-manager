import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: "up" | "down" | "flat";
  loading?: boolean;
  className?: string;
}

export function MetricCard({ title, value, subtitle, icon, loading, className }: MetricCardProps) {
  if (loading) {
    return (
      <div className={cn("rounded-lg border bg-card p-4 space-y-2", className)}>
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-3 w-32" />
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border bg-card p-4 space-y-1 transition-colors hover:border-primary/30", className)}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
        {icon && <span className="text-muted-foreground">{icon}</span>}
      </div>
      <p className="text-2xl font-bold font-mono tracking-tight">{typeof value === "number" ? value.toLocaleString() : value}</p>
      {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
    </div>
  );
}
